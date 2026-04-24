"""Per-channel SQLite state store (DESIGN.md §11).

Every channel owns a dedicated SQLite file at
``/state/channel-{channel_number}.sqlite``. Tables:

* ``schema_version``: single row tracking the migration level.
* ``collections``: per-collection cursor + expression hash.
* ``recent_plays``: rolling play log used by ``random_with_memory``.
* ``runs``: per-channel run markers (outcome, counts).

All writes are wrapped in an explicit transaction; the database is opened in
WAL mode for crash-safety and concurrent read access.
"""

from __future__ import annotations

import hashlib
import random
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging import get_logger

logger = get_logger(__name__)

SCHEMA_VERSION = 1

RECENT_PLAYS_TTL_DAYS = 30


def expression_sha(canonical_expression: str) -> str:
    return hashlib.sha256(canonical_expression.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class CollectionState:
    name: str
    cursor: int
    expression_hash: str
    updated_at: str


class StateStore:
    """A per-channel SQLite state store.

    Use as a context manager to ensure commits/rollbacks. Concurrent access
    across processes is safe thanks to WAL mode; within a process, a single
    `StateStore` instance should be used serially.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # ---- lifecycle ----

    def open(self) -> None:
        if self._conn is not None:
            return
        self._conn = self._connect_or_recover(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._ensure_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "StateStore":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None and self._conn is not None:
                self._conn.commit()
            elif self._conn is not None:
                self._conn.rollback()
        finally:
            self.close()

    @staticmethod
    def _connect_or_recover(path: Path) -> sqlite3.Connection:
        """Open a connection, recovering from corruption by renaming the DB."""
        if path.exists():
            try:
                c = sqlite3.connect(path)
                cur = c.execute("PRAGMA integrity_check;")
                rows = [r[0] for r in cur.fetchall()]
                if rows != ["ok"]:
                    c.close()
                    ts = int(time.time())
                    corrupt = path.with_name(f"{path.name}.corrupt-{ts}")
                    shutil.move(str(path), str(corrupt))
                    logger.warning(
                        "corrupt state DB recovered",
                        extra={"event": "state.corrupt_recovered", "file": str(corrupt)},
                    )
                    return sqlite3.connect(path)
                return c
            except sqlite3.DatabaseError:
                ts = int(time.time())
                corrupt = path.with_name(f"{path.name}.corrupt-{ts}")
                shutil.move(str(path), str(corrupt))
                logger.warning(
                    "corrupt state DB recovered",
                    extra={"event": "state.corrupt_recovered", "file": str(corrupt)},
                )
                return sqlite3.connect(path)
        return sqlite3.connect(path)

    # ---- schema ----

    def _ensure_schema(self) -> None:
        assert self._conn is not None
        c = self._conn
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);"
        )
        row = c.execute("SELECT version FROM schema_version;").fetchone()
        current = int(row[0]) if row else 0
        if current == 0:
            self._apply_v1()
            c.execute("INSERT INTO schema_version(version) VALUES (?);", (SCHEMA_VERSION,))
        elif current != SCHEMA_VERSION:
            raise RuntimeError(
                f"state DB at {self.path} is schema v{current}; code expects v{SCHEMA_VERSION}"
            )
        c.commit()

    def _apply_v1(self) -> None:
        assert self._conn is not None
        c = self._conn
        c.executescript(
            """
            CREATE TABLE collections (
                name               TEXT PRIMARY KEY,
                cursor             INTEGER NOT NULL DEFAULT 0,
                expression_hash    TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            );
            CREATE TABLE recent_plays (
                collection         TEXT NOT NULL,
                item_id            TEXT NOT NULL,
                played_at          TEXT NOT NULL,
                PRIMARY KEY (collection, played_at, item_id)
            );
            CREATE INDEX recent_plays_by_collection
                ON recent_plays (collection, played_at DESC);
            CREATE TABLE runs (
                run_id             TEXT PRIMARY KEY,
                started_at         TEXT NOT NULL,
                finished_at        TEXT,
                outcome            TEXT,
                items_written      INTEGER,
                notes              TEXT
            );
            """
        )

    # ---- collection cursors ----

    def get_or_init_cursor(self, collection: str, expression_hash_: str) -> int:
        """Return current cursor; reset to 0 if the expression hash changed."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT cursor, expression_hash FROM collections WHERE name = ?;",
            (collection,),
        ).fetchone()
        now_iso = datetime.now().isoformat()
        if row is None:
            self._conn.execute(
                "INSERT INTO collections(name, cursor, expression_hash, updated_at) VALUES (?, 0, ?, ?);",
                (collection, expression_hash_, now_iso),
            )
            return 0
        if row["expression_hash"] != expression_hash_:
            logger.info(
                "expression changed; cursor reset",
                extra={"event": "state.cursor_reset", "collection": collection},
            )
            self._conn.execute(
                "UPDATE collections SET cursor = 0, expression_hash = ?, updated_at = ? WHERE name = ?;",
                (expression_hash_, now_iso, collection),
            )
            return 0
        return int(row["cursor"])

    def set_cursor(self, collection: str, cursor: int) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE collections SET cursor = ?, updated_at = ? WHERE name = ?;",
            (int(cursor), datetime.now().isoformat(), collection),
        )

    # ---- recent plays (for random_with_memory) ----

    def record_play(self, collection: str, item_id: str, played_at: datetime | None = None) -> None:
        assert self._conn is not None
        ts = (played_at or datetime.now()).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO recent_plays(collection, item_id, played_at) VALUES (?, ?, ?);",
            (collection, item_id, ts),
        )

    def last_n_ids(self, collection: str, n: int) -> set[str]:
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT item_id FROM recent_plays WHERE collection = ? ORDER BY played_at DESC LIMIT ?;",
            (collection, int(n)),
        ).fetchall()
        return {r["item_id"] for r in rows}

    def prune_recent_plays(self, older_than_days: int = RECENT_PLAYS_TTL_DAYS) -> int:
        assert self._conn is not None
        cutoff = (datetime.now() - _timedelta_days(older_than_days)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM recent_plays WHERE played_at < ?;",
            (cutoff,),
        )
        return cur.rowcount

    # ---- run markers ----

    def start_run(self, run_id: str, notes: str | None = None) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO runs(run_id, started_at, notes) VALUES (?, ?, ?);",
            (run_id, datetime.now().isoformat(), notes),
        )

    def finish_run(self, run_id: str, outcome: str, items_written: int, notes: str | None = None) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, outcome = ?, items_written = ?, notes = ? WHERE run_id = ?;",
            (datetime.now().isoformat(), outcome, int(items_written), notes, run_id),
        )

    def last_run(self) -> dict | None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1;"
        ).fetchone()
        return dict(row) if row else None


