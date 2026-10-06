"""Push buttons (to GND, internal pull-up) via libgpiod edge events, with short/long press detection."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import timedelta
from typing import Callable

from .gpio import resolve

log = logging.getLogger(__name__)
Event = tuple[str, str]  # (button name, "short" | "long")


class ButtonLogic:
    """Pure press/release -> short/long state machine. A long press fires while still held."""

    def __init__(self, long_press_s: float = 0.8):
        self.long_press_s = long_press_s
        self._down: dict[str, float] = {}
        self._fired: set[str] = set()

    def press(self, name: str, t: float) -> None:
        self._down[name] = t
        self._fired.discard(name)

    def release(self, name: str, t: float) -> list[Event]:
        start = self._down.pop(name, None)
        if start is None:
            return []
        if name in self._fired:
            self._fired.discard(name)
            return []
        return [(name, "long" if t - start >= self.long_press_s else "short")]

    def poll(self, t: float) -> list[Event]:
        out = []
        for name, start in self._down.items():
            if name not in self._fired and t - start >= self.long_press_s:
                self._fired.add(name)
                out.append((name, "long"))
        return out


class Buttons(threading.Thread):
    def __init__(self, pins: dict[str, str], long_press_s: float, on_event: Callable[[str, str], None]):
        super().__init__(daemon=True, name="buttons")
        self.pins, self.on_event = pins, on_event
        self.logic = ButtonLogic(long_press_s)
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        import gpiod
        from gpiod.line import Bias, Direction, Edge, EdgeEventType

        by_chip: dict[str, dict[int, str]] = defaultdict(dict)
        for name, spec in self.pins.items():
            try:
                path, off = resolve(spec)
                by_chip[path][off] = name
            except LookupError as e:
                log.error("button %s: %s", name, e)
        requests = []
        for path, lines in by_chip.items():
            settings = gpiod.LineSettings(
                direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.BOTH,
                debounce_period=timedelta(milliseconds=25),
            )
            requests.append((gpiod.request_lines(path, consumer="haptic-buttons", config={o: settings for o in lines}), lines))
        if not requests:
            log.error("no buttons available")
            return
        log.info("buttons ready: %s", ", ".join(self.pins))
        while not self._halt.is_set():
            for req, lines in requests:
                if req.wait_edge_events(timedelta(milliseconds=50 // len(requests))):
                    for ev in req.read_edge_events():
                        name = lines.get(ev.line_offset)
                        if name is None:
                            continue
                        now = time.monotonic()
                        if ev.event_type == EdgeEventType.FALLING_EDGE:
                            self.logic.press(name, now)
                        else:
                            for e in self.logic.release(name, now):
                                self.on_event(*e)
            for e in self.logic.poll(time.monotonic()):
                self.on_event(*e)
