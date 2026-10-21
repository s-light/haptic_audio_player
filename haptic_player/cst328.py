"""Minimal CST328 capacitive-touch driver over Linux I2C (/dev/i2c-N), polled.

No Blinka/busio: Blinka has no PocketBeagle 2 support, and CircuitPython has no CST328 library. The register map and
read sequence follow ESPHome's `cst328` component (esphome/components/cst328/touchscreen), see
docs/reference/waveshare-lcd-2.8.md. Registers are 16 bit, big-endian on the wire.

Bring-up on the board:  python -m haptic_player.cst328 --info   |   python -m haptic_player.cst328 --watch
"""

from __future__ import annotations

import fcntl
import os
import time
from dataclasses import dataclass
from typing import Callable, Protocol

I2C_SLAVE = 0x0703

MAX_POINTS = 5
TOUCH_DATA_SIZE = MAX_POINTS * 5 + 2  # 27 bytes from REG_TOUCH_INFO

REG_TOUCH_INFO = 0xD000
REG_FINGER_COUNT = 0xD005
REG_RESOLUTION = 0xD1F8  # x, y max (u16 LE each)
REG_FW_CRC_BOOT = 0xD1FC
REG_CHIP_PROJECT = 0xD204
REG_FW_REVISION = 0xD208
REG_MODE_DEBUG_INFO = 0xD101
REG_MODE_NORMAL = 0xD109

FW_CRC_OK = 0xCACA
SYNC_BYTE = 0xAB
RESET_LOW_S = 0.005
BOOT_S = 0.3  # datasheet 200 ms, typically much less


class CST328Error(Exception):
    pass


@dataclass(frozen=True)
class Touch:
    id: int
    x: int
    y: int
    pressure: int


@dataclass(frozen=True)
class ChipInfo:
    chip_id: int
    project_id: int
    fw_version: tuple[int, int, int]  # major, minor, build
    x_max: int
    y_max: int


class Bus(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, n: int) -> bytes: ...
    def close(self) -> None: ...


class I2CBus:
    def __init__(self, bus: int, address: int):
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)

    def write(self, data: bytes) -> None:
        os.write(self.fd, data)

    def read(self, n: int) -> bytes:
        return os.read(self.fd, n)

    def close(self) -> None:
        os.close(self.fd)


def parse_touches(buf: bytes) -> list[Touch]:
    """Decode the TOUCH_DATA_SIZE bytes read from REG_TOUCH_INFO.

    Byte 5 (= REG_FINGER_COUNT) holds the finger count in its low nibble, so the first point takes 7 bytes
    (5 + the 2 bytes in between) and every following one 5: [id<<4|state, x[11:4], y[11:4], x[3:0]<<4|y[3:0], z].
    """
    if len(buf) < TOUCH_DATA_SIZE:
        raise CST328Error(f"short touch read ({len(buf)} bytes)")
    count = buf[REG_FINGER_COUNT - REG_TOUCH_INFO] & 0x0F
    if count == 0 or count > MAX_POINTS:
        return []
    touches = []
    i = 0
    for n in range(count):
        touches.append(Touch(
            id=buf[i] >> 4,
            x=(buf[i + 1] << 4) | (buf[i + 3] >> 4),
            y=(buf[i + 2] << 4) | (buf[i + 3] & 0x0F),
            pressure=buf[i + 4],
        ))
        i += 7 if n == 0 else 5
    return touches


class CST328:
    def __init__(self, bus: Bus, reset: Callable[[bool], None] | None = None):
        """`reset(level)` drives the RST pin (True = released); None if RST is not wired/controlled."""
        self.bus = bus
        self.reset = reset
        self.info: ChipInfo | None = None

    def _read_reg(self, reg: int, n: int) -> bytes:
        self.bus.write(bytes([reg >> 8, reg & 0xFF]))
        data = self.bus.read(n)
        if len(data) != n:
            raise CST328Error(f"short read at 0x{reg:04X}: {len(data)}/{n} bytes")
        return data

    def _write_reg(self, reg: int, data: bytes = b"") -> None:
        self.bus.write(bytes([reg >> 8, reg & 0xFF]) + data)

    def hardware_reset(self) -> None:
        if self.reset is None:
            return
        self.reset(True)
        time.sleep(0.05)
        self.reset(False)
        time.sleep(RESET_LOW_S)
        self.reset(True)
        time.sleep(BOOT_S)

    def setup(self) -> ChipInfo:
        """Reset, read chip/firmware info (verifies the firmware CRC), switch to normal mode."""
        self.hardware_reset()
        self._write_reg(REG_MODE_DEBUG_INFO)
        crc_boot = self._read_reg(REG_FW_CRC_BOOT, 4)
        crc = crc_boot[2] | crc_boot[3] << 8
        if crc != FW_CRC_OK:
            raise CST328Error(f"firmware CRC 0x{crc:04X}, expected 0x{FW_CRC_OK:04X} (no CST328 at this address?)")
        cp = self._read_reg(REG_CHIP_PROJECT, 4)
        fw = self._read_reg(REG_FW_REVISION, 4)
        try:
            res = self._read_reg(REG_RESOLUTION, 4)
            x_max, y_max = res[0] | res[1] << 8, res[2] | res[3] << 8
        except (OSError, CST328Error):
            x_max, y_max = 240, 320
        self.info = ChipInfo(
            chip_id=cp[2] | cp[3] << 8,
            project_id=cp[0] | cp[1] << 8,
            fw_version=(fw[3], fw[2], fw[0] | fw[1] << 8),
            x_max=x_max or 240,
            y_max=y_max or 320,
        )
        self._write_reg(REG_MODE_NORMAL)
        self._read_reg(REG_TOUCH_INFO, 1)
        self._write_reg(REG_TOUCH_INFO, bytes([SYNC_BYTE]))
        return self.info

    def read_touches(self) -> list[Touch]:
        """Current touch points (empty = no finger). Acknowledges the data afterwards, as the chip expects."""
        touches = parse_touches(self._read_reg(REG_TOUCH_INFO, TOUCH_DATA_SIZE))
        self._write_reg(REG_FINGER_COUNT, b"\x00")
        self._write_reg(REG_TOUCH_INFO, bytes([SYNC_BYTE]))
        return touches

    def close(self) -> None:
        self.bus.close()


def open_from_config(cfg) -> tuple[CST328, Callable[[], None]]:
    """CST328 on cfg.touch (bus + RST line through libgpiod); the second value releases the RST line."""
    import gpiod
    from gpiod.line import Direction, Value

    from .gpio import resolve

    path, off = resolve(cfg.rst)
    req = gpiod.request_lines(path, consumer="haptic-touch-rst",
                              config={off: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE)})

    def reset(level: bool) -> None:
        req.set_value(off, Value.ACTIVE if level else Value.INACTIVE)

    return CST328(I2CBus(cfg.i2c_bus, cfg.address), reset), req.release


if __name__ == "__main__":
    import argparse

    from .config import load_config

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--info", action="store_true", help="print chip / firmware info and exit")
    ap.add_argument("--watch", action="store_true", help="print touch points until Ctrl-C")
    args = ap.parse_args()
    tcfg = load_config(args.data_dir).touch
    chip, release = open_from_config(tcfg)
    try:
        print(chip.setup())
        while args.watch:
            for t in chip.read_touches():
                print(t)
            time.sleep(tcfg.poll_interval)
    except KeyboardInterrupt:
        pass
    finally:
        chip.close()
        release()
