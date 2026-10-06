from haptic_player.buttons import ButtonLogic
from haptic_player.nfc import TagTracker


def test_short_and_long_press():
    b = ButtonLogic(0.8)
    b.press("a", 0.0)
    assert b.release("a", 0.3) == [("a", "short")]
    b.press("a", 1.0)
    assert b.poll(1.5) == []
    assert b.poll(1.9) == [("a", "long")]  # fires while held
    assert b.poll(2.5) == []  # only once
    assert b.release("a", 3.0) == []  # no extra short after long
    assert b.release("a", 3.1) == []  # stray release


def test_tag_tracker():
    t = TagTracker(lost_polls=3)
    assert t.update(None) is None
    assert t.update("AA") == ("tag", "AA")
    assert t.update("AA") is None  # still there
    assert t.update(None) is None and t.update(None) is None
    assert t.update("AA") is None  # flicker does not re-trigger
    assert [t.update(None) for _ in range(3)] == [None, None, ("removed", "AA")]
    assert t.update("BB") == ("tag", "BB")
    assert t.update("CC") == ("tag", "CC")  # direct swap
