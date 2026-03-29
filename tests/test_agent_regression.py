"""Regression guard for agent observation extraction and memory grading.

Every test here was written to expose a specific bug that was found and fixed.
If any test fails, it means a regression was introduced in the extraction or
memory scoring logic.

Bug catalog:
  REG-01  Speech regex stripped system narration ("The inscription says:")
  REG-02  Importance overwrite: pickup(=4) clobbered discovery(=5) in same tick
  REG-03  HAVE: facts persisted after agent dropped the item
  REG-04  HAVE: facts persisted after agent used (consumed) the item
  REG-05  Metaphorical "unlocks" triggered false SOLVED facts
  REG-06  FAILED cleanup missed room-tag prefix ("[Lab] FAILED:...")
  REG-07  FAILED cleanup couldn't cross-match target object after "on"
  REG-08  BLOCKED cleanup truncated object name, preventing STATE match
"""

import unittest.mock as mock

from agenttown.agents.brain import LLMBrain
from agenttown.agents.memory import AgentMemory, MemoryEntry, _keyword_relevance
from agenttown.world.models import AgentState


def _make_brain_and_agent(name: str = "Alice"):
    """Create a brain (bypassing API client) and a test agent."""
    with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
        with mock.patch("anthropic.Anthropic"):
            brain = LLMBrain(api_key="fake-key")
    agent = AgentState(name=name, room_id="r1", goal="Escape the room")
    return brain, agent


# ---------------------------------------------------------------------------
# REG-01: System narration with "says:" must NOT be stripped as agent speech
# ---------------------------------------------------------------------------

class TestReg01SystemNarrationSays:
    """The inscription/sign/statue 'says:' is narration, not agent speech."""

    def test_inscription_says_keyword_preserved(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            "The ancient inscription says: 'moonlight' is the password to the vault.",
            "examine", tick=1, room="Crypt",
        )
        wm = brain.memory.get_working_memory()
        assert any("moonlight" in f for f in wm), \
            f"Keyword from system narration lost: {wm}"

    def test_sign_says_quote_preserved(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            'The wooden sign says: "Beware the guardian of the eastern wing"',
            "examine", tick=1, room="Entrance",
        )
        wm = brain.memory.get_working_memory()
        assert any("Beware the guardian" in f for f in wm), \
            f"Quote from sign narration lost: {wm}"

    def test_agent_speech_still_stripped(self):
        """Actual agent speech (capitalized name + says:) should still be filtered."""
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            'Bob says to Alice: "I think the answer is somewhere in the library"',
            "talk", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert not any("answer is somewhere" in f.lower() for f in wm), \
            f"Agent speech leaked into facts: {wm}"


# ---------------------------------------------------------------------------
# REG-02: Importance must use max(), never overwrite downward
# ---------------------------------------------------------------------------

