import pytest

from haptic_player.cst328 import CST328, CST328Error, TOUCH_DATA_SIZE, parse_touches


def touch_buf(points: list[tuple[int, int, int, int]]) -> bytes:
    """Build a REG_TOUCH_INFO read: points = (id, x, y, pressure); finger count lives at byte 5."""
    buf = bytearray(TOUCH_DATA_SIZE)
    i = 0
    for n, (pid, x, y, z) in enumerate(points):
        buf[i : i + 5] = bytes([pid << 4 | 6, x >> 4, y >> 4, (x & 0xF) << 4 | (y & 0xF), z])
        i += 7 if n == 0 else 5
    buf[5] = len(points)
    return bytes(buf)


def test_parse_single_and_multi_touch():
    assert parse_touches(touch_buf([])) == []
    (t,) = parse_touches(touch_buf([(0, 123, 301, 40)]))
    assert (t.id, t.x, t.y, t.pressure) == (0, 123, 301, 40)
    ts = parse_touches(touch_buf([(0, 10, 20, 5), (1, 239, 319, 9), (2, 1, 2, 3)]))
    assert [(t.id, t.x, t.y, t.pressure) for t in ts] == [(0, 10, 20, 5), (1, 239, 319, 9), (2, 1, 2, 3)]


def test_parse_ignores_bogus_count_and_rejects_short():
    buf = bytearray(touch_buf([(0, 1, 2, 3)]))
    buf[5] = 0x0F
    assert parse_touches(bytes(buf)) == []
    buf[5] = 0xF0  # high nibble is not the count
    assert parse_touches(bytes(buf)) == []
    with pytest.raises(CST328Error):
        parse_touches(b"\x00" * 5)


class FakeBus:
    """Answers register reads from a dict {reg: bytes}; records writes."""

    def __init__(self, regs: dict[int, bytes]):
        self.regs, self.writes, self.pending = regs, [], 0

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        if len(data) == 2:
            self.pending = data[0] << 8 | data[1]

    def read(self, n: int) -> bytes:
        return self.regs[self.pending][:n].ljust(n, b"\x00")

    def close(self) -> None:
        pass


def chip_regs(crc: int = 0xCACA) -> dict[int, bytes]:
    return {
        0xD1FC: bytes([0, 0, crc & 0xFF, crc >> 8]),
        0xD204: bytes([0x34, 0x12, 0x28, 0x03]),  # project 0x1234, chip 0x0328
        0xD208: bytes([7, 0, 2, 1]),  # build 7, minor 2, major 1
        0xD1F8: bytes([0xF0, 0, 0x40, 1]),  # 240 x 320
        0xD000: touch_buf([(0, 100, 200, 30)]),
    }


def test_setup_reads_info_and_enters_normal_mode(monkeypatch):
    monkeypatch.setattr("haptic_player.cst328.time.sleep", lambda s: None)
    bus, levels = FakeBus(chip_regs()), []
    chip = CST328(bus, reset=levels.append)
    info = chip.setup()
    assert levels == [True, False, True]
    assert (info.chip_id, info.project_id, info.fw_version, info.x_max, info.y_max) == (0x328, 0x1234, (1, 2, 7), 240, 320)
    assert bytes([0xD1, 0x09]) in bus.writes  # normal mode
    assert bus.writes[-1] == bytes([0xD0, 0x00, 0xAB])  # sync


def test_setup_rejects_wrong_firmware_crc(monkeypatch):
    monkeypatch.setattr("haptic_player.cst328.time.sleep", lambda s: None)
    with pytest.raises(CST328Error, match="CRC"):
        CST328(FakeBus(chip_regs(crc=0x0000))).setup()


def test_read_touches_acknowledges():
    bus = FakeBus(chip_regs())
    (t,) = CST328(bus).read_touches()
    assert (t.x, t.y, t.pressure) == (100, 200, 30)
    assert bus.writes[-2:] == [bytes([0xD0, 0x05, 0x00]), bytes([0xD0, 0x00, 0xAB])]
