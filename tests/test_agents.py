"""Tests for agent memory, prompts, and brain interface."""

from agenttown.agents.memory import AgentMemory, MemoryEntry
from agenttown.agents.prompts import (
    AGENT_TOOLS,
    build_perception_message,
    build_system_prompt,
)
from agenttown.agents.brain import _parse_json


class TestAgentMemory:
    def test_record_and_recall(self):
        mem = AgentMemory()
        mem.record(tick=0, content="Saw a key", category="discovery")
        mem.record(tick=1, content="Talked to Bob", category="dialogue")

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
        mem = AgentMemory(max_stream=5)
        for i in range(10):
            mem.record(tick=i, content=f"Event {i}")
        assert len(mem.all_entries()) == 5
        assert mem.all_entries()[0].content == "Event 5"

    def test_clear(self):
        mem = AgentMemory()
        mem.record(tick=0, content="Something")
        mem.update_working_memory(["fact 1"])
        mem.add_reflection(tick=0, content="reflection")
        mem.clear()
        assert len(mem.all_entries()) == 0
        assert len(mem.get_working_memory()) == 0
        assert len(mem.get_reflections()) == 0

    # --- Working Memory ---

    def test_working_memory(self):
        mem = AgentMemory(max_working=3)
        mem.update_working_memory(["code is 1847", "key behind painting", "Bob has the note"])
        assert len(mem.get_working_memory()) == 3
        assert "code is 1847" in mem.working_memory_text()

    def test_working_memory_trim(self):
        mem = AgentMemory(max_working=2)
        mem.update_working_memory(["a", "b", "c", "d"])
        assert len(mem.get_working_memory()) == 2

    def test_empty_working_memory(self):
        mem = AgentMemory()
        assert "No key facts" in mem.working_memory_text()

    # --- Retrieval Scoring ---

    def test_retrieval_scores_recent_higher(self):
        mem = AgentMemory()
        mem.record(tick=0, content="Old event", importance=3)
        mem.record(tick=10, content="New event", importance=3)

        retrieved = mem.retrieve(current_tick=10, top_k=2)
        # New event should score higher (more recent)
        assert retrieved[0].content == "New event"

    def test_retrieval_scores_important_higher(self):
        mem = AgentMemory()
        mem.record(tick=5, content="Routine", importance=1)
        mem.record(tick=5, content="Discovery!", importance=5)

        retrieved = mem.retrieve(current_tick=5, top_k=2)
        assert retrieved[0].content == "Discovery!"

    def test_retrieval_top_k(self):
        mem = AgentMemory()
        for i in range(20):
            mem.record(tick=i, content=f"Event {i}")
        retrieved = mem.retrieve(current_tick=20, top_k=5)
        assert len(retrieved) == 5

    # --- Reflections ---

    def test_reflections(self):
        mem = AgentMemory(reflect_every=3)
        for i in range(3):
            mem.record(tick=i, content=f"Event {i}")
        assert mem.should_reflect()

        mem.add_reflection(tick=3, content="I learned something important")
        assert not mem.should_reflect()  # reset after reflection
        assert len(mem.get_reflections()) == 1

        # Reflection also added to stream for retrieval
        assert any(e.category == "reflection" for e in mem.all_entries())

    def test_reflection_importance(self):
        mem = AgentMemory()
        mem.add_reflection(tick=5, content="Key insight")
        assert mem.get_reflections()[0].importance == 5

    # --- Prompt Building ---

    def test_build_memory_prompt(self):
        mem = AgentMemory()
        mem.update_working_memory(["code is 1847", "door is locked"])
        mem.record(tick=0, content="Found a note", importance=4)
        mem.add_reflection(tick=1, content="Need to find the workshop")

        prompt = mem.build_memory_prompt(current_tick=2)
        assert "code is 1847" in prompt
        assert "Found a note" in prompt
        assert "Need to find the workshop" in prompt
        assert "Working Memory" in prompt
        assert "Reflections" in prompt

    def test_build_memory_prompt_empty(self):
        mem = AgentMemory()
        prompt = mem.build_memory_prompt(current_tick=0)
        assert "No key facts" in prompt


class TestPrompts:
    def test_build_system_prompt(self):
        prompt = build_system_prompt(
            name="Alice",
            description="A curious explorer",
            goal="Escape the room",
            memory_summary="No key facts yet.",
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
        assert tool_names == {"move", "pick_up", "drop", "use", "examine", "talk", "interact", "combine"}


class TestParseJson:
    def test_plain_json(self):
        result = _parse_json('{"facts": ["code is 1847"], "importance": 4}')
        assert result["facts"] == ["code is 1847"]
        assert result["importance"] == 4

    def test_json_in_code_fence(self):
        result = _parse_json('```json\n{"facts": ["a"], "importance": 2}\n```')
        assert result["facts"] == ["a"]

    def test_invalid_json(self):
        result = _parse_json("not json at all")
        assert result is None

    def test_empty_string(self):
        result = _parse_json("")
        assert result is None
