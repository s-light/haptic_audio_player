# haptic_audio_player

simple child-friendly haptic audio player

## HW

-   [PocketBeagle2](https://docs.beagle.cc/boards/pocketbeagle-2)
-   [Adafruit Voice Bonnet](https://learn.adafruit.com/adafruit-voice-bonnet/overview)
-   [RFID NFC Kit PN532](https://www.tinytronics.nl/en/communication-and-signals/wireless/rfid/rfid-nfc-kit-pn532-with-s50-card-and-s50-key-tag)
-   USB-Memory Stick or SD-Card Breakout for music and config storage
-   [WaveShare 2.8inch LCD Display Module 240x320 with Touch Panel (ST7789T3 + CST328)](https://eckstein-shop.de/WaveShare-28inch-LCD-Display-Module-240x320-with-Touch-Panel-ST7789T3-CST328) (optional)
-   some haptic push buttons for play-pause / record
-   on-off power button
-   USB-Powerbank for powering

## Functionality

-   the RFID-Tag select song or album
-   there are special tags that select _recording_ slot
-   buttons for start / stop of the playback / recording
-   Display shows runtime and song title / cover-art
-   webUI for configuration
-   drag and drop the songs albums via the WEB-UI or just copy them to the sd-card.
-   best case: sd-card is also available as USB-Masstorage via the PB2 USB-Gadget interface

## implementation

-   webUI
    VUE / quasar based
-   managing / playing
    all that is easy possible in circuitpython
-   setup in python.
-   maybe if you think it does not make sens to do all this in python lets do it in js (node-js) so all is the same langauge..
-   the main sd-card should be readonly in the final thing - so that the system is safe for hard-shut-off

## Status / quick start

Implemented (see [docs/PLAN.md](docs/PLAN.md)); **not yet tested on real hardware** → [docs/BRING-UP.md](docs/BRING-UP.md).

-   wiring: [hw/wiring-diagram.svg](hw/wiring-diagram.svg) (`python3 hw/generate-wiring-diagram.py`)
-   reference material: [docs/reference/](docs/reference/)
-   on the PocketBeagle 2: `./setup_pb2.py` (steps: `--list-steps`; `readonly-root` last, opt-in)
-   data partition `LABEL=HAPTIC` (FAT) → `music/`, `recordings/`, `tags.json`, `config.toml` ([config.example.toml](config.example.toml))
-   try it on a PC without hardware:
    ```
    python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
    (cd webui && pnpm install && pnpm build)    # -> webui/dist/spa; dev: pnpm dev
    .venv/bin/python -m haptic_player --simulate --data-dir /tmp/haptic    # http://localhost:8080
    .venv/bin/pytest
    ```

