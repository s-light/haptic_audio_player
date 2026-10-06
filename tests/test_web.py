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
    assert (await client.post("/api/system/storage", json={"mode": "usb"})).status == 200  # simulated


async def test_websocket_pushes_state(client, ctl):
    async with client.ws_connect("/ws") as ws:
        first = await ws.receive_json()
        assert first["mode"] == "idle"
        await client.post("/api/control", json={"action": "select_slot", "value": 4})
        msg = await ws.receive_json()
        assert msg["slot"] == 4
