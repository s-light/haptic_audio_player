# Hardware bring-up checklist

Nothing in this repo has run on a real PocketBeagle 2 yet (it was developed against the official DTS/pin tables,
the Voice Bonnet schematic and unit tests). Go through this list top to bottom; each item says what to look at if
it fails. Do it **before** `./setup_pb2.py readonly-root`.

0. **Wire** everything per `hw/wiring-diagram.svg`. Voice Bonnet privacy switch **ON**. Check 3.3 V vs 5 V twice.
1. `./setup_pb2.py` (stops after `overlay` asking for a reboot) → reboot → `./setup_pb2.py` again.
   - overlay build error → check `/opt/source/dtb-*/` exists; compare label names (`mcasp0`, `main_i2c2`, `main_gpio0`, `ecap2`,
     `main_spi0`) with the base DTB: `dtc -I dtb -O dts /boot/firmware/ti/k3-am6232-pocketbeagle2.dtb | grep -n "mcasp0\|ecap2"`.
2. **I²C**: `i2cdetect -y 2` → `1a` (WM8960) and `24` (PN532).
   Nothing at all → pull-ups (add 4.7 kΩ to 3V3 on SDA/SCL), wiring, `dmesg | grep i2c`.
3. **Audio card**: `cat /proc/asound/cards` shows `haptic`; `dmesg | grep -i "wm8960\|mcasp\|haptic"`.
   - no card → codec probe failed (I²C, wrong DT label) or McASP pin conflict (`dmesg | grep -i pinctrl`, `ecap2` must be disabled).
   - card, but silent → privacy switch, oscillator frequency (`haptic_mclk` in the overlay), mixer: `amixer -c haptic scontents`.
   - `speaker-test -D plughw:CARD=haptic -c2 -t sine -l 1` ; record: `arecord -D plughw:CARD=haptic -f S16_LE -r 44100 -c1 -d 3 t.wav && aplay t.wav`.
4. **NFC**: `sudo -u $USER .venv/bin/python - <<<'from haptic_player.pn532 import *; p=PN532(I2CTransport(2,0x24)); print(p.setup()); print(p.read_uid())'`
   → firmware tuple, then a UID with a tag on the reader. `journalctl -u haptic-player` shows `NFC reader ready`.
5. **Buttons**: `gpioget`/`gpiomon` on `GPIO0_45..48` (chip label `600000.gpio`, lines 45–48): pressed = low.
   Not toggling → pad mux (`/sys/kernel/debug/pinctrl/*/pinmux-pins`), the overlay's `main_gpio0` pinctrl hook.
6. **Display**: `ls /dev/spidev0.0`; `.venv/bin/python -m haptic_player.display --test`
   (colour bars, then the sample screen). Black/noise → MOSI direction: the overlay assumes D1 = MOSI (P2.25); if
   your kernel's McSPI is configured the other way, wire MOSI to P2.27 (SPI0_D0) instead. Colours inverted → `invert = false`.
7. **Player**: open `http://<board>:8080`, upload an album (drag & drop), assign a tag via "Tag zuweisen", lay it on the reader.
8. **Recording**: assign an "Aufnahme-Slot" tag, lay it on, press record, speak, press again → file under `recordings/slot-NN/`.
9. **Hard-shut-off test** (after `readonly-root` + reboot): pull the power while playing, boot again → everything still works,
   `mount | grep ' / '` shows `ro`.
10. **Data stick + USB to a computer**: stick (FAT32, label `HAPTIC`) in the host port → `lsblk -f`, `mount | grep haptic`.
    `systemctl status haptic-usb-gadget` ok; `.venv/bin/python -m haptic_player.usbgadget status` → `"function": true`;
    the USB network still works (`ping 192.168.7.1`/web UI). Connect to a PC: `cat /sys/class/udc/*/state` → `configured`,
    after ~2 s the PC shows a drive with your music, the display shows "USB", the web UI banner appears (still reachable).
    Eject on the PC → the player is back, no auto re-attach until you replug. Web UI "Zurück zum Player" while connected → stays player.
    Problems: no `mass_storage.haptic` dir → `setup` error (look at `/sys/kernel/config/usb_gadget/*`); Windows ignores the drive → check
    interface/IAD descriptors of the composite gadget.

Known assumptions to confirm: oscillator frequency (24 MHz), codec as I²S master working with McASP0 in slave mode,
5 V from `P1.24` is enough for the bonnet amplifier, `PWR.BTN` usable with USB-C power only.
