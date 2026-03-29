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
        assert "unsolved" in REFLECT_PROMPT.lower() or "puzzles" in REFLECT_PROMPT.lower()
        assert "missing" in REFLECT_PROMPT.lower()
        assert "failed" in REFLECT_PROMPT.lower() or "repeated" in REFLECT_PROMPT.lower()
        assert "prioritize" in REFLECT_PROMPT.lower() or "next" in REFLECT_PROMPT.lower()

    def test_reflect_prompt_format_fields(self):
        """Prompt must accept all five format fields."""
        result = REFLECT_PROMPT.format(
            name="Alice",
            goal="Escape",
            memories="T1:found key; T2:tried door",
            working_memory="code: 1847; door locked",
            action_history="T1 examine:door, T2 examine:key",
        )
        assert "Alice" in result
        assert "Escape" in result
        assert "T1:found key" in result
        assert "code: 1847" in result

    def test_reflect_prompt_compact(self):
        """Prompt should be compact (< 300 tokens ~ roughly < 1200 chars)."""
        assert len(REFLECT_PROMPT) < 1200


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
        brain.memory.record(tick=1, content="test")
        events = "The door is locked and won't open"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("BLOCKED:" in f or "FAILED:" in f for f in wm)

    def test_speech_not_extracted_as_facts(self):
        """Agent speech should NOT pollute working memory."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'Bob says to Alice: "Have you found the code yet? I need the digits!"'
        brain._extract_facts(agent, events, "talk", tick=1)
        wm = brain.memory.get_working_memory()
        combined = " ".join(wm).lower()
        assert "have you found" not in combined
        assert "i need the digits" not in combined

    def test_discovery_importance_5(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "The old painting reveals a hidden compartment with a golden key"
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("FOUND:" in f for f in wm)
        assert brain.memory._stream[-1].importance == 5

    def test_solved_tracked(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "Alice solves the ancient puzzle after entering the code"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("SOLVED:" in f for f in wm)

    def test_unlocked_tracked(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "Alice unlocks the chest with the brass key"
        brain._extract_facts(agent, events, "use", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("SOLVED:" in f for f in wm)
        assert brain.memory._stream[-1].importance == 5

    def test_codes_extracted(self):
        """Number codes should be extracted with CODE prefix."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'The inscription reads "The answer is 1847"'
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("CODE" in f and "1847" in f for f in wm)

    def test_quotes_extracted_with_context(self):
        """Quoted clues should be extracted with CLUE prefix."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'The wall has an inscription: "Seek the light beyond the shadow"'
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("Seek the light" in f for f in wm)
        assert any("CLUE" in f for f in wm)

    def test_keywords_extracted(self):
        """Single-quoted passwords/keywords should be extracted."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "The inscription reads: speak the word 'dr. eleanor voss' to the final ward."
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("KEYWORD" in f and "dr. eleanor voss" in f for f in wm)

    def test_examine_state_tracked(self):
        """Object states from examine should be tracked."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "Alice examines Victorian Combination Safe: It is unlocked."
        brain._extract_facts(agent, events, "examine", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("STATE:" in f and "unlocked" in f for f in wm)

    def test_wrong_code_failure_has_context(self):
        """Wrong code failures should include which code and which target."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'Alice enters "open" on Victorian Combination Safe. Wrong code!'
        brain._extract_facts(agent, events, "interact", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f and "open" in f for f in wm)

    def test_pickup_failure_has_context(self):
        """Pickup failures should say what couldn't be picked up."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = "Bob looks for 'Dr. Eleanor Voss's Journal' but can't find anything to pick up."
        brain._extract_facts(agent, events, "pick_up", tick=1)
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f and "journal" in f.lower() for f in wm)

    def test_facts_include_room_context(self):
        """Facts should include room location when available."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'Alice examines Inscription: "The code is 4219"'
        brain._extract_facts(agent, events, "examine", tick=1, room="The Grand Foyer")
        wm = brain.memory.get_working_memory()
        # Should have room tag in the fact
        assert any("Grand Foyer" in f for f in wm)

    def test_clue_includes_source_object(self):
        """Clues should reference which object they came from."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = 'Alice examines Ancient Tome: The text reads "Only the worthy may pass"'
        brain._extract_facts(agent, events, "examine", tick=1, room="Library")
        wm = brain.memory.get_working_memory()
        combined = " ".join(wm)
        assert "Ancient Tome" in combined
        assert "Only the worthy" in combined


class TestObservationExtractionAndMemoryGrading:
    """5 multi-tick scenarios testing the full observation→extraction→retrieval pipeline.

    Each scenario simulates a realistic sequence of game events, then judges:
      1. Are the RIGHT facts extracted to working memory?
      2. Are STALE/WRONG facts cleaned up?
      3. Does retrieval rank the most relevant memories highest?
      4. Does importance grading reflect event significance?
    """

    def _make_brain_and_agent(self, name="Alice"):
        import unittest.mock as mock
        with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
            with mock.patch("anthropic.Anthropic"):
                brain = LLMBrain(api_key="fake-key")
        agent = AgentState(name=name, room_id="r1", goal="Escape the room")
        return brain, agent

    # -----------------------------------------------------------------------
    # Scenario 1: Multi-room exploration — clues accumulate across rooms
    # -----------------------------------------------------------------------
    def test_scenario_1_multi_room_clue_accumulation(self):
        """Agent explores 3 rooms, finds clues in each. Working memory should
        hold clues from ALL rooms with room tags, and retrieval should surface
        room-specific clues when queried."""
        brain, agent = self._make_brain_and_agent()

        # Tick 1: Foyer — find inscription
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            'Alice examines Stone Tablet: The inscription reads "Three keys unlock the way"',
            "examine", tick=1, room="Grand Foyer",
        )

        # Tick 3: Library — find a code
        brain.memory.record(tick=3, content="test")
        brain._extract_facts(
            agent,
            'Alice examines Dusty Ledger: The final page shows the number 7734',
            "examine", tick=3, room="Library",
        )

        # Tick 5: Workshop — find a keyword
        brain.memory.record(tick=5, content="test")
        brain._extract_facts(
            agent,
            "Alice examines Rusted Plaque: It says to speak 'prometheus' at the gate.",
            "examine", tick=5, room="Workshop",
        )

        wm = brain.memory.get_working_memory()

        # JUDGE: All three clues should be in working memory
        assert any("Three keys" in f for f in wm), \
            "FAIL: Foyer inscription lost — clues must persist across rooms"
        assert any("7734" in f and "CODE" in f for f in wm), \
            "FAIL: Library code not extracted as CODE"
        assert any("prometheus" in f and "KEYWORD" in f for f in wm), \
            "FAIL: Workshop keyword not extracted as KEYWORD"

        # JUDGE: Room tags should be present for location context
        assert any("Grand Foyer" in f for f in wm), \
            "FAIL: Room tag missing — agent won't know WHERE the clue was"
        assert any("Library" in f for f in wm), \
            "FAIL: Library room tag missing"
        assert any("Workshop" in f for f in wm), \
            "FAIL: Workshop room tag missing"

        # JUDGE: Retrieval should surface library clue for code-related queries
        brain.memory.record(tick=5, content="Found code 7734 in Library ledger", importance=5)
        retrieved = brain.memory.retrieve(current_tick=6, query="enter code on safe", top_k=3)
        contents = [m.content for m in retrieved]
        assert any("7734" in c for c in contents), \
            "FAIL: Code memory not surfaced for code-related query"

    # -----------------------------------------------------------------------
    # Scenario 2: Failed attempts cleaned up after success
    # -----------------------------------------------------------------------
    def test_scenario_2_failure_cleanup_after_solve(self):
        """Agent tries wrong codes, then succeeds. Working memory should drop
        the FAILED entries once the puzzle is SOLVED."""
        brain, agent = self._make_brain_and_agent()

        # Tick 1: Wrong code attempt
        brain.memory.record(tick=1, content="tried wrong code on safe", importance=3)
        brain._extract_facts(
            agent,
            'Alice enters "1234" on Victorian Safe. Wrong code!',
            "interact", tick=1, room="Study",
        )
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f for f in wm), \
            "FAIL: Wrong code not tracked as FAILED"

        # Tick 3: Another wrong code
        brain._extract_facts(
            agent,
            'Alice enters "5678" on Victorian Safe. Wrong code!',
            "interact", tick=3, room="Study",
        )

        # Tick 5: Finally solves it
        brain.memory.record(tick=5, content="solved safe", importance=5)
        brain._extract_facts(
            agent,
            'Alice enters "9012" on Victorian Safe. The safe is now unlocked! Alice solves the Victorian Safe',
            "interact", tick=5, room="Study",
        )

        wm = brain.memory.get_working_memory()

        # JUDGE: SOLVED should be present
        assert any("SOLVED" in f for f in wm), \
            "FAIL: Solve event not recorded"

        # JUDGE: Old FAILED entries for the same puzzle should be cleaned
        failed_facts = [f for f in wm if "FAILED:" in f and "Victorian" in f]
        assert len(failed_facts) == 0, \
            f"FAIL: Stale FAILED facts not cleaned after solve: {failed_facts}"

        # JUDGE: Importance of the solve entry should be maximum
        assert brain.memory._stream[-1].importance == 5, \
            "FAIL: Solve event should have importance 5"

    # -----------------------------------------------------------------------
    # Scenario 3: Competing memories — importance vs recency in retrieval
    # -----------------------------------------------------------------------
    def test_scenario_3_importance_vs_recency_retrieval(self):
        """A critical discovery at tick 2 should still outrank trivial recent
        events at tick 20 when the query is relevant."""
        brain, agent = self._make_brain_and_agent()

        # Tick 2: Critical discovery — the master code
        brain.memory.record(
            tick=2,
            content="CRITICAL: Found master code 8421 engraved inside the clock",
            category="observation",
            importance=5,
        )

        # Ticks 5-19: Mundane events (moving, waiting, examining empty shelves)
        for t in range(5, 20):
            brain.memory.record(
                tick=t,
                content=f"Tick {t}: Walked around the hallway. Nothing new.",
                category="observation",
                importance=1,
            )

        # JUDGE: Query about codes — the critical memory should rank top-3
        retrieved = brain.memory.retrieve(current_tick=20, query="enter code on keypad", top_k=3)
        contents = [m.content for m in retrieved]
        assert any("8421" in c for c in contents), \
            f"FAIL: Critical code memory drowned by 15 trivial events. Got: {contents}"

        # JUDGE: The critical memory's score should beat the most recent trivial one
        all_scored = []
        for entry in brain.memory.all_entries():
            score = entry.retrieval_score(
                current_tick=20,
                query_keywords={"code", "keypad", "enter"},
            )
            all_scored.append((entry.content[:50], score))
        all_scored.sort(key=lambda x: x[1], reverse=True)
        assert "8421" in all_scored[0][0], \
            f"FAIL: Code memory not top-ranked. Top was: {all_scored[0]}"

    # -----------------------------------------------------------------------
    # Scenario 4: Collaborative play — speech filtered, shared clues kept
    # -----------------------------------------------------------------------
    def test_scenario_4_collaborative_speech_filtering(self):
        """Two agents talk. Speech itself should NOT pollute working memory,
        but system events containing codes/clues from the conversation context
        SHOULD be extracted."""
        brain, agent = self._make_brain_and_agent("Alice")

        # Tick 1: Bob speaks — raw speech should be filtered
        brain.memory.record(tick=1, content="Bob spoke to Alice", importance=2)
        brain._extract_facts(
            agent,
            'Bob says to Alice: "Hey, have you checked the basement? I think the password might be hidden there."',
            "talk", tick=1, room="Foyer",
        )
        wm = brain.memory.get_working_memory()
        speech_fragments = [f for f in wm if "have you checked" in f.lower() or "i think" in f.lower()]
        assert len(speech_fragments) == 0, \
            f"FAIL: Raw speech polluting working memory: {speech_fragments}"

        # Tick 3: System event reveals code AFTER conversation
        brain._extract_facts(
            agent,
            'Alice examines Basement Panel: The display shows code 6319',
            "examine", tick=3, room="Basement",
        )
        wm = brain.memory.get_working_memory()
        assert any("6319" in f and "CODE" in f for f in wm), \
            "FAIL: Code from examine event not extracted after conversation"

        # Tick 5: Agent picks up an item Bob mentioned
        brain._extract_facts(
            agent,
            'Alice picks up the iron key from the shelf.',
            "pick_up", tick=5, room="Basement",
        )
        wm = brain.memory.get_working_memory()
        assert any("HAVE:" in f and "iron key" in f for f in wm), \
            "FAIL: Picked-up item not tracked in working memory"

        # JUDGE: Working memory should have actionable items, not chat noise
        for fact in wm:
            assert not fact.startswith('"'), \
                f"FAIL: Raw quote as fact — this is chat noise: {fact}"

    # -----------------------------------------------------------------------
    # Scenario 5: Full escape sequence — memory tells the story
    # -----------------------------------------------------------------------
    def test_scenario_5_full_escape_sequence_memory_coherence(self):
        """Simulate a complete 8-tick escape sequence. At the end, working
        memory + retrieval should give a coherent picture of what happened,
        what's solved, and what remains."""
        brain, agent = self._make_brain_and_agent()

        ticks = [
            # (tick, events, action, room, summary)
            (1, 'Alice examines Old Painting: Behind it is an inscription "The first is 4"',
             "examine", "Gallery",
             'Tick 1: examine. Results: Old Painting reveals inscription "The first is 4"'),
            (2, "Alice moves north and enters the Laboratory",
             "move", "Laboratory",
             "Tick 2: move. Alice enters Laboratory"),
            (3, 'Alice examines Microscope: A note reads "The second is 8"',
             "examine", "Laboratory",
             'Tick 3: examine. Results: Microscope note reads "The second is 8"'),
            (4, 'Alice enters "48" on Lab Keypad. Wrong code!',
             "interact", "Laboratory",
             'Tick 4: interact. Results: enters "48" on Lab Keypad, wrong code'),
            (5, 'Alice examines Chemical Shelf: A hidden note says "The third is 2"',
             "examine", "Laboratory",
             'Tick 5: examine. Results: Chemical Shelf note says "The third is 2"'),
            (6, 'Alice enters "482" on Lab Keypad. The keypad is now unlocked! Alice solves the Lab Keypad',
             "interact", "Laboratory",
             "Tick 6: interact. Results: solves Lab Keypad, keypad unlocked"),
            (7, "Alice picks up the crystal key from the unlocked cabinet.",
             "pick_up", "Laboratory",
             "Tick 7: pick_up. Results: picks up crystal key"),
            (8, "Alice uses crystal key on Exit Door. The Exit Door is now unlocked!",
             "use", "Gallery",
             "Tick 8: use. Results: crystal key unlocks Exit Door"),
        ]

        for tick, events, action, room, summary in ticks:
            brain.memory.record(tick=tick, content=summary, importance=3)
            brain._extract_facts(agent, events, action, tick=tick, room=room)

        wm = brain.memory.get_working_memory()
        wm_text = " ".join(wm)

        # JUDGE 1: Solved puzzles should be tracked
        assert any("SOLVED" in f for f in wm), \
            f"FAIL: No SOLVED marker after completing the puzzle. WM: {wm}"

        # JUDGE 2: The wrong code attempt (tick 4) should be cleaned up
        failed_keypad = [f for f in wm if "FAILED:" in f and "48" in f]
        assert len(failed_keypad) == 0, \
            f"FAIL: Stale wrong-code FAILED not cleaned after solve: {failed_keypad}"

        # JUDGE 3: Crystal key was used on the door — HAVE should be cleaned
        assert not any("HAVE:" in f and "crystal key" in f for f in wm), \
            f"FAIL: Crystal key HAVE persists after use. WM: {wm}"

        # JUDGE 4: Clue numbers should be extracted
        assert any("4" in f and ("CLUE" in f or "CODE" in f) for f in wm) or \
               any("482" in f for f in wm), \
            f"FAIL: Clue numbers from paintings/notes not tracked. WM: {wm}"

        # JUDGE 5: Memory stream should have correct importance gradient
        # The solve event (tick 6) and unlock (tick 8) should be high importance
        stream = brain.memory.all_entries()
        solve_entries = [e for e in stream if e.tick == 6]
        assert any(e.importance >= 4 for e in solve_entries), \
            f"FAIL: Solve tick should have high importance. Got: {[(e.content[:40], e.importance) for e in solve_entries]}"

        # JUDGE 6: Retrieval for "use key on door" should surface the crystal key memory
        retrieved = brain.memory.retrieve(current_tick=9, query="use key on exit door", top_k=5)
        contents = [m.content for m in retrieved]
        top_5_text = " ".join(contents)
        assert "crystal key" in top_5_text.lower() or "exit door" in top_5_text.lower() or "key" in top_5_text.lower(), \
            f"FAIL: Key/door memories not surfaced for door query. Got: {contents}"


