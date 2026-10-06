# What the stock PocketBeagle 2 device tree already does (v6.18.x)

Read from `src-k3-am62-pocketbeagle2-pinmux.dtsi.txt` and `src-k3-am6232-pocketbeagle2.dts.txt` in this folder
(upstream: <https://github.com/beagleboard/BeagleBoard-DeviceTrees>, branch `v6.18.x`). These facts drive
`overlays/k3-am62-pocketbeagle2-haptic-player.dtso`.

| Item | Base DTS state | Consequence for us |
| :-- | :-- | :-- |
| `main_i2c2` (`/dev/i2c-2`) | `okay`, 400 kHz, pinctrl `main_i2c2_pins_default` = **P1.26 SDA / P1.28 SCL** (pads 0xb4/0xb0 mode 1) | WM8960 + PN532 sit here, **no pin-mux needed** |
| `main_i2c1` | enabled but **no pinctrl** → pins never routed | not used in v1 (touch, later) |
| `main_i2c0` | internal (MSPM0 @0x48, EEPROM @0x50) | do not touch |
| `main_spi0` | `okay`, pinctrl: CLK 0x1bc, **D0 output**, D1 input, CS0 0x1b4 | we re-declare the pinctrl with kernel-default direction (D0 = MISO in, **D1 = MOSI out**) and add a `spidev` child |
| `mcasp0/1/2` | not enabled | overlay enables `mcasp0` (P1.02, P1.04, P2.01, P2.03A) |
| `ecap2` | `okay`, claims pad **0x1a4 = P2.01 = MCASP0_ACLKX** | overlay sets `ecap2` to `disabled` (else pin conflict) |
| `main_gpio0` / `main_gpio1` | `pinctrl-0` **commented out** | plain GPIO pads keep reset-default mux (input buffer off) → overlay muxes every GPIO we use (mode 7, pull-up for buttons) |
| `main_uart0`, `main_uart6` | uart0 on P1.30/P1.32 (free), uart6 = console | untouched |
| aliases | `serial*`, `i2c0..3`, `spi0`, `spi2`, `mmc0/1`, `usb0/1` | – |
| `usb0` | peripheral (device) mode | basis for the mass-storage gadget |

## McASP0 header pins (modes from the official table)
| Header pin | Pad | McASP0 function | used as |
| :-- | :-- | :-- | :-- |
| P2.01 | 0x1a4 | `MCASP0_ACLKX` (mode 0) | BCLK (input, codec = master) |
| P1.04 | 0x1a8 | `MCASP0_AFSX` (mode 0) | LRCLK (input) |
| P1.02 | 0x1a0 | `MCASP0_AXR0` (mode 0) | serializer 0 = **TX** → codec DACDAT |
| P2.03A | 0x19c | `MCASP0_AXR1` (mode 0) | serializer 1 = **RX** ← codec ADCDAT |

`P2.03` (MDIO0_MDIO) shares the header pin with `P2.03A` – leave the MDIO pad untouched.
