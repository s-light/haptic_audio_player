"""USB mass-storage gadget: export the data partition to a PC (exclusive hand-over, see
docs/reference/readonly-root-and-storage.md). Must run as root.

    sudo python -m haptic_player.usbgadget on|off|status
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GADGET = Path("/sys/kernel/config/usb_gadget/haptic")
LABEL = "HAPTIC"
MOUNTPOINT = "/srv/haptic"


def _run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def udc_name() -> str:
    udcs = sorted(p.name for p in Path("/sys/class/udc").glob("*"))
    if not udcs:
        raise RuntimeError("no USB device controller found (/sys/class/udc is empty)")
    return udcs[0]


def is_exported() -> bool:
    udc = GADGET / "UDC"
    return udc.exists() and udc.read_text().strip() != ""


def block_device() -> str:
    dev = _run("blkid", "-L", LABEL, check=False).stdout.strip()
    if not dev:
        raise RuntimeError(f"no partition with label {LABEL}")
    return dev


def _bb_gadget_service() -> bool:
    """BeagleBoard images ship bb-usb-gadgets.service (USB ethernet + mass storage composite) that owns the UDC."""
    return _run("systemctl", "cat", "bb-usb-gadgets.service", check=False).returncode == 0


def enable() -> None:
    if is_exported():
        return
    if _bb_gadget_service():
        _run("systemctl", "stop", "bb-usb-gadgets.service", check=False)
    dev = block_device()
    r = _run("umount", MOUNTPOINT, check=False)
    if r.returncode and _run("mountpoint", "-q", MOUNTPOINT, check=False).returncode == 0:
        raise RuntimeError(f"cannot unmount {MOUNTPOINT}: {r.stderr.strip()}")
    _run("modprobe", "libcomposite")
    GADGET.mkdir(parents=True, exist_ok=True)
    (GADGET / "idVendor").write_text("0x1d6b")  # Linux Foundation
    (GADGET / "idProduct").write_text("0x0104")  # multifunction composite gadget
    (GADGET / "bcdUSB").write_text("0x0200")
    strings = GADGET / "strings" / "0x409"
    strings.mkdir(parents=True, exist_ok=True)
    (strings / "serialnumber").write_text("haptic0001")
    (strings / "manufacturer").write_text("haptic_audio_player")
    (strings / "product").write_text("Haptic Player Storage")
    cfg = GADGET / "configs" / "c.1"
    (cfg / "strings" / "0x409").mkdir(parents=True, exist_ok=True)
    (cfg / "strings" / "0x409" / "configuration").write_text("mass storage")
    func = GADGET / "functions" / "mass_storage.0"
    func.mkdir(parents=True, exist_ok=True)
    (func / "lun.0" / "removable").write_text("1")
    (func / "lun.0" / "ro").write_text("0")
    (func / "lun.0" / "file").write_text(dev)
    link = cfg / "mass_storage.0"
    if not link.exists():
        link.symlink_to(func)
    (GADGET / "UDC").write_text(udc_name())


def disable() -> None:
    if GADGET.exists():
        try:
            (GADGET / "UDC").write_text("")
        except OSError:
            pass
        (GADGET / "functions" / "mass_storage.0" / "lun.0" / "file").write_text("")
        link = GADGET / "configs" / "c.1" / "mass_storage.0"
        if link.is_symlink():
            link.unlink()
        for d in (GADGET / "configs" / "c.1" / "strings" / "0x409", GADGET / "configs" / "c.1",
                  GADGET / "functions" / "mass_storage.0", GADGET / "strings" / "0x409", GADGET):
            try:
                d.rmdir()
            except OSError:
                pass
    _run("sync", check=False)
    if _bb_gadget_service():
        _run("systemctl", "start", "bb-usb-gadgets.service", check=False)
    if _run("mountpoint", "-q", MOUNTPOINT, check=False).returncode != 0:
        r = _run("mount", MOUNTPOINT, check=False)
        if r.returncode:
            raise RuntimeError(f"cannot mount {MOUNTPOINT}: {r.stderr.strip()}")


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "status"
    try:
        if action == "on":
            enable()
        elif action == "off":
            disable()
        elif action != "status":
            print(__doc__)
            return 2
    except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print("usb" if is_exported() else "player")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
