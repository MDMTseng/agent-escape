"""Tests for agent memory, prompts, and brain interface."""

from agenttown.agents.memory import AgentMemory, MemoryEntry
from agenttown.agents.prompts import (
    AGENT_TOOLS,
    build_perception_message,
    build_system_prompt,
)
from agenttown.agents.brain import _parse_json, _extract_key_outcomes, REFLECT_PROMPT, LLMBrain
from agenttown.world.models import AgentState


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

    # --- Relevance Scoring ---

    def test_relevance_boosts_matching_memories(self):
        mem = AgentMemory()
        mem.record(tick=5, content="Found brass key behind the painting", importance=4)
        mem.record(tick=5, content="Bob said hello to Alice", importance=4)

        # Query about painting — should rank painting memory higher
        retrieved = mem.retrieve(current_tick=5, query="examine the old painting in workshop", top_k=2)
        assert retrieved[0].content == "Found brass key behind the painting"

    def test_relevance_with_no_query_is_neutral(self):
        mem = AgentMemory()
        mem.record(tick=5, content="Found key", importance=5)
        mem.record(tick=5, content="Talked to Bob", importance=3)

        # No query — falls back to recency × importance only
        retrieved = mem.retrieve(current_tick=5, top_k=2)
        assert retrieved[0].content == "Found key"  # higher importance wins

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
        assert "workshop" in prompt

    def test_build_memory_prompt_empty(self):
        mem = AgentMemory()
        prompt = mem.build_memory_prompt(current_tick=0)
        assert "No memories" in prompt


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
        assert "locked" in msg
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
        assert "nothing" in msg
        assert "none" in msg
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

    def test_perception_shows_changes(self):
        """Changes should appear in the perception message."""
        perception = {
            "tick": 2,
            "room": {"name": "Hall", "description": "A grand hall"},
            "entities": [],
            "exits": [],
            "others": [],
            "inventory": [],
            "recent_events": [],
            "changes": ["Key is gone", "Bob arrived"],
        }
        msg = build_perception_message(perception)
        assert "Changes:" in msg
        assert "Key is gone" in msg
        assert "Bob arrived" in msg

    def test_perception_no_changes_no_line(self):
        """No changes should not produce a Changes line."""
        perception = {
            "tick": 0,
            "room": {"name": "Room"},
            "entities": [],
            "exits": [],
            "others": [],
            "inventory": [],
            "recent_events": [],
            "changes": [],
        }
        msg = build_perception_message(perception)
        assert "Changes:" not in msg

    def test_perception_shows_messages_for_agent(self):
        """Directed messages should appear in the perception message."""
        perception = {
            "tick": 2,
            "room": {"name": "Hall"},
            "entities": [],
            "exits": [],
            "others": [],
            "inventory": [],
            "recent_events": [],
            "messages_for_agent": ['Bob: "The code is 42"'],
        }
        msg = build_perception_message(perception)
        assert "Messages for you:" in msg
        assert "code is 42" in msg

    def test_perception_shows_observations_not_hints(self):
        """Hints should be labeled 'Observations:', not 'HINTS:'."""
        perception = {
            "tick": 1,
            "room": {"name": "Room"},
            "entities": [],
            "exits": [],
            "others": [],
            "inventory": [],
            "recent_events": [],
            "hints": ["The floor plate is slightly depressed."],
        }
        msg = build_perception_message(perception)
        assert "Observations:" in msg
        assert "HINTS:" not in msg

    def test_perception_shows_visited_and_explored_rooms(self):
        """Perception message should show visited vs explored rooms."""
        perception = {
            "tick": 3,
            "room": {"name": "Room C"},
            "entities": [],
            "exits": [],
            "others": [],
            "inventory": [],
            "recent_events": [],
            "visited_rooms": ["Room C"],
            "explored_rooms": ["Room A", "Room B"],
        }
        msg = build_perception_message(perception)
        assert "Visited rooms:" in msg
        assert "Fully explored rooms:" in msg
        assert "Room A" in msg
        assert "Room C" in msg


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