def _timedelta_days(n: int) -> Any:
    from datetime import timedelta

    return timedelta(days=int(n))


# ---------------------------------------------------------------------------
# Mode-specific cursor / selection helpers (DESIGN.md §11.3).
# ---------------------------------------------------------------------------


def pick_sequential(items: list[dict], cursor: int) -> tuple[dict, int]:
    """Return the next item and the new cursor (wraps modulo `len(items)`)."""
    if not items:
        raise ValueError("empty items")
    idx = cursor % len(items)
    return items[idx], (idx + 1) % len(items)


def pick_chronological(items: list[dict], cursor: int, sort_field: str = "PremiereDate") -> tuple[dict, int]:
    """Sort by `sort_field` (ascending) and advance a cursor through the list."""
    if not items:
        raise ValueError("empty items")
    ordered = sorted(items, key=lambda i: (i.get(sort_field) or "", i.get("Name") or ""))
    idx = cursor % len(ordered)
    return ordered[idx], (idx + 1) % len(ordered)


def pick_shuffle(items: list[dict], seed: int | None = None) -> dict:
    """Stateless shuffle: choose uniformly at random."""
    if not items:
        raise ValueError("empty items")
    rng = random.Random(seed)
    return rng.choice(items)


def pick_random_with_memory(
    items: list[dict], recent_ids: set[str], seed: int | None = None
) -> dict:
    """Exclude recently-played items; if everything is excluded, fall back."""
    if not items:
        raise ValueError("empty items")
    eligible = [i for i in items if i.get("Id") not in recent_ids]
    pool = eligible or items
    rng = random.Random(seed)
    return rng.choice(pool)


def pick_weighted_random(
    items: list[dict], weight_field: str, seed: int | None = None
) -> dict:
    """Stateless weighted pick using `weight_field`; missing weights are 1.0."""
    if not items:
        raise ValueError("empty items")
    rng = random.Random(seed)
    weights = [float(i.get(weight_field) or 1.0) for i in items]
    return rng.choices(items, weights=weights, k=1)[0]


__all__ = [
    "CollectionState",
    "RECENT_PLAYS_TTL_DAYS",
    "SCHEMA_VERSION",
    "StateStore",
    "expression_sha",
    "pick_chronological",
    "pick_random_with_memory",
    "pick_sequential",
    "pick_shuffle",
    "pick_weighted_random",
]
