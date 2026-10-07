"""USB mass storage next to the board's USB network: hand the data stick to a connected computer.

The BeagleBoard image's own gadget (`bb-usb-gadgets.service`, configfs `g_multi`: network + serial) stays in
place - the web UI is reached through its USB network, so it must keep working. `setup` adds ONE extra
mass-storage function to that gadget (empty drive, "no media"); `attach` / `detach` then only insert / eject the
medium (no unbind, the network does not flap). Exclusive hand-over: the data partition is unmounted locally
while the computer owns it. See docs/reference/readonly-root-and-storage.md.

Must run as root (the app calls it through sudo):

    python -m haptic_player.usbgadget setup     # once per boot (haptic-usb-gadget.service)
    python -m haptic_player.usbgadget attach    # unmount the data partition, give it to the computer
    python -m haptic_player.usbgadget detach    # computer ejects / unplugged: take it back, fsck, mount
    python -m haptic_player.usbgadget status    # one JSON line
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CONFIGFS = Path("/sys/kernel/config/usb_gadget")
UDC_CLASS = Path("/sys/class/udc")
FUNCTION = "mass_storage.haptic"
LABEL = "HAPTIC"
MOUNTPOINT = "/srv/haptic"


class GadgetError(RuntimeError):
    pass


def _run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _write(path: Path, value: str) -> None:
    """configfs/sysfs attributes act on a write() call - an empty string would not even issue one, so always
    terminate with a newline (`echo "" > attr`), which the kernel strips."""
    path.write_text(value + "\n")


def find_gadget(root: Path | None = None) -> Path | None:
    """The gadget that owns the UDC (the stock one); else the only/first one."""
    root = root or CONFIGFS
    if not root.is_dir():
        return None
    found = sorted(p for p in root.iterdir() if p.is_dir())
    for g in found:
        udc = g / "UDC"
        if udc.exists() and udc.read_text().strip():
            return g
    return found[0] if found else None


def lun_dir(gadget: Path) -> Path:
    return gadget / "functions" / FUNCTION / "lun.0"


def udc_state(udc_class: Path | None = None) -> str:
    """`configured` once a USB host has enumerated us; a plain powerbank never gets there."""
    udc_class = udc_class or UDC_CLASS
    for udc in sorted(udc_class.glob("*")) if udc_class.is_dir() else []:
        try:
            return (udc / "state").read_text().strip()
        except OSError:
            continue
    return "none"


def read_state(root: Path | None = None, udc_class: Path | None = None) -> dict:
    """Readable without root (used by the app's watcher)."""
    g = find_gadget(root)
    function = g is not None and lun_dir(g).is_dir()
    attached = False
    if function:
        try:
            attached = bool((lun_dir(g) / "file").read_text().strip())  # type: ignore[arg-type]
        except OSError:
            pass
    return {"function": function, "host": udc_state(udc_class) == "configured", "udc": udc_state(udc_class), "attached": attached}


def block_device() -> str:
    dev = _run("blkid", "-L", LABEL, check=False).stdout.strip()
    if not dev:
        raise GadgetError(f"no partition with label {LABEL} (USB stick plugged in?)")
    return dev


def is_mounted() -> bool:
    return _run("mountpoint", "-q", MOUNTPOINT, check=False).returncode == 0


def setup() -> None:
    g = find_gadget()
    if g is None:
        raise GadgetError("no USB gadget found - is bb-usb-gadgets.service running?")
    if not lun_dir(g).is_dir():
        _run("modprobe", "usb_f_mass_storage", check=False)
        configs = sorted(p for p in (g / "configs").glob("*") if p.is_dir())
        if not configs:
            raise GadgetError(f"{g} has no configuration")
        udc = (g / "UDC").read_text().strip()
        if udc:
            _write(g / "UDC", "")  # unbind once, the network is back in about a second
        try:
            (g / "functions" / FUNCTION).mkdir(exist_ok=True)
            link = configs[0] / FUNCTION
            if not link.exists():
                link.symlink_to(g / "functions" / FUNCTION)
        finally:
            if udc:
                _write(g / "UDC", udc)
    lun = lun_dir(g)
    _write(lun / "removable", "1")
    _write(lun / "ro", "0")
    if not (lun / "file").read_text().strip():
        _write(lun / "file", "")


def attach() -> None:
    g = find_gadget()
    if g is None or not lun_dir(g).is_dir():
        setup()
        g = find_gadget()
    assert g is not None
    dev = block_device()
    if is_mounted():
        _run("sync")
        r = _run("umount", MOUNTPOINT, check=False)
        if r.returncode:
            raise GadgetError(f"cannot unmount {MOUNTPOINT}: {r.stderr.strip()}")
    _write(lun_dir(g) / "file", dev)


def detach() -> None:
    g = find_gadget()
    if g is not None and lun_dir(g).is_dir():
        lun = lun_dir(g)
        if (lun / "file").read_text().strip():
            try:
                _write(lun / "file", "")
            except OSError:
                _write(lun / "forced_eject", "1")  # host still holds the medium locked
    _run("sync", check=False)
    try:
        dev = block_device()
    except GadgetError:
        return  # stick pulled meanwhile - nothing to mount
    if not is_mounted():
        _run("fsck.vfat", "-a", dev, check=False)  # the computer may have left the dirty bit set
        r = _run("mount", MOUNTPOINT, check=False)
        if r.returncode:
            raise GadgetError(f"cannot mount {MOUNTPOINT}: {r.stderr.strip()}")


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "status"
    try:
        if action == "setup":
            setup()
        elif action == "attach":
            attach()
        elif action == "detach":
            detach()
        elif action != "status":
            print(__doc__)
            return 2
    except (GadgetError, OSError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    state = read_state()
    state["mounted"] = is_mounted()
    print(json.dumps(state))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
