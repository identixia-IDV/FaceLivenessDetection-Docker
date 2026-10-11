"""SQLite gallery for still 1:N identity.

The HTTP routes stay on the feature/match documents. Names and thumbnails
live here so the demo can join them by row id. VideoWorker uses the same id
as person_id.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None
_PATH: Path | None = None


@dataclass(frozen=True)
class Person:
    id: int
    name: str
    feature: str
    thumbnail: bytes | None
    created_at: int
    payload: str


def open_db(root: Path) -> None:
    global _CONN, _PATH
    path = Path(root) / "data" / "gallery.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if _CONN is not None and _PATH == path:
            return
        if _CONN is not None:
            _CONN.close()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                feature TEXT NOT NULL,
                thumbnail BLOB,
                created_at INTEGER NOT NULL,
                payload TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
        _CONN = conn
        _PATH = path


def _db() -> sqlite3.Connection:
    if _CONN is None:
        raise RuntimeError("gallery is not open")
    return _CONN


def add(name: str, feature: str, thumbnail: bytes | None, payload: str = "") -> int:
    trimmed = name.strip()
    if not trimmed or not feature:
        raise ValueError("name and feature are required")
    now = int(time.time() * 1000)
    with _LOCK:
        cur = _db().execute(
            "INSERT INTO people (name, feature, thumbnail, created_at, payload) VALUES (?, ?, ?, ?, ?)",
            (trimmed, feature, thumbnail, now, payload or ""),
        )
        _db().commit()
        return int(cur.lastrowid)


def get(index: int) -> Person | None:
    with _LOCK:
        row = _db().execute(
            "SELECT id, name, feature, thumbnail, created_at, payload FROM people WHERE id = ?",
            (int(index),),
        ).fetchone()
    if not row:
        return None
    return Person(*row)


def list_people() -> list[Person]:
    with _LOCK:
        rows = _db().execute(
            "SELECT id, name, feature, thumbnail, created_at, payload FROM people ORDER BY id"
        ).fetchall()
    return [Person(*row) for row in rows]


def delete(index: int) -> bool:
    with _LOCK:
        cur = _db().execute("DELETE FROM people WHERE id = ?", (int(index),))
        _db().commit()
        return cur.rowcount > 0


def clear() -> None:
    with _LOCK:
        _db().execute("DELETE FROM people")
        _db().commit()


def is_empty() -> bool:
    return not list_people()
