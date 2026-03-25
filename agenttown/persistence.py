"""SQLite-based game save/load persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agenttown.world.world import World

_SCHEMA_STORIES = """\
CREATE TABLE IF NOT EXISTS stories (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    theme            TEXT NOT NULL DEFAULT '',
    premise          TEXT NOT NULL DEFAULT '',
    difficulty       INTEGER NOT NULL DEFAULT 3,
    world_bible      TEXT NOT NULL DEFAULT '{}',
    escape_chain     TEXT NOT NULL DEFAULT '[]',
    initial_snapshot TEXT NOT NULL DEFAULT '{}',
    brain_init       TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    last_played_at   TEXT
);
"""

_SCHEMA_SAVES = """\
CREATE TABLE IF NOT EXISTS saves (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id         INTEGER REFERENCES stories(id) ON DELETE CASCADE,
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
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute(_SCHEMA_STORIES)
        self._conn.execute(_SCHEMA_SAVES)
        # Add story_id column to saves if it doesn't exist (migration)
        try:
            self._conn.execute("SELECT story_id FROM saves LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE saves ADD COLUMN story_id INTEGER REFERENCES stories(id)")
        self._conn.commit()

    # --- Story management ---

    def create_story(
        self,
        title: str,
        theme: str,
        premise: str,
        difficulty: int,
        world_bible: dict,
        escape_chain: list,
        world: World,
        brains: dict[str, Any],
    ) -> int:
        """Create a new story and save its initial state. Returns story ID."""
        now = datetime.now(timezone.utc).isoformat()
        world_data = json.dumps(world.full_snapshot())
        brain_data = json.dumps({aid: b.snapshot() for aid, b in brains.items()})

        cur = self._conn.execute(
            "INSERT INTO stories (title, theme, premise, difficulty, world_bible, "
            "escape_chain, initial_snapshot, brain_init, created_at, last_played_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, theme, premise, difficulty, json.dumps(world_bible),
             json.dumps(escape_chain), world_data, brain_data, now, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_stories(self) -> list[dict]:
        """List all stories with save counts."""
        rows = self._conn.execute(
            "SELECT s.id, s.title, s.theme, s.premise, s.difficulty, "
            "s.created_at, s.last_played_at, "
            "(SELECT COUNT(*) FROM saves sv WHERE sv.story_id = s.id) as save_count, "
            "(SELECT MAX(sv.tick) FROM saves sv WHERE sv.story_id = s.id) as max_tick "
            "FROM stories s ORDER BY s.last_played_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_story(self, story_id: int) -> dict | None:
        """Get full story data including saves."""
        row = self._conn.execute(
            "SELECT * FROM stories WHERE id = ?", (story_id,)
        ).fetchone()
        if not row:
            return None
        saves = self._conn.execute(
            "SELECT id, name, created_at, tick FROM saves WHERE story_id = ? ORDER BY tick DESC",
            (story_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "title": row["title"],
            "theme": row["theme"],
            "premise": row["premise"],
            "difficulty": row["difficulty"],
            "world_bible": json.loads(row["world_bible"]),
            "escape_chain": json.loads(row["escape_chain"]),
            "initial_snapshot": json.loads(row["initial_snapshot"]),
            "brain_init": json.loads(row["brain_init"]),
            "created_at": row["created_at"],
            "last_played_at": row["last_played_at"],
            "saves": [dict(s) for s in saves],
        }

    def delete_story(self, story_id: int) -> bool:
        """Delete a story and all its saves."""
        self._conn.execute("DELETE FROM saves WHERE story_id = ?", (story_id,))
        cur = self._conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def touch_story(self, story_id: int) -> None:
        """Update last_played_at timestamp."""
        self._conn.execute(
            "UPDATE stories SET last_played_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), story_id),
        )
        self._conn.commit()

    # --- Save management ---

    def save(
        self,
        world: World,
        brains: dict[str, Any],
        scenario: str = "",
        name: str | None = None,
        story_id: int | None = None,
    ) -> int:
        """Save current game state. Returns the save ID."""
        tick = world.state.tick
        save_name = name or f"Tick {tick}"

        world_data = json.dumps(world.full_snapshot())
        brain_data = json.dumps({
            aid: brain.snapshot() for aid, brain in brains.items()
        })

        cur = self._conn.execute(
            "INSERT INTO saves (story_id, name, created_at, tick, scenario, world_snapshot, brain_snapshots) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                story_id,
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

    def list_saves(self, story_id: int | None = None) -> list[dict]:
        """List saves (metadata only, no blobs). Optionally filter by story."""
        if story_id is not None:
            rows = self._conn.execute(
                "SELECT id, story_id, name, created_at, tick, scenario FROM saves "
                "WHERE story_id = ? ORDER BY id DESC", (story_id,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, story_id, name, created_at, tick, scenario FROM saves ORDER BY id DESC"
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
