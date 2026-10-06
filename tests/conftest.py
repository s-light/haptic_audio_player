import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from haptic_player.config import Config
from haptic_player.controller import Controller
from haptic_player.library import Library
from haptic_player.player import FakePlayer
from haptic_player.recorder import Recorder
from haptic_player.tags import TagStore


@pytest.fixture
def cfg(tmp_path):
    c = Config(data_dir=tmp_path / "data", runtime_dir=tmp_path / "run", simulate=True, webui_dir=tmp_path / "nodist")
    (c.music_dir / "Kinderlieder").mkdir(parents=True)
    for i in (1, 2, 10):
        (c.music_dir / "Kinderlieder" / f"{i:02d} Lied {i}.mp3").write_bytes(b"x")
    (c.music_dir / "Kinderlieder" / "cover.jpg").write_bytes(b"jpg")
    (c.music_dir / "Single Song.ogg").write_bytes(b"x")
    (c.music_dir / "notes.txt").write_text("ignore me")
    c.recordings_dir.mkdir(parents=True)
    return c


@pytest.fixture
def ctl(cfg):
    player = FakePlayer()
    return Controller(cfg, player, Recorder(cfg), Library(cfg.music_dir), TagStore(cfg.tags_file))
