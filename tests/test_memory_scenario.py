"""Tests for the memory test scenario — verifies clue chain works."""

from agenttown.scenarios.memory_test import build_memory_test
from agenttown.world.actions import Examine, Interact, Move, Talk
from agenttown.world.models import EntityState


def test_memory_test_builds():
    world, agent_ids = build_memory_test()
    assert len(agent_ids) == 2
    assert len(world.state.rooms) == 2
    assert len(world.state.doors) == 1


def test_full_memory_chain():
    """Simulate the ideal play: read code → move → enter code → speak password."""
    world, _ = build_memory_test()
    a = world.state.agents["agent_a"]
    b = world.state.agents["agent_b"]

    # Agent A examines the code note
    events = world.process_action(Examine(target="Code Note"), a)
    assert any("7392" in e.description for e in events)

    # Agent A examines the hint book
    events = world.process_action(Examine(target="Hint Book"), a)
    assert any("exit key" in e.description.lower() for e in events)

    # Agent A moves to the lab
    world.process_action(Move(direction="east"), a)
    assert a.room_id == "lab"

    # Agent A tells Agent B the code
    world.process_action(Talk(message="The code is 7392", to="Agent B"), a)

    # Agent A enters the code on the lock box (from memory!)
    events = world.process_action(Interact(target="Lock Box", payload="7392"), a)
    assert any("clicks open" in e.description.lower() for e in events)
    assert world.state.rooms["lab"].entities["lock_box"].state == EntityState.SOLVED
    assert world.state.rooms["lab"].entities["exit_key"].state == EntityState.DEFAULT

    # Agent B examines the plaque
    events = world.process_action(Examine(target="Wall Plaque"), b)
    assert any("phoenix" in e.description.lower() for e in events)

    # Agent B tells Agent A the secret word
    world.process_action(Talk(message="The secret word is PHOENIX", to="Agent A"), b)

    # Agent A speaks the password
    world.process_action(Talk(message="PHOENIX"), a)
    assert world.finished
    assert "memory" in world.state.finish_reason.lower()


def test_wrong_code_fails():
    world, _ = build_memory_test()
    a = world.state.agents["agent_a"]

    world.process_action(Move(direction="east"), a)
    events = world.process_action(Interact(target="Lock Box", payload="0000"), a)
    assert not world.state.rooms["lab"].entities["lock_box"].state == EntityState.SOLVED


def test_agents_can_talk_across_rooms_fail():
    """Agent A can't talk to Agent B from the library (different rooms)."""
    world, _ = build_memory_test()
    a = world.state.agents["agent_a"]

    events = world.process_action(Talk(message="Hello", to="Agent B"), a)
    assert any("not here" in e.description.lower() for e in events)
