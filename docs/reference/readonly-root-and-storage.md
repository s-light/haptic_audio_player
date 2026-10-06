# Read-only root + writable data partition + USB mass storage

Requirement from the README: *the main SD card should be read-only in the final thing so the system is safe
against a hard shut-off.*

## Approach (proven on the sibling light-desk project, PocketBeagle 2)
`overlayroot` needs an initrd, which this board's U-Boot/extlinux setup cannot load reliably (kernel panic
`Failed to execute /init`). So we use the **classic fstab read-only root**:

1. add `ro` to the `/` entry in `/etc/fstab` (the kernel already boots root `ro`; it is
   `systemd-remount-fs` that flips it to rw because fstab lacks the option),
2. `journald` → `Storage=volatile` (RAM only),
3. disable stock-image services that hold files open for writing on `/` (docker/containerd),
4. everything that must be **written at runtime** lives on a **separate data partition** (`LABEL=HAPTIC`,
   mounted at `/srv/haptic`):
   `music/`, `recordings/`, `tags.json`, `config.toml`.
5. volatile state (mpv IPC socket, logs) → `/run` / tmpfs.

`./readwrite.sh` / `./readonly.sh` remount `/` for maintenance. `./setup_pb2.py readonly-root` is deliberately **not**
part of the default run – lock down only after everything else works.

## Data partition
- Label `HAPTIC`, filesystem **vfat** (readable on Windows/macOS/Linux, and exportable as USB mass storage).
  Mounted with `nofail,noatime,flush,uid=…,gid=…` – a missing stick must never block boot.
- Can be a second partition on the SD card, a USB stick, or an SD-card breakout – anything that carries the label.
- FAT is not journaled: the app writes small files atomically (write temp → `fsync` → rename) and runs `sync`
  after uploads/recordings. A hard power cut during a *write* can still lose that file, but never the system.

## USB mass-storage gadget (best case from the README)
The PB2's USB-C port is a device-capable USB controller (`usb0`, peripheral mode in the base DTS).
Exporting a filesystem to a PC while Linux has it mounted read-write corrupts it, so the app uses the
standard **exclusive hand-over**:

```
normal mode : /srv/haptic mounted rw on the player, no gadget
storage mode: player stops, unmounts /srv/haptic, configfs gadget exports the block device
              (`/sys/kernel/config/usb_gadget/haptic/functions/mass_storage.0/lun.0/file`) to the PC
back        : gadget removed, partition mounted again, library rescanned
```
Triggered from the web UI (button "USB-Speicher-Modus") or `sudo haptic-usb-gadget on|off`.
Caveat: while the PC owns the stick the player and web UI on the device are paused (the partition is not
mounted locally). Storage mode is meant for use while the board is connected to a PC.
**Untested on hardware** – the configfs sequence follows the kernel documentation
(`Documentation/usb/gadget_configfs.rst`).
