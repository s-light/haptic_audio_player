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


def _mp3_with_cover(path, cover: bytes | None):
    """A tiny but valid MP3 (3 MPEG-1 Layer III frames) with an optional ID3 APIC picture."""
    frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)
    path.write_bytes(frame * 3)
    if cover is not None:
        from mutagen.id3 import APIC, ID3

        tags = ID3()
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="front", data=cover))
        tags.save(path)


PNG = bytes.fromhex("89504e470d0a1a0a")  # not a decodable image - the library only transports the bytes


def test_embedded_covers_for_singles_and_albums(tmp_path):
    music = tmp_path / "music"
    (music / "Album A").mkdir(parents=True)
    (music / "Album B").mkdir()
    (music / "Album C").mkdir()
    _mp3_with_cover(music / "single with cover.mp3", PNG)
    _mp3_with_cover(music / "single plain.mp3", None)
    _mp3_with_cover(music / "Album A" / "01 a.mp3", None)
    _mp3_with_cover(music / "Album A" / "02 b.mp3", PNG)  # first track WITHOUT cover, second has one
    _mp3_with_cover(music / "Album B" / "01 a.mp3", PNG)
    (music / "Album B" / "cover.jpg").write_bytes(b"jpg")  # folder image wins over embedded
    _mp3_with_cover(music / "Album C" / "01 a.mp3", None)
    lib = Library(music)
    covers = {a.path: a.cover for a in lib.albums}
    assert covers["single with cover.mp3"] == "single with cover.mp3"
    assert covers["single plain.mp3"] is None
    assert covers["Album A"] == "Album A/02 b.mp3"
    assert covers["Album B"] == "Album B/cover.jpg"
    assert covers["Album C"] is None
    assert lib.embedded_cover("single with cover.mp3") == (PNG, "image/png")
    assert lib.track_cover("Album A/01 a.mp3") is None and lib.track_cover("Album A/02 b.mp3") == "Album A/02 b.mp3"


async def test_now_playing_prefers_track_cover_and_display_gets_a_file(tmp_path):
    from haptic_player.config import Config
    from haptic_player.controller import Controller
    from haptic_player.player import FakePlayer
    from haptic_player.recorder import Recorder
    from haptic_player.tags import TagStore

    cfg = Config(data_dir=tmp_path / "d", runtime_dir=tmp_path / "run", simulate=True)
    (cfg.music_dir / "Album").mkdir(parents=True)
    _mp3_with_cover(cfg.music_dir / "Album" / "01 a.mp3", PNG)
    _mp3_with_cover(cfg.music_dir / "Album" / "02 b.mp3", None)
    (cfg.music_dir / "Album" / "cover.jpg").write_bytes(b"folder")
    ctl = Controller(cfg, FakePlayer(), Recorder(cfg), Library(cfg.music_dir), TagStore(cfg.tags_file))
    await ctl.play_item("album", "Album")
    assert ctl.snapshot()["now"]["cover"] == "Album/01 a.mp3"  # own embedded cover
    shown = ctl.view().cover
    assert shown and open(shown, "rb").read() == PNG and str(cfg.runtime_dir) in shown  # extracted to the cache
    await ctl.player.next()
    assert ctl.snapshot()["now"]["cover"] == "Album/cover.jpg"  # no embedded cover -> folder image
    assert ctl.view().cover == str(cfg.music_dir / "Album" / "cover.jpg")
