"""Minimal PN532 driver over Linux I2C (/dev/i2c-N), enough to read ISO14443A UIDs.

No Blinka/busio: Blinka has no PocketBeagle 2 support. Protocol: NXP UM0701-02, see docs/reference/pn532-nfc.md.
"""

from __future__ import annotations

import fcntl
import os
import time
from typing import Protocol

I2C_SLAVE = 0x0703
PREAMBLE = b"\x00\x00\xff"
ACK = b"\x00\x00\xff\x00\xff\x00"

CMD_GET_FIRMWARE = 0x02
CMD_SAM_CONFIGURATION = 0x14
CMD_RF_CONFIGURATION = 0x32
CMD_IN_LIST_PASSIVE = 0x4A
CMD_IN_RELEASE = 0x52


class PN532Error(Exception):
    pass


def build_frame(command: int, data: bytes = b"") -> bytes:
    """Normal information frame host -> PN532 (TFI = 0xD4)."""
    payload = bytes([0xD4, command]) + data
    length = len(payload)
    if length > 255:
        raise ValueError("frame too long")
    lcs = (0x100 - length) & 0xFF
    dcs = (0x100 - sum(payload)) & 0xFF
    return PREAMBLE + bytes([length, lcs]) + payload + bytes([dcs, 0x00])


def parse_frame(raw: bytes) -> bytes:
    """Return TFI+data of a PN532 -> host frame, or b'' for an ACK. Raises PN532Error on malformed frames."""
    i = raw.find(PREAMBLE)
    if i < 0:
        raise PN532Error(f"no start code in {raw.hex()}")
    raw = raw[i + 3 :]
    if len(raw) < 2:
        raise PN532Error("truncated frame")
    length, lcs = raw[0], raw[1]
    if length == 0 and lcs == 0xFF:
        return b""  # ACK
    if length == 0xFF and lcs == 0x00:
        raise PN532Error("extended frames not supported")
    if (length + lcs) & 0xFF:
        raise PN532Error("length checksum mismatch")
    body = raw[2 : 2 + length]
    if len(body) < length or len(raw) < 2 + length + 1:
        raise PN532Error("truncated frame")
    dcs = raw[2 + length]
    if (sum(body) + dcs) & 0xFF:
        raise PN532Error("data checksum mismatch")
    if body[0] == 0x7F:
        raise PN532Error("PN532 application error frame")
    return body


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, n: int) -> bytes: ...
    def close(self) -> None: ...


class I2CTransport:
    def __init__(self, bus: int, address: int):
        self.fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)

    def write(self, data: bytes) -> None:
        os.write(self.fd, data)

    def read(self, n: int) -> bytes:
        return os.read(self.fd, n)

    def close(self) -> None:
        os.close(self.fd)


class PN532:
    def __init__(self, transport: Transport, timeout: float = 1.0):
        self.t = transport
        self.timeout = timeout

    def _read_response(self, n: int, timeout: float) -> bytes:
        """Every I2C read starts with a status byte; bit0 = ready."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                data = self.t.read(n + 1)
            except OSError:
                data = b""
            if data and data[0] & 1:
                return data[1:]
            if time.monotonic() > deadline:
                raise PN532Error("timeout waiting for PN532")
            time.sleep(0.005)

    def call(self, command: int, data: bytes = b"", timeout: float | None = None) -> bytes:
        timeout = self.timeout if timeout is None else timeout
        self.t.write(build_frame(command, data))
        ack = self._read_response(6, timeout)
        if ack[:6] != ACK:
            raise PN532Error(f"no ACK, got {ack.hex()}")
        raw = self._read_response(64, timeout)
        body = parse_frame(raw)
        if len(body) < 2 or body[0] != 0xD5 or body[1] != command + 1:
            raise PN532Error(f"unexpected response {body.hex()}")
        return body[2:]

    def firmware(self) -> tuple[int, int, int, int]:
        ic, ver, rev, support = self.call(CMD_GET_FIRMWARE)[:4]
        return ic, ver, rev, support

    def setup(self) -> tuple[int, int, int, int]:
        """Wake-up + normal-mode SAM + short passive-activation retry (so polling returns quickly)."""
        try:
            self.t.write(b"\x00")  # wake up (I2C needs no special wake sequence, but a dummy write is harmless)
        except OSError:
            pass
        fw = self.firmware()
        self.call(CMD_SAM_CONFIGURATION, b"\x01\x14\x01")
        self.call(CMD_RF_CONFIGURATION, b"\x05\xff\x01\x01")  # MxRtyPassiveActivation = 1
        return fw

    def read_uid(self) -> bytes | None:
        """One poll for an ISO14443A tag @106 kbit/s; UID or None."""
        resp = self.call(CMD_IN_LIST_PASSIVE, b"\x01\x00", timeout=1.5)
        return parse_passive_response(resp)

    def release(self) -> None:
        self.call(CMD_IN_RELEASE, b"\x00")


def parse_passive_response(resp: bytes) -> bytes | None:
    """InListPassiveTarget response: NbTg [Tg SENS_RES(2) SEL_RES NFCIDLength NFCID...]."""
    if not resp or resp[0] == 0:
        return None
    if len(resp) < 6:
        raise PN532Error("short InListPassiveTarget response")
    uid_len = resp[5]
    uid = resp[6 : 6 + uid_len]
    if len(uid) != uid_len:
        raise PN532Error("truncated UID")
    return bytes(uid)
