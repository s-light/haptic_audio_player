"""ALSA mixer setup + master volume (applied at start: root is read-only, `alsactl store` can't persist)."""

from __future__ import annotations

import asyncio
import logging

from .config import Config

log = logging.getLogger(__name__)


async def _amixer(card: str, *args: str) -> int:
    proc = await asyncio.create_subprocess_exec(
        "amixer", "-q", "-c", card, "sset", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode:
        log.warning("amixer %s failed: %s", " ".join(args), err.decode().strip())
    return proc.returncode or 0


async def init_mixer(cfg: Config) -> None:
    if cfg.simulate or not cfg.audio.init_mixer:
        return
    for control in cfg.audio.mixer:
        await _amixer(cfg.audio.card, *control)
