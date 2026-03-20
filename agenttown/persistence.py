"""SQLite-based game save/load persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agenttown.world.world import World

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS saves (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    tick             INTEGER NOT NULL,
    scenario         TEXT NOT NULL DEFAULT '',
    world_snapshot   TEXT NOT NULL,
    brain_snapshots  TEXT NOT NULL
);
"""


class GameStore:
    """Stores and retrieves game saves from SQLite."""

    def __init__(self, db_path: str = "agenttown_saves.db") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save(
        self,
        world: World,
        brains: dict[str, Any],
        scenario: str = "",
        name: str | None = None,
    ) -> int:
        """Save current game state. Returns the save ID."""
        tick = world.state.tick
        save_name = name or f"Tick {tick}"

        world_data = json.dumps(world.full_snapshot())
        brain_data = json.dumps({
            aid: brain.snapshot() for aid, brain in brains.items()
        })

        cur = self._conn.execute(
            "INSERT INTO saves (name, created_at, tick, scenario, world_snapshot, brain_snapshots) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                save_name,
                datetime.now(timezone.utc).isoformat(),
                tick,
                scenario,
                world_data,
                brain_data,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_saves(self) -> list[dict]:
        """List all saves (metadata only, no blobs)."""
        rows = self._conn.execute(
            "SELECT id, name, created_at, tick, scenario FROM saves ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def load(self, save_id: int) -> dict | None:
        """Load a save by ID. Returns parsed data or None."""
        row = self._conn.execute(
            "SELECT * FROM saves WHERE id = ?", (save_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "tick": row["tick"],
            "scenario": row["scenario"],
            "world_snapshot": json.loads(row["world_snapshot"]),
            "brain_snapshots": json.loads(row["brain_snapshots"]),
        }

    def latest(self) -> dict | None:
        """Load the most recent save, or None if no saves exist."""
        row = self._conn.execute(
            "SELECT id FROM saves ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return self.load(row["id"])

    def delete(self, save_id: int) -> bool:
        """Delete a save by ID."""
        cur = self._conn.execute("DELETE FROM saves WHERE id = ?", (save_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
