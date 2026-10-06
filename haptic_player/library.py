"""Music library: albums = sub-directories of music/, single tracks = audio files directly in music/."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import AUDIO_EXTENSIONS, COVER_EXTENSIONS, COVER_NAMES

try:  # optional - falls back to file names
    import mutagen
except ImportError:  # pragma: no cover
    mutagen = None


class UnsafePath(ValueError):
    pass


def natural_key(s: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def is_audio(p: Path) -> bool:
    return p.suffix.lower() in AUDIO_EXTENSIONS and not p.name.startswith(".")


def safe_join(base: Path, rel: str) -> Path:
    """Resolve `rel` below `base`; reject anything escaping it (uploads, API paths)."""
    if rel.startswith("/") or "\x00" in rel:
        raise UnsafePath(rel)
    base = base.resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise UnsafePath(rel)
    return p


def pretty_title(p: Path) -> str:
    name = re.sub(r"^\d{1,3}[\s._-]+", "", p.stem)
    return name.replace("_", " ").strip() or p.stem


@dataclass
class Track:
    path: str  # relative to music dir
    title: str
    artist: str = ""
    duration: float = 0.0


@dataclass
class Album:
    path: str  # relative dir name ("" never used); for single files = the file path
    title: str
    tracks: list[Track] = field(default_factory=list)
    cover: str | None = None  # relative path of cover image, or None
    single: bool = False


def read_track(base: Path, p: Path) -> Track:
    title, artist, duration = pretty_title(p), "", 0.0
    if mutagen is not None:
        try:
            f = mutagen.File(p, easy=True)
            if f is not None:
                title = (f.get("title") or [title])[0]
                artist = (f.get("artist") or [""])[0]
                duration = float(getattr(f.info, "length", 0.0) or 0.0)
        except Exception:  # corrupt file: still list it
            pass
    return Track(path=p.relative_to(base).as_posix(), title=title, artist=artist, duration=duration)


def find_cover(base: Path, d: Path) -> str | None:
    for stem in COVER_NAMES:
        for ext in COVER_EXTENSIONS:
            for cand in (stem + ext, stem.capitalize() + ext):
                if (d / cand).is_file():
                    return (d / cand).relative_to(base).as_posix()
    return None


class Library:
    def __init__(self, music_dir: Path):
        self.music_dir = Path(music_dir)
        self.albums: list[Album] = []
        self.scan()

    def scan(self) -> None:
        base = self.music_dir
        albums: list[Album] = []
        if base.is_dir():
            for d in sorted((x for x in base.iterdir() if x.is_dir() and not x.name.startswith(".")), key=lambda x: natural_key(x.name)):
                files = sorted((f for f in d.rglob("*") if f.is_file() and is_audio(f)), key=lambda f: natural_key(f.relative_to(d).as_posix()))
                if files:
                    albums.append(Album(path=d.relative_to(base).as_posix(), title=d.name, tracks=[read_track(base, f) for f in files], cover=find_cover(base, d)))
            for f in sorted((x for x in base.iterdir() if x.is_file() and is_audio(x)), key=lambda x: natural_key(x.name)):
                t = read_track(base, f)
                albums.append(Album(path=t.path, title=t.title, tracks=[t], single=True))
        self.albums = albums

    def get(self, path: str) -> Album | None:
        return next((a for a in self.albums if a.path == path), None)

    def files_for(self, path: str) -> list[Path]:
        """Absolute file list to hand to the player for an album dir or single track path."""
        a = self.get(path)
        if a is not None:
            return [self.music_dir / t.path for t in a.tracks]
        # a track inside an album
        p = safe_join(self.music_dir, path)
        if p.is_file() and is_audio(p):
            return [p]
        return []

    def track(self, path: str) -> Track | None:
        for a in self.albums:
            for t in a.tracks:
                if t.path == path:
                    return t
        return None

    def as_dict(self) -> list[dict]:
        return [
            {
                "path": a.path,
                "title": a.title,
                "single": a.single,
                "cover": a.cover,
                "tracks": [{"path": t.path, "title": t.title, "artist": t.artist, "duration": t.duration} for t in a.tracks],
            }
            for a in self.albums
        ]

    def embedded_cover(self, rel: str) -> tuple[bytes, str] | None:
        """Embedded cover art of a track (mp3 APIC / flac picture / mp4 covr), if mutagen is present."""
        if mutagen is None:
            return None
        try:
            f = mutagen.File(safe_join(self.music_dir, rel))
        except Exception:
            return None
        if f is None:
            return None
        pics = getattr(f, "pictures", None)
        if pics:
            return pics[0].data, pics[0].mime or "image/jpeg"
        tags = getattr(f, "tags", None)
        if tags is not None:
            for key in tags.keys():
                if str(key).startswith("APIC"):
                    fr = tags[key]
                    return fr.data, fr.mime
            covr = tags.get("covr") if hasattr(tags, "get") else None
            if covr:
                return bytes(covr[0]), "image/jpeg"
        return None
