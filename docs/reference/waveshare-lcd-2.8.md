# Waveshare 2.8" capacitive-touch LCD (ST7789T3 + CST328) – reference

Sources
- Shop: <https://eckstein-shop.de/WaveShare-28inch-LCD-Display-Module-240x320-with-Touch-Panel-ST7789T3-CST328>
- Wiki (pinout): <https://www.waveshare.com/wiki/2.8inch_Capacitive_Touch_LCD>

## Facts
- 240 × 320 px, 262 k colours, driver **ST7789** (write-only SPI, **no MISO**), touch **CST328** (V1 board; V2 = CST3530) via I²C
- Supply 3.3 V / 5 V – **"supply voltage and logic voltage must be the same"** → we supply 3.3 V
- 13-pin header (Raspberry-Pi pin numbers in brackets are what Waveshare documents):

| Module pin | Function | Pi (BCM) | PB2 pin used here |
| :-- | :-- | :-- | :-- |
| VCC | 3.3 V | | P2.23 (VDD_3V3) |
| GND | GND | | P2.15 (GND) |
| MOSI | SPI data in | GPIO10 | P2.25 (SPI0_D1 = MOSI) |
| SCLK | SPI clock | GPIO11 | P2.29 (SPI0_CLK) |
| LCD_CS | chip select | GPIO8 | P2.31 (SPI0_CS0) |
| LCD_DC | data/command | GPIO25 | P2.17 (GPIO0_64) |
| LCD_RST | reset, active low | GPIO27 | P2.18 (GPIO0_53) |
| LCD_BL | backlight | GPIO18 | P2.22 (GPIO0_63) – plain on/off |
| TP_SDA | touch I²C data | GPIO2 | P1.33 (I2C1_SDA) |
| TP_SCL | touch I²C clock | GPIO3 | P1.36A (I2C1_SCL) |
| TP_INT | touch interrupt | GPIO4 | P2.24 (GPIO0_51) |
| TP_RST | touch reset | GPIO17 | P2.28 (GPIO0_61) |

## Touch (wired; driver `haptic_player/cst328.py`, not hooked into the controller yet)
The CST328 usually answers at I²C address 0x1A – **the same address as the WM8960**, so it is on `I2C1`
(`/dev/i2c-1`, P1.33 SDA / P1.36A SCL) instead of `I2C2`. The stock DTS enables `main_i2c1` but never routes its
pins; our overlay does (`haptic_i2c1_pins`). INT (P2.24) and RST (P2.28) are muxed as GPIO as well.
Check first: `i2cdetect -y 1` → `1a`. The display works without touch.
No CircuitPython/Blinka driver exists for the CST328 (and Blinka has no PB2 support), so `cst328.py` talks to
`/dev/i2c-1` directly. Protocol from ESPHome's `cst328` component: 16-bit big-endian registers; reset pulse on RST,
write `0xD101` (debug mode), read `0xD1FC` (firmware CRC must be `0xCACA`), `0xD204` chip/project, `0xD208` firmware,
`0xD1F8` resolution, write `0xD109` (normal mode), sync byte `0xAB` to `0xD000`. A poll reads 27 bytes from `0xD000`
(finger count = low nibble of byte 5; point 0 at offset 0, then 7, 12, …: `id<<4|state, x[11:4], y[11:4],
x[3:0]<<4|y[3:0], pressure`), then writes `0` to `0xD005` and `0xAB` to `0xD000`.

## How we drive it
No kernel framebuffer driver: `haptic_player/display.py` talks to `/dev/spidev0.0` directly (Pillow renders the
frame, numpy converts to RGB565, sent in chunks), DC/RST/BL toggled through libgpiod. Init sequence: SWRESET,
SLPOUT, COLMOD 16-bit, MADCTL (rotation), INVON (this panel needs inversion), DISPON. SPI clock default 32 MHz
(config `display.spi_hz`).
Panel is optional: with `display.enabled = false` (or no spidev) a null display is used.
