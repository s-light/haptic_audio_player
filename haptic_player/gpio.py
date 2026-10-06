"""libgpiod v2 helpers: resolve `GPIOx_y` / header-name specs to (chip path, line offset)."""

from __future__ import annotations

import glob
import re

# AM62x main_gpio0 / main_gpio1 platform-device names (= gpiochip labels)
CHIP_LABELS = {0: "600000.gpio", 1: "601000.gpio"}
_SPEC = re.compile(r"^GPIO(\d+)_(\d+)$", re.IGNORECASE)


def parse_spec(spec: str) -> tuple[int, int] | None:
    m = _SPEC.match(spec.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def resolve(spec: str) -> tuple[str, int]:
    import gpiod  # system package python3-libgpiod; imported lazily so tests/simulate don't need it

    parsed = parse_spec(spec)
    chips = sorted(glob.glob("/dev/gpiochip*"))
    if parsed:
        ctrl, line = parsed
        want = CHIP_LABELS.get(ctrl)
        for path in chips:
            with gpiod.Chip(path) as chip:
                if want and chip.get_info().label.startswith(want):
                    return path, line
        raise LookupError(f"no gpiochip for {spec} (looked for label {want})")
    # header name like "P2.02": kernel line names, optional "(ball)" / " [alt]" suffix stripped
    for path in chips:
        with gpiod.Chip(path) as chip:
            info = chip.get_info()
            for off in range(info.num_lines):
                name = chip.get_line_info(off).name
                if name and re.split(r"[\s(\[/]", name, 1)[0] == spec:
                    return path, off
    raise LookupError(f"gpio line {spec!r} not found (see `gpioinfo`)")
