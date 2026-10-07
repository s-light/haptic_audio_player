"""Playback. MpvPlayer drives `mpv --idle` over its JSON IPC socket; FakePlayer is an in-memory stand-in
(used by --simulate when mpv is missing, and by the tests)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Callable

from .config import Config

log = logging.getLogger(__name__)
Callback = Callable[[], None]


class PlayerBase:
    """State is a flat dict, broadcast to the web UI/display on every change."""

    kind = "none"  # "mpv" = real audio, "fake" = no sound (simulate without mpv)

    def __init__(self) -> None:
        self.state: dict = {"active": False, "paused": False, "file": "", "title": "", "position": 0.0,
                            "duration": 0.0, "index": 0, "count": 0, "volume": 70, "label": ""}
        self.on_change: Callback | None = None
        self.on_finished: Callback | None = None  # whole playlist ended on its own

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    async def start(self, volume: int) -> None: ...
    async def close(self) -> None: ...
    async def play_files(self, files: list[Path], label: str = "") -> None: ...
    async def toggle_pause(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def stop(self) -> None: ...
    async def next(self) -> None: ...
    async def prev(self) -> None: ...
    async def seek(self, seconds: float) -> None: ...
    async def set_volume(self, volume: int) -> None: ...


class FakePlayer(PlayerBase):
    """No audio; plays 'virtually' so state/display/UI can be exercised."""

    kind = "fake"

    def __init__(self) -> None:
        super().__init__()
        self.files: list[Path] = []
        self._ticker: asyncio.Task | None = None

    async def start(self, volume: int) -> None:
        self.state["volume"] = volume

    async def close(self) -> None:
        if self._ticker:
            self._ticker.cancel()

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(1)
            if self.state["active"] and not self.state["paused"]:
                self.state["position"] += 1
                if self.state["duration"] and self.state["position"] >= self.state["duration"]:
                    await self.next()
                self._changed()

    def _load(self, index: int) -> None:
        f = self.files[index]
        self.state.update(active=True, paused=False, file=str(f), title=f.stem, position=0.0, duration=180.0, index=index)

    async def play_files(self, files: list[Path], label: str = "") -> None:
        self.files = list(files)
        if not self.files:
            return
        self.state.update(count=len(self.files), label=label)
        self._load(0)
        if self._ticker is None:
            self._ticker = asyncio.create_task(self._tick())
        self._changed()

    async def toggle_pause(self) -> None:
        if self.state["active"]:
            self.state["paused"] = not self.state["paused"]
            self._changed()

    async def pause(self) -> None:
        if self.state["active"] and not self.state["paused"]:
            await self.toggle_pause()

    async def resume(self) -> None:
        if self.state["active"] and self.state["paused"]:
            await self.toggle_pause()

    async def stop(self) -> None:
        self.state.update(active=False, paused=False, position=0.0, title="", file="", count=0, index=0, duration=0.0, label="")
        self._changed()

    async def next(self) -> None:
        i = self.state["index"] + 1
        if i >= len(self.files):
            await self.stop()
            if self.on_finished:
                self.on_finished()
        else:
            self._load(i)
            self._changed()

    async def prev(self) -> None:
        if self.state["active"]:
            if self.state["position"] > 3:
                self._load(self.state["index"])
            else:
                self._load(max(0, self.state["index"] - 1))
            self._changed()

    async def seek(self, seconds: float) -> None:
        self.state["position"] = max(0.0, seconds)
        self._changed()

    async def set_volume(self, volume: int) -> None:
        self.state["volume"] = max(0, min(100, int(volume)))
        self._changed()


class MpvPlayer(PlayerBase):
    kind = "mpv"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._req = 0
        self._last_emit = 0.0
        self._stopping = False

    async def start(self, volume: int) -> None:
        sock = self.cfg.mpv_socket
        sock.parent.mkdir(parents=True, exist_ok=True)
        if sock.exists():
            sock.unlink()
        args = ["mpv", "--idle=yes", "--no-video", "--no-terminal", "--force-window=no", "--audio-display=no",
                f"--input-ipc-server={sock}", f"--volume={volume}", "--volume-max=100",
                f"--audio-device={'auto' if self.cfg.simulate else self.cfg.audio.mpv_device}", "--keep-open=no"]
        self.proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.DEVNULL)
        for _ in range(50):
            if sock.exists():
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("mpv IPC socket did not appear")
        self._reader, self._writer = await asyncio.open_unix_connection(str(sock))
        self.state["volume"] = volume
        self._task = asyncio.create_task(self._read_loop())
        for i, prop in enumerate(["time-pos", "duration", "pause", "playlist-pos", "playlist-count", "path", "media-title", "idle-active"], 1):
            await self._send(["observe_property", i, prop], wait=False)

    async def close(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
        if self._writer:
            self._writer.close()
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            await self.proc.wait()

    async def _send(self, command: list, wait: bool = True) -> None:
        assert self._writer is not None
        self._req += 1
        self._writer.write(json.dumps({"command": command, "request_id": self._req}).encode() + b"\n")
        await self._writer.drain()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while True:
            line = await self._reader.readline()
            if not line:
                if not self._stopping:
                    log.error("mpv IPC closed")
                return
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle(ev)

    def _handle(self, ev: dict) -> None:
        name = ev.get("event")
        s = self.state
        if name == "property-change":
            prop, val = ev.get("name"), ev.get("data")
            if prop == "time-pos":
                s["position"] = float(val or 0.0)
                now = time.monotonic()
                if now - self._last_emit < 0.5:  # position ticks: throttle UI traffic
                    return
                self._last_emit = now
            elif prop == "duration":
                s["duration"] = float(val or 0.0)
            elif prop == "pause":
                s["paused"] = bool(val)
            elif prop == "playlist-pos":
                s["index"] = max(0, int(val if val is not None else 0))
            elif prop == "playlist-count":
                s["count"] = int(val or 0)
            elif prop == "path":
                s["file"] = val or ""
            elif prop == "media-title":
                s["title"] = val or ""
            elif prop == "idle-active":
                was = s["active"]
                s["active"] = not bool(val)
                if val:
                    s.update(position=0.0, duration=0.0, paused=False, title="", file="", count=0, index=0, label="")
                    if was and self.on_finished:
                        self.on_finished()
            self._changed()

    async def play_files(self, files: list[Path], label: str = "") -> None:
        if not files:
            return
        self.state["label"] = label
        await self._send(["loadfile", str(files[0]), "replace"])
        for f in files[1:]:
            await self._send(["loadfile", str(f), "append"])
        await self._send(["set_property", "pause", False])

    async def toggle_pause(self) -> None:
        await self._send(["cycle", "pause"])

    async def pause(self) -> None:
        await self._send(["set_property", "pause", True])

    async def resume(self) -> None:
        await self._send(["set_property", "pause", False])

    async def stop(self) -> None:
        await self._send(["stop"])

    async def next(self) -> None:
        await self._send(["playlist-next", "weak"])

    async def prev(self) -> None:
        if self.state["position"] > 3:
            await self._send(["seek", 0, "absolute"])
        else:
            await self._send(["playlist-prev", "weak"])

    async def seek(self, seconds: float) -> None:
        await self._send(["seek", seconds, "absolute"])

    async def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        self.state["volume"] = volume
        await self._send(["set_property", "volume", volume])
        self._changed()


def make_player(cfg: Config) -> PlayerBase:
    if cfg.simulate and shutil.which("mpv") is None:
        log.warning("mpv not found - using FakePlayer: NO SOUND (install it: sudo apt install mpv)")
        return FakePlayer()
    return MpvPlayer(cfg)