class TestWorkingMemoryOverflowAndDedup:
    """Edge cases: overflow cap, deduplication, state replacement."""

    def _make_brain_and_agent(self, name="Alice"):
        import unittest.mock as mock
        with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
            with mock.patch("anthropic.Anthropic"):
                brain = LLMBrain(api_key="fake-key")
        agent = AgentState(name=name, room_id="r1", goal="Escape the room")
        return brain, agent

    def test_working_memory_cap_at_10(self):
        """When >10 facts accumulate, oldest facts are dropped, newest kept."""
        brain, agent = self._make_brain_and_agent()
        # Seed 8 existing facts
        brain.memory.update_working_memory([f"OLD_FACT_{i}" for i in range(8)])

        # Add events that generate 4+ new facts → total > 10
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            (
                'Alice examines Shelf: "First clue here"\n'
                'Alice examines Desk: "Second clue here"\n'
                'Alice examines Box: The combination is 9999\n'
                "Alice picks up the silver ring from the floor."
            ),
            "examine", tick=1, room="Vault",
        )

        wm = brain.memory.get_working_memory()
        assert len(wm) <= 10, f"Working memory exceeded cap: {len(wm)} facts"
        # Newest facts (from this tick) should survive
        assert any("9999" in f for f in wm), "Newest code fact dropped"
        assert any("silver ring" in f for f in wm), "Newest pickup fact dropped"

    def test_duplicate_codes_not_repeated(self):
        """Same code found twice should not appear twice in working memory."""
        brain, agent = self._make_brain_and_agent()

        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, 'Alice examines Panel: The code is 4455', "examine", tick=1,
        )
        brain._extract_facts(
            agent, 'Alice examines Panel: The code is 4455', "examine", tick=2,
        )

        wm = brain.memory.get_working_memory()
        code_facts = [f for f in wm if "4455" in f and "CODE" in f]
        assert len(code_facts) == 1, f"Duplicate code facts: {code_facts}"

    def test_duplicate_clues_not_repeated(self):
        """Same quoted clue appearing twice should only be stored once."""
        brain, agent = self._make_brain_and_agent()

        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, 'The wall reads "Beneath the moonlight lies the truth"',
            "examine", tick=1,
        )
        brain._extract_facts(
            agent, 'The wall reads "Beneath the moonlight lies the truth"',
            "examine", tick=2,
        )

        wm = brain.memory.get_working_memory()
        moonlight_facts = [f for f in wm if "Beneath the moonlight" in f]
        assert len(moonlight_facts) == 1, f"Duplicate clue: {moonlight_facts}"

    def test_state_replacement_locked_to_unlocked(self):
        """STATE facts for the same object should be replaced, not stacked."""
        brain, agent = self._make_brain_and_agent()

        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "Alice examines Iron Door: It is locked", "examine", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert any("STATE:" in f and "locked" in f for f in wm)

        # Later: same door is now unlocked
        brain._extract_facts(
            agent, "Alice examines Iron Door: It is unlocked", "examine", tick=5,
        )
        wm = brain.memory.get_working_memory()
        state_facts = [f for f in wm if "STATE:" in f and "Iron Door" in f]
        assert len(state_facts) == 1, f"State not replaced, got both: {state_facts}"
        assert "unlocked" in state_facts[0], f"Old locked state not overwritten: {state_facts[0]}"

    def test_blocked_cleanup_after_unlock(self):
        """BLOCKED fact should be removed when the door's STATE becomes unlocked."""
        brain, agent = self._make_brain_and_agent()

        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "The iron gate is locked. Alice can't pass through.",
            "move", tick=1, room="Corridor",
        )
        wm = brain.memory.get_working_memory()
        assert any("BLOCKED:" in f for f in wm), f"BLOCKED not recorded: {wm}"

        # Later: gate is unlocked via state event
        brain._extract_facts(
            agent, "Alice examines iron gate: It is unlocked",
            "examine", tick=5, room="Corridor",
        )
        wm = brain.memory.get_working_memory()
        blocked_facts = [f for f in wm if "BLOCKED:" in f and "iron gate" in f.lower()]
        assert len(blocked_facts) == 0, f"BLOCKED not cleaned after unlock: {blocked_facts}"


