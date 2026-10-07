"""Display: Renderer (state -> PIL image, hardware independent), St7789 driver (spidev + libgpiod), DisplayThread.

    python -m haptic_player.display --test        # colour bars + sample screen on the real panel
    python -m haptic_player.display --png out.png # render the sample screen to a file
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import DisplayConfig
from .gpio import resolve

log = logging.getLogger(__name__)

BG = (12, 14, 20)
FG = (235, 238, 245)
DIM = (140, 148, 165)
ACCENT = (80, 200, 120)
REC = (235, 64, 64)
PAUSE = (240, 180, 60)
BAR_BG = (45, 50, 62)
FONT_PATHS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf")
FONT_BOLD_PATHS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf")


@dataclass(frozen=True)
class View:
    """What the screen shows; frozen so DisplayThread can skip identical frames."""

    mode: str = "idle"  # idle | playing | paused | recording
    title: str = ""
    subtitle: str = ""
    position: int = 0
    duration: int = 0
    index: int = 0
    count: int = 0
    slot: int = 0  # selected recording slot (0 = none)
    volume: int = 0
    cover: str = ""  # path of a cover image file
    message: str = ""  # transient hint, e.g. "unknown tag"
    ip: str = ""


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in FONT_BOLD_PATHS if bold else FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def fmt_time(s: int) -> str:
    return f"{s // 60:d}:{s % 60:02d}"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, len(lines[-1]) - 1)] + "…"
    return lines


class Renderer:
    def __init__(self, width: int = 240, height: int = 320):
        self.w, self.h = width, height
        self._cover_cache: tuple[str, Image.Image] | None = None

    def _cover(self, path: str, size: int) -> Image.Image | None:
        if not path:
            return None
        if self._cover_cache and self._cover_cache[0] == path:
            return self._cover_cache[1]
        try:
            img = Image.open(path).convert("RGB")
            img = img.resize((size, size), Image.LANCZOS)
        except Exception:
            return None
        self._cover_cache = (path, img)
        return img

    def render(self, v: View) -> Image.Image:
        img = Image.new("RGB", (self.w, self.h), BG)
        d = ImageDraw.Draw(img)
        small, mid, big = _font(14), _font(18), _font(19, bold=True)
        pad = 10

        # status bar
        label, color = {"playing": ("PLAY", ACCENT), "paused": ("PAUSE", PAUSE), "recording": ("REC", REC), "computer": ("USB", PAUSE)}.get(v.mode, ("READY", DIM))
        if v.mode == "recording":
            d.ellipse((pad, 12, pad + 14, 26), fill=REC)
            d.text((pad + 22, 8), f"{label}  slot {v.slot}", font=mid, fill=color)
        else:
            d.text((pad, 8), label, font=mid, fill=color)
            if v.slot:
                d.text((self.w - pad, 10), f"slot {v.slot}", font=small, fill=DIM, anchor="ra")
        d.line((pad, 36, self.w - pad, 36), fill=BAR_BG, width=2)

        # cover
        size = min(self.w - 2 * pad, 130)
        cx, cy = (self.w - size) // 2, 44
        cover = self._cover(v.cover, size)
        if cover is not None:
            img.paste(cover, (cx, cy))
        else:
            d.rounded_rectangle((cx, cy, cx + size, cy + size), 12, fill=BAR_BG)
            d.text((cx + size // 2, cy + size // 2), "♪" if v.mode != "recording" else "●", font=_font(64), fill=DIM if v.mode != "recording" else REC, anchor="mm")

        # title / subtitle
        y = cy + size + 8
        title = v.title or ("Tag auflegen…" if v.mode == "idle" else "")
        for line in _wrap(d, title, big, self.w - 2 * pad, 2):
            d.text((pad, y), line, font=big, fill=FG)
            y += 24
        if v.subtitle:
            d.text((pad, y), _wrap(d, v.subtitle, small, self.w - 2 * pad, 1)[0], font=small, fill=DIM)

        # progress
        by = self.h - 44
        d.rounded_rectangle((pad, by, self.w - pad, by + 8), 4, fill=BAR_BG)
        if v.duration > 0:
            fill = int((self.w - 2 * pad) * min(1.0, v.position / v.duration))
            if fill > 0:
                d.rounded_rectangle((pad, by, pad + fill, by + 8), 4, fill=color)
        d.text((pad, by + 14), fmt_time(v.position), font=small, fill=FG)
        if v.duration > 0:
            d.text((self.w - pad, by + 14), fmt_time(v.duration), font=small, fill=DIM, anchor="ra")
        if v.count > 1:
            d.text((self.w // 2, by + 14), f"{v.index + 1}/{v.count}", font=small, fill=DIM, anchor="ma")
        if v.message:
            d.rounded_rectangle((pad, 40, self.w - pad, 70), 8, fill=(60, 40, 20))
            d.text((self.w // 2, 55), v.message, font=small, fill=PAUSE, anchor="mm")
        return img


def to_rgb565(img: Image.Image) -> bytes:
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    v = ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    return v.astype(">u2").tobytes()


class Sink(Protocol):
    def show(self, img: Image.Image) -> None: ...
    def close(self) -> None: ...


class NullSink:
    def show(self, img: Image.Image) -> None:
        pass

    def close(self) -> None:
        pass


class St7789:
    """ST7789 over /dev/spidevX.Y; DC/RST/BL through libgpiod outputs."""

    MADCTL = {0: 0x00, 90: 0x60, 180: 0xC0, 270: 0xA0}

    def __init__(self, cfg: DisplayConfig):
        import gpiod
        import spidev
        from gpiod.line import Direction, Value

        self.cfg = cfg
        self._Value = Value
        bus, dev = (int(x) for x in cfg.spidev.rsplit("spidev", 1)[1].split("."))
        self.spi = spidev.SpiDev()
        self.spi.open(bus, dev)
        self.spi.max_speed_hz = cfg.spi_hz
        self.spi.mode = 0
        self.w, self.h = (cfg.height, cfg.width) if cfg.rotation in (90, 270) else (cfg.width, cfg.height)
        self._lines: dict[str, tuple[object, int]] = {}
        for name in ("dc", "rst", "backlight"):
            path, off = resolve(getattr(cfg, name))
            req = gpiod.request_lines(path, consumer=f"haptic-lcd-{name}",
                                      config={off: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE)})
            self._lines[name] = (req, off)
        self._init_panel()

    def _set(self, name: str, on: bool) -> None:
        req, off = self._lines[name]
        req.set_value(off, self._Value.ACTIVE if on else self._Value.INACTIVE)  # type: ignore[attr-defined]

    def _cmd(self, cmd: int, data: bytes = b"") -> None:
        self._set("dc", False)
        self.spi.writebytes([cmd])
        if data:
            self._set("dc", True)
            self.spi.writebytes(list(data))

    def _init_panel(self) -> None:
        self._set("rst", True); time.sleep(0.01)
        self._set("rst", False); time.sleep(0.02)
        self._set("rst", True); time.sleep(0.15)
        self._cmd(0x01); time.sleep(0.15)  # SWRESET
        self._cmd(0x11); time.sleep(0.12)  # SLPOUT
        self._cmd(0x3A, b"\x55")  # COLMOD: 16 bit
        self._cmd(0x36, bytes([self.MADCTL[self.cfg.rotation]]))
        self._cmd(0xB2, b"\x0c\x0c\x00\x33\x33")
        self._cmd(0xB7, b"\x35")
        self._cmd(0xBB, b"\x19")
        self._cmd(0xC0, b"\x2c")
        self._cmd(0xC2, b"\x01")
        self._cmd(0xC3, b"\x12")
        self._cmd(0xC4, b"\x20")
        self._cmd(0xC6, b"\x0f")
        self._cmd(0xD0, b"\xa4\xa1")
        self._cmd(0xE0, bytes.fromhex("d0040d11132b3f544c180d0b1f23"))
        self._cmd(0xE1, bytes.fromhex("d0040c11132c3f4451 2f1f1f2023".replace(" ", "")))
        self._cmd(0x21 if self.cfg.invert else 0x20)  # INVON / INVOFF
        self._cmd(0x13)  # NORON
        self._cmd(0x29); time.sleep(0.05)  # DISPON
        self._set("backlight", True)

    def show(self, img: Image.Image) -> None:
        if img.size != (self.w, self.h):
            img = img.resize((self.w, self.h))
        self._cmd(0x2A, bytes([0, 0, (self.w - 1) >> 8, (self.w - 1) & 0xFF]))
        self._cmd(0x2B, bytes([0, 0, (self.h - 1) >> 8, (self.h - 1) & 0xFF]))
        self._cmd(0x2C)
        self._set("dc", True)
        raw = to_rgb565(img)
        for i in range(0, len(raw), 4096):
            self.spi.writebytes2(raw[i : i + 4096])

    def close(self) -> None:
        try:
            self._set("backlight", False)
            self.spi.close()
        except Exception:
            pass


class PngSink:
    """--simulate: the latest frame is written to a PNG (also served at /api/display.png)."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def show(self, img: Image.Image) -> None:
        tmp = self.path.with_suffix(".tmp.png")
        img.save(tmp)
        tmp.replace(self.path)

    def close(self) -> None:
        pass


