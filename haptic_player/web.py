"""aiohttp app: REST under /api, WebSocket /ws (state push), static Quasar UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

from aiohttp import WSMsgType, web

from .config import AUDIO_EXTENSIONS, COVER_EXTENSIONS, Config, save_persisted
from .controller import Controller
from .library import UnsafePath, is_audio, safe_join
from .recorder import list_slots, slot_dir
from .tags import TYPES

log = logging.getLogger(__name__)
CONTROLLER = web.AppKey("controller", Controller)
CONFIG = web.AppKey("config", Config)
WSS = web.AppKey("wss", set)
PNG = web.AppKey("png", Path)

UPLOAD_EXTENSIONS = AUDIO_EXTENSIONS | set(COVER_EXTENSIONS)


def err(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def json_body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid json"}), content_type="application/json")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text=json.dumps({"error": "object expected"}), content_type="application/json")
    return data


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return ""


def create_app(cfg: Config, ctl: Controller, png_path: Path | None = None) -> web.Application:
    app = web.Application(client_max_size=0)  # uploads are streamed, no body-size cap
    app[CONTROLLER], app[CONFIG], app[WSS] = ctl, cfg, set()
    app[PNG] = png_path or (cfg.runtime_dir / "display.png")
    routes = web.RouteTableDef()

    # ---- state / websocket ------------------------------------------
    @routes.get("/api/state")
    async def state(request):
        return web.json_response(ctl.snapshot())

    @routes.get("/ws")
    async def ws(request):
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(request)
        app[WSS].add(sock)
        await sock.send_json(ctl.snapshot())
        try:
            async for msg in sock:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            app[WSS].discard(sock)
        return sock

    def broadcast(snap: dict) -> None:
        for s in list(app[WSS]):
            if s.closed:
                app[WSS].discard(s)
            else:
                asyncio.get_running_loop().create_task(_safe_send(s, snap))

    async def _safe_send(s, snap):
        try:
            await s.send_json(snap)
        except Exception:
            app[WSS].discard(s)

    ctl.listeners.append(broadcast)

    # ---- control -----------------------------------------------------
    @routes.post("/api/control")
    async def control(request):
        d = await json_body(request)
        action = d.get("action")
        if action == "play_pause":
            await ctl.toggle_play()
        elif action == "stop":
            await ctl.stop()
        elif action == "next":
            await ctl.handle_button("next", "short")
        elif action == "prev":
            await ctl.handle_button("prev", "short")
        elif action == "record":
            await ctl.toggle_record()
        elif action == "volume":
            await ctl.set_volume(int(d.get("value", 0)))
        elif action == "seek":
            await ctl.player.seek(float(d.get("value", 0)))
        elif action == "select_slot":
            ctl.selected_slot = max(0, int(d.get("value", 0)))
            ctl.notify()
        else:
            return err(400, f"unknown action {action!r}")
        return web.json_response(ctl.snapshot())

    # ---- library -----------------------------------------------------
    @routes.get("/api/library")
    async def library(request):
        return web.json_response(ctl.library.as_dict())

    @routes.post("/api/library/rescan")
    async def rescan(request):
        await asyncio.to_thread(ctl.library.scan)
        return web.json_response(ctl.library.as_dict())

    @routes.post("/api/library/play")
    async def play(request):
        d = await json_body(request)
        ok = await ctl.play_item(d.get("type", "album"), str(d.get("path", "")))
        return web.json_response({"ok": ok})

    @routes.delete("/api/library")
    async def library_delete(request):
        try:
            p = safe_join(cfg.music_dir, request.query.get("path", ""))
        except UnsafePath:
            return err(400, "bad path")
        if p == cfg.music_dir.resolve() or not p.exists():
            return err(404, "not found")
        if ctl.player.state["active"]:
            await ctl.stop()
        await asyncio.to_thread(shutil.rmtree if p.is_dir() else os.unlink, p)
        await asyncio.to_thread(ctl.library.scan)
        return web.json_response(ctl.library.as_dict())

    @routes.post("/api/library/upload")
    async def upload(request):
        """multipart: a text field `relpath` before a file part gives its relative path (folder drop:
        'Album/01.mp3' - browsers only send the basename in `filename`); optional text field `album` forces
        a target folder."""
        reader = await request.multipart()
        album, relpath, saved, skipped = "", "", [], []
        async for part in reader:
            if part.name == "album":
                album = (await part.text()).strip().strip("/")
                continue
            if part.name == "relpath":
                relpath = (await part.text()).strip()
                continue
            if part.filename is None:
                continue
            rel = (relpath or part.filename).replace("\\", "/").lstrip("/")
            relpath = ""
            if album:
                rel = f"{album}/{Path(rel).name}"
            if Path(rel).suffix.lower() not in UPLOAD_EXTENSIONS or Path(rel).name.startswith("."):
                skipped.append(rel)
                await part.read()  # drain
                continue
            try:
                dest = safe_join(cfg.music_dir, rel)
            except UnsafePath:
                skipped.append(rel)
                await part.read()
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".upload-")
            try:
                with os.fdopen(fd, "wb") as fh:
                    while chunk := await part.read_chunk(1 << 20):
                        await asyncio.to_thread(fh.write, chunk)
                    fh.flush()
                    await asyncio.to_thread(os.fsync, fh.fileno())
                os.replace(tmp, dest)
                saved.append(rel)
            except BaseException:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                raise
        await asyncio.to_thread(ctl.library.scan)
        return web.json_response({"saved": saved, "skipped": skipped})

    @routes.get("/api/cover")
    async def cover(request):
        rel = request.query.get("path", "")
        try:
            p = safe_join(cfg.music_dir, rel)
        except UnsafePath:
            return err(400, "bad path")
        if p.is_file() and p.suffix.lower() in COVER_EXTENSIONS:
            return web.FileResponse(p, headers={"Cache-Control": "max-age=3600"})
        if p.is_file() and is_audio(p):
            emb = await asyncio.to_thread(ctl.library.embedded_cover, rel)
            if emb:
                return web.Response(body=emb[0], content_type=emb[1], headers={"Cache-Control": "max-age=3600"})
        return err(404, "no cover")

    # ---- tags --------------------------------------------------------
    @routes.get("/api/tags")
    async def tags(request):
        return web.json_response([{"uid": t.uid, "type": t.type, "target": t.target, "label": t.label} for t in ctl.tags.all()])

    @routes.post("/api/tags")
    async def tags_set(request):
        d = await json_body(request)
        if d.get("type") not in TYPES:
            return err(400, "bad type")
        try:
            t = ctl.tags.set(str(d.get("uid", "")), d["type"], str(d.get("target", "")), str(d.get("label", "")))
        except ValueError as e:
            return err(400, str(e))
        ctl.notify()
        return web.json_response({"uid": t.uid, "type": t.type, "target": t.target, "label": t.label})

    @routes.delete("/api/tags/{uid}")
    async def tags_delete(request):
        try:
            ok = ctl.tags.delete(request.match_info["uid"])
        except ValueError as e:
            return err(400, str(e))
        return web.json_response({"deleted": ok})

    @routes.post("/api/tags/learn")
    async def learn(request):
        d = await json_body(request)
        if d.get("type") not in TYPES or not str(d.get("target", "")):
            return err(400, "type and target required")
        ctl.start_learn(d["type"], str(d["target"]), str(d.get("label", "")))
        return web.json_response({"ok": True})

    @routes.delete("/api/tags/learn")
    async def learn_cancel(request):
        ctl.cancel_learn()
        return web.json_response({"ok": True})

    # ---- recordings --------------------------------------------------
    @routes.get("/api/recordings")
    async def recordings(request):
        slots = list_slots(cfg)
        for s in slots:
            t = ctl.tags.for_target("record", str(s["slot"]))
            s["tag"] = t.uid if t else None
        return web.json_response(slots)

    def rec_path(request) -> Path:
        slot = int(request.match_info["slot"])
        return safe_join(slot_dir(cfg, slot), request.match_info["name"])

    @routes.get("/api/recordings/{slot}/{name}")
    async def rec_get(request):
        try:
            p = rec_path(request)
        except (UnsafePath, ValueError):
            return err(400, "bad path")
        return web.FileResponse(p) if p.is_file() else err(404, "not found")

    @routes.delete("/api/recordings/{slot}/{name}")
    async def rec_delete(request):
        try:
            p = rec_path(request)
        except (UnsafePath, ValueError):
            return err(400, "bad path")
        if not p.is_file():
            return err(404, "not found")
        p.unlink()
        return web.json_response({"deleted": True})

    @routes.post("/api/recordings/{slot}/play")
    async def rec_play(request):
        ok = await ctl.play_item("record", request.match_info["slot"])
        return web.json_response({"ok": ok})

    # ---- settings / system -------------------------------------------
    @routes.get("/api/settings")
    async def settings(request):
        return web.json_response({"on_tag_remove": cfg.on_tag_remove, "volume_step": cfg.volume_step,
                                  "long_press_s": cfg.long_press_s, "volume": ctl.player.state["volume"]})

    @routes.post("/api/settings")
    async def settings_set(request):
        d = await json_body(request)
        if "on_tag_remove" in d:
            if d["on_tag_remove"] not in ("none", "pause", "stop"):
                return err(400, "on_tag_remove must be none|pause|stop")
            cfg.on_tag_remove = d["on_tag_remove"]
        if "volume_step" in d:
            cfg.volume_step = max(1, min(25, int(d["volume_step"])))
        if "long_press_s" in d:
            cfg.long_press_s = max(0.3, min(3.0, float(d["long_press_s"])))
        try:
            save_persisted(cfg)
        except OSError as e:
            return err(500, f"could not save: {e}")
        ctl.notify()
        return web.json_response({"ok": True})

    @routes.get("/api/system")
    async def system(request):
        try:
            du = shutil.disk_usage(cfg.data_dir)
            disk = {"total": du.total, "free": du.free}
        except OSError:
            disk = None
        root_ro = any(l.split()[1] == "/" and "ro" in l.split()[3].split(",") for l in Path("/proc/mounts").read_text().splitlines() if len(l.split()) > 3) if Path("/proc/mounts").exists() else None
        return web.json_response({"hostname": socket.gethostname(), "ip": local_ip(), "disk": disk, "root_readonly": root_ro,
                                  "nfc_ok": ctl.nfc_ok, "simulate": cfg.simulate, "data_dir": str(cfg.data_dir)})

    async def sudo(*cmd: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec("sudo", "-n", *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        return proc.returncode or 0, out.decode().strip()

    @routes.post("/api/system/power")
    async def power(request):
        d = await json_body(request)
        action = d.get("action")
        if action not in ("shutdown", "reboot"):
            return err(400, "action must be shutdown|reboot")
        if cfg.simulate:
            return web.json_response({"ok": True, "simulated": True})
        await ctl.stop()
        rc, out = await sudo("/usr/bin/systemctl", "poweroff" if action == "shutdown" else "reboot")
        return web.json_response({"ok": rc == 0, "output": out}, status=200 if rc == 0 else 500)

    @routes.post("/api/system/storage")
    async def storage(request):
        """mode 'usb': hand the data partition to a connected PC; mode 'player': take it back."""
        d = await json_body(request)
        mode = d.get("mode")
        if mode not in ("usb", "player"):
            return err(400, "mode must be usb|player")
        if cfg.simulate:
            return web.json_response({"ok": True, "simulated": True, "mode": mode})
        if mode == "usb":
            await ctl.stop()
        rc, out = await sudo(sys.executable, "-m", "haptic_player.usbgadget", "on" if mode == "usb" else "off")
        if rc == 0 and mode == "player":
            await asyncio.to_thread(ctl.library.scan)
        return web.json_response({"ok": rc == 0, "output": out, "mode": out.splitlines()[-1] if out else mode}, status=200 if rc == 0 else 500)

    # ---- dev / simulate ----------------------------------------------
    if cfg.simulate:
        @routes.post("/api/dev/scan")
        async def dev_scan(request):
            d = await json_body(request)
            await ctl.handle_tag(str(d.get("uid", "")))
            return web.json_response({"ok": True})

        @routes.post("/api/dev/remove")
        async def dev_remove(request):
            await ctl.handle_tag_removed()
            return web.json_response({"ok": True})

        @routes.post("/api/dev/button")
        async def dev_button(request):
            d = await json_body(request)
            await ctl.handle_button(str(d.get("name")), str(d.get("kind", "short")))
            return web.json_response({"ok": True})

    @routes.get("/api/display.png")
    async def display_png(request):
        p = app[PNG]
        return web.FileResponse(p, headers={"Cache-Control": "no-store"}) if p.exists() else err(404, "no display frame")

    app.add_routes(routes)

    # ---- static web UI (SPA) -----------------------------------------
    dist = Path(cfg.webui_dir)
    if (dist / "index.html").exists():
        async def index(request):
            return web.FileResponse(dist / "index.html")

        app.router.add_get("/", index)
        app.router.add_static("/assets", dist / "assets") if (dist / "assets").exists() else None

        @web.middleware
        async def spa(request, handler):
            try:
                return await handler(request)
            except web.HTTPNotFound:
                if request.method == "GET" and not request.path.startswith("/api") and request.path != "/ws":
                    f = (dist / request.path.lstrip("/")).resolve()
                    if dist.resolve() in f.parents and f.is_file():
                        return web.FileResponse(f)
                    return web.FileResponse(dist / "index.html")
                raise

        app.middlewares.append(spa)
    else:
        async def no_ui(request):
            return web.Response(text="haptic player API is running, web UI not built (see README: webui)", content_type="text/plain")

        app.router.add_get("/", no_ui)
    return app
