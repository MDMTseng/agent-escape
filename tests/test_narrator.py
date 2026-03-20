"""Tests for the Narrator module."""

from unittest.mock import MagicMock, patch

from agenttown.agents.narrator import (
    NARRATOR_SYSTEM_PROMPT,
    NARRATE_TEMPLATE,
    Narrator,
)
from agenttown.world.events import Event
from agenttown.world.models import AgentState, Room, WorldState


def _make_test_events():
    return [
        Event(
            tick=0, event_type="examine", actor_id="alice", room_id="r1",
            description="Alice examines the old painting.",
            visible_to=["alice"],
        ),
        Event(
            tick=0, event_type="state_change", actor_id="alice", room_id="r1",
            description="Brass Key is revealed!",
            visible_to=["alice"],
        ),
    ]


def _make_test_world():
    ws = WorldState()
    room = Room(id="r1", name="The Workshop", description="A cluttered workshop.")
    ws.add_room(room)
    agent = AgentState(id="alice", name="Alice", description="A curious explorer", room_id="r1")
    ws.add_agent(agent)
    return ws


def test_narrator_system_prompt_has_key_elements():
    assert "Ravenwood Manor" in NARRATOR_SYSTEM_PROMPT
    assert "third person" in NARRATOR_SYSTEM_PROMPT
    assert "sensory" in NARRATOR_SYSTEM_PROMPT


def test_narrate_empty_events():
    narrator = Narrator.__new__(Narrator)
    result = narrator.narrate([], WorldState(), tick=0)
    assert result == ""


def test_narrate_only_waits():
    narrator = Narrator.__new__(Narrator)
    events = [
        Event(tick=0, event_type="wait", actor_id="a1", room_id="r1",
              description="Alice waits.", visible_to=["a1"]),
    ]
    result = narrator.narrate(events, WorldState(), tick=0)
    assert "silent" in result.lower() or "dust" in result.lower()


def test_narrate_template_formatting():
    """Verify the template can be filled without errors."""
    result = NARRATE_TEMPLATE.format(
        room_descriptions="**Study**: A dusty room.",
        agent_descriptions="**Alice** (explorer) — in Study, carrying: nothing",
        tick=5,
        raw_events="- [examine] Alice examines the note.",
    )
    assert "Tick 5" in result
    assert "Alice examines" in result


@patch("agenttown.agents.narrator.OpenAI")
def test_narrate_calls_api(mock_openai_cls):
    """Verify narrator calls the API with correct structure."""
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "The dust swirled as Alice reached behind the painting."
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_cls.return_value = mock_client

    narrator = Narrator()
    events = _make_test_events()
    world = _make_test_world()

    result = narrator.narrate(events, world, tick=0)

    assert "painting" in result.lower()
    mock_client.chat.completions.create.assert_called_once()


@patch("agenttown.agents.narrator.OpenAI")
def test_narrate_fallback_on_error(mock_openai_cls):
    """On API error, narrator returns raw event descriptions."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API down")
    mock_openai_cls.return_value = mock_client

    narrator = Narrator()
    events = _make_test_events()
    world = _make_test_world()

    result = narrator.narrate(events, world, tick=0)

    assert "Alice examines" in result
    assert "Brass Key" in result