class DisplayThread(threading.Thread):
    """Renders the newest View (dropping stale ones) and skips frames identical to the last one."""

    def __init__(self, sink: Sink, renderer: Renderer):
        super().__init__(daemon=True, name="display")
        self.sink, self.renderer = sink, renderer
        self._q: queue.Queue[View | None] = queue.Queue()
        self._last: View | None = None

    def update(self, view: View) -> None:
        self._q.put(view)

    def stop(self) -> None:
        self._q.put(None)

    def run(self) -> None:
        while True:
            v = self._q.get()
            while True:  # coalesce: only the newest matters
                try:
                    nxt = self._q.get_nowait()
                except queue.Empty:
                    break
                v = nxt
                if v is None:
                    break
            if v is None:
                self.sink.close()
                return
            if v == self._last:
                continue
            self._last = v
            try:
                self.sink.show(self.renderer.render(v))
            except Exception:
                log.exception("display update failed")


def make_display(cfg: DisplayConfig, simulate: bool, png_path: Path) -> DisplayThread | None:
    if not cfg.enabled:
        return None
    renderer = Renderer(cfg.width, cfg.height) if cfg.rotation in (0, 180) else Renderer(cfg.height, cfg.width)
    if simulate:
        sink: Sink = PngSink(png_path)
    else:
        try:
            sink = St7789(cfg)
        except Exception as e:
            log.warning("display unavailable (%s) - running without", e)
            return None
    t = DisplayThread(sink, renderer)
    t.start()
    return t