class TestReg02ImportanceOverwrite:

    def test_discovery_then_pickup_keeps_importance_5(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test", importance=2)
        brain._extract_facts(
            agent,
            "The painting reveals a hidden chamber. Alice picks up the golden idol.",
            "examine", tick=1,
        )
        assert brain.memory._stream[-1].importance == 5

    def test_code_then_pickup_keeps_importance_5(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test", importance=2)
        brain._extract_facts(
            agent,
            "The keypad displays 9921. Alice picks up the note.",
            "examine", tick=1,
        )
        assert brain.memory._stream[-1].importance == 5


# ---------------------------------------------------------------------------
# REG-03 / REG-04: HAVE cleanup on drop and use
# ---------------------------------------------------------------------------

class TestReg03Reg04HaveCleanup:

    def test_have_removed_after_drop(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(agent, "Alice picks up the brass key.", "pick_up", tick=1)
        assert any("HAVE:" in f and "brass key" in f for f in brain.memory.get_working_memory())

        brain._extract_facts(agent, "Alice drops the brass key.", "drop", tick=2)
        wm = brain.memory.get_working_memory()
        assert not any("HAVE:" in f and "brass key" in f for f in wm), \
            f"HAVE persists after drop: {wm}"

    def test_have_removed_after_use(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(agent, "Alice picks up the silver key.", "pick_up", tick=1)

        brain._extract_facts(
            agent,
            "Alice uses silver key on Iron Door. The Iron Door is now unlocked!",
            "use", tick=2,
        )
        wm = brain.memory.get_working_memory()
        assert not any("HAVE:" in f and "silver key" in f for f in wm), \
            f"HAVE persists after use: {wm}"

    def test_other_items_survive_targeted_drop(self):
        """Dropping one item should not affect other HAVE facts."""
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(agent, "Alice picks up the torch.", "pick_up", tick=1)
        brain._extract_facts(agent, "Alice picks up the compass.", "pick_up", tick=2)
        brain._extract_facts(agent, "Alice drops the torch.", "drop", tick=3)

        wm = brain.memory.get_working_memory()
        assert not any("HAVE:" in f and "torch" in f for f in wm), "Torch not cleaned"
        assert any("HAVE:" in f and "compass" in f for f in wm), "Compass wrongly cleaned"


# ---------------------------------------------------------------------------
# REG-05: Metaphorical "unlocks" must NOT trigger SOLVED
# ---------------------------------------------------------------------------

class TestReg05FalseSolved:

    def test_metaphorical_unlocks_no_solved(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            "The inscription unlocks a new understanding of the ancient language.",
            "examine", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert not any("SOLVED" in f for f in wm), f"False SOLVED: {wm}"

    def test_real_agent_unlock_still_works(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            "Alice unlocks the treasure chest with the golden key.",
            "use", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert any("SOLVED" in f for f in wm), f"Real SOLVED not tracked: {wm}"

    def test_passive_unlock_still_works(self):
        """'is now unlocked' should always trigger SOLVED."""
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            "The gate is now unlocked after the lever is pulled.",
            "interact", tick=1,
        )
        wm = brain.memory.get_working_memory()
        assert any("SOLVED" in f for f in wm), f"Passive unlock not tracked: {wm}"


# ---------------------------------------------------------------------------
# REG-06 / REG-07: FAILED cleanup with room-tag prefix and cross-object matching
# ---------------------------------------------------------------------------

class TestReg06Reg07FailedCleanup:

    def test_failed_with_room_tag_cleaned_after_solve(self):
        """[Room] FAILED: ... should be cleaned when puzzle is later SOLVED."""
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            'Alice enters "999" on Vault Keypad. Wrong code!',
            "interact", tick=1, room="Vault",
        )
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f for f in wm), "Precondition: FAILED recorded"

        brain.memory.record(tick=5, content="test")
        brain._extract_facts(
            agent,
            "Alice solves the Vault Keypad after entering the correct code.",
            "interact", tick=5, room="Vault",
        )
        wm = brain.memory.get_working_memory()
        assert not any("FAILED:" in f and "Vault" in f for f in wm), \
            f"FAILED with room tag not cleaned: {wm}"

    def test_failed_cross_object_matching(self):
        """FAILED fact 'code X on SafeName' should be cleaned when SafeName is SOLVED."""
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent,
            'Alice enters "abc" on Crystal Safe. Wrong code!',
            "interact", tick=1, room="Study",
        )
        brain.memory.record(tick=3, content="test")
        brain._extract_facts(
            agent,
            "Alice solves the Crystal Safe.",
            "interact", tick=3, room="Study",
        )
        wm = brain.memory.get_working_memory()
        assert not any("FAILED:" in f and "Crystal" in f for f in wm), \
            f"FAILED not cleaned via cross-object match: {wm}"


# ---------------------------------------------------------------------------
# REG-08: BLOCKED cleanup with proper object name extraction
# ---------------------------------------------------------------------------

class TestReg08BlockedCleanup:

    def test_blocked_cleaned_after_state_unlocked(self):
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "The iron gate is locked. Alice can't pass through.",
            "move", tick=1, room="Corridor",
        )
        assert any("BLOCKED:" in f for f in brain.memory.get_working_memory())

        brain._extract_facts(
            agent, "Alice examines iron gate: It is unlocked",
            "examine", tick=5, room="Corridor",
        )
        wm = brain.memory.get_working_memory()
        assert not any("BLOCKED:" in f and "iron gate" in f.lower() for f in wm), \
            f"BLOCKED persists after unlock: {wm}"

    def test_blocked_with_room_tag_cleaned(self):
        """Room-tagged BLOCKED facts should also be cleaned."""
        brain, agent = _make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "The oak door is locked.",
            "move", tick=1, room="Library",
        )
        brain._extract_facts(
            agent, "Alice examines oak door: It is unlocked",
            "examine", tick=3, room="Library",
        )
        wm = brain.memory.get_working_memory()
        assert not any("BLOCKED:" in f and "oak door" in f.lower() for f in wm), \
            f"Room-tagged BLOCKED not cleaned: {wm}"


