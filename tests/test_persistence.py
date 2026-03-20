"""Tests for SQLite persistence — save/load game state."""

import os
import tempfile

import pytest

from agenttown.agents.memory import AgentMemory, MemoryEntry
from agenttown.persistence import GameStore
from agenttown.scenarios.escape_room import build_escape_room
from agenttown.world.actions import Examine, Move, PickUp
from agenttown.world.world import World


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_saves.db")
    s = GameStore(db_path)
    yield s
    s.close()


@pytest.fixture
def world_and_brains():
    """Create a world with dummy brains that have snapshot/from_snapshot."""
    world, agent_ids = build_escape_room()

    # Use a simple mock brain with snapshot support
    class MockBrain:
        def __init__(self):
            self.memory = AgentMemory()
            self._message_history = {}
            self._model = "mock"

        def snapshot(self):
            return {
                "model": self._model,
                "memory": self.memory.snapshot(),
                "message_history": dict(self._message_history),
            }

        @classmethod
        def from_snapshot(cls, data):
            b = cls()
            b._model = data.get("model", "mock")
            b.memory = AgentMemory.from_snapshot(data["memory"])
            b._message_history = data.get("message_history", {})
            return b

    brains = {aid: MockBrain() for aid in agent_ids}
    return world, brains


class TestAgentMemorySnapshot:
    def test_roundtrip(self):
        mem = AgentMemory()
        mem.update_working_memory(["code is 1847", "key behind painting"])
        mem.record(tick=0, content="Found note", importance=4, category="discovery")
        mem.record(tick=1, content="Talked to Bob", importance=2, category="dialogue")
        mem.add_reflection(tick=2, content="Should go to workshop next")

        data = mem.snapshot()
        restored = AgentMemory.from_snapshot(data)

        assert restored.get_working_memory() == ["code is 1847", "key behind painting"]
        assert len(restored.all_entries()) == 3  # 2 records + 1 reflection
        assert restored.get_reflections()[0].content == "Should go to workshop next"
        assert restored._ticks_since_reflect == 0  # reset after reflection

    def test_empty_roundtrip(self):
        mem = AgentMemory()
        data = mem.snapshot()
        restored = AgentMemory.from_snapshot(data)
        assert len(restored.all_entries()) == 0
        assert len(restored.get_working_memory()) == 0


class TestWorldFullSnapshot:
    def test_roundtrip(self):
        world, _ = build_escape_room()
        alice = world.state.agents["alice"]

        # Do some actions
        world.process_action(Move(direction="east"), alice)
        world.process_action(Examine(target="Old Painting"), alice)
        world.process_action(PickUp(target="Brass Key"), alice)
        world.advance_tick()

        # Save
        data = world.full_snapshot()

        # Restore
        restored = World.from_full_snapshot(data)
        assert restored.tick == 1
        assert restored.state.agents["alice"].room_id == "workshop"
        assert restored.state.agents["alice"].has_item("brass key") is not None
        assert len(restored.event_log.all_events()) > 0


class TestGameStore:
    def test_save_and_load(self, store, world_and_brains):
        world, brains = world_and_brains
        brains["alice"].memory.update_working_memory(["test fact"])

        save_id = store.save(world, brains, "escape_room", "Test Save")
        assert save_id is not None

        loaded = store.load(save_id)
        assert loaded is not None
        assert loaded["name"] == "Test Save"
        assert loaded["tick"] == 0
        assert loaded["scenario"] == "escape_room"
        assert "alice" in loaded["brain_snapshots"]
        assert loaded["brain_snapshots"]["alice"]["memory"]["working"] == ["test fact"]

    def test_list_saves(self, store, world_and_brains):
        world, brains = world_and_brains
        store.save(world, brains, "escape_room", "Save 1")
        store.save(world, brains, "escape_room", "Save 2")

        saves = store.list_saves()
        assert len(saves) == 2
        assert saves[0]["name"] == "Save 2"  # most recent first
        assert saves[1]["name"] == "Save 1"

    def test_latest(self, store, world_and_brains):
        world, brains = world_and_brains
        store.save(world, brains, "escape_room", "First")
        world.advance_tick()
        store.save(world, brains, "escape_room", "Second")

        latest = store.latest()
        assert latest["name"] == "Second"
        assert latest["tick"] == 1

    def test_latest_empty(self, store):
        assert store.latest() is None

    def test_load_nonexistent(self, store):
        assert store.load(9999) is None

    def test_delete(self, store, world_and_brains):
        world, brains = world_and_brains
        save_id = store.save(world, brains, "escape_room")
        assert store.delete(save_id)
        assert store.load(save_id) is None

    def test_world_state_restored_correctly(self, store, world_and_brains):
        world, brains = world_and_brains
        alice = world.state.agents["alice"]

        # Progress the game
        world.process_action(Move(direction="east"), alice)
        world.advance_tick()

        save_id = store.save(world, brains, "escape_room", "After move")
        loaded = store.load(save_id)

        restored = World.from_full_snapshot(loaded["world_snapshot"])
        assert restored.state.agents["alice"].room_id == "workshop"
        assert restored.tick == 1
