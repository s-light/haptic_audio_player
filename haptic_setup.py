"""Helpers for setup_pb2.py (PocketBeagle 2): users/sudoers, apt, udev, systemd units, fstab,
device-tree overlays (extlinux boot), read-only root. Patterned after the sibling light-desk project's
lightdesk_setup.py. All helpers that touch the system expect root (setup_pb2.py re-execs via sudo)."""

from __future__ import annotations

import grp
import os
import pwd
import re
import subprocess
import sys
from pathlib import Path


class NeedsReboot(Exception):
    pass


def fail(message: str):
    print(message, file=sys.stderr)
    sys.exit(1)


def step(title: str) -> None:
    print(f"==> {title}")


def require_root(what: str) -> None:
    if os.geteuid() != 0:
        fail(f"{what}: must run as root")


def run(cmd, **kwargs):
    kwargs.setdefault("check", True)
    print(f"    $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def invoking_user() -> str:
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or os.environ["LOGNAME"]


# --- root filesystem state -------------------------------------------------

def root_is_readonly() -> bool:
    for line in Path("/proc/mounts").read_text().splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[1] == "/" and "ro" in parts[3].split(","):
            return True
    return False


def require_writable_root(hint: str = "./readwrite.sh") -> None:
    if root_is_readonly():
        fail(f"root filesystem is read-only - run {hint} first (and ./readonly.sh again afterwards)")


# --- users / groups / sudoers ----------------------------------------------

def ensure_group(name: str, system: bool = True) -> None:
    try:
        grp.getgrnam(name)
        return
    except KeyError:
        pass
    run(["groupadd", *(["--system"] if system else []), name])


def add_to_groups(user: str, groups: list[str]) -> None:
    for g in groups:
        ensure_group(g)
    run(["usermod", "-aG", ",".join(groups), user])


def add_nopasswd_sudoers(filename: str, user: str, rules: list[str]) -> None:
    """/etc/sudoers.d/<filename>: NOPASSWD for exactly `rules`, validated with visudo - never a blanket rule."""
    require_root("add_nopasswd_sudoers")
    path = Path("/etc/sudoers.d") / filename
    step(f"installing {path}")
    path.write_text(f"{user} ALL=(root) NOPASSWD: " + ", ".join(rules) + "\n")
    path.chmod(0o440)
    run(["visudo", "-c", "-f", str(path)])


# --- apt / venv / udev / systemd ---------------------------------------------

def apt_install(*packages: str) -> None:
    require_root("apt_install")
    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", *packages])


def ensure_venv(venv_dir: Path, requirements: Path, user: str) -> None:
    """venv WITH system site packages: python3-libgpiod (and the other apt python packages) must be visible."""
    venv_dir = Path(venv_dir)
    if (venv_dir / "bin" / "python3").exists():
        print(f"    venv already exists at {venv_dir}")
    else:
        run([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)])
    run([str(venv_dir / "bin" / "pip"), "install", "--upgrade", "pip"], stdout=subprocess.DEVNULL)
    run([str(venv_dir / "bin" / "pip"), "install", "-r", str(requirements)])
    pw = pwd.getpwnam(user)
    run(["chown", "-R", f"{pw.pw_uid}:{pw.pw_gid}", str(venv_dir)])


