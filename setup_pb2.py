#!/usr/bin/env python3
"""Single entry point for the PocketBeagle 2 setup of the haptic audio player.

    ./setup_pb2.py              # run every default step, in order
    ./setup_pb2.py STEP_NAME    # run just one step
    ./setup_pb2.py --list-steps

Run as your normal user: the script re-execs itself through `sudo` once, so you get one password prompt.
Every step is idempotent - safe to re-run any time. Steps that need a reboot (the device-tree overlay) stop
cleanly with a message; reboot and run this again.

Default steps:  packages sudoers groups venv datadir overlay webui service
Opt-in steps (never part of the default run):
    usb-gadget     prepare USB mass-storage mode (libcomposite)   - untested on hardware
    readonly-root  make / read-only (fstab 'ro', volatile journal, tmpfs for /var/log) - do this LAST, then reboot

If the root filesystem is already read-only (after readonly-root), run ./readwrite.sh before setup steps and
./readonly.sh afterwards.
"""

import os
import pwd
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_DIR))
import haptic_setup as hs  # noqa: E402
from haptic_setup import NeedsReboot  # noqa: E402

VENV_DIR = REPO_DIR / ".venv"
DATA_DIR = Path("/srv/haptic")
DATA_LABEL = "HAPTIC"
OVERLAY = "k3-am62-pocketbeagle2-haptic-player"
SERVICE = "haptic-player.service"
GROUPS = ["audio", "i2c", "gpio", "spi"]

APT_PACKAGES = [
    "mpv", "alsa-utils", "i2c-tools", "gpiod", "python3-venv", "python3-libgpiod", "python3-aiohttp",
    "python3-pil", "python3-numpy", "python3-mutagen", "python3-spidev", "fonts-dejavu-core",
    "build-essential", "device-tree-compiler",
]


def user() -> str:
    return hs.invoking_user()


def step_packages():
    """apt packages (audio, gpio, i2c, python libs, overlay build tools)."""
    hs.require_writable_root()
    hs.apt_install(*APT_PACKAGES)


def step_sudoers():
    """NOPASSWD sudo for the player user, scoped to: this script, the service, power, USB gadget helper."""
    hs.require_writable_root()
    py = VENV_DIR / "bin" / "python"
    hs.add_nopasswd_sudoers("haptic-player", user(), [
        f"{Path(__file__).resolve()} *",
        "/usr/bin/systemctl poweroff", "/usr/bin/systemctl reboot",
        f"/usr/bin/systemctl * {SERVICE}", f"/usr/bin/journalctl -u {SERVICE}*",
        f"{py} -m haptic_player.usbgadget on", f"{py} -m haptic_player.usbgadget off",
        f"{py} -m haptic_player.usbgadget status",
    ])


def step_groups():
    """device access: i2c / spidev / gpiochip / audio groups + udev rules."""
    hs.require_writable_root()
    hs.add_to_groups(user(), GROUPS)
    hs.install_udev_rules("/etc/udev/rules.d/60-haptic-player.rules", "\n".join([
        'SUBSYSTEM=="i2c-dev", GROUP="i2c", MODE="0660"',
        'SUBSYSTEM=="spidev", GROUP="spi", MODE="0660"',
        'SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"',
        "",
    ]))


def step_venv():
    """python venv (with system site packages for libgpiod) + requirements."""
    hs.require_writable_root()
    hs.ensure_venv(VENV_DIR, REPO_DIR / "requirements.txt", user())


def step_datadir():
    """writable data partition: fstab entry for LABEL=HAPTIC at /srv/haptic (music, recordings, tags, config)."""
    hs.require_writable_root()
    pw = pwd.getpwnam(user())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hs.ensure_fstab_line(
        str(DATA_DIR),
        f"LABEL={DATA_LABEL} {DATA_DIR} vfat noatime,nofail,flush,uid={pw.pw_uid},gid={pw.pw_gid},umask=0002,x-systemd.device-timeout=5 0 0",
    )
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    if not subprocess.run(["blkid", "-L", DATA_LABEL], capture_output=True, text=True).stdout.strip():
        print(f"\n    !! no partition labelled {DATA_LABEL} found. Create one (USB stick, SD card or 2nd SD partition), e.g.:\n"
              f"       sudo mkfs.vfat -F 32 -n {DATA_LABEL} /dev/sdX1      # CAREFUL: pick the right device\n"
              f"    then re-run ./setup_pb2.py datadir")
        return
    if subprocess.run(["mountpoint", "-q", str(DATA_DIR)]).returncode != 0:
        hs.run(["mount", str(DATA_DIR)])
    for sub in ("music", "recordings"):
        (DATA_DIR / sub).mkdir(exist_ok=True)


