"""Controller: the one place where inputs (tags, buttons, web) turn into player/recorder actions."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Callable

from .config import COVER_EXTENSIONS, Config, save_persisted
from .display import View
from .library import Library
from .player import PlayerBase
from .recorder import Recorder, list_slot
from .tags import Tag, TagStore, normalize_uid

log = logging.getLogger(__name__)


class Controller:
    def __init__(self, cfg: Config, player: PlayerBase, recorder: Recorder, library: Library, tags: TagStore):
        self.cfg, self.player, self.recorder, self.library, self.tags = cfg, player, recorder, library, tags
        self.selected_slot = 0
        self.current: tuple[str, str] | None = None  # (type, target) of what is loaded
        self.last_play: tuple[str, str] | None = None
        self.last_scan: dict | None = None
        self.learn: dict | None = None  # {"type","target","label"} - assign next scanned tag
        self.message = ""
        self.nfc_ok = False
        self.storage = None  # set by __main__ (haptic_player.storage.Storage)
        self.listeners: list[Callable[[dict], None]] = []
        self.view_sink: Callable[[View], None] | None = None
        self._msg_handle: asyncio.TimerHandle | None = None
        self._rec_ticker: asyncio.Task | None = None
        player.on_change = self.notify
        player.on_finished = self._on_finished

    # ---- state -------------------------------------------------------
    @property
    def mode(self) -> str:
        if self.recorder.active:
            return "recording"
        s = self.player.state
        if not s["active"]:
            return "idle"
        return "paused" if s["paused"] else "playing"

    def _now_playing(self) -> dict:
        s = self.player.state
        info = {"title": s["title"], "subtitle": s["label"], "cover": None, "path": None}
        if s["file"]:
            try:
                rel = Path(s["file"]).resolve().relative_to(self.cfg.music_dir.resolve()).as_posix()
            except ValueError:
                rel = None
            if rel:
                info["path"] = rel
                info["cover"] = self.library.track_cover(rel)  # the track's own embedded cover wins ...
                t = self.library.track(rel)
                if t:
                    info["title"] = t.title
                    if t.artist and not s["label"]:
                        info["subtitle"] = t.artist
                album = self.library.get(rel.split("/")[0]) if "/" in rel else None
                if album is not None:
                    info["cover"] = info["cover"] or album.cover  # ... else the album's (folder image / first embedded)
                    if not info["subtitle"]:
                        info["subtitle"] = album.title
            elif "recordings" in Path(s["file"]).parts:
                info["title"] = info["title"] or "Aufnahme"
        return info

    def snapshot(self) -> dict:
        s = self.player.state
        now = self._now_playing()
        rec = self.recorder
        return {
            "mode": self.mode,
            "player": dict(s),
            "now": now,
            "slot": self.selected_slot,
            "recording": {"active": rec.active, "slot": rec.slot, "elapsed": round(rec.elapsed, 1)},
            "last_scan": self.last_scan,
            "learn": self.learn,
            "message": self.message,
            "nfc_ok": self.nfc_ok,
            "simulate": self.cfg.simulate,
            "audio": self.player.kind,
            "storage": self.storage.snapshot() if self.storage else {"mode": "player", "host": False, "available": False, "error": ""},
            "volume": s["volume"],
            "on_tag_remove": self.cfg.on_tag_remove,
        }

    def view(self) -> View:
        s, now = self.player.state, self._now_playing()
        mode = self.mode
        if self.at_computer:
            return View(mode="computer", title="Speicher am Computer", subtitle="am PC auswerfen oder Kabel ziehen", message=self.message)
        cover = self._cover_file(now["cover"]) if now["cover"] else ""
        if mode == "recording":
            return View(mode=mode, title="Aufnahme läuft", subtitle="", position=int(self.recorder.elapsed), slot=self.recorder.slot or 0, message=self.message)
        return View(mode=mode, title=now["title"], subtitle=now["subtitle"] or "", position=int(s["position"]), duration=int(s["duration"]),
                    index=s["index"], count=s["count"], slot=self.selected_slot, volume=s["volume"], cover=cover, message=self.message)

    def _cover_file(self, rel: str) -> str:
        """Image file for the display: folder images are used in place, embedded covers are extracted once into
        a cache below the runtime dir (tmpfs - the root filesystem is read-only)."""
        src = self.cfg.music_dir / rel
        if src.suffix.lower() in COVER_EXTENSIONS:
            return str(src)
        try:
            key = hashlib.sha1(f"{rel}:{src.stat().st_mtime_ns}".encode()).hexdigest()[:16]
            dest = self.cfg.runtime_dir / "covers" / key
            if not dest.exists():
                emb = self.library.embedded_cover(rel)
                if emb is None:
                    return ""
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(emb[0])
            return str(dest)
        except OSError:
            return ""

    def notify(self) -> None:
        snap = None
        for fn in list(self.listeners):
            snap = snap or self.snapshot()
            try:
                fn(snap)
            except Exception:
                log.exception("listener failed")
        if self.view_sink:
            self.view_sink(self.view())

    def flash(self, message: str, seconds: float = 3.0) -> None:
        self.message = message
        if self._msg_handle:
            self._msg_handle.cancel()
        self._msg_handle = asyncio.get_running_loop().call_later(seconds, self._clear_message)
        self.notify()

    def _clear_message(self) -> None:
        self.message = ""
        self.notify()

    def _on_finished(self) -> None:
        self.current = None
        self.notify()

    # ---- inputs ------------------------------------------------------
    @property
    def at_computer(self) -> bool:
        return self.storage is not None and self.storage.mode == "computer"

    async def handle_tag(self, uid: str) -> None:
        uid = normalize_uid(uid)
        if self.at_computer:
            self.flash("Speicher ist am Computer")
            return
        tag = self.tags.get(uid)
        self.last_scan = {"uid": uid, "known": tag is not None, "time": time.time(),
                          "type": tag.type if tag else None, "target": tag.target if tag else None, "label": tag.label if tag else None}
        log.info("tag %s (%s)", uid, f"{tag.type}:{tag.target}" if tag else "unknown")
        if self.learn:
            ln, self.learn = self.learn, None
            self.tags.set(uid, ln["type"], ln["target"], ln.get("label", ""))
            self.last_scan["known"] = True
            self.flash("Tag zugewiesen")
            return
        if tag is None:
            self.flash("Unbekannter Tag")
            return
        if self.recorder.active:
            self.flash("Aufnahme läuft")
            return
        await self.play_tag(tag)

    async def play_tag(self, tag: Tag) -> None:
        key = (tag.type, tag.target)
        if tag.type == "record":
            self.selected_slot = tag.slot
        if self.current == key and self.player.state["active"]:
            if self.player.state["paused"]:
                await self.player.resume()  # same tag put back after "pause on remove"
            return
        await self.play_item(tag.type, tag.target, tag.label)

    async def play_item(self, type: str, target: str, label: str = "") -> bool:
        if type == "record":
            files = list_slot(self.cfg, int(target))
            label = label or f"Aufnahme {int(target)}"
            self.selected_slot = int(target)
            if not files:
                self.flash(f"Slot {int(target)} leer - Aufnahme-Taste")
                self.notify()
                return False
        else:
            files = self.library.files_for(target)
            if not files:
                self.flash("Nicht gefunden")
                return False
            if not label:
                a = self.library.get(target)
                label = a.title if a else ""
        self.current = self.last_play = (type, target)
        await self.player.play_files(files, label)
        return True

    async def handle_tag_removed(self) -> None:
        mode = self.cfg.on_tag_remove
        if self.recorder.active or mode == "none":
            return
        if mode == "pause":
            await self.player.pause()
        elif mode == "stop":
            await self.stop()

    async def handle_button(self, name: str, kind: str) -> None:
        log.info("button %s %s", name, kind)
        if self.at_computer:
            self.flash("Speicher ist am Computer")
            return
        if name == "play_pause":
            if kind == "long":
                await self.stop()
            else:
                await self.toggle_play()
        elif name == "record":
            await self.toggle_record()
        elif name in ("prev", "next"):
            if kind == "long":
                step = self.cfg.volume_step * (1 if name == "next" else -1)
                await self.set_volume(self.player.state["volume"] + step)
            elif self.player.state["active"]:
                await (self.player.next() if name == "next" else self.player.prev())

    # ---- actions (also used by the web API) --------------------------
    async def toggle_play(self) -> None:
        if self.recorder.active:
            await self.toggle_record()
        elif self.player.state["active"]:
            await self.player.toggle_pause()
        elif self.last_play:
            await self.play_item(*self.last_play)

    async def stop(self) -> None:
        if self.recorder.active:
            await self._stop_recording()
        await self.player.stop()
        self.current = None
        self.notify()

    async def toggle_record(self) -> None:
        if self.recorder.active:
            await self._stop_recording()
            return
        if not self.selected_slot:
            self.flash("Aufnahme-Tag auflegen")
            return
        await self.player.stop()
        self.current = None
        try:
            await self.recorder.start(self.selected_slot)
        except Exception as e:
            log.exception("recording failed to start")
            self.flash(f"Aufnahme-Fehler: {e}")
            return
        self._rec_ticker = asyncio.create_task(self._rec_tick())
        self.notify()

    async def _stop_recording(self) -> None:
        path = await self.recorder.stop()
        if self._rec_ticker:
            self._rec_ticker.cancel()
            self._rec_ticker = None
        self.flash("Aufnahme gespeichert" if path else "Nichts aufgenommen")

    async def _rec_tick(self) -> None:
        while self.recorder.active:
            self.notify()
            await asyncio.sleep(1)

    async def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        await self.player.set_volume(volume)
        self.cfg.volume = volume
        try:
            save_persisted(self.cfg)
        except OSError:
            log.warning("could not persist volume (data partition read-only?)")

    def start_learn(self, type: str, target: str, label: str = "") -> None:
        self.learn = {"type": type, "target": target, "label": label}
        self.notify()

    def cancel_learn(self) -> None:
        self.learn = None
        self.notify()

    async def reload_data(self) -> None:
        """The data stick is back from the computer: it may have edited tags.json or the music folder."""
        self.tags.load()
        await asyncio.to_thread(self.library.scan)
        self.notify()
