#!/usr/bin/env python3
"""Generate wiring-diagram.svg - how to wire the haptic audio player's parts to the PocketBeagle 2 headers.

Usage:
    python3 hw/generate-wiring-diagram.py      # writes hw/wiring-diagram.svg next to this script (stdlib only)

Layout (same dark look as the sibling light-desk pinout diagram, but with real wires): the PocketBeagle 2 in
the middle lists every header pin this project uses; the Voice Bonnet + PN532 (I2C) sit on the left, the
display, buttons and power button on the right. Each peripheral pin row sits at the same height as its
PocketBeagle pin, so the primary wire is straight; pins shared by several parts (3V3, GND, I2C2) fan out with
curves. A schematic header strip at the bottom shows where the used pins are on P1/P2.

The data below is the single source of truth for the wiring and must match docs/PLAN.md section 2,
overlays/k3-am62-pocketbeagle2-haptic-player.dtso and haptic_player/config.py (pin defaults).
Pin functions come from docs/reference/pocketbeagle2-pinout.md (official BeagleBoard.org table).
"""

from pathlib import Path

# ---- palette ----------------------------------------------------------------
BG, PANEL, STROKE = "#0b0d12", "#1f2430", "#3b4252"
TEXT, SUB, FAINT = "#e5e7eb", "#9aa3b2", "#5b6472"
GROUPS = {
    "i2s": ("#c084fc", None, "I2S audio (McASP0)"),
    "i2c": ("#22d3ee", None, "I2C2 (codec 0x1A, PN532 0x24)"),
    "spi": ("#fb923c", None, "SPI0 to display"),
    "lcd": ("#facc15", None, "display control GPIO"),
    "btn": ("#a3e635", None, "buttons (to GND, internal pull-up)"),
    "usb": ("#60a5fa", None, "USB host (usb1) - data stick"),
    "v33": ("#dc2626", None, "3.3 V"),
    "v5": ("#ec4899", "7,5", "5 V (dashed - check before wiring)"),
    "gnd": ("#6b7280", None, "GND"),
    "misc": ("#9ca3af", None, "power button / reserved"),
}

# PocketBeagle pins used: id -> (header pin, function, group)
PB = {
    "bclk": ("P2.01", "MCASP0_ACLKX  BCLK", "i2s"),
    "lrclk": ("P1.04", "MCASP0_AFSX  LRCLK", "i2s"),
    "dac": ("P1.02", "MCASP0_AXR0  DAC data", "i2s"),
    "adc": ("P2.03A", "MCASP0_AXR1  ADC data", "i2s"),
    "v5": ("P1.24", "VOUT 5 V", "v5"),
    "v33a": ("P1.14", "VDD_3V3", "v33"),
    "gnda": ("P1.15", "GND", "gnd"),
    "sda": ("P1.26", "I2C2_SDA", "i2c"),
    "scl": ("P1.28", "I2C2_SCL", "i2c"),
    "v33b": ("P2.23", "VDD_3V3", "v33"),
    "gndb": ("P2.15", "GND", "gnd"),
    "mosi": ("P2.25", "SPI0_D1  MOSI", "spi"),
    "sclk": ("P2.29", "SPI0_CLK", "spi"),
    "cs": ("P2.31", "SPI0_CS0", "spi"),
    "dc": ("P2.17", "GPIO0_64  DC", "lcd"),
    "rst": ("P2.18", "GPIO0_53  RST", "lcd"),
    "bl": ("P2.22", "GPIO0_63  BL", "lcd"),
    "tint": ("P2.24", "GPIO0_51  TP_INT", "lcd"),
    "trst": ("P2.28", "GPIO0_61  TP_RST", "lcd"),
    "b1": ("P2.02", "GPIO0_45  play/pause", "btn"),
    "b2": ("P2.04", "GPIO0_46  record", "btn"),
    "b3": ("P2.06", "GPIO0_47  prev", "btn"),
    "b4": ("P2.08", "GPIO0_48  next", "btn"),
    "pwr": ("P2.12", "PWR.BTN", "misc"),
    "usbm": ("P1.09", "USB1.D-", "usb"),
    "usbp": ("P1.11", "USB1.D+", "usb"),
}

