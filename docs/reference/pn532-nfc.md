# PN532 NFC/RFID kit – reference

Sources
- Shop page: <https://www.tinytronics.nl/en/communication-and-signals/wireless/rfid/rfid-nfc-kit-pn532-with-s50-card-and-s50-key-tag>
- NXP PN532 datasheet / user manual UM0701-02 (host interface, I²C framing, command set)

## Kit
- PN532 module with **I²C / SPI / HSU (UART)** selection by two DIP switches; 3.3–5 V supply
  (I²C and HSU through a level shifter, SPI is 3.3 V only)
- Supports MIFARE, FeliCa, NTAG …; read distance ≈ 5–7 cm
- Includes one MIFARE Classic (S50) card and one S50 key tag; any ISO14443A tag works for us (we only read the UID)

## Mode used here: I²C
DIP switches: `SEL0 = ON, SEL1 = OFF` for I²C on the common red PN532 boards **(check the silkscreen of *your*
board – it is printed beside the switches)**.

| PN532 pin | PB2 pin | signal |
| :-- | :-- | :-- |
| VCC | P1.14 | VDD_3V3 (supply the module with 3.3 V so the I²C lines are 3.3 V) |
| GND | P1.15 | GND |
| SDA | P1.26 | I2C2_SDA |
| SCL | P1.28 | I2C2_SCL |

I²C address: **0x24** (7-bit; the datasheet's 0x48 is the 8-bit write address). Shares bus `I2C2`
(`/dev/i2c-2`) with the WM8960 (0x1A) – no conflict.

## Protocol we implement (`haptic_player/pn532.py`)
Frame: `00 00 FF LEN LCS TFI DATA… DCS 00`, TFI `D4` host→PN532, `D5` PN532→host; ACK frame
`00 00 FF 00 FF 00`. Over I²C every read returns a leading **status byte** (`bit0 = 1` → ready).

| Command | Code | Use |
| :-- | :-- | :-- |
| GetFirmwareVersion | `0x02` | detect chip |
| SAMConfiguration (normal mode) | `0x14` `01 14 01` | required once after wake-up |
| InListPassiveTarget | `0x4A` `01 00` | poll one ISO14443A tag @106 kbit/s → UID |
| InRelease | `0x52` | release target |

The module does **not** need the IRQ pin; we poll the ready byte.

## Tag handling
- A tag is identified by its **UID** (4, 7 or 10 bytes, hex string, upper case).
- The tag stores nothing; the mapping *UID → album / track / recording slot* is in `tags.json` on the data
  partition (editable in the web UI). That also means a lost tag can simply be replaced.
- Debounce: a tag that stays on the reader is reported once; removal is detected after
  `tag_lost_polls` consecutive empty polls (default 3 × 0.2 s).
