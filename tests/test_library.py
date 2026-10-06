import pytest

from haptic_player.library import Library, UnsafePath, natural_key, safe_join


def test_scan_albums_and_singles(cfg):
    lib = Library(cfg.music_dir)
    paths = [a.path for a in lib.albums]
    assert paths == ["Kinderlieder", "Single Song.ogg"]
    album = lib.get("Kinderlieder")
    assert [t.path for t in album.tracks] == ["Kinderlieder/01 Lied 1.mp3", "Kinderlieder/02 Lied 2.mp3", "Kinderlieder/10 Lied 10.mp3"]  # natural order
    assert album.cover == "Kinderlieder/cover.jpg"
    assert lib.get("Single Song.ogg").single
    assert lib.track("Kinderlieder/02 Lied 2.mp3").title


def test_files_for(cfg):
    lib = Library(cfg.music_dir)
    assert len(lib.files_for("Kinderlieder")) == 3
    assert [p.name for p in lib.files_for("Kinderlieder/02 Lied 2.mp3")] == ["02 Lied 2.mp3"]
    assert lib.files_for("nope") == []
    with pytest.raises(UnsafePath):
        lib.files_for("../../etc/passwd")


def test_safe_join(tmp_path):
    assert safe_join(tmp_path, "a/b.mp3") == (tmp_path / "a" / "b.mp3").resolve()
    for bad in ("../x", "/etc/passwd", "a/../../x"):
        with pytest.raises(UnsafePath):
            safe_join(tmp_path, bad)


def test_missing_music_dir(tmp_path):
    assert Library(tmp_path / "nothing").albums == []


def test_natural_key():
    assert sorted(["10", "2", "1"], key=natural_key) == ["1", "2", "10"]