# ---------------------------------------------------------------------------
# Composite regression: full multi-tick scenario touching all fixed bugs
# ---------------------------------------------------------------------------

class TestRegressionComposite:
    """End-to-end scenario that would have failed before all 8 fixes."""

    def test_full_game_with_all_edge_cases(self):
        brain, agent = _make_brain_and_agent()

        # T1: System narration gives keyword (REG-01)
        brain.memory.record(tick=1, content="T1: examine", importance=2)
        brain._extract_facts(
            agent,
            "The statue says: speak 'celestial' to open the vault.",
            "examine", tick=1, room="Temple",
        )

        # T2: Pick up a key (sets up REG-03/04)
        brain.memory.record(tick=2, content="T2: pick_up", importance=2)
        brain._extract_facts(
            agent, "Alice picks up the jade key.", "pick_up", tick=2, room="Temple",
        )

        # T3: Wrong code on door (sets up REG-06/07)
        brain.memory.record(tick=3, content="T3: interact", importance=2)
        brain._extract_facts(
            agent,
            'Alice enters "wrong" on Temple Gate. Wrong code!',
            "interact", tick=3, room="Temple",
        )

        # T4: Discovery + pickup in same event string (REG-02 importance preserved)
        brain.memory.record(tick=4, content="T4: examine", importance=2)
        brain._extract_facts(
            agent,
            "The painting reveals a hidden map. Alice picks up the star gem from the pedestal.",
            "examine", tick=4, room="Temple",
        )

        # T5: Use key on door — consumed (REG-04), door unlocked (REG-08)
        brain.memory.record(tick=5, content="T5: use", importance=2)
        brain._extract_facts(
            agent,
            "Alice uses jade key on Temple Gate. The Temple Gate is now unlocked! "
            "Alice solves the Temple Gate.",
            "use", tick=5, room="Temple",
        )

        # T6: Metaphorical unlock (REG-05)
        brain.memory.record(tick=6, content="T6: examine", importance=2)
        brain._extract_facts(
            agent,
            "The mural unlocks a deeper appreciation of the temple's history.",
            "examine", tick=6, room="Inner Temple",
        )

        wm = brain.memory.get_working_memory()

        # REG-01: Keyword from narration survived
        assert any("celestial" in f for f in wm), f"REG-01 regression: {wm}"

        # REG-02: Discovery importance not clobbered
        t4_entries = [e for e in brain.memory.all_entries() if e.tick == 4]
        assert any(e.importance >= 5 for e in t4_entries), f"REG-02 regression: {t4_entries}"

        # REG-03/04: Jade key HAVE cleaned after use
        assert not any("HAVE:" in f and "jade key" in f for f in wm), f"REG-04 regression: {wm}"

        # Star gem still in inventory (not dropped/used)
        assert any("HAVE:" in f and "star gem" in f for f in wm), f"Star gem lost: {wm}"

        # REG-05: No false SOLVED from mural
        mural_solved = [f for f in wm if "SOLVED" in f and "mural" in f.lower()]
        assert len(mural_solved) == 0, f"REG-05 regression: {mural_solved}"

        # REG-06/07: Wrong code FAILED cleaned after solve
        failed = [f for f in wm if "FAILED:" in f and "Temple" in f]
        assert len(failed) == 0, f"REG-06/07 regression: {failed}"

        # Real SOLVED is present
        assert any("SOLVED" in f for f in wm), f"Real SOLVED missing: {wm}"


