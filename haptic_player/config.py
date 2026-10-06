"""Configuration: defaults < <data_dir>/config.toml. Written back atomically (data partition is the only writable place)."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".wav", ".m4a", ".aac", ".wma"}
COVER_NAMES = ("cover", "folder", "front", "album")
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png")


@dataclass
class Pins:
    """GPIO lines as `GPIOx_y` (official table) or a gpioinfo line name such as `P2.02`."""

    play_pause: str = "GPIO0_45"  # P2.02
    record: str = "GPIO0_46"  # P2.04
    prev: str = "GPIO0_47"  # P2.06
    next: str = "GPIO0_48"  # P2.08


@dataclass
class DisplayConfig:
    enabled: bool = True
    spidev: str = "/dev/spidev0.0"
    spi_hz: int = 32_000_000
    dc: str = "GPIO0_64"  # P2.17
    rst: str = "GPIO0_53"  # P2.18
    backlight: str = "GPIO0_63"  # P2.22
    rotation: int = 0  # 0/90/180/270
    width: int = 240
    height: int = 320
    invert: bool = True


@dataclass
class NfcConfig:
    enabled: bool = True
    i2c_bus: int = 2
    address: int = 0x24
    poll_interval: float = 0.2
    tag_lost_polls: int = 3


@dataclass
class AudioConfig:
    card: str = "haptic"
    mpv_device: str = "alsa/plughw:CARD=haptic"
    record_device: str = "plughw:CARD=haptic,DEV=0"
    record_rate: int = 44100
    record_channels: int = 1
    init_mixer: bool = True
    # amixer controls applied at start (WM8960 routing is off by default)
    mixer: list[list[str]] = field(
        default_factory=lambda: [
            ["Left Output Mixer PCM", "on"],
            ["Right Output Mixer PCM", "on"],
            ["Playback", "230"],
            ["Speaker", "115"],
            ["Headphone", "115"],
            ["Left Input Mixer Boost", "on"],
            ["Right Input Mixer Boost", "on"],
            ["Capture", "50"],
        ]
    )


@dataclass
class Config:
    data_dir: Path = Path("/srv/haptic")
    host: str = "0.0.0.0"
    port: int = 8080
    volume: int = 70  # 0..100
    volume_step: int = 5
    on_tag_remove: str = "none"  # none | pause | stop
    long_press_s: float = 0.8
    auto_record_slots: int = 8
    webui_dir: Path = Path(__file__).resolve().parent.parent / "webui" / "dist" / "spa"
    runtime_dir: Path = Path("/run/haptic")
    simulate: bool = False
    pins: Pins = field(default_factory=Pins)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    nfc: NfcConfig = field(default_factory=NfcConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

    @property
    def music_dir(self) -> Path:
        return self.data_dir / "music"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def tags_file(self) -> Path:
        return self.data_dir / "tags.json"

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.toml"

    @property
    def mpv_socket(self) -> Path:
        return self.runtime_dir / "mpv.sock"

    def ensure_dirs(self) -> None:
        for d in (self.music_dir, self.recordings_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)


def _merge(obj: Any, data: dict[str, Any]) -> None:
    for f in fields(obj):
        if f.name not in data:
            continue
        cur = getattr(obj, f.name)
        val = data[f.name]
        if is_dataclass(cur) and isinstance(val, dict):
            _merge(cur, val)
        elif isinstance(cur, Path):
            setattr(obj, f.name, Path(val))
        else:
            setattr(obj, f.name, val)


def load_config(data_dir: Path | str | None = None, **overrides: Any) -> Config:
    cfg = Config()
    if data_dir is not None:
        cfg.data_dir = Path(data_dir)
    path = cfg.config_file
    if path.exists():
        with path.open("rb") as fh:
            _merge(cfg, tomllib.load(fh))
    for key, val in overrides.items():
        if val is not None:
            setattr(cfg, key, val)
    cfg.data_dir = Path(cfg.data_dir)
    return cfg


# Only these keys are persisted by the app / editable via the web UI
# (hardware pins are changed by editing config.toml by hand).
PERSISTED = ("volume", "on_tag_remove", "volume_step", "long_press_s")


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v))


def atomic_write(path: Path, data: str | bytes) -> None:
    """Write temp -> fsync -> rename, so a hard power cut never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode() if isinstance(data, str) else data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def save_persisted(cfg: Config) -> None:
    """Rewrite config.toml: keep existing hardware sections, update the app-level keys."""
    existing: dict[str, Any] = {}
    if cfg.config_file.exists():
        with cfg.config_file.open("rb") as fh:
            existing = tomllib.load(fh)
    for key in PERSISTED:
        existing[key] = getattr(cfg, key)
    lines = [f"{k} = {_toml_value(v)}" for k, v in existing.items() if not isinstance(v, (dict, list))]
    for k, v in existing.items():
        if isinstance(v, dict):
            lines += ["", f"[{k}]"] + [f"{kk} = {_toml_value(vv)}" for kk, vv in v.items() if not isinstance(vv, (dict, list))]
    atomic_write(cfg.config_file, "\n".join(lines) + "\n")
