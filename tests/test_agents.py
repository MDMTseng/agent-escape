"""Tests for agent memory, prompts, and brain interface."""

from unittest.mock import MagicMock, patch

import pytest

from agenttown.agents.memory import AgentMemory
from agenttown.agents.prompts import (
    AGENT_TOOLS,
    build_perception_message,
    build_system_prompt,
)
from agenttown.world.actions import Examine, Move, Wait


class TestAgentMemory:
    def test_record_and_recall(self):
        mem = AgentMemory()
        mem.record(tick=0, content="Saw a key", category="discovery")
        mem.record(tick=1, content="Talked to Bob", category="conversation")

        assert len(mem.all_entries()) == 2
        assert len(mem.recent(1)) == 1
        assert mem.recent(1)[0].content == "Talked to Bob"

    def test_by_category(self):
        mem = AgentMemory()
        mem.record(tick=0, content="A", category="observation")
        mem.record(tick=1, content="B", category="discovery")
        mem.record(tick=2, content="C", category="observation")

        obs = mem.by_category("observation")
        assert len(obs) == 2

    def test_max_entries_trim(self):
        mem = AgentMemory(max_entries=5)
        for i in range(10):
            mem.record(tick=i, content=f"Event {i}")
        assert len(mem.all_entries()) == 5
        assert mem.all_entries()[0].content == "Event 5"

    def test_summary(self):
        mem = AgentMemory()
        mem.record(tick=0, content="Found a note")
        summary = mem.summary()
        assert "Found a note" in summary

    def test_empty_summary(self):
        mem = AgentMemory()
        assert "No memories" in mem.summary()

    def test_clear(self):
        mem = AgentMemory()
        mem.record(tick=0, content="Something")
        mem.clear()
        assert len(mem.all_entries()) == 0


class TestPrompts:
    def test_build_system_prompt(self):
        prompt = build_system_prompt(
            name="Alice",
            description="A curious explorer",
            goal="Escape the room",
            memory_summary="No memories yet.",
        )
        assert "Alice" in prompt
        assert "curious explorer" in prompt
        assert "Escape the room" in prompt

    def test_build_perception_message(self):
        perception = {
            "tick": 5,
            "room": {"name": "Study", "description": "A dusty study"},
            "entities": [
                {"name": "Note", "state": "default"},
                {"name": "Door", "state": "locked"},
            ],
            "exits": [{"direction": "north", "name": "Wooden Door"}],
            "others": [{"name": "Bob"}],
            "inventory": [{"name": "Key"}],
            "recent_events": ["Alice picked up a key"],
        }
        msg = build_perception_message(perception)
        assert "Study" in msg
        assert "Note" in msg
        assert "Door (locked)" in msg
        assert "Bob" in msg
        assert "Key" in msg
        assert "picked up" in msg

    def test_perception_empty_fields(self):
        perception = {
            "tick": 0,
            "room": {"name": "Empty Room"},
            "entities": [],
            "exits": [],
            "others": [],
            "inventory": [],
            "recent_events": [],
        }
        msg = build_perception_message(perception)
        assert "nothing notable" in msg
        assert "nobody" in msg
        assert "empty" in msg

    def test_agent_tools_structure(self):
        """All tools must have name, description, and input_schema."""
        for tool in AGENT_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

        tool_names = {t["name"] for t in AGENT_TOOLS}
        assert tool_names == {"move", "pick_up", "drop", "use", "examine", "talk", "wait"}
