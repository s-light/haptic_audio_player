import io

import pytest
from aiohttp import FormData

from haptic_player.web import create_app


@pytest.fixture
async def client(aiohttp_client, cfg, ctl):
    return await aiohttp_client(create_app(cfg, ctl))


async def test_state_library_and_play(client):
    assert (await (await client.get("/api/state")).json())["mode"] == "idle"
    lib = await (await client.get("/api/library")).json()
    assert [a["path"] for a in lib] == ["Kinderlieder", "Single Song.ogg"]
    r = await client.post("/api/library/play", json={"type": "album", "path": "Kinderlieder"})
    assert (await r.json())["ok"]
    assert (await (await client.get("/api/state")).json())["mode"] == "playing"
    r = await client.post("/api/control", json={"action": "play_pause"})
    assert (await r.json())["mode"] == "paused"
    assert (await client.post("/api/control", json={"action": "bogus"})).status == 400


async def test_tags_crud_and_learn(client, ctl):
    r = await client.post("/api/tags", json={"uid": "aa:11", "type": "album", "target": "Kinderlieder", "label": "K"})
    assert r.status == 200
    assert (await (await client.get("/api/tags")).json())[0]["uid"] == "AA11"
    assert (await client.post("/api/tags", json={"uid": "zz", "type": "album", "target": "x"})).status == 400
    assert (await client.post("/api/tags", json={"uid": "AA11", "type": "nope", "target": "x"})).status == 400
    await client.post("/api/tags/learn", json={"type": "record", "target": "3"})
    assert ctl.learn is not None
    await ctl.handle_tag("BB22")
    assert ctl.tags.get("BB22").slot == 3
    assert (await (await client.delete("/api/tags/AA11")).json())["deleted"]


async def test_upload_and_path_safety(client, cfg):
    fd = FormData()
    for rel in ("Neues Album/01 Song.mp3", "../evil.mp3", "Neues Album/readme.exe"):
        fd.add_field("relpath", rel)
        fd.add_field("file", io.BytesIO(b"abc"), filename=rel.rsplit("/", 1)[-1])
    r = await client.post("/api/library/upload", data=fd)
    body = await r.json()
    assert body["saved"] == ["Neues Album/01 Song.mp3"]
    assert set(body["skipped"]) == {"../evil.mp3", "Neues Album/readme.exe"}
    assert (cfg.music_dir / "Neues Album" / "01 Song.mp3").read_bytes() == b"abc"
    assert not (cfg.music_dir.parent / "evil.mp3").exists()
    assert any(a["path"] == "Neues Album" for a in await (await client.get("/api/library")).json())

    r = await client.delete("/api/library", params={"path": "Neues Album"})
    assert r.status == 200 and not (cfg.music_dir / "Neues Album").exists()
    assert (await client.delete("/api/library", params={"path": "../data"})).status == 400
    assert (await client.delete("/api/library", params={"path": ""})).status == 404


async def test_cover_and_recordings(client, cfg):
    assert (await client.get("/api/cover", params={"path": "Kinderlieder/cover.jpg"})).status == 200
    assert (await client.get("/api/cover", params={"path": "../x"})).status == 400
    d = cfg.recordings_dir / "slot-01"
    d.mkdir()
    (d / "rec-1.wav").write_bytes(b"RIFF")
    slots = await (await client.get("/api/recordings")).json()
    assert slots[0]["files"] == ["rec-1.wav"] and slots[1]["files"] == []
    assert (await client.get("/api/recordings/1/rec-1.wav")).status == 200
    assert (await client.get("/api/recordings/1/..%2F..%2Ftags.json")).status in (400, 404)
    assert (await (await client.delete("/api/recordings/1/rec-1.wav")).json())["deleted"]


async def test_settings_and_dev_endpoints(client, ctl, cfg):
    assert (await client.post("/api/settings", json={"on_tag_remove": "pause", "volume_step": 10})).status == 200
    assert cfg.on_tag_remove == "pause" and "pause" in cfg.config_file.read_text()
    assert (await client.post("/api/settings", json={"on_tag_remove": "explode"})).status == 400
    ctl.tags.set("AA11", "track", "Single Song.ogg")
    await client.post("/api/dev/scan", json={"uid": "AA11"})
    assert ctl.mode == "playing"


