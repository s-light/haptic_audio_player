"""Tag poller thread: calls on_tag(uid_hex) when a new tag appears and on_remove() when it has left."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .config import NfcConfig
from .pn532 import PN532, I2CTransport, PN532Error

log = logging.getLogger(__name__)


class TagTracker:
    """Pure state machine (testable): feed polls, get 'new' / 'removed' events."""

    def __init__(self, lost_polls: int = 3):
        self.lost_polls = lost_polls
        self.current: str | None = None
        self._missed = 0

    def update(self, uid: str | None) -> tuple[str, str | None] | None:
        if uid is not None:
            self._missed = 0
            if uid != self.current:
                self.current = uid
                return ("tag", uid)
            return None
        if self.current is not None:
            self._missed += 1
            if self._missed >= self.lost_polls:
                gone, self.current = self.current, None
                return ("removed", gone)
        return None


class NfcReader(threading.Thread):
    def __init__(self, cfg: NfcConfig, on_tag: Callable[[str], None], on_remove: Callable[[], None]):
        super().__init__(daemon=True, name="nfc")
        self.cfg, self.on_tag, self.on_remove = cfg, on_tag, on_remove
        self._halt = threading.Event()
        self.ok = False
        self.firmware = ""

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        tracker = TagTracker(self.cfg.tag_lost_polls)
        while not self._halt.is_set():
            try:
                transport = I2CTransport(self.cfg.i2c_bus, self.cfg.address)
                pn = PN532(transport)
                ic, ver, rev, _ = pn.setup()
                self.firmware, self.ok = f"PN5{ic:02x} v{ver}.{rev}", True
                log.info("NFC reader ready: %s", self.firmware)
                while not self._halt.is_set():
                    uid = pn.read_uid()
                    ev = tracker.update(uid.hex().upper() if uid else None)
                    if ev:
                        (self.on_tag(ev[1]) if ev[0] == "tag" else self.on_remove())  # type: ignore[arg-type]
                    time.sleep(self.cfg.poll_interval)
            except (OSError, PN532Error) as e:
                self.ok = False
                log.warning("NFC error: %s - retrying in 3 s", e)
                self._halt.wait(3)
            finally:
                try:
                    transport.close()  # type: ignore[possibly-undefined]
                except Exception:
                    pass
