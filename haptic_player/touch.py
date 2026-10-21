"""Touch input: CST328 touch points -> on-screen button events (same (name, "short" | "long") events as buttons.py)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .buttons import ButtonLogic, Event
from .cst328 import CST328, Touch
from .display import hit_button

log = logging.getLogger(__name__)

NATIVE_W, NATIVE_H = 240, 320  # the panel in its native (portrait) orientation; touch coordinates are in this frame
MIN_TAP_S = 0.03  # shorter contacts are ignored (noise)


def map_touch(x: int, y: int, rotation: int) -> tuple[int, int]:
    """Native touch coordinates -> coordinates in the rendered image of the given display rotation.

    0 and 180 are verified on the real panel; 90/270 follow the ST7789 MADCTL setting in display.py and are untested.
    """
    if rotation == 180:
        return NATIVE_W - 1 - x, NATIVE_H - 1 - y
    if rotation == 90:
        return y, NATIVE_W - 1 - x
    if rotation == 270:
        return NATIVE_H - 1 - y, x
    return x, y


class TouchLogic:
    """Pure state machine: feed the current touch points every poll, get button events and the held button.

    A finger that goes down on a button presses it; lifting it releases it (short/long by duration, a long press
    fires while still held). Sliding off the button cancels; the finger then has to be lifted before the next press.
    Only the first finger counts.
    """

    def __init__(self, width: int, height: int, rotation: int = 0, long_press_s: float = 0.8):
        self.w, self.h, self.rotation = width, height, rotation
        self.logic = ButtonLogic(long_press_s)
        self.held = ""  # button under the finger, "" = none
        self._since = 0.0
        self._cancelled = False

    def _over(self, touches: list[Touch]) -> str:
        x, y = map_touch(touches[0].x, touches[0].y, self.rotation)
        return hit_button(x, y, self.w, self.h)

    def update(self, touches: list[Touch], now: float) -> list[Event]:
        events: list[Event] = []
        if not touches:
            if self.held and now - self._since >= MIN_TAP_S:
                events += self.logic.release(self.held, now)
            elif self.held:
                self.logic.cancel(self.held)
            self.held, self._cancelled = "", False
            return events
        over = self._over(touches)
        if self.held and over != self.held:
            self.logic.cancel(self.held)
            self.held, self._cancelled = "", True
        elif not self.held and over and not self._cancelled:
            self.held, self._since = over, now
            self.logic.press(over, now)
        return events + self.logic.poll(now)


class TouchReader(threading.Thread):
    def __init__(self, chip: CST328, width: int, height: int, rotation: int, long_press_s: float, poll_s: float,
                 on_event: Callable[[str, str], None], on_pressed: Callable[[str], None]):
        super().__init__(daemon=True, name="touch")
        self.chip, self.poll_s = chip, poll_s
        self.logic = TouchLogic(width, height, rotation, long_press_s)
        self.on_event, self.on_pressed = on_event, on_pressed
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        pressed = ""
        errors = 0
        while not self._halt.is_set():
            try:
                touches = self.chip.read_touches()
                errors = 0
            except Exception as e:
                errors += 1
                if errors in (1, 50):
                    log.warning("touch read failed: %s", e)
                self._halt.wait(min(1.0, 0.05 * errors))
                touches = []
            for ev in self.logic.update(touches, time.monotonic()):
                self.on_event(*ev)
            if self.logic.held != pressed:
                pressed = self.logic.held
                self.on_pressed(pressed)
            self._halt.wait(self.poll_s)