SAMPLE = View(mode="playing", title="Alle meine Entchen", subtitle="Kinderlieder", position=83, duration=165, index=2, count=12, slot=0, volume=70)

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="show colour bars then the sample screen on the real panel")
    ap.add_argument("--png", help="render the sample screen to this PNG instead")
    ap.add_argument("--rotation", type=int, default=0)
    a = ap.parse_args()
    cfg = DisplayConfig(rotation=a.rotation)
    r = Renderer(cfg.width, cfg.height) if a.rotation in (0, 180) else Renderer(cfg.height, cfg.width)
    if a.png:
        r.render(SAMPLE).save(a.png)
        print("wrote", a.png)
    elif a.test:
        lcd = St7789(cfg)
        bars = Image.new("RGB", (lcd.w, lcd.h))
        bd = ImageDraw.Draw(bars)
        for i, c in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]):
            bd.rectangle((0, i * lcd.h // 4, lcd.w, (i + 1) * lcd.h // 4), fill=c)
        lcd.show(bars)
        time.sleep(3)
        lcd.show(r.render(SAMPLE))
        print("red/green/blue/white bars, then the sample screen - if colours are wrong try invert=false; "
              "if the screen stays black/noisy MOSI may be on SPI0_D0 (see docs/BRING-UP.md)")
    else:
        ap.print_help()