async def test_websocket_pushes_state(client, ctl):
    async with client.ws_connect("/ws") as ws:
        first = await ws.receive_json()
        assert first["mode"] == "idle"
        await client.post("/api/control", json={"action": "select_slot", "value": 4})
        msg = await ws.receive_json()
        assert msg["slot"] == 4


async def test_storage_api_and_write_guard(aiohttp_client, cfg, ctl):
    from haptic_player.storage import FakeBackend, Storage

    backend = FakeBackend()
    ctl.storage = Storage(cfg.usb, backend, ctl.stop, ctl.reload_data, ctl.notify)
    client = await aiohttp_client(create_app(cfg, ctl))
    ctl.tags.set("AA11", "album", "Kinderlieder")
    r = await client.post("/api/storage", json={"mode": "computer"})
    assert r.status == 409 and "Computer" in (await r.json())["error"]  # nobody connected
    await client.post("/api/dev/usb", json={"host": True})
    await ctl.storage.tick(0)
    r = await client.post("/api/storage", json={"mode": "computer"})
    assert r.status == 200 and (await r.json())["mode"] == "computer"
    assert (await (await client.get("/api/state")).json())["storage"]["mode"] == "computer"
    # writes are refused while the computer owns the stick, reads still work
    assert (await client.post("/api/tags", json={"uid": "BB22", "type": "album", "target": "x"})).status == 409
    assert (await client.get("/api/tags")).status == 200
    await ctl.handle_tag("AA11")
    assert ctl.mode == "idle"  # tag scans are ignored too
    assert (await client.post("/api/storage", json={"mode": "player"})).status == 200
    assert (await client.post("/api/tags", json={"uid": "BB22", "type": "album", "target": "Kinderlieder"})).status == 200
    assert (await client.post("/api/storage", json={"mode": "nope"})).status == 400


async def test_cover_endpoint_serves_embedded_cover(aiohttp_client, tmp_path):
    from haptic_player.config import Config
    from haptic_player.controller import Controller
    from haptic_player.library import Library
    from haptic_player.player import FakePlayer
    from haptic_player.recorder import Recorder
    from haptic_player.tags import TagStore
    from tests.test_library import PNG, _mp3_with_cover

    cfg = Config(data_dir=tmp_path / "d", runtime_dir=tmp_path / "run", simulate=True, webui_dir=tmp_path / "nodist")
    cfg.music_dir.mkdir(parents=True)
    _mp3_with_cover(cfg.music_dir / "song.mp3", PNG)
    _mp3_with_cover(cfg.music_dir / "plain.mp3", None)
    ctl = Controller(cfg, FakePlayer(), Recorder(cfg), Library(cfg.music_dir), TagStore(cfg.tags_file))
    client = await aiohttp_client(create_app(cfg, ctl))
    r = await client.get("/api/cover", params={"path": "song.mp3"})
    assert r.status == 200 and r.content_type == "image/png" and await r.read() == PNG
    assert (await client.get("/api/cover", params={"path": "plain.mp3"})).status == 404
    lib = await (await client.get("/api/library")).json()
    assert {a["path"]: a["cover"] for a in lib} == {"song.mp3": "song.mp3", "plain.mp3": None}


async def test_spa_history_mode_fallback(aiohttp_client, tmp_path):
    """The Quasar app runs in router *history* mode: /library etc. must serve index.html on a reload."""
    from haptic_player.config import Config
    from haptic_player.controller import Controller
    from haptic_player.library import Library
    from haptic_player.player import FakePlayer
    from haptic_player.recorder import Recorder
    from haptic_player.tags import TagStore

    dist = tmp_path / "spa"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.ico").write_bytes(b"ico")
    cfg = Config(data_dir=tmp_path / "d", runtime_dir=tmp_path / "run", simulate=True, webui_dir=dist)
    cfg.music_dir.mkdir(parents=True)
    ctl = Controller(cfg, FakePlayer(), Recorder(cfg), Library(cfg.music_dir), TagStore(cfg.tags_file))
    client = await aiohttp_client(create_app(cfg, ctl))
    for path in ("/", "/library", "/tags", "/recordings", "/system"):
        r = await client.get(path)
        assert r.status == 200 and "app" in await r.text(), path
    assert (await client.get("/assets/app.js")).status == 200
    assert await (await client.get("/favicon.ico")).read() == b"ico"
    assert (await client.get("/api/does-not-exist")).status == 404  # API errors stay errors
    assert (await client.get("/../etc/passwd")).status in (200, 404)  # never leaves the dist dir