def write_file(path: str | Path, content: str, mode: int | None = None) -> bool:
    """Write only if changed; returns True if it changed."""
    path = Path(path)
    if path.exists() and path.read_text() == content:
        return False
    step(f"writing {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mode is not None:
        path.chmod(mode)
    return True


def install_udev_rules(path: str, content: str) -> None:
    require_root("install_udev_rules")
    if write_file(path, content):
        run(["udevadm", "control", "--reload-rules"])
        run(["udevadm", "trigger"])


def install_systemd_unit(template: Path, unit_name: str, substitutions: dict, enable_now: bool = False) -> None:
    require_root("install_systemd_unit")
    text = Path(template).read_text()
    for key, value in substitutions.items():
        text = text.replace(f"__{key}__", str(value))
    write_file(Path("/etc/systemd/system") / unit_name, text)
    run(["systemctl", "daemon-reload"])
    if enable_now:
        run(["systemctl", "enable", unit_name])
        run(["systemctl", "restart", unit_name])


# --- fstab ----------------------------------------------------------------------

def ensure_fstab_line(mountpoint: str, line: str) -> bool:
    """Append `line` to /etc/fstab unless an entry for `mountpoint` exists. Returns True if added."""
    fstab = Path("/etc/fstab")
    text = fstab.read_text()
    for existing in text.splitlines():
        parts = existing.split()
        if len(parts) > 1 and not existing.lstrip().startswith("#") and parts[1] == mountpoint:
            print(f"    fstab already has an entry for {mountpoint}")
            return False
    fstab.with_name(f"fstab.bak-{os.getpid()}").write_text(text)
    fstab.write_text(text + ("" if text.endswith("\n") else "\n") + line + "\n")
    print(f"    added to fstab: {line}")
    return True


# --- device-tree overlays: PocketBeagle 2 (extlinux, full dtb tree build) ---------

def compile_and_install_overlay(dtso_path: Path, overlay_name: str, dtb_src_dir: Path | None = None) -> Path:
    """Copy the .dtso into the kernel DTB source tree (/opt/source/dtb-X.Y.x) and build it there - the overlay
    uses the C preprocessor macros (AM62X_IOPAD), so a bare `dtc -@` is not enough. Installs to /boot/firmware/overlays."""
    require_root("compile_and_install_overlay")
    if dtb_src_dir is None:
        release = subprocess.run(["uname", "-r"], capture_output=True, text=True, check=True).stdout
        minor = re.match(r"^(\d+\.\d+)", release).group(1)
        dtb_src_dir = Path(f"/opt/source/dtb-{minor}.x")
    if not Path(dtb_src_dir).is_dir():
        fail(f"DTB source tree not found: {dtb_src_dir} (BeagleBoard images ship it under /opt/source; "
             "adjust the path if your image differs)")
    overlays_src = Path(dtb_src_dir) / "src" / "arm64" / "overlays"
    (overlays_src / f"{overlay_name}.dtso").write_bytes(Path(dtso_path).read_bytes())
    run(["make", f"src/arm64/overlays/{overlay_name}.dtbo"], cwd=dtb_src_dir)
    dest = Path("/boot/firmware/overlays") / f"{overlay_name}.dtbo"
    run(["cp", str(overlays_src / f"{overlay_name}.dtbo"), str(dest)])
    return dest


def wire_overlay_into_extlinux(overlay_name: str, extlinux_conf: str = "/boot/firmware/extlinux/extlinux.conf") -> None:
    """Add `fdtoverlays /overlays/<name>.dtbo` to the default label (or append to an existing fdtoverlays line). Idempotent."""
    conf = Path(extlinux_conf)
    overlay_line = f"/overlays/{overlay_name}.dtbo"
    lines = conf.read_text().splitlines(keepends=True)
    m = re.search(r"^default\s+(.+)$", "".join(lines), re.MULTILINE)
    if not m:
        fail(f"no 'default' line in {conf}")
    label = m.group(1).strip()
    start = next((i for i, l in enumerate(lines) if re.match(r"^label\s+" + re.escape(label) + r"\s*$", l.strip())), None)
    if start is None:
        fail(f"default label {label!r} not found in {conf}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == ""), len(lines))
    block, changed, found = lines[start:end], False, False
    for i, line in enumerate(block):
        s = line.strip()
        if s.startswith("fdtoverlays"):
            found = True
            if overlay_line not in s:
                block[i] = line.rstrip("\n") + " " + overlay_line + "\n"
                changed = True
            break
        if s.startswith("#fdtoverlays"):
            block[i] = f"{line[: len(line) - len(line.lstrip())]}fdtoverlays {overlay_line}\n"
            found = changed = True
            break
    if not found:
        for i, line in enumerate(block):
            if line.strip().startswith("fdtdir"):
                block.insert(i + 1, f"{line[: len(line) - len(line.lstrip())]}fdtoverlays {overlay_line}\n")
                changed = True
                break
        else:
            fail("could not find where to insert fdtoverlays in the label block")
    if changed:
        lines[start:end] = block
        conf.write_text("".join(lines))
        print(f"    updated: label '{label}' now loads {overlay_line}")
    else:
        print(f"    already up to date: label '{label}' loads {overlay_line}")


# --- read-only root -----------------------------------------------------------------

TMPFS_LINES = {
    "/var/tmp": "tmpfs /var/tmp tmpfs defaults,noatime,nosuid,nodev,size=16m 0 0",
    "/var/log": "tmpfs /var/log tmpfs defaults,noatime,nosuid,nodev,size=16m 0 0",
}


def make_root_readonly() -> None:
    """fstab-based read-only root (overlayroot needs an initrd, which this board's U-Boot/extlinux setup can't
    load - see docs/reference/readonly-root-and-storage.md). Takes effect on the next boot."""
    require_root("make_root_readonly")
    step("disabling docker/containerd (hold files open for writing on /)")
    listed = subprocess.run(["systemctl", "list-unit-files", "docker.service"], capture_output=True, text=True).stdout
    if "docker.service" in listed:
        run(["systemctl", "disable", "--now", "docker.service", "docker.socket", "containerd.service"], check=False)
    step("journald: volatile (RAM) storage")
    write_file("/etc/systemd/journald.conf.d/volatile.conf", "[Journal]\nStorage=volatile\n")
    run(["systemctl", "restart", "systemd-journald"])
    for mp, line in TMPFS_LINES.items():
        ensure_fstab_line(mp, line)
    fstab = Path("/etc/fstab")
    out, changed = [], False
    for line in fstab.read_text().splitlines():
        parts = line.split()
        if len(parts) > 3 and not line.lstrip().startswith("#") and parts[1] == "/":
            opts = parts[3].split(",")
            if "ro" not in opts:
                parts[3] = ",".join(opts + ["ro"])
                line, changed = "\t".join(parts), True
        out.append(line)
    if changed:
        fstab.with_name("fstab.bak-before-ro").write_text(fstab.read_text())
        fstab.write_text("\n".join(out) + "\n")
        print("    added 'ro' to the / entry in /etc/fstab (backup: /etc/fstab.bak-before-ro)")
    else:
        print("    / is already 'ro' in /etc/fstab")
    print("    reboot to activate. Recovery: edit /etc/fstab back (e.g. SD card in another machine).")