# ---------------------------------------------------------------------------
# Structured event path — tests that the new dispatcher produces the same
# facts as the regex path, but from structured event dicts.
# ---------------------------------------------------------------------------

class TestStructuredEventExtraction:
    """Verify that structured events produce correct facts without any regex."""

    def _make_brain_and_agent(self, name="Alice"):
        with mock.patch("agenttown.agents.brain.get_api_key", return_value="fake-key"):
            with mock.patch("anthropic.Anthropic"):
                brain = LLMBrain(api_key="fake-key")
        agent = AgentState(name=name, room_id="r1", goal="Escape the room")
        return brain, agent

    def test_pickup_via_structured(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "pick_up", tick=1, room="Hall",
            structured_events=[{"type": "pick_up", "item": "brass key"}],
        )
        wm = brain.memory.get_working_memory()
        assert any("HAVE:" in f and "brass key" in f for f in wm), f"WM: {wm}"

    def test_drop_cleans_have_via_structured(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "pick_up", tick=1, room="Hall",
            structured_events=[{"type": "pick_up", "item": "brass key"}],
        )
        brain._extract_facts(
            agent, "", "drop", tick=2, room="Hall",
            structured_events=[{"type": "drop", "item": "brass key"}],
        )
        wm = brain.memory.get_working_memory()
        assert not any("HAVE:" in f and "brass key" in f for f in wm), f"WM: {wm}"

    def test_examine_extracts_code(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "examine", tick=1, room="Vault",
            structured_events=[{
                "type": "examine",
                "target": "Ancient Dial",
                "text": "The dial shows the number 7734 engraved in gold.",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("CODE" in f and "7734" in f for f in wm), f"WM: {wm}"
        assert any("Ancient Dial" in f for f in wm), f"Source missing: {wm}"

    def test_examine_extracts_keyword(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "examine", tick=1, room="Temple",
            structured_events=[{
                "type": "examine",
                "target": "Stone Tablet",
                "text": "The inscription reads: speak 'prometheus' at the gate.",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("KEYWORD" in f and "prometheus" in f for f in wm), f"WM: {wm}"

    def test_examine_extracts_quote_clue(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "examine", tick=1, room="Library",
            structured_events=[{
                "type": "examine",
                "target": "Old Book",
                "text": 'The page reads "Seek the light beyond the shadow"',
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("Seek the light" in f and "CLUE" in f for f in wm), f"WM: {wm}"

    def test_examine_state_tracked(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "examine", tick=1, room="Hall",
            structured_events=[{
                "type": "examine",
                "target": "Iron Door",
                "text": "A heavy door. It is locked.",
                "state": "locked",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("STATE:" in f and "locked" in f for f in wm), f"WM: {wm}"

    def test_fail_wrong_code(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "interact", tick=1, room="Study",
            structured_events=[{
                "type": "fail",
                "target": "Victorian Safe",
                "code": "1234",
                "reason": "wrong_code",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("FAILED:" in f and "1234" in f and "Victorian Safe" in f for f in wm), f"WM: {wm}"

    def test_fail_locked_door(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "move", tick=1, room="Corridor",
            structured_events=[{
                "type": "fail",
                "target": "Iron Gate",
                "reason": "locked",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("BLOCKED:" in f and "Iron Gate" in f for f in wm), f"WM: {wm}"

    def test_use_solved(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "interact", tick=1, room="Lab",
            structured_events=[{
                "type": "use",
                "target": "Lab Keypad",
                "code": "482",
                "result": "solved",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("SOLVED" in f and "Lab Keypad" in f for f in wm), f"WM: {wm}"

    def test_use_key_consumes_and_solves(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        # First pick up the key
        brain._extract_facts(
            agent, "", "pick_up", tick=1, room="Hall",
            structured_events=[{"type": "pick_up", "item": "golden key"}],
        )
        # Then use it — consumed
        brain._extract_facts(
            agent, "", "use", tick=2, room="Hall",
            structured_events=[{
                "type": "use",
                "item": "golden key",
                "target": "Treasure Chest",
                "result": "unlocked",
                "consumed": True,
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("SOLVED" in f and "Treasure Chest" in f for f in wm), f"WM: {wm}"
        assert not any("HAVE:" in f and "golden key" in f for f in wm), \
            f"Consumed key still in HAVE: {wm}"

    def test_state_change_revealed(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "examine", tick=1, room="Gallery",
            structured_events=[{
                "type": "state_change",
                "change": "revealed",
                "target": "Hidden Compartment",
                "source": "Old Painting",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("FOUND:" in f and "Hidden Compartment" in f for f in wm), f"WM: {wm}"

    def test_move_tracks_visited(self):
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "move", tick=1, room="Laboratory",
            structured_events=[{
                "type": "move",
                "direction": "north",
                "room_name": "Laboratory",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert any("VISITED:" in f and "Laboratory" in f for f in wm), f"WM: {wm}"

    def test_no_false_solved_from_metaphorical_structured(self):
        """Structured events with type 'examine' should never produce SOLVED."""
        brain, agent = self._make_brain_and_agent()
        brain.memory.record(tick=1, content="test")
        brain._extract_facts(
            agent, "", "examine", tick=1, room="Temple",
            structured_events=[{
                "type": "examine",
                "target": "Mural",
                "text": "The mural unlocks a deeper understanding of ancient history.",
            }],
        )
        wm = brain.memory.get_working_memory()
        assert not any("SOLVED" in f for f in wm), f"False SOLVED from examine text: {wm}"

    def test_structured_full_sequence(self):
        """End-to-end: examine clue → wrong code → right code → use key."""
        brain, agent = self._make_brain_and_agent()

        # T1: Find code
        brain.memory.record(tick=1, content="T1")
        brain._extract_facts(agent, "", "examine", tick=1, room="Lab",
                             structured_events=[{
                                 "type": "examine", "target": "Dial",
                                 "text": "The code is 4821",
                             }])
        # T2: Wrong code
        brain.memory.record(tick=2, content="T2")
        brain._extract_facts(agent, "", "interact", tick=2, room="Lab",
                             structured_events=[{
                                 "type": "fail", "target": "Safe",
                                 "code": "9999", "reason": "wrong_code",
                             }])
        # T3: Right code
        brain.memory.record(tick=3, content="T3")
        brain._extract_facts(agent, "", "interact", tick=3, room="Lab",
                             structured_events=[
                                 {"type": "use", "target": "Safe", "code": "4821", "result": "solved"},
                                 {"type": "state_change", "change": "unlocked", "target": "Safe"},
                             ])

        wm = brain.memory.get_working_memory()
        assert any("CODE" in f and "4821" in f for f in wm), f"Code lost: {wm}"
        assert any("SOLVED" in f and "Safe" in f for f in wm), f"SOLVED missing: {wm}"
        # Wrong code FAILED should be cleaned
        assert not any("FAILED:" in f and "9999" in f for f in wm), \
            f"Stale FAILED not cleaned: {wm}"
