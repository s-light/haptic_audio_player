import pytest

from haptic_player.config import load_config, save_persisted
from haptic_player.tags import TagStore, normalize_uid


def test_normalize_uid():
    assert normalize_uid("04:a1 b2:c3") == "04A1B2C3"
    for bad in ("", "xyz", "ABC"):
        with pytest.raises(ValueError):
            normalize_uid(bad)


def test_tagstore_roundtrip_and_move(tmp_path):
    s = TagStore(tmp_path / "tags.json")
    s.set("AA11", "album", "Kinderlieder", "Lieder")
    s.set("BB22", "record", "2")
    assert TagStore(tmp_path / "tags.json").get("aa11").target == "Kinderlieder"
    assert TagStore(tmp_path / "tags.json").get("BB22").slot == 2
    # same target on another tag -> moves
    s.set("CC33", "album", "Kinderlieder")
    assert s.get("AA11") is None and s.get("CC33") is not None
    assert s.for_target("record", "2").uid == "BB22"
    assert s.delete("CC33") and not s.delete("CC33")


def test_tagstore_rejects_bad_record_and_survives_garbage(tmp_path):
    s = TagStore(tmp_path / "tags.json")
    with pytest.raises(ValueError):
        s.set("AA11", "record", "zero")
    (tmp_path / "tags.json").write_text("{not json")
    assert TagStore(tmp_path / "tags.json").all() == []


def test_config_defaults_toml_and_persist(tmp_path):
    (tmp_path / "config.toml").write_text('volume = 33\n[nfc]\ni2c_bus = 5\n[display]\nenabled = false\n')
    cfg = load_config(tmp_path)
    assert cfg.volume == 33 and cfg.nfc.i2c_bus == 5 and not cfg.display.enabled
    assert cfg.pins.play_pause == "GPIO0_45"
    cfg.volume = 45
    cfg.on_tag_remove = "pause"
    save_persisted(cfg)
    again = load_config(tmp_path)
    assert again.volume == 45 and again.on_tag_remove == "pause" and again.nfc.i2c_bus == 5 and not again.display.enabled
