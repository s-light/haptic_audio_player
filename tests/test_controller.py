import pytest

from haptic_player.recorder import list_slot


async def test_unknown_tag_flashes_and_records_last_scan(ctl):
    await ctl.handle_tag("DEADBEEF")
    assert ctl.last_scan["uid"] == "DEADBEEF" and not ctl.last_scan["known"]
    assert ctl.message and ctl.mode == "idle"


async def test_album_tag_plays_and_buttons_work(ctl):
    ctl.tags.set("AA11", "album", "Kinderlieder", "Lieder")
    await ctl.handle_tag("aa11")
    assert ctl.mode == "playing" and ctl.player.state["count"] == 3
    await ctl.handle_button("play_pause", "short")
    assert ctl.mode == "paused"
    await ctl.handle_button("play_pause", "short")
    assert ctl.mode == "playing"
    await ctl.handle_button("next", "short")
    assert ctl.player.state["index"] == 1
    await ctl.handle_button("prev", "short")
    assert ctl.player.state["index"] == 0
    await ctl.handle_button("play_pause", "long")
    assert ctl.mode == "idle"
    await ctl.handle_button("play_pause", "short")  # replays last item
    assert ctl.mode == "playing"


async def test_volume_long_press_persists(ctl, cfg):
    await ctl.player.start(70)
    await ctl.handle_button("next", "long")
    assert ctl.player.state["volume"] == 75
    await ctl.handle_button("prev", "long")
    await ctl.handle_button("prev", "long")
    assert ctl.player.state["volume"] == 65
    assert "volume = 65" in cfg.config_file.read_text()


@pytest.mark.parametrize("mode,expected", [("none", "playing"), ("pause", "paused"), ("stop", "idle")])
async def test_on_tag_remove(ctl, mode, expected):
    ctl.cfg.on_tag_remove = mode
    ctl.tags.set("AA11", "album", "Kinderlieder")
    await ctl.handle_tag("AA11")
    await ctl.handle_tag_removed()
    assert ctl.mode == expected


async def test_same_tag_after_pause_resumes_instead_of_restart(ctl):
    ctl.cfg.on_tag_remove = "pause"
    ctl.tags.set("AA11", "album", "Kinderlieder")
    await ctl.handle_tag("AA11")
    await ctl.player.next()
    await ctl.handle_tag_removed()
    await ctl.handle_tag("AA11")
    assert ctl.mode == "playing" and ctl.player.state["index"] == 1


async def test_learn_mode_assigns_next_tag_without_playing(ctl):
    ctl.start_learn("album", "Single Song.ogg", "Song")
    await ctl.handle_tag("CAFE01")
    assert ctl.tags.get("CAFE01").target == "Single Song.ogg"
    assert ctl.learn is None and ctl.mode == "idle"


async def test_record_flow(ctl, cfg):
    await ctl.handle_button("record", "short")
    assert ctl.mode == "idle" and ctl.message  # no slot selected yet
    ctl.tags.set("BB22", "record", "2")
    await ctl.handle_tag("BB22")
    assert ctl.selected_slot == 2 and ctl.mode == "idle"  # empty slot: nothing to play
    await ctl.handle_button("record", "short")
    assert ctl.mode == "recording" and ctl.recorder.slot == 2
    await ctl.handle_tag("AA11")  # ignored while recording
    await ctl.handle_button("play_pause", "short")  # stops recording
    assert ctl.mode == "idle"
    assert len(list_slot(cfg, 2)) == 1
    await ctl.handle_tag("BB22")  # now plays the recording
    assert ctl.mode == "playing" and ctl.player.state["count"] == 1


async def test_snapshot_and_view(ctl):
    ctl.tags.set("AA11", "album", "Kinderlieder", "Lieder")
    await ctl.handle_tag("AA11")
    snap = ctl.snapshot()
    assert snap["mode"] == "playing" and snap["now"]["cover"] == "Kinderlieder/cover.jpg"
    v = ctl.view()
    assert v.mode == "playing" and v.count == 3 and v.cover.endswith("cover.jpg")
