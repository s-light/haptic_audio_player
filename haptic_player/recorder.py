"""Recording slots: recordings/slot-NN/rec-<timestamp>.wav, new file per recording (never overwritten)."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

from .config import Config
from .library import natural_key


def slot_dir(cfg: Config, slot: int) -> Path:
    return cfg.recordings_dir / f"slot-{slot:02d}"


def list_slot(cfg: Config, slot: int) -> list[Path]:
    d = slot_dir(cfg, slot)
    return sorted((f for f in d.glob("*.wav") if f.is_file()), key=lambda f: natural_key(f.name)) if d.is_dir() else []


def list_slots(cfg: Config) -> list[dict]:
    slots = []
    for n in range(1, cfg.auto_record_slots + 1):
        files = list_slot(cfg, n)
        slots.append({"slot": n, "files": [f.name for f in files]})
    return slots


class Recorder:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self.path: Path | None = None
        self.slot: int | None = None
        self.started: float = 0.0

    @property
    def active(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started if self.active else 0.0

    async def start(self, slot: int) -> Path:
        if self.active:
            raise RuntimeError("already recording")
        d = slot_dir(self.cfg, slot)
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / time.strftime("rec-%Y%m%d-%H%M%S.wav")
        self.slot = slot
        a = self.cfg.audio
        if self.cfg.simulate:
            self.path.write_bytes(b"")  # placeholder so the UI has something to list
            self.proc = await asyncio.create_subprocess_exec("sleep", "86400")
        else:
            self.proc = await asyncio.create_subprocess_exec(
                "arecord", "-q", "-D", a.record_device, "-f", "S16_LE", "-r", str(a.record_rate),
                "-c", str(a.record_channels), "-t", "wav", str(self.path),
                stdin=asyncio.subprocess.DEVNULL,
            )
        self.started = time.monotonic()
        return self.path

    async def stop(self) -> Path | None:
        if self.proc is None:
            return None
        proc, path = self.proc, self.path
        if proc.returncode is None:
            proc.send_signal(signal.SIGINT)  # arecord finalises the WAV header on SIGINT
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        self.proc = None
        if path is not None and path.exists():
            if path.stat().st_size < 64 and not self.cfg.simulate:
                path.unlink()  # nothing recorded
                path = None
            else:
                try:
                    os.sync()
                except OSError:
                    pass
        return path