class TestReflectPrompt:
    def test_reflect_prompt_contains_key_questions(self):
        """The new reflect prompt should ask about unsolved puzzles, failures, etc."""
        assert "unsolved puzzles" in REFLECT_PROMPT.lower()
        assert "missing" in REFLECT_PROMPT.lower()
        assert "failed" in REFLECT_PROMPT.lower()
        assert "prioritize" in REFLECT_PROMPT.lower()

    def test_reflect_prompt_format_fields(self):
        """Prompt must accept all four format fields."""
        result = REFLECT_PROMPT.format(
            name="Alice",
            goal="Escape",
            memories="T1:found key; T2:tried door",
            working_memory="code: 1847; door locked",
        )
        assert "Alice" in result
        assert "Escape" in result
        assert "T1:found key" in result
        assert "code: 1847" in result

    def test_reflect_prompt_compact(self):
        """Prompt should be compact (< 200 tokens ~ roughly < 800 chars)."""
        assert len(REFLECT_PROMPT) < 800


class TestExtractKeyOutcomes:
    def test_extracts_solve_events(self):
        events = ["Alice solved the puzzle", "Nothing happened"]
        result = _extract_key_outcomes(events)
        assert "solved" in result.lower()

    def test_extracts_fail_events(self):
        events = ["Alice tries to open the door", "Bob can't reach the shelf"]
        result = _extract_key_outcomes(events)
        assert "tries to" in result
        assert "can't" in result

    def test_extracts_talk_events(self):
        events = ["Bob says: the code is hidden", "Wind blows"]
        result = _extract_key_outcomes(events)
        assert "says" in result

    def test_extracts_discovery_events(self):
        events = ["The painting reveals a secret passage"]
        result = _extract_key_outcomes(events)
        assert "reveals" in result

    def test_no_key_outcomes(self):
        events = ["Wind blows gently", "The room is quiet"]
        result = _extract_key_outcomes(events)
        assert result == ""

    def test_limits_to_four(self):
        events = [
            "Alice fails attempt 1",
            "Bob fails attempt 2",
            "Carol fails attempt 3",
            "Dave fails attempt 4",
            "Eve fails attempt 5",
        ]
        result = _extract_key_outcomes(events)
        assert result.count(";") <= 3  # max 4 items = max 3 semicolons


class TestExtractFactsImproved:
    """Test the improved _extract_facts with failure, communication, discovery, and solve tracking."""

    def _make_brain_and_agent(self):
        """Create a brain (bypassing API client) and a test agent."""
        # Patch to avoid needing a real API key
        import unittest.mock as mock
        with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
            with mock.patch("anthropic.Anthropic"):
                brain = LLMBrain(api_key="fake-key")
        agent = AgentState(name="Alice", room_id="r1", goal="Escape the room")
        return brain, agent

    def test_failed_actions_tracked(self):
        brain, agent = self._make_brain_and_agent()
        events = "Alice tries to open the heavy door but it won't budge"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f for f in wm)

    def test_cant_actions_tracked(self):
        brain, agent = self._make_brain_and_agent()
        events = "Alice can't reach the top shelf without a ladder"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f for f in wm)

    def test_locked_tracked(self):
        brain, agent = self._make_brain_and_agent()
        # Need stream entry for importance update
        brain.memory.record(tick=1, content="test")
        events = "The door is locked and won't open"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f for f in wm)

    def test_communication_tracked(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'Bob says: "The code is hidden behind the painting"'
        brain._extract_facts(agent, events, "talk", tick=1)
        wm = brain.memory.get_working_memory()
        # Should capture the speech content OR the quoted clue
        assert len(wm) > 0
        combined = " ".join(wm)
        assert "code" in combined.lower() or "painting" in combined.lower()

    def test_discovery_importance_5(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "The old painting reveals a hidden compartment with a golden key"
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("DISCOVERED:" in f for f in wm)
        # Importance should be 5
        assert brain.memory._stream[-1].importance == 5

    def test_solved_tracked(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "The ancient puzzle solved after entering the code"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("SOLVED:" in f for f in wm)

    def test_unlocked_tracked(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "Alice unlocked the chest with the brass key"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("SOLVED:" in f for f in wm)
        assert brain.memory._stream[-1].importance == 5

    def test_codes_still_extracted(self):
        """Verify legacy code extraction still works."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'The inscription reads "The answer is 1847"'
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("code: 1847" in f for f in wm)

    def test_quotes_still_extracted(self):
        """Verify legacy quote extraction still works."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'The wall has an inscription: "Seek the light beyond the shadow"'
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("Seek the light" in f for f in wm)
