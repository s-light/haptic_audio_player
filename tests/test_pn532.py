import pytest

from haptic_player.pn532 import ACK, PN532, PN532Error, build_frame, parse_frame, parse_passive_response


def test_build_frame_get_firmware():
    # datasheet example: 00 00 FF 02 FE D4 02 2A 00
    assert build_frame(0x02) == bytes.fromhex("0000ff02fed4022a00")


def test_build_frame_in_list_passive():
    assert build_frame(0x4A, b"\x01\x00") == bytes.fromhex("0000ff04fcd44a01 00e100".replace(" ", ""))


def test_parse_ack_and_response():
    assert parse_frame(ACK) == b""
    resp = bytes.fromhex("0000ff06fad50332010607e800".replace(" ", ""))
    assert parse_frame(resp) == bytes.fromhex("d50332010607")


def test_parse_rejects_bad_checksums():
    with pytest.raises(PN532Error):
        parse_frame(bytes.fromhex("0000ff06fbd50332010607e800"))  # LCS wrong
    with pytest.raises(PN532Error):
        parse_frame(bytes.fromhex("0000ff06fad50332010607e900"))  # DCS wrong
    with pytest.raises(PN532Error):
        parse_frame(b"\x01\x02\x03")


def test_parse_passive_response():
    assert parse_passive_response(b"\x00") is None
    resp = bytes.fromhex("01 01 0004 08 04 DEADBEEF".replace(" ", ""))
    assert parse_passive_response(resp) == bytes.fromhex("DEADBEEF")
    seven = bytes.fromhex("01 01 0044 00 07 04112233445566".replace(" ", ""))
    assert parse_passive_response(seven).hex() == "04112233445566"
    with pytest.raises(PN532Error):
        parse_passive_response(bytes.fromhex("0101000800 04 DEAD".replace(" ", "")))


class FakeTransport:
    """Plays back: after each write, an ACK then the queued response, each prefixed by a ready byte."""

    def __init__(self, responses):
        self.queue, self.written = [], []
        self.responses = list(responses)

    def write(self, data):
        self.written.append(data)
        if data[:3] == b"\x00\x00\xff":
            self.queue = [b"\x01" + ACK, b"\x01" + self.responses.pop(0)]

    def read(self, n):
        return self.queue.pop(0) if self.queue else b"\x00"

    def close(self):
        pass


def response_frame(command, data):
    payload = bytes([0xD5, command + 1]) + data
    return b"\x00\x00\xff" + bytes([len(payload), (0x100 - len(payload)) & 0xFF]) + payload + bytes([(0x100 - sum(payload)) & 0xFF, 0])


def test_read_uid_roundtrip():
    t = FakeTransport([response_frame(0x4A, bytes.fromhex("0101000804 04 A1B2C3D4".replace(" ", "")))])
    assert PN532(t).read_uid() == bytes.fromhex("A1B2C3D4")
    assert t.written[0] == build_frame(0x4A, b"\x01\x00")


def test_read_uid_none_and_timeout():
    assert PN532(FakeTransport([response_frame(0x4A, b"\x00")])).read_uid() is None

    class Dead(FakeTransport):
        def write(self, data):
            pass

        def read(self, n):
            return b"\x00"

    with pytest.raises(PN532Error):
        PN532(Dead([]), timeout=0.05).call(0x02)