# peripherals: side = where the box sits relative to the PocketBeagle.
# pins: (label on the peripheral, pb pin id, optional wire group override)
BOXES = [
    dict(side="L", title="Adafruit Voice Bonnet", sub="WM8960 codec - Raspberry Pi HAT, wired by jumpers",
         pins=[("GPIO18  BCLK   (pin 12)", "bclk"), ("GPIO19  LRCLK  (pin 35)", "lrclk"),
               ("GPIO21  DOUT -> DAC  (pin 40)", "dac"), ("GPIO20  DIN <- ADC  (pin 38)", "adc"),
               ("5V  (pin 2/4)", "v5"), ("3V3  (pin 1)", "v33a"), ("GND  (pin 6)", "gnda"),
               ("SDA  (pin 3)", "sda"), ("SCL  (pin 5)", "scl")],
         notes=["privacy switch must be ON - it gates the codec's MCLK oscillator",
                "speakers: JST-PH L/R  -  headphones: 3.5 mm jack",
                "I2C address 0x1A"]),
    dict(side="L", title="PN532 NFC kit (I2C mode)", sub="DIP switches: I2C (check silkscreen)",
         pins=[("VCC (3.3 V)", "v33a"), ("GND", "gnda"), ("SDA", "sda"), ("SCL", "scl")],
         notes=["I2C address 0x24 - shares I2C2 with the codec", "IRQ / RSTO not connected (polled)"]),
    dict(side="L", title="USB-A socket (data stick)", sub="usb1 host - music, recordings, tags, config",
         pins=[("VBUS 5 V", "v5"), ("D-", "usbm"), ("D+", "usbp"), ("GND", "gnda")],
         notes=["stick = FAT32, label HAPTIC (plugs into the PB2's usb1 host)",
                "keep D+/D- short and twisted; stick draws up to ~100-500 mA",
                "check P1.03 / P1.05 (DRVVBUS / VBUS) against the PB2 schematic"]),
    dict(side="R", title="Waveshare 2.8\" LCD (ST7789 + CST328)", sub="optional - 240x320, 3.3 V logic",
         pins=[("VCC (3.3 V)", "v33b"), ("GND", "gndb"), ("MOSI", "mosi"), ("SCLK", "sclk"), ("LCD_CS", "cs"),
               ("LCD_DC", "dc"), ("LCD_RST", "rst"), ("LCD_BL", "bl"), ("TP_INT", "tint"), ("TP_RST", "trst")],
         notes=["TP_SDA / TP_SCL: not connected (v1). The CST328 sits at",
                "0x1A like the codec -> needs its own bus (I2C1);",
                "touch is not implemented yet"]),
    dict(side="R", title="Push buttons (4x)", sub="one leg to the pin, other leg to GND",
         pins=[("play / pause  (long: stop)", "b1"), ("record  (start / stop)", "b2"),
               ("prev  (long: volume -)", "b3"), ("next  (long: volume +)", "b4")],
         notes=["other leg of every button -> GND (P2.15)"], gnd_note=True),
    dict(side="R", title="On/off button", sub="to GND = PMIC power button",
         pins=[("one leg", "pwr")], notes=["other leg -> GND  (verify PWR.BTN behaviour on USB-C power)"]),
]

ROW = 32
BOX_W = 440
PB_W = 520
GAP = 250
LEFT_X = 40
PB_X = LEFT_X + BOX_W + GAP
RIGHT_X = PB_X + PB_W + GAP
W = RIGHT_X + BOX_W + 40


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wire_style(group):
    color, dash, _ = GROUPS[group]
    return color, (f' stroke-dasharray="{dash}"' if dash else ""), (4 if group in ("v5", "v33", "gnd") else 3)


