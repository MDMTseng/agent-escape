"""Tests for the escape room scenario — verifies the full puzzle chain works."""

from agenttown.scenarios.escape_room import build_escape_room
from agenttown.world.actions import Examine, Move, PickUp, Use
from agenttown.world.models import EntityState


def test_escape_room_builds():
    world, agent_ids = build_escape_room()
    assert len(agent_ids) == 2
    assert "alice" in agent_ids
    assert "bob" in agent_ids
    assert len(world.state.rooms) == 3
    assert len(world.state.doors) == 2


def test_full_escape_sequence():
    """Walk through the entire escape room puzzle chain."""
    world, _ = build_escape_room()
    alice = world.state.agents["alice"]

    # 1. Examine the note in Start Room
    result = world.process_action(Examine(target="Crumpled Note"), alice)
    assert result[0].event_type == "examine"

    # 2. Pick up the note
    world.process_action(PickUp(target="Crumpled Note"), alice)
    assert alice.has_item("crumpled note") is not None

    # 3. Move to the Puzzle Room (east)
    world.process_action(Move(direction="east"), alice)
    assert alice.room_id == "puzzle"

    # 4. Examine the painting — should reveal the brass key
    world.process_action(Examine(target="Old Painting"), alice)
    puzzle_room = world.state.rooms["puzzle"]
    assert puzzle_room.entities["brass_key"].state == EntityState.DEFAULT

    # 5. Pick up the brass key
    world.process_action(PickUp(target="Brass Key"), alice)
    assert alice.has_item("brass key") is not None

    # 6. Use brass key on the steel door — should unlock it
    assert world.state.doors["door_workshop_hallway"].locked is True
    world.process_action(Use(item="Brass Key", target="Steel Door"), alice)
    assert world.state.doors["door_workshop_hallway"].locked is False
    assert alice.has_item("brass key") is None  # key consumed

    # 7. Move to the Exit Room (south)
    world.process_action(Move(direction="south"), alice)
    assert alice.room_id == "exit"

    # 8. Examine the Iron Door
    world.process_action(Examine(target="Iron Door"), alice)

    # 9. "Use" any item on the exit door to escape (need an item to use)
    # Pick up note again to use — but note is in inventory already
    # The exit door has on_use that just triggers on any item
    # Actually we need to handle "use" on exit door without an item — let's use the note
    world.process_action(Use(item="Crumpled Note", target="Iron Door"), alice)

    assert world.state.finished
    assert "escaped" in world.state.finish_reason.lower()


def test_locked_door_blocks_movement():
    """Can't walk through a locked door."""
    world, _ = build_escape_room()
    alice = world.state.agents["alice"]

    # Move to puzzle room
    world.process_action(Move(direction="east"), alice)
    assert alice.room_id == "puzzle"

    # Try to go south through locked door
    events = world.process_action(Move(direction="south"), alice)
    assert alice.room_id == "puzzle"  # didn't move
    assert any("locked" in e.description.lower() for e in events)


def test_hidden_key_not_visible_before_examine():
    """The brass key should be hidden until the painting is examined."""
    world, _ = build_escape_room()
    alice = world.state.agents["alice"]

    world.process_action(Move(direction="east"), alice)
    puzzle_room = world.state.rooms["puzzle"]

    # Key exists but is hidden
    assert puzzle_room.entities["brass_key"].state == EntityState.HIDDEN
    assert "brass_key" not in [e.id for e in puzzle_room.visible_entities()]

    # Can't pick up hidden item
    events = world.process_action(PickUp(target="Brass Key"), alice)
    assert alice.has_item("brass key") is None
