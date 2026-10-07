"""Who owns the data stick: the player (mounted locally) or a connected computer (USB mass storage)?

Default behaviour: when a USB host enumerates the board (`/sys/class/udc/*/state == configured` - a plain
powerbank never does) the stick is handed to the computer, the player pauses. The user can switch back
("Zurück zum Player") and it stays that way until the computer is reconnected; ejecting the drive on the
computer or unplugging the cable also gives it back. The USB network (web UI) is never touched - see
haptic_player/usbgadget.py.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from . import usbgadget
from .config import UsbConfig

log = logging.getLogger(__name__)
REPO_DIR = Path(__file__).resolve().parent.parent


@dataclass
class GadgetState:
    function: bool = False  # mass-storage function present (setup done)
    host: bool = False  # a computer has enumerated us
    attached: bool = False  # medium inserted (the computer owns the stick)


class Backend(Protocol):
    def read(self) -> GadgetState: ...
    async def attach(self) -> tuple[bool, str]: ...
    async def detach(self) -> tuple[bool, str]: ...


class SysfsBackend:
    """Real hardware: read sysfs directly, change things through `sudo -n python -m haptic_player.usbgadget`."""

    def read(self) -> GadgetState:
        s = usbgadget.read_state()
        return GadgetState(function=s["function"], host=s["host"], attached=s["attached"])

    async def _sudo(self, action: str) -> tuple[bool, str]:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-n", sys.executable, "-m", "haptic_player.usbgadget", action,
            cwd=REPO_DIR, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        return proc.returncode == 0, out.decode().strip()

    async def attach(self) -> tuple[bool, str]:
        return await self._sudo("attach")

    async def detach(self) -> tuple[bool, str]:
        return await self._sudo("detach")


class FakeBackend:
    """--simulate / tests: `host` is toggled through POST /api/dev/usb."""

    def __init__(self) -> None:
        self.state = GadgetState(function=True)
        self.fail_attach = ""

    def read(self) -> GadgetState:
        return GadgetState(self.state.function, self.state.host, self.state.attached)

    async def attach(self) -> tuple[bool, str]:
        if self.fail_attach:
            return False, self.fail_attach
        self.state.attached = True
        return True, ""

    async def detach(self) -> tuple[bool, str]:
        self.state.attached = False
        return True, ""


class Storage:
    def __init__(self, cfg: UsbConfig, backend: Backend, before_computer: Callable[[], Awaitable[None]],
                 after_player: Callable[[], Awaitable[None]], on_change: Callable[[], None]):
        self.cfg, self.backend = cfg, backend
        self.before_computer, self.after_player, self.on_change = before_computer, after_player, on_change
        self.mode = "player"  # player | computer
        self.host = False
        self.available = False
        self.override = False  # user chose "player" while connected -> no auto switch until reconnect
        self.error = ""
        self._connected_since: float | None = None
        self._lock = asyncio.Lock()

    def snapshot(self) -> dict:
        return {"mode": self.mode, "host": self.host, "available": self.available, "error": self.error}

    async def to_computer(self, user: bool = False) -> bool:
        async with self._lock:
            if self.mode == "computer":
                return True
            if user and not self.host:
                self.error = "Kein Computer per USB verbunden"
                self.on_change()
                return False
            if not self.available:
                self.error = "USB-Speichermodus nicht eingerichtet (./setup_pb2.py usb-gadget)"
                self.on_change()
                return False
            await self.before_computer()
            ok, out = await self.backend.attach()
            if not ok:
                log.error("attach failed: %s", out)
                self.error = out or "Freigabe fehlgeschlagen"
                self.override = True  # no retry loop
                self.on_change()
                return False
            self.mode, self.error = "computer", ""
            log.info("data stick handed to the computer")
            self.on_change()
            return True

    async def to_player(self, user: bool = True) -> bool:
        async with self._lock:
            if self.mode == "player":
                return True
            ok, out = await self.backend.detach()
            if not ok:
                log.error("detach failed: %s", out)
                self.error = out or "Rücknahme fehlgeschlagen"
                self.on_change()
                return False
            self.mode, self.error = "player", ""
            if self.host:
                self.override = True  # stay in player mode until the computer reconnects
            log.info("data stick back at the player")
            await self.after_player()
            self.on_change()
            return True

    async def tick(self, now: float | None = None) -> None:
        """One watcher step (also called directly by the tests)."""
        now = time.monotonic() if now is None else now
        st = self.backend.read()
        changed = (st.function, st.host) != (self.available, self.host)
        self.available, self.host = st.function, st.host
        if st.host:
            if self._connected_since is None:
                self._connected_since = now
        else:
            self._connected_since = None
            self.override = False
        if self.mode == "player" and st.attached and st.function:
            self.mode = "computer"  # attached before we started (e.g. app restart)
            changed = True
        if self.mode == "player":
            stable = self._connected_since is not None and now - self._connected_since >= self.cfg.debounce_s
            if self.cfg.auto_switch and st.function and stable and not self.override:
                await self.to_computer()
        elif not st.host or not st.attached:
            await self.to_player(user=False)  # unplugged, or ejected on the computer
        elif changed:
            self.on_change()
        if changed:
            self.on_change()

    async def watch(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("storage watcher")
            await asyncio.sleep(self.cfg.poll_s)
