"""UID -> target mapping, stored as tags.json on the data partition."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import atomic_write

TYPES = ("album", "track", "record")


def normalize_uid(uid: str) -> str:
    uid = uid.replace(":", "").replace(" ", "").upper()
    if not uid or any(c not in "0123456789ABCDEF" for c in uid) or len(uid) % 2:
        raise ValueError(f"invalid tag uid {uid!r}")
    return uid


@dataclass
class Tag:
    uid: str
    type: str  # album | track | record
    target: str  # relative path below music/ ; for "record": slot number as string
    label: str = ""

    def __post_init__(self) -> None:
        if self.type not in TYPES:
            raise ValueError(f"unknown tag type {self.type!r}")
        if self.type == "record":
            if not str(self.target).isdigit() or int(self.target) < 1:
                raise ValueError("record tag target must be a slot number >= 1")
            self.target = str(int(self.target))

    @property
    def slot(self) -> int:
        return int(self.target)


class TagStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._tags: dict[str, Tag] = {}
        self.load()

    def load(self) -> None:
        self._tags = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for uid, d in raw.items():
            try:
                self._tags[uid] = Tag(uid=uid, type=d["type"], target=str(d["target"]), label=d.get("label", ""))
            except (KeyError, ValueError):
                continue

    def save(self) -> None:
        data = {uid: {k: v for k, v in asdict(t).items() if k != "uid"} for uid, t in sorted(self._tags.items())}
        atomic_write(self.path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def get(self, uid: str) -> Tag | None:
        return self._tags.get(normalize_uid(uid))

    def set(self, uid: str, type: str, target: str, label: str = "") -> Tag:
        uid = normalize_uid(uid)
        # a target is assigned to one tag only: re-assigning moves it
        for other in [t for t in self._tags.values() if t.type == type and t.target == str(target) and t.uid != uid]:
            del self._tags[other.uid]
        tag = Tag(uid=uid, type=type, target=str(target), label=label)
        self._tags[uid] = tag
        self.save()
        return tag

    def delete(self, uid: str) -> bool:
        uid = normalize_uid(uid)
        if uid in self._tags:
            del self._tags[uid]
            self.save()
            return True
        return False

    def all(self) -> list[Tag]:
        return sorted(self._tags.values(), key=lambda t: (t.type, t.target))

    def for_target(self, type: str, target: str) -> Tag | None:
        return next((t for t in self._tags.values() if t.type == type and t.target == str(target)), None)
