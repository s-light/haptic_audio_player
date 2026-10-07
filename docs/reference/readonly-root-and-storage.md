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

## Data stick: a USB stick on the PB2's host port
Music, recordings, tags and config live on a **USB stick (FAT32, label `HAPTIC`)** in the PB2's `usb1` host port
(P1.09 D−, P1.11 D+, 5 V from `P1.24`, GND; keep the D± wires short and twisted - see `hw/wiring-diagram.svg`;
check how P1.03 `USB1_DRVVBUS` / P1.05 `USB1_VBUS` are used in the PB2 schematic). Chosen over an SD card because:
- the SD controllers' clock/command/data lines are **not on the P1/P2 headers** (only `MMC2_SDCD/SDWP` are), so a
  4-bit SD breakout cannot be used in 4-bit mode;
- SPI-mode SD (`mmc_spi`, CS1 = P2.36 on the display's SPI0 bus) is fast enough for audio but needs
  `CONFIG_MMC_SPI` in the BeagleBoard kernel (unverified) and more overlay work.

## USB to a computer (network + storage together)
The board is reached through its **USB network gadget** (`bb-usb-gadgets.service`, configfs `g_multi`) - that must
keep working at all times, so the stock gadget is **not replaced**. `haptic-usb-gadget.service` runs
`python -m haptic_player.usbgadget setup` once per boot: it adds a single `mass_storage.haptic` function to the
existing gadget (unbind/rebind once, network back in about a second) with an **empty** removable LUN
("no media"). After that, inserting/ejecting the medium is just writing `lun.0/file` - no unbind, no network flap.

Exclusive hand-over (Linux and the computer must never mount the FAT at the same time):

```
player mode  : /srv/haptic mounted on the board
computer mode: board stops playback, unmounts /srv/haptic, lun.0/file = /dev/sdX1  -> computer sees a USB drive
back         : lun.0/file cleared (forced_eject if the computer still holds it), fsck.vfat -a, mount, rescan
```
`haptic_player/storage.py` decides when:
- a computer is *connected* when `/sys/class/udc/*/state == configured` (a powerbank never enumerates) and stays
  so for `usb.debounce_s` (2 s) -> **automatic switch to computer mode** (config `usb.auto_switch`);
- **back to the player** on: cable unplugged, drive ejected on the computer (kernel clears the medium), or the web UI button;
- when the user switches back while the computer is still connected, it **stays in player mode until the next
  reconnect** (no tug-of-war);
- in computer mode the player ignores tags/buttons, the web API refuses writes (HTTP 409), the display shows "USB";
  the web UI stays reachable over the USB network;
- after coming back the app reloads `tags.json` and rescans the library (the computer may have changed them).

Helper actions run through `sudo -n python -m haptic_player.usbgadget attach|detach` (scoped sudoers rule).
**Untested on hardware** - the configfs sequence follows the kernel docs (`Documentation/usb/gadget_configfs.rst`,
`Documentation/ABI/testing/configfs-usb-gadget-mass-storage`). Things to confirm at bring-up: the stock gadget's
config directory layout, Windows accepting the extra mass-storage interface next to RNDIS/NCM, and the
`configured` state reading.
