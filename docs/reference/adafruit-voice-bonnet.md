# Adafruit Voice Bonnet (WM8960) – reference

Sources
- Guide: <https://learn.adafruit.com/adafruit-voice-bonnet/overview> and `/pinouts`
- Schematic (EAGLE): <https://github.com/adafruit/Adafruit-Voice-Bonnet-PCB> (`Adafruit Voice Bonnet.sch`, netlist read 2026-10-04)
- WM8960 datasheet: <https://cdn-learn.adafruit.com/assets/assets/000/096/503/original/WM8960_v4.4.pdf>

The bonnet is a **Raspberry Pi 40-pin HAT**. The PocketBeagle 2 has two 2×18 headers, so the bonnet
**cannot be plugged in** – it is wired with jumper wires to the pads of its 2×20 header (see
`hw/wiring-diagram.svg`).

## What it has
- WM8960 stereo codec, I²S for playback *and* capture
- 2× 1 W class-D speaker outputs (JST-PH), 3.5 mm headphone/line-out jack, 2× MEMS microphones
- 1 push button (GPIO17, 10 k pull-up to 3.3 V, reads LOW when pressed)
- 3× DotStar RGB LEDs (data GPIO5, clock GPIO6)
- STEMMA QT I²C connector, 3-pin JST on GPIO12
- DPDT slide switch ("privacy switch"): **it gates the codec's master-clock oscillator** (net `MCLK_EN`
  → `OSC1.INH`) – **the switch must be in the ON position or the codec has no clock and there is no audio**.

## Signals used from the 2×20 header (derived from the schematic netlist)

| Pi header pin | Pi name | Net | Direction (relative to host) | Notes |
| :-- | :-- | :-- | :-- | :-- |
| 2, 4 | 5V | 5.0V | power in | powers the class-D amplifier (U3 regulator) |
| 1 (and 17) | 3V3 | 3.3V | power in | **needed**: codec digital supply, MCLK oscillator VCC, button pull-up |
| 6, 9, 14, … | GND | GND | | |
| 3 | GPIO2 / SDA | SDA | bidir | WM8960 control, I²C address **0x1A** (fixed) |
| 5 | GPIO3 / SCL | SCL | in | |
| 12 | GPIO18 | I2S_BCLK | codec ↔ host | |
| 35 | GPIO19 | I2S_LRCLK | codec ↔ host | ADCLRC and DACLRC are tied together → DT: `wlf,shared-lrclk` |
| 38 | GPIO20 | I2S_DIN | codec → host | ADC data (microphones) |
| 40 | GPIO21 | I2S_DOUT | host → codec | DAC data (speaker/headphone) |
| 11 | GPIO17 | BUTTON | out | optional extra button (not used by this project) |
| 29 / 31 | GPIO5/GPIO6 | LEDD/LEDC | in | DotStars, not used |

Everything else on the header is unconnected for our purposes.

## Clocking
- `MCLK` comes from an on-board oscillator `OSC1` (ECS-3225MV, 3.2×2.5 mm). The **frequency is not stated in
  the schematic text** – read it off the part marking or measure it. The overlay assumes **24 MHz** (`haptic_mclk`,
  property `clock-frequency`); change it if different. The Linux `wm8960` driver configures its PLL from the
  MCLK rate.
- The overlay makes the **codec the I²S clock master** (it generates BCLK + LRCLK from MCLK); the AM62x McASP
  runs as clock slave. Simplest, and avoids needing a McASP AUXCLK.

## Mixer
Typical ALSA controls on the WM8960 (names from the mainline driver): `Playback`, `Speaker`, `Headphone`,
`Capture`, `Left/Right Input Mixer Boost`, `Left/Right Output Mixer PCM`. The routing switches
(`Left Output Mixer PCM Playback Switch`, …) default to **off** – the app sets them at start
(`haptic_player/audio.py`), because the root filesystem is read-only and `alsactl store` cannot persist them.

## Open points (verify at bring-up)
1. Oscillator frequency (see above).
2. Whether the 3.3 V from a PB2 pin (P1.14) is enough for the bonnet's 3V3 rail: bonnet draws only a few mA there.
3. 5 V amplifier current at loud volume (~0.4 A worst case for 2×1 W). Powering the bonnet's 5 V from the
   PB2 `VOUT` pin (P1.24) is convenient but its current rating is not documented – if the board resets when
   the volume is high, feed the bonnet 5 V from the USB powerbank directly (common GND!).
