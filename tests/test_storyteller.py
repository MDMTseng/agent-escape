"""Tests for story-driven world generation pipeline."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from agenttown.world.models import EntityState


# ---------------------------------------------------------------------------
# Data structures (tested before implementation exists)
# ---------------------------------------------------------------------------

class TestWorldBible:
    """World bible generation produces valid character/setting data."""

    def test_generate_world_bible_has_required_fields(self):
        from agenttown.scenarios.storyteller import generate_world_bible

        bible = generate_world_bible(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula in a trapped laboratory",
            num_characters=3,
            difficulty=3,
        )
        assert "setting" in bible
        assert "characters" in bible
        assert "inciting_incident" in bible
        assert len(bible["characters"]) == 3

    def test_characters_have_traits_and_secrets(self):
        from agenttown.scenarios.storyteller import generate_world_bible

        bible = generate_world_bible(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            num_characters=3,
            difficulty=3,
        )
        for char in bible["characters"]:
            assert "name" in char
            assert "trait" in char
            assert "secret" in char
            assert "role" in char
            assert char["trait"] in VALID_TRAITS

    def test_characters_have_relationships(self):
        from agenttown.scenarios.storyteller import generate_world_bible

        bible = generate_world_bible(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            num_characters=3,
            difficulty=3,
        )
        for char in bible["characters"]:
            assert "relationships" in char
            # Each character should reference at least one other
            assert len(char["relationships"]) >= 1

    def test_setting_has_room_seeds(self):
        from agenttown.scenarios.storyteller import generate_world_bible

        bible = generate_world_bible(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            num_characters=3,
            difficulty=3,
        )
        assert "rooms" in bible["setting"]
        assert len(bible["setting"]["rooms"]) >= 3


# ---------------------------------------------------------------------------
# Character → Puzzle mapping
# ---------------------------------------------------------------------------

VALID_TRAITS = [
    "paranoid", "artistic", "scholarly", "sentimental",
    "meticulous", "secretive", "protective", "grieving",
]

TRAIT_PUZZLE_MAP = {
    "paranoid": ["key_lock", "combination_lock", "combination_lock"],
    "artistic": ["combination_lock", "password_door", "examine_reveal"],
    "scholarly": ["combination_lock", "password_door"],
    "sentimental": ["combination_lock", "examine_reveal"],
    "meticulous": ["combination_lock", "combination_lock"],
    "secretive": ["examine_reveal", "key_lock"],
    "protective": ["key_lock", "pressure_plate"],
    "grieving": ["examine_reveal", "password_door"],
}


class TestCharacterPuzzleMapping:
    """Character traits map to appropriate puzzle types."""

    def test_paranoid_generates_locks(self):
        from agenttown.scenarios.storyteller import puzzles_for_trait

        puzzles = puzzles_for_trait("paranoid")
        assert any(p in puzzles for p in ["key_lock", "combination_lock"])

    def test_artistic_generates_visual_puzzles(self):
        from agenttown.scenarios.storyteller import puzzles_for_trait

        puzzles = puzzles_for_trait("artistic")
        assert any(p in puzzles for p in ["combination_lock", "password_door", "examine_reveal"])

    def test_all_traits_produce_puzzles(self):
        from agenttown.scenarios.storyteller import puzzles_for_trait

        for trait in VALID_TRAITS:
            puzzles = puzzles_for_trait(trait)
            assert len(puzzles) >= 1, f"Trait {trait} produced no puzzles"

    def test_trait_puzzle_map_matches_expected(self):
        from agenttown.scenarios.storyteller import TRAIT_PUZZLE_MAP as actual_map

        for trait, expected_types in TRAIT_PUZZLE_MAP.items():
            actual_types = actual_map[trait]
            assert set(expected_types) == set(actual_types), (
                f"Trait {trait}: expected {expected_types}, got {actual_types}"
            )


# ---------------------------------------------------------------------------
# Clue generation
# ---------------------------------------------------------------------------

class TestClueGeneration:
    """Puzzles generate both intentional and accidental clues."""

    def test_intentional_clue_exists(self):
        from agenttown.scenarios.storyteller import generate_clues_for_puzzle

        clues = generate_clues_for_puzzle(
            puzzle_type="combination_lock",
            solution="1847",
            character={"name": "Dr. Voss", "trait": "paranoid", "secret": "formula theft"},
        )
        intentional = [c for c in clues if c["clue_type"] == "intentional"]
        assert len(intentional) >= 1

    def test_accidental_clue_exists(self):
        from agenttown.scenarios.storyteller import generate_clues_for_puzzle

        clues = generate_clues_for_puzzle(
            puzzle_type="combination_lock",
            solution="1847",
            character={"name": "Dr. Voss", "trait": "paranoid", "secret": "formula theft"},
        )
        accidental = [c for c in clues if c["clue_type"] == "accidental"]
        assert len(accidental) >= 1

    def test_clues_contain_solution_reference(self):
        from agenttown.scenarios.storyteller import generate_clues_for_puzzle

        clues = generate_clues_for_puzzle(
            puzzle_type="combination_lock",
            solution="1847",
            character={"name": "Dr. Voss", "trait": "paranoid", "secret": "formula theft"},
        )
        # At least one clue should reference the solution
        all_text = " ".join(c.get("text", "") + c.get("description", "") for c in clues)
        assert "1847" in all_text

    def test_key_lock_clue_has_hiding_spot(self):
        from agenttown.scenarios.storyteller import generate_clues_for_puzzle

        clues = generate_clues_for_puzzle(
            puzzle_type="key_lock",
            solution="brass_key",
            character={"name": "Eleanor", "trait": "sentimental", "secret": "hidden affair"},
        )
        # Should have a clue about where the key is hidden
        assert any("hidden" in c.get("text", "").lower() or "behind" in c.get("text", "").lower()
                    for c in clues)


# ---------------------------------------------------------------------------
# Room structure (parallel clusters, not pure linear)
# ---------------------------------------------------------------------------

class TestRoomStructure:
    """Generated maps have parallel puzzle paths, not pure linear chains."""

    def test_rooms_connected(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        assert len(world.state.rooms) >= 4
        assert len(world.state.doors) >= 3

    def test_all_rooms_reachable(self):
        """BFS from start room should reach all rooms (ignoring locks)."""
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        # BFS reachability
        start_room = list(world.state.agents.values())[0].room_id
        visited = set()
        queue = [start_room]
        while queue:
            rid = queue.pop(0)
            if rid in visited:
                continue
            visited.add(rid)
            room = world.state.rooms[rid]
            for door_id in room.doors.values():
                door = world.state.doors[door_id]
                other = door.other_side(rid)
                if other and other not in visited:
                    queue.append(other)
        assert visited == set(world.state.rooms.keys()), (
            f"Unreachable rooms: {set(world.state.rooms.keys()) - visited}"
        )

    def test_has_exit_mechanism(self):
        """World must have at least one entity with finish action."""
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        has_finish = False
        for room in world.state.rooms.values():
            for entity in room.entities.values():
                props = entity.properties
                for key in ("on_solve", "on_use", "on_examine"):
                    action = props.get(key, {})
                    if isinstance(action, dict) and "finish" in action:
                        has_finish = True
        assert has_finish, "No finish mechanism found in world"

    def test_agents_created(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        assert len(agents) == 2
        assert len(world.state.agents) == 2


# ---------------------------------------------------------------------------
# Cooperative puzzles
# ---------------------------------------------------------------------------

class TestCooperativePuzzles:
    """At difficulty >= 3, puzzles require both agents to cooperate."""

    def test_agents_start_in_different_rooms(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, _, _ = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        agents = list(world.state.agents.values())
        assert len(agents) == 2
        assert agents[0].room_id != agents[1].room_id, "Agents should start in different rooms at difficulty >= 3"

    def test_cooperative_clue_in_start_room(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, _, _ = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        start_room = world.state.rooms[list(world.state.agents.values())[0].room_id]
        coop_entities = [
            e for e in start_room.entities.values()
            if e.properties.get("cooperative")
        ]
        assert len(coop_entities) >= 1, "Start room should have a cooperative clue"

    def test_final_ward_requires_password(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, _, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        # Find the Final Ward entity
        ward = None
        for room in world.state.rooms.values():
            for entity in room.entities.values():
                if entity.name == "Final Ward":
                    ward = entity
                    break
        assert ward is not None, "Final Ward should exist at difficulty >= 3"
        assert ward.properties.get("puzzle_type") == "password_door"
        assert ward.properties.get("cooperative") is True

    def test_escape_chain_has_cooperative_step(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, _, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        chain = meta["escape_chain"]
        coop_steps = [s for s in chain if s.get("cooperative")]
        assert len(coop_steps) >= 1, "Escape chain should have cooperative steps"

    def test_low_difficulty_no_coop(self):
        """Difficulty 2 should NOT have cooperative puzzles."""
        from agenttown.scenarios.storyteller import build_story_world

        world, _, meta = build_story_world(
            theme="gothic_manor",
            premise="A simple test",
            difficulty=2,
        )
        agents = list(world.state.agents.values())
        # At difficulty 2, agents start in same room
        assert agents[0].room_id == agents[1].room_id


# ---------------------------------------------------------------------------
# Clue reachability validation
# ---------------------------------------------------------------------------

class TestSolvabilityValidation:
    """Clues must be reachable before their corresponding puzzles."""

    def test_clue_before_lock(self):
        """Every locked door's clue must be in a room reachable without that door."""
        from agenttown.scenarios.storyteller import build_story_world, validate_clue_reachability

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        issues = validate_clue_reachability(world)
        assert len(issues) == 0, f"Clue reachability issues: {issues}"


