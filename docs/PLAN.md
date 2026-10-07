# Implementation plan – haptic audio player

Child-friendly player: put an RFID tag on the reader → the album/song starts. Big buttons for play/pause and
record. Optional display. Web UI for configuration and uploads. Root filesystem read-only (hard-shut-off safe).

Reference material (all fetched into `docs/reference/`): PocketBeagle 2 pin table, stock device-tree findings,
Voice Bonnet, PN532, Waveshare LCD, read-only/USB-gadget notes, software-stack notes.

## 1. Decisions

| Topic | Decision | Reason |
| :-- | :-- | :-- |
| Language | **Python 3 / asyncio** for the device, **Quasar CLI (Vue 3, TypeScript, Pinia)** for the web UI | README preference; Blinka/CircuitPython does not support the PB2 → use plain Linux APIs (see `reference/software-stack.md`). Node was considered, rejected: all hardware libs/projects here are Python. |
| Audio out/in | WM8960 on the Voice Bonnet via McASP0 (I²S), ALSA card `haptic` | bonnet is a Pi HAT → **wired by jumper wires**, there is no 40-pin socket on the PB2 |
| Playback | `mpv` over JSON IPC | formats, gapless, position/duration |
| Recording | `arecord` → WAV, one new file per recording, never overwrites | child safety: nothing recorded is ever lost by accident |
| NFC | PN532 on I²C2 (0x24), polled, own minimal driver | no Blinka |
| Tag mapping | `tags.json` (UID → album/track/record-slot) | tags hold no data, replaceable |
| Display | ST7789 over spidev, rendered with Pillow; optional | |
| Touch (CST328) | wired/reserved, **not implemented in v1** | address clash with WM8960 (0x1A) → needs I2C1 |
| Storage | root **read-only**; data on a **USB stick** (FAT32, `LABEL=HAPTIC`) in the PB2's usb1 host port, mounted at `/srv/haptic` | README requirement; simplest, no SPI/kernel risk (4-bit SD is not on the headers) |
| USB to a computer | the board's USB **network gadget stays** (web UI is reached through it); one mass-storage function is added; when a computer enumerates the gadget it automatically gets the stick, the player pauses; switch back in the UI / eject / unplug | "best case" item; exclusive hand-over, never both at once |

## 2. Hardware / pin plan (details + diagram: `hw/wiring-diagram.svg`, generator `hw/generate-wiring-diagram.py`)

| Function | PB2 pin(s) | Notes |
| :-- | :-- | :-- |
| I²C2 SDA / SCL | P1.26 / P1.28 | already muxed by stock DTS; WM8960 0x1A + PN532 0x24 |
| I²S BCLK / LRCLK | P2.01 / P1.04 | McASP0 ACLKX / AFSX (codec is master) |
| I²S DAC data (→codec) / ADC data (←codec) | P1.02 / P2.03A | McASP0 AXR0 (TX) / AXR1 (RX) |
| Bonnet 5 V / 3V3 / GND | P1.24 / P1.14 / P1.15 | |
| PN532 3V3 / GND | P1.14 / P1.15 | I²C mode, DIP switches |
| Display SPI MOSI / SCLK / CS | P2.25 / P2.29 / P2.31 | SPI0, `/dev/spidev0.0` |
| Display DC / RST / BL | P2.17 / P2.18 / P2.22 | GPIO0_64 / 0_53 / 0_63 |
| Touch INT / RST (reserved) | P2.24 / P2.28 | |
| Display 3V3 / GND | P2.23 / P2.15 | |
| Buttons: play-pause, record, prev, next | P2.02, P2.04, P2.06, P2.08 | to GND, internal pull-up; long-press play-pause = stop |
| On/off button | P2.12 (PWR.BTN) → GND | PMIC power button |
| Power | USB-C powerbank | |