class TestRetrievalScoringEdgeCases:
    """Granular tests for the recency × importance × relevance scoring formula."""

    def test_recency_decay_curve(self):
        """Verify exponential decay: score at age 0 = 1.0, drops with age."""
        entry = MemoryEntry(tick=10, content="test", importance=5)
        assert entry.recency_score(current_tick=10) == 1.0
        score_5 = entry.recency_score(current_tick=15)
        score_20 = entry.recency_score(current_tick=30)
        assert score_5 > score_20, "Older memory should have lower recency"
        # 0.95^5 ≈ 0.774, 0.95^20 ≈ 0.358
        assert abs(score_5 - 0.95**5) < 0.001
        assert abs(score_20 - 0.95**20) < 0.001

    def test_recency_never_negative(self):
        """Even with future ticks, recency should not go negative."""
        entry = MemoryEntry(tick=100, content="test", importance=3)
        # current_tick < entry.tick → age clamped to 0
        assert entry.recency_score(current_tick=50) == 1.0

    def test_importance_normalization(self):
        """Importance 1-5 maps to 0.2-1.0 in the score formula."""
        low = MemoryEntry(tick=0, content="boring", importance=1)
        high = MemoryEntry(tick=0, content="critical", importance=5)
        # At same tick, no query → relevance=0.5 for both
        low_score = low.retrieval_score(current_tick=0)
        high_score = high.retrieval_score(current_tick=0)
        assert high_score / low_score == 5.0, "Importance 5 should score 5x importance 1"

    def test_keyword_relevance_exact_match(self):
        """Keyword overlap should boost relevance score significantly."""
        from agenttown.agents.memory import _keyword_relevance, _extract_keywords
        # Perfect overlap
        score_high = _keyword_relevance(
            "Found the brass key behind painting",
            {"brass", "key", "painting"},
        )
        # No overlap
        score_zero = _keyword_relevance(
            "Wind blows through the hallway",
            {"brass", "key", "painting"},
        )
        assert score_high > 0.5, f"High overlap should score > 0.5, got {score_high}"
        assert score_zero < 0.3, f"No overlap should score low, got {score_zero}"

    def test_keyword_relevance_partial_match(self):
        """Partial keyword overlap should give intermediate scores."""
        from agenttown.agents.memory import _keyword_relevance
        score = _keyword_relevance(
            "The old painting hides a secret passage",
            {"painting", "code", "safe", "keypad"},
        )
        # 1 out of 4 keywords match → moderate score
        assert 0.0 < score < 1.0, f"Partial overlap should be intermediate: {score}"

    def test_retrieval_empty_stream(self):
        """Retrieve on empty memory should return empty list, not crash."""
        mem = AgentMemory()
        retrieved = mem.retrieve(current_tick=10, query="anything", top_k=5)
        assert retrieved == []

    def test_retrieval_fewer_than_top_k(self):
        """If stream has fewer entries than top_k, return all of them."""
        mem = AgentMemory()
        mem.record(tick=1, content="Only one", importance=3)
        retrieved = mem.retrieve(current_tick=2, top_k=10)
        assert len(retrieved) == 1

    def test_reflection_always_ranks_high(self):
        """Reflections (importance=5) should consistently rank near the top."""
        mem = AgentMemory()
        # 10 low-importance filler events
        for t in range(10):
            mem.record(tick=t, content=f"Walked around aimlessly {t}", importance=1)
        # One reflection at tick 5
        mem.add_reflection(tick=5, content="I need to find the hidden key in the garden")

        retrieved = mem.retrieve(current_tick=10, query="find key garden", top_k=3)
        contents = [m.content for m in retrieved]
        assert any("hidden key" in c for c in contents), \
            f"Reflection not in top 3: {contents}"

    def test_very_old_high_importance_vs_recent_low(self):
        """At extreme age gaps, even high importance loses to very recent events."""
        mem = AgentMemory()
        mem.record(tick=0, content="Ancient critical discovery", importance=5)
        # 100 ticks later
        mem.record(tick=100, content="Just noticed something here", importance=3)

        retrieved = mem.retrieve(current_tick=100, top_k=1)
        # 0.95^100 ≈ 0.006 → ancient: 0.006 * 1.0 * 0.5 = 0.003
        # recent: 1.0 * 0.6 * 0.5 = 0.3
        assert retrieved[0].tick == 100, \
            "At 100 ticks distance, recency decay should dominate"


