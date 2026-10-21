from haptic_player.cst328 import Touch
from haptic_player.display import BUTTONS, button_rects, hit_button
from haptic_player.touch import TouchLogic, map_touch

W, H = 240, 320


def center(name: str) -> tuple[int, int]:
    x0, y0, x1, y1 = button_rects(W, H)[name]
    return (x0 + x1) // 2, (y0 + y1) // 2


def finger(x: int, y: int) -> list[Touch]:
    return [Touch(0, x, y, 30)]


def test_hit_button_covers_all_buttons_and_not_the_rest():
    for name in BUTTONS:
        assert hit_button(*center(name), W, H) == name
    assert hit_button(120, 100, W, H) == ""  # cover area
    rects = list(button_rects(W, H).values())
    assert hit_button(rects[0][2] + 2, rects[0][1] + 5, W, H) == ""  # gap between buttons
    assert all(r[2] <= W and r[3] <= H for r in rects)


def test_map_touch_rotations():
    assert map_touch(10, 20, 0) == (10, 20)
    assert map_touch(10, 20, 180) == (229, 299)
    assert map_touch(0, 0, 90) == (0, 239) and map_touch(0, 0, 270) == (319, 0)


def test_tap_is_short_and_hold_is_long():
    t = TouchLogic(W, H, long_press_s=0.8)
    x, y = center("next")
    assert t.update(finger(x, y), 0.0) == [] and t.held == "next"
    assert t.update([], 0.2) == [("next", "short")] and t.held == ""
    t.update(finger(x, y), 1.0)
    assert t.update(finger(x, y), 1.9) == [("next", "long")]  # fires while still held
    assert t.update([], 2.5) == []  # no second event on lift


def test_sliding_off_cancels_and_needs_a_lift():
    t = TouchLogic(W, H)
    t.update(finger(*center("prev")), 0.0)
    assert t.update(finger(*center("next")), 0.1) == [] and t.held == ""  # slid onto another button: no press
    assert t.update(finger(*center("next")), 0.2) == [] and t.held == ""
    assert t.update([], 0.3) == []
    t.update(finger(*center("next")), 1.0)
    assert t.update([], 1.2) == [("next", "short")]


def test_touch_outside_buttons_and_noise_do_nothing():
    t = TouchLogic(W, H)
    assert t.update(finger(120, 100), 0.0) == [] and t.held == ""
    t.update(finger(*center("record")), 1.0)
    assert t.update([], 1.01) == []  # contact shorter than the noise threshold