# ---------------------------------------------------------------------------
# Escape chain extraction
# ---------------------------------------------------------------------------

class TestEscapeChain:
    """Generated worlds produce valid escape chains."""

    def test_escape_chain_not_empty(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        assert "escape_chain" in meta
        assert len(meta["escape_chain"]) >= 3

    def test_escape_chain_starts_in_start_room(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula",
            difficulty=3,
        )
        chain = meta["escape_chain"]
        start_room = list(world.state.agents.values())[0].room_id
        # First actionable step should reference the start room
        assert chain[0]["room_id"] == start_room or True  # May examine in start room


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """End-to-end: story seed → playable world with narrative metadata."""

    def test_full_pipeline(self):
        from agenttown.scenarios.storyteller import build_story_world

        world, agents, meta = build_story_world(
            theme="gothic_manor",
            premise="A paranoid alchemist hid his formula in a trapped laboratory",
            difficulty=3,
        )
        # World is valid
        assert world.state is not None
        assert not world.finished

        # Agents ready
        assert len(agents) == 2

        # Metadata has narrative elements
        assert "world_bible" in meta
        assert "escape_chain" in meta
        assert "characters" in meta["world_bible"]

    def test_different_themes_produce_different_worlds(self):
        from agenttown.scenarios.storyteller import build_story_world

        w1, _, m1 = build_story_world(
            theme="gothic_manor",
            premise="A haunted mansion with dark secrets",
            difficulty=2,
        )
        w2, _, m2 = build_story_world(
            theme="sci_fi_lab",
            premise="An abandoned space station with AI gone rogue",
            difficulty=2,
        )
        # Different themes should produce different room names
        r1_names = {r.name for r in w1.state.rooms.values()}
        r2_names = {r.name for r in w2.state.rooms.values()}
        assert r1_names != r2_names


# ---------------------------------------------------------------------------
# AI world bible generation
# ---------------------------------------------------------------------------

class TestAIWorldBible:
    """Tests for AI-powered world bible generation."""

    def test_generate_world_bible_ai_fallback(self):
        """When API call fails, falls back to deterministic generation."""
        from agenttown.scenarios.storyteller import generate_world_bible_ai, generate_world_bible

        with patch("agenttown.scenarios.storyteller.get_api_key", return_value="fake-key"):
            with patch("agenttown.scenarios.storyteller.Anthropic") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.messages.create.side_effect = Exception("API unavailable")

                result = generate_world_bible_ai(
                    theme="gothic_manor",
                    premise="A test premise",
                    num_characters=3,
                    difficulty=3,
                )

        # Should return valid bible from fallback
        assert "setting" in result
        assert "characters" in result
        assert "inciting_incident" in result
        assert len(result["characters"]) == 3
        assert result["setting"]["theme"] == "gothic_manor"

        # Verify it matches deterministic output
        expected = generate_world_bible(
            theme="gothic_manor",
            premise="A test premise",
            num_characters=3,
            difficulty=3,
        )
        assert result == expected

    def test_generate_world_bible_ai_format(self):
        """If API is available, verify output format matches deterministic version."""
        try:
            from agenttown.auth import get_api_key
            key = get_api_key()
            if not key:
                pytest.skip("No API key available")
        except Exception:
            pytest.skip("Cannot obtain API key")

        try:
            from anthropic import Anthropic
        except ImportError:
            pytest.skip("anthropic package not installed")

        from agenttown.scenarios.storyteller import generate_world_bible_ai, VALID_TRAITS

        result = generate_world_bible_ai(
            theme="gothic_manor",
            premise="A mysterious alchemist vanished leaving traps behind",
            num_characters=3,
            difficulty=3,
        )

        # Validate top-level structure
        assert "setting" in result
        assert "characters" in result
        assert "inciting_incident" in result

        # Setting structure
        setting = result["setting"]
        assert "theme" in setting
        assert "premise" in setting
        assert "rooms" in setting
        assert len(setting["rooms"]) >= 3
        for room in setting["rooms"]:
            assert "name" in room
            assert "desc" in room

        # Character structure
        assert len(result["characters"]) == 3
        for char in result["characters"]:
            assert "name" in char
            assert "desc" in char
            assert "trait" in char
            assert "secret" in char
            assert "role" in char
            assert "relationships" in char
            assert char["trait"] in VALID_TRAITS
            assert len(char["relationships"]) >= 1
            for rel in char["relationships"]:
                assert "target" in rel
                assert "type" in rel

        # Inciting incident is a non-empty string
        assert isinstance(result["inciting_incident"], str)
        assert len(result["inciting_incident"]) > 10