class TestMemoryStreamIntegrity:
    """Tests for stream trimming, persistence, and prompt building coherence."""

    def test_stream_trim_preserves_newest(self):
        """When stream overflows, the oldest entries are dropped."""
        mem = AgentMemory(max_stream=5)
        for i in range(8):
            mem.record(tick=i, content=f"Event {i}", importance=3)
        entries = mem.all_entries()
        assert len(entries) == 5
        assert entries[0].content == "Event 3"
        assert entries[-1].content == "Event 7"

    def test_snapshot_roundtrip(self):
        """Memory state should survive serialize → deserialize."""
        mem = AgentMemory()
        mem.update_working_memory(["code is 999", "door locked"])
        mem.record(tick=1, content="Found key", category="discovery", importance=5)
        mem.record(tick=2, content="Used key", category="observation", importance=4)
        mem.add_reflection(tick=3, content="Need to check basement")

        snap = mem.snapshot()
        restored = AgentMemory.from_snapshot(snap)

        assert restored.get_working_memory() == ["code is 999", "door locked"]
        assert len(restored.all_entries()) == 3  # 2 records + 1 reflection in stream
        assert len(restored.get_reflections()) == 1
        assert restored.get_reflections()[0].content == "Need to check basement"

    def test_snapshot_preserves_importance(self):
        """Importance values must survive snapshot roundtrip."""
        mem = AgentMemory()
        mem.record(tick=1, content="trivial", importance=1)
        mem.record(tick=2, content="critical", importance=5)

        restored = AgentMemory.from_snapshot(mem.snapshot())
        entries = restored.all_entries()
        assert entries[0].importance == 1
        assert entries[1].importance == 5

    def test_build_memory_prompt_includes_all_tiers(self):
        """Prompt should include working memory, reflection, and retrieved memories."""
        mem = AgentMemory()
        mem.update_working_memory(["the password is 'aurora'"])
        mem.record(tick=1, content="Examined the vault door", importance=4)
        mem.record(tick=2, content="Found combination 3721", importance=5)
        mem.add_reflection(tick=3, content="Try the code on the vault next")

        prompt = mem.build_memory_prompt(current_tick=4, query="vault code")
        assert "aurora" in prompt, "Working memory missing from prompt"
        assert "vault" in prompt.lower(), "Retrieved memories missing"
        assert "Plan:" in prompt, "Reflection missing from prompt"

    def test_should_reflect_timing(self):
        """Reflection triggers after reflect_every ticks of recording."""
        mem = AgentMemory(reflect_every=3)
        assert not mem.should_reflect()

        mem.record(tick=1, content="A")
        mem.record(tick=2, content="B")
        assert not mem.should_reflect()

        mem.record(tick=3, content="C")
        assert mem.should_reflect()

        # After reflection, counter resets
        mem.add_reflection(tick=4, content="Reflected")
        assert not mem.should_reflect()

        # Count resumes
        mem.record(tick=5, content="D")
        mem.record(tick=6, content="E")
        mem.record(tick=7, content="F")
        assert mem.should_reflect()