def step_overlay():
    """compile + install the device-tree overlay (I2S/WM8960, SPI0 display, GPIO pads) and wire it into extlinux."""
    hs.require_writable_root()
    hs.compile_and_install_overlay(REPO_DIR / "overlays" / f"{OVERLAY}.dtso", OVERLAY)
    hs.wire_overlay_into_extlinux(OVERLAY)
    cards = Path("/proc/asound/cards")
    if not cards.exists() or "haptic" not in cards.read_text():
        raise NeedsReboot("overlay installed and wired, but the 'haptic' sound card is not there yet - "
                          "reboot (with the Voice Bonnet wired, see hw/wiring-diagram.svg), then re-run ./setup_pb2.py")


def step_webui():
    """web UI (webui/dist/spa): build it here if Node >= 22.12 is available, else tell how to deploy a PC build."""
    spa = REPO_DIR / "webui" / "dist" / "spa" / "index.html"
    if spa.exists():
        print("    webui/dist/spa already built")
        return
    hint = ("    !! web UI not built. The Quasar CLI needs Node >= 22.12 (Debian's nodejs is usually older).\n"
            "       Build on your PC and copy it over:   webui/deploy.sh <user>@<board>\n"
            "       (root may be read-only: ./readwrite.sh first), then re-run ./setup_pb2.py webui")
    have = lambda c: subprocess.run(["which", c], capture_output=True).returncode == 0
    node_ok = False
    if have("node"):
        ver = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
        major, minor = (int(x) for x in ver.split(".")[:2])
        node_ok = (major, minor) >= (22, 12)
    if not node_ok or not have("pnpm"):
        print(hint)
        return
    web = REPO_DIR / "webui"
    # as the normal user (never pnpm as root). Needs several 100 MB RAM.
    hs.run(["sudo", "-u", user(), "pnpm", "install", "--frozen-lockfile"], cwd=web)
    hs.run(["sudo", "-u", user(), "pnpm", "run", "build"], cwd=web)


def step_service():
    """install + enable + (re)start haptic-player.service."""
    hs.require_writable_root()
    hs.install_systemd_unit(REPO_DIR / "systemd" / SERVICE, SERVICE, {
        "USER": user(), "REPO_DIR": REPO_DIR, "VENV_DIR": VENV_DIR, "DATA_DIR": DATA_DIR,
    }, enable_now=True)


def step_usb_gadget():
    """(opt-in) USB mass-storage mode: load libcomposite at boot; check a device controller exists."""
    hs.require_writable_root()
    hs.write_file("/etc/modules-load.d/haptic-usb-gadget.conf", "libcomposite\n")
    subprocess.run(["modprobe", "libcomposite"], check=False)
    udc = Path("/sys/class/udc")
    udcs = [u.name for u in udc.glob("*")] if udc.exists() else []
    print(f"    USB device controllers: {udcs or 'NONE - gadget mode will not work'}")
    print("    toggle from the web UI (System -> USB-Speichermodus) or: sudo .venv/bin/python -m haptic_player.usbgadget on|off")


def step_readonly_root():
    """(opt-in, LAST) make / read-only: fstab 'ro', volatile journal, tmpfs /var/log + /var/tmp. Reboot afterwards."""
    if hs.root_is_readonly():
        print("    root is already read-only")
        return
    hs.make_root_readonly()


STEPS = [
    ("packages", step_packages),
    ("sudoers", step_sudoers),
    ("groups", step_groups),
    ("venv", step_venv),
    ("datadir", step_datadir),
    ("overlay", step_overlay),
    ("webui", step_webui),
    ("service", step_service),
]
OPTIONAL = [
    ("usb-gadget", step_usb_gadget),
    ("readonly-root", step_readonly_root),
]


def main():
    args = sys.argv[1:]
    if args and args[0] == "--list-steps":
        for name, _ in STEPS:
            print(name)
        for name, _ in OPTIONAL:
            print(f"{name}  (opt-in)")
        return

    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", "-E", str(Path(__file__).resolve()), *args])

    every = dict(STEPS + OPTIONAL)
    if args:
        if args[0] not in every:
            hs.fail(f"unknown step {args[0]!r} - see --list-steps")
        selected = [(args[0], every[args[0]])]
    else:
        selected = STEPS

    for name, func in selected:
        print(f"\n===== {name} =====")
        try:
            func()
        except NeedsReboot as e:
            print(f"\n{e}")
            sys.exit(0)
    print("\nall done." + ("" if args else " Optional next steps: ./setup_pb2.py usb-gadget ; ./setup_pb2.py readonly-root (last!)"))


if __name__ == "__main__":
    main()