def main():
    out = []
    put = out.append

    # --- lay out boxes: each side stacks its boxes top to bottom ---------------
    ys = {"L": 150, "R": 150}
    placed = []  # (box, x, y_top, [pin y])
    for b in BOXES:
        x = LEFT_X if b["side"] == "L" else RIGHT_X
        y = ys[b["side"]]
        head = 62
        pin_ys = [y + head + i * ROW + ROW // 2 for i in range(len(b["pins"]))]
        h = head + len(b["pins"]) * ROW + 12 + (22 if b.get("gnd_note") else 0) + len(b["notes"]) * 19 + 14
        placed.append((b, x, y, h, pin_ys))
        ys[b["side"]] = y + h + 34

    # PocketBeagle pin positions: y of the first peripheral pin using it
    pb_side, pb_y = {}, {}
    for b, x, y, h, pin_ys in placed:
        for (label, pid), py in zip(b["pins"], pin_ys):
            if pid not in pb_y:
                pb_y[pid], pb_side[pid] = py, b["side"]
    # keep PB rows from overlapping when two different pins would sit at nearly the same height on one side
    for side in "LR":
        ids = sorted((p for p in pb_y if pb_side[p] == side), key=lambda p: pb_y[p])
        for a, b2 in zip(ids, ids[1:]):
            if pb_y[b2] - pb_y[a] < 26:
                pb_y[b2] = pb_y[a] + 26

    top = 150
    bottom = max(ys["L"], ys["R"])
    strip_y = bottom + 20
    H = strip_y + 330

    put(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Helvetica, Arial, sans-serif">')
    put(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    put(f'<text x="{W/2}" y="46" text-anchor="middle" font-size="30" font-weight="700" fill="{TEXT}">haptic_audio_player – wiring (PocketBeagle 2)</text>')
    put(f'<text x="{W/2}" y="76" text-anchor="middle" font-size="16" fill="{SUB}">all signals 3.3 V · pin functions from the official PB2 pin table · generated by hw/generate-wiring-diagram.py</text>')
    put(f'<text x="{W/2}" y="102" text-anchor="middle" font-size="15" fill="{GROUPS["v5"][0]}">The Voice Bonnet is a Raspberry-Pi HAT: it has a 40-pin socket, the PocketBeagle 2 does not – connect the pads with jumper wires.</text>')

    # --- PocketBeagle box ------------------------------------------------------
    pb_top = top - 20
    pb_bot = bottom - 14
    put(f'<rect x="{PB_X}" y="{pb_top}" width="{PB_W}" height="{pb_bot-pb_top}" rx="22" fill="{PANEL}" stroke="{STROKE}" stroke-width="3"/>')
    put(f'<text x="{PB_X+PB_W/2}" y="{pb_top+38}" text-anchor="middle" font-size="24" font-weight="700" fill="{TEXT}">PocketBeagle 2</text>')
    put(f'<text x="{PB_X+PB_W/2}" y="{pb_top+60}" text-anchor="middle" font-size="14" fill="{SUB}">AM6232 · P1 / P2 headers (used pins only)</text>')
    put(f'<rect x="{PB_X+PB_W/2-60}" y="{(pb_top+pb_bot)/2-30}" width="120" height="60" rx="8" fill="#111318" stroke="{FAINT}" stroke-width="2"/>')
    put(f'<text x="{PB_X+PB_W/2}" y="{(pb_top+pb_bot)/2+5}" text-anchor="middle" font-size="15" fill="{SUB}">AM6232</text>')
    ux = PB_X + PB_W / 2
    put(f'<rect x="{ux-34}" y="{pb_bot-8}" width="68" height="16" rx="4" fill="#c7cdd6" stroke="#4b5563" stroke-width="2"/>')
    put(f'<text x="{ux}" y="{pb_bot+32}" text-anchor="middle" font-size="14" fill="{TEXT}">USB-C  ←  USB powerbank (5 V)</text>')

    # --- wires first (under the boxes' text) -----------------------------------
    for b, x, y, h, pin_ys in placed:
        for (label, pid), py in zip(b["pins"], pin_ys):
            group = PB[pid][2]
            color, dash, sw = wire_style(group)
            if b["side"] == "L":
                x1, x2 = PB_X, x + BOX_W
            else:
                x1, x2 = PB_X + PB_W, x
            y1 = pb_y[pid]
            mid = (x1 + x2) / 2
            put(f'<path d="M{x1},{y1} C{mid},{y1} {mid},{py} {x2},{py}" fill="none" stroke="{color}" stroke-width="{sw}"{dash}/>')

    # --- peripheral boxes --------------------------------------------------------
    for b, x, y, h, pin_ys in placed:
        put(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{h}" rx="12" fill="{PANEL}" stroke="{STROKE}" stroke-width="2"/>')
        put(f'<text x="{x+16}" y="{y+28}" font-size="18" font-weight="700" fill="{TEXT}">{esc(b["title"])}</text>')
        put(f'<text x="{x+16}" y="{y+48}" font-size="13" fill="{SUB}">{esc(b["sub"])}</text>')
        for (label, pid), py in zip(b["pins"], pin_ys):
            color, _, _ = wire_style(PB[pid][2])
            ex = x + BOX_W if b["side"] == "L" else x
            put(f'<circle cx="{ex}" cy="{py}" r="7" fill="{color}" stroke="#05060a" stroke-width="1.5"/>')
            if b["side"] == "L":
                put(f'<text x="{ex-18}" y="{py+5}" text-anchor="end" font-size="15" fill="{TEXT}">{esc(label)}</text>')
            else:
                put(f'<text x="{ex+18}" y="{py+5}" font-size="15" fill="{TEXT}">{esc(label)}</text>')
        ny = pin_ys[-1] + ROW // 2 + 8
        if b.get("gnd_note"):
            ny += 6
        for note in b["notes"]:
            put(f'<text x="{x+16}" y="{ny+8}" font-size="13" fill="{SUB}">{esc(note)}</text>')
            ny += 19

    # --- PocketBeagle pin labels (on top of wires) ------------------------------
    for pid, (hdr, func, group) in PB.items():
        if pid not in pb_y:
            continue
        color, _, _ = wire_style(group)
        y = pb_y[pid]
        if pb_side[pid] == "L":
            put(f'<circle cx="{PB_X}" cy="{y}" r="8" fill="{color}" stroke="#05060a" stroke-width="1.5"/>')
            put(f'<text x="{PB_X+18}" y="{y+5}" font-size="15" fill="{TEXT}"><tspan font-weight="700">{hdr}</tspan><tspan fill="{SUB}" dx="8">{esc(func)}</tspan></text>')
        else:
            put(f'<circle cx="{PB_X+PB_W}" cy="{y}" r="8" fill="{color}" stroke="#05060a" stroke-width="1.5"/>')
            put(f'<text x="{PB_X+PB_W-18}" y="{y+5}" text-anchor="end" font-size="15" fill="{TEXT}"><tspan fill="{SUB}">{esc(func)}</tspan><tspan font-weight="700" dx="8">{hdr}</tspan></text>')

    # --- schematic header strips ---------------------------------------------------
    used = {PB[p][0] for p in pb_y}
    gcol = {PB[p][0]: PB[p][2] for p in pb_y}
    sx0, sw_ = LEFT_X + 60, W - 2 * (LEFT_X + 60)
    put(f'<text x="{LEFT_X}" y="{strip_y+20}" font-size="20" font-weight="700" fill="{TEXT}">Where the used pins are on the headers</text>')
    put(f'<text x="{LEFT_X}" y="{strip_y+42}" font-size="13" fill="{SUB}">schematic strips (odd pins top row, even pins bottom row, not to scale) – always check pin 1 / numbering against the board silkscreen</text>')
    col = lambda n: sx0 + (n - 1) // 2 * (sw_ / 17)
    for hi, hdr in enumerate(("P1", "P2")):
        y0 = strip_y + 90 + hi * 120
        put(f'<text x="{LEFT_X}" y="{y0+24}" font-size="20" font-weight="700" fill="{TEXT}">{hdr}</text>')
        put(f'<rect x="{sx0-22}" y="{y0-18}" width="{sw_+44}" height="{ROW*2+4}" rx="8" fill="none" stroke="{FAINT}" stroke-width="1.5"/>')
        for pin in range(1, 37):
            name = f"{hdr}.{pin:02d}"
            alt = f"{hdr}.{pin:02d}A"
            x = col(pin)
            y = y0 + (0 if pin % 2 else ROW)
            hit = name if name in used else alt if alt in used else None
            if hit:
                c, _, _ = wire_style(gcol[hit])
                put(f'<circle cx="{x}" cy="{y}" r="9" fill="{c}" stroke="#05060a" stroke-width="1.5"/>')
            else:
                put(f'<circle cx="{x}" cy="{y}" r="5" fill="{FAINT}"/>')
            if pin <= 2 or pin % 4 in (1, 2) and False:
                pass
            put(f'<text x="{x}" y="{y0-26 if pin % 2 else y0+ROW+26}" text-anchor="middle" font-size="11" fill="{SUB if hit else FAINT}">{pin}</text>')
        put(f'<rect x="{col(1)-12}" y="{y0-12}" width="24" height="24" fill="none" stroke="#f59e0b" stroke-width="2"/>')
        put(f'<text x="{col(1)+22}" y="{y0-26}" font-size="11" fill="#f59e0b">pin 1</text>')

    # --- legend --------------------------------------------------------------------
    ly = strip_y + 340 - 20
    lx = LEFT_X
    for g, (color, dash, label) in GROUPS.items():
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        put(f'<line x1="{lx}" y1="{ly}" x2="{lx+34}" y2="{ly}" stroke="{color}" stroke-width="5"{dash_attr}/>')
        put(f'<text x="{lx+44}" y="{ly+5}" font-size="14" fill="{TEXT}">{esc(label)}</text>')
        lx += 44 + 8.2 * len(label) + 28
        if lx > W - 300:
            lx, ly = LEFT_X, ly + 26
    H = int(ly + 40)
    svg = "\n".join(out).replace(f'viewBox="0 0 {W} {strip_y + 330}"', f'viewBox="0 0 {W} {H}"').replace(f'height="{strip_y + 330}"', f'height="{H}"')
    svg = svg.replace(f'<rect width="{W}" height="{strip_y + 330}"', f'<rect width="{W}" height="{H}"')
    path = Path(__file__).resolve().parent / "wiring-diagram.svg"
    path.write_text(svg + "\n</svg>\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