## 3. Device-tree overlay (`overlays/k3-am62-pocketbeagle2-haptic-player.dtso`)
Single overlay: McASP0 pinmux + enable, WM8960 codec node on `main_i2c2`, fixed-clock `haptic_mclk` (24 MHz),
`simple-audio-card` "haptic" (codec = clock master, I²S, shared LRCLK), `ecap2` disabled (pin clash on P2.01),
SPI0 re-declared + `spidev` child, GPIO pads (buttons pull-up, display control) muxed to mode 7.
Reasoning for every line: `reference/devicetree-base-findings.md`. **Written from the DTS sources, not yet booted.**

## 4. Software architecture (`haptic_player/`)

```
inputs                    core (asyncio)                         outputs
 PN532 poller (thread) ─┐                                    ┌─ mpv (IPC)          audio
 GPIO buttons (thread) ─┼─▶ Controller (state machine) ──────┼─ arecord            recording
 web API / WebSocket   ─┘      │   │   │                     ├─ ST7789 renderer     display
                               │   │   └ TagStore (tags.json) └─ WebSocket push     web UI
                               │   └ Library (music/ scan)
                               └ Recorder (recordings/slot-NN/)
```
Modules: `config` · `library` · `tags` · `pn532` · `nfc` · `buttons` · `gpio` · `player` · `recorder` · `audio` ·
`display` · `controller` · `web` · `usbgadget` · `__main__` (`--simulate` runs without any hardware).

### Behaviour
- **Tag scanned** (known): `album`/`track` → play from the start; `record` slot N → select recording slot N
  (display/web show it; LED-less feedback via display + short confirmation beep optional later).
- **Unknown tag**: ignored for playback, shown as "last scanned" in the web UI (one click to assign); web UI
  "learn" mode assigns the next scanned tag to the chosen target.
- **Tag removed**: configurable `none` (default) / `pause` / `stop`.
- **Play/pause button**: toggle; if idle replays the last item; long-press = stop.
- **Record button**: needs a selected slot → start recording; again → stop & save. While recording, playback is paused.
  The slot is played by scanning the same record tag (plays all its recordings, newest last).
- **prev/next**: track skip (long-press = volume down/up).
- Volume persisted in `config.toml` (data partition).

### Data partition layout (`/srv/haptic`)
```
music/<Album>/01 Title.mp3 …   music/Single.mp3        (cover: cover.jpg|folder.jpg|embedded)
recordings/slot-01/rec-20261004-101530.wav …
tags.json      config.toml
```

## 5. Web UI (Quasar)
Pages: **Player** (now playing, controls, volume, slot), **Library** (albums, drag-and-drop upload, assign tag),
**Tags** (assigned tags, learn mode, record slots), **Recordings** (play/delete), **System** (settings, storage
mode, safe shutdown). Realtime state through `/ws`. REST under `/api/*`.

## 6. Setup script (`setup_pb2.py`, modelled on light-desk's `setup_pb2.py`, helpers in `haptic_setup.py`)
Steps (idempotent, `./setup_pb2.py [STEP]`, `--list-steps`; re-execs itself via sudo once):
`packages` → `sudoers` → `venv` → `datadir` (fstab entry for `LABEL=HAPTIC`, dirs) → `overlay` (compile, install,
wire into extlinux; asks for reboot) → `webui` (pnpm build, or `webui/deploy.sh` from a PC) → `service` (systemd unit) → `udev` (i2c/spidev/gpio
groups, usb gadget helper) → *opt-in:* `usb-gadget`, `readonly-root` (**last**, never in the default run).

## 7. Work packages & status
1. Docs + references ✔
2. Overlay ✔ (untested on hardware)
3. Core python modules + unit tests ✔
4. Web backend + web UI ✔ (UI built with `pnpm build`)
5. Setup script + systemd + read-only tooling ✔
6. Wiring diagram ✔
7. **Bring-up on hardware – open** (checklist in `docs/BRING-UP.md`)

## 8. Risks
1. Overlay never booted on a PB2 (codec clock = 24 MHz assumption, McASP slave-mode details).
2. SPI0 MOSI direction (D1 vs D0) – display test tool `python -m haptic_player.display --test` tells quickly.
3. 5 V rail current for the bonnet's amplifier.
4. FAT data partition + hard power cut during a write.
5. PWR.BTN behaviour when powered from USB-C only.
