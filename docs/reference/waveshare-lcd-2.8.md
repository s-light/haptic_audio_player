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
| TP_SDA | touch I²C data | GPIO2 | *reserved – see below* |
| TP_SCL | touch I²C clock | GPIO3 | *reserved* |
| TP_INT | touch interrupt | GPIO4 | P2.24 (GPIO0_51) – wired, unused in v1 |
| TP_RST | touch reset | GPIO17 | P2.28 (GPIO0_61) – wired, unused in v1 |

## Touch (not implemented in v1)
The CST328 usually answers at I²C address 0x1A – **the same address as the WM8960**, so it must **not** be put on
`I2C2`. The planned home is `I2C1` (P1.33 SDA / P1.36A SCL, needs a pin-mux overlay, see the sibling
light-desk project's `k3-am62-pocketbeagle2-light-desk-i2c1-adc.dtso`). In v1 the touch pins are only
documented; the display works without them.

## How we drive it
No kernel framebuffer driver: `haptic_player/display.py` talks to `/dev/spidev0.0` directly (Pillow renders the
frame, numpy converts to RGB565, sent in chunks), DC/RST/BL toggled through libgpiod. Init sequence: SWRESET,
SLPOUT, COLMOD 16-bit, MADCTL (rotation), INVON (this panel needs inversion), DISPON. SPI clock default 32 MHz
(config `display.spi_hz`).
Panel is optional: with `display.enabled = false` (or no spidev) a null display is used.