class TestExtractionEdgeCases:
    """Edge cases in _extract_facts: empty input, multi-event, mixed signals."""

    def _make_brain_and_agent(self, name="Alice"):
        import unittest.mock as mock
        with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
            with mock.patch("anthropic.Anthropic"):
                brain = LLMBrain(api_key="fake-key")
        agent = AgentState(name=name, room_id="r1", goal="Escape the room")
        return brain, agent

    def test_empty_events_no_crash(self):
        """Empty event string should not crash or add junk facts."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(agent, "", "wait", tick=1)
        wm = brain.memory.get_working_memory()
        # Should be empty or contain only pre-existing facts
        assert all(f.strip() for f in wm), f"Junk facts from empty events: {wm}"

    def test_no_room_tag_when_room_empty(self):
        """Facts should not have empty bracket tags when room is not provided."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, 'Alice examines Note: "The secret word is hidden"',
            "examine", tick=1, room="",
        )
        wm = brain.memory.get_working_memory()
        for f in wm:
            assert not f.startswith("["), f"Empty room tag present: {f}"

    def test_multi_event_single_tick(self):
        """Multiple events in one tick should all be extracted."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = (
            'Alice examines Clock: The time shows 1147\n'
            'Alice picks up the ruby gem from the pedestal.\n'
            'Alice examines Painting: "Follow the stars to the north"'
        )
        brain._extract_facts(agent, events, "examine", tick=1, room="Hall")

        wm = brain.memory.get_working_memory()
        assert any("1147" in f and "CODE" in f for f in wm), f"Code not extracted: {wm}"
        assert any("ruby gem" in f and "HAVE:" in f for f in wm), f"Pickup not extracted: {wm}"
        assert any("Follow the stars" in f for f in wm), f"Clue not extracted: {wm}"

    def test_room_enter_tracked_for_correct_agent(self):
        """Only the named agent's room entries should be tracked."""
        brain, agent = self._make_brain_and_agent("Alice")
        brain.memory.record(tick=1, content="test")
        events = "Alice enters the Dungeon. Bob enters the Tower."
        brain._extract_facts(agent, events, "move", tick=1)

        wm = brain.memory.get_working_memory()
        assert any("VISITED:" in f and "dungeon" in f.lower() for f in wm), \
            f"Alice's room entry not tracked: {wm}"
        # Bob's entry should NOT be tracked as Alice's visited room
        bob_visited = [f for f in wm if "VISITED:" in f and "tower" in f.lower()]
        assert len(bob_visited) == 0, f"Bob's room entry tracked as Alice's: {bob_visited}"

    def test_mixed_speech_and_system_events(self):
        """Speech should be filtered but system events on the same line should survive."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        events = (
            'Bob says to Alice: "I found nothing useful"\n'
            'Alice examines Safe: The combination lock shows code 5522\n'
            'Carol says: "Anyone need help?"'
        )
        brain._extract_facts(agent, events, "examine", tick=1, room="Office")

        wm = brain.memory.get_working_memory()
        # System event code should be extracted
        assert any("5522" in f for f in wm), f"Code from system event lost: {wm}"
        # Speech content should NOT be in facts
        combined = " ".join(wm).lower()
        assert "nothing useful" not in combined, "Speech leaked into working memory"
        assert "anyone need help" not in combined, "Speech leaked into working memory"

    def test_importance_stays_at_2_for_mundane_events(self):
        """Events with no special patterns should get baseline importance 2."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test", importance=2)
        brain._extract_facts(
            agent, "The wind blows gently through the window.",
            "wait", tick=1,
        )
        # Last stream entry importance should be 2 (default, nothing interesting)
        assert brain.memory._stream[-1].importance == 2

    def test_examine_filters_boring_descriptions(self):
        """Examine results without key words (unlock, code, etc.) should not be stored."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "Alice examines Wooden Chair: A plain wooden chair. Nothing special.",
            "examine", tick=1,
        )
        wm = brain.memory.get_working_memory()
        examined_facts = [f for f in wm if "EXAMINED" in f and "Chair" in f]
        assert len(examined_facts) == 0, f"Boring examine stored as fact: {examined_facts}"

    def test_short_quotes_ignored(self):
        """Quoted strings shorter than 5 chars should not be extracted as clues."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        # Short quote alone — should be ignored (< 5 chars)
        brain._extract_facts(
            agent, 'The label says "Hi".',
            "examine", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert not any("Hi" in f and "CLUE" in f for f in wm), "Short quote extracted as CLUE"

        # Long quote alone — should be extracted
        brain._extract_facts(
            agent, 'The wall inscription reads "The treasure lies beneath the oak tree"',
            "examine", tick=2,
        )
        wm = brain.memory.get_working_memory()
        assert any("treasure lies beneath" in f for f in wm), f"Long quote missed: {wm}"

    def test_codes_must_be_3_plus_digits(self):
        """1-2 digit numbers should not be extracted as codes."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "Room 42 has shelf 7, but also keypad code 8831.",
            "examine", tick=1,
        )
        wm = brain.memory.get_working_memory()
        code_facts = [f for f in wm if "CODE" in f]
        assert any("8831" in f for f in code_facts), f"4-digit code missed: {wm}"
        assert not any("42" in f and "CODE" in f for f in wm), "2-digit extracted as code"


class TestLogicHoles:
    """Tests that expose logic holes in _extract_facts — each starts FAILING,
    then we fix the production code to make them pass."""

    def _make_brain_and_agent(self, name="Alice"):
        import unittest.mock as mock
        with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
            with mock.patch("anthropic.Anthropic"):
                brain = LLMBrain(api_key="fake-key")
        agent = AgentState(name=name, room_id="r1", goal="Escape the room")
        return brain, agent

    # -------------------------------------------------------------------
    # HOLE 1: System narration with "says:" stripped as agent speech
    # The speech regex treats "The inscription says: 'moonlight'" as
    # agent speech and erases the clue entirely.
    # -------------------------------------------------------------------
    def test_hole1_system_narration_says_not_stripped(self):
        """System narration like 'The inscription says: ...' should NOT be
        stripped as agent speech. Only 'AgentName says:' should be stripped."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            "The ancient inscription says: 'moonlight' is the password to the vault.",
            "examine", tick=1, room="Crypt",
        )
        wm = brain.memory.get_working_memory()
        assert any("moonlight" in f for f in wm), \
            f"HOLE 1: System narration 'says:' stripped as speech — keyword lost. WM: {wm}"

    # -------------------------------------------------------------------
    # HOLE 2: Importance overwrite — pickup(=4) clobbers discovery(=5)
    # The pickup section uses `importance = 4` instead of max().
    # -------------------------------------------------------------------
    def test_hole2_importance_not_clobbered_by_pickup(self):
        """When a discovery (importance=5) and pickup (importance=4) happen
        in the same tick, importance should stay at 5, not drop to 4."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test", importance=2)
        brain._extract_facts(
            agent,
            "The painting reveals a hidden chamber. Alice picks up the golden idol.",
            "examine", tick=1,
        )
        assert brain.memory._stream[-1].importance == 5, \
            f"HOLE 2: Importance dropped to {brain.memory._stream[-1].importance} — pickup overwrote discovery"

    # -------------------------------------------------------------------
    # HOLE 3: HAVE items persist after drop
    # No cleanup removes HAVE: facts when the agent drops the item.
    # -------------------------------------------------------------------
    def test_hole3_have_cleaned_after_drop(self):
        """HAVE: fact should be removed when the agent drops the item."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "Alice picks up the brass key.", "pick_up", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert any("HAVE:" in f and "brass key" in f for f in wm), "Precondition: HAVE recorded"

        brain._extract_facts(
            agent, "Alice drops the brass key.", "drop", tick=2,
        )
        wm = brain.memory.get_working_memory()
        have_facts = [f for f in wm if "HAVE:" in f and "brass key" in f]
        assert len(have_facts) == 0, \
            f"HOLE 3: HAVE persists after drop — agent thinks it still has item. {have_facts}"

    # -------------------------------------------------------------------
    # HOLE 4: HAVE items persist after being used (consumed)
    # Using a key on a door consumes it, but HAVE: stays.
    # -------------------------------------------------------------------
    def test_hole4_have_cleaned_after_use(self):
        """HAVE: fact should be removed when the item is used on something."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "Alice picks up the silver key.", "pick_up", tick=1,
        )

        brain._extract_facts(
            agent,
            "Alice uses silver key on Iron Door. The Iron Door is now unlocked!",
            "use", tick=2,
        )
        wm = brain.memory.get_working_memory()
        have_facts = [f for f in wm if "HAVE:" in f and "silver key" in f]
        assert len(have_facts) == 0, \
            f"HOLE 4: HAVE persists after use — agent will try to use consumed item again. {have_facts}"

    # -------------------------------------------------------------------
    # HOLE 5: False SOLVED from metaphorical "unlocks"
    # "unlocks a new understanding" is NOT a puzzle solve.
    # -------------------------------------------------------------------
    def test_hole5_metaphorical_unlock_not_solved(self):
        """Metaphorical uses of 'unlocks' should NOT trigger SOLVED.
        Only 'is now unlocked' or 'Agent unlocks ObjectName' should count."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            "The inscription unlocks a new understanding of the ancient language.",
            "examine", tick=1,
        )
        wm = brain.memory.get_working_memory()
        solved_facts = [f for f in wm if "SOLVED" in f]
        assert len(solved_facts) == 0, \
            f"HOLE 5: Metaphorical 'unlocks' created false SOLVED: {solved_facts}"
