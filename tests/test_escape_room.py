"""Tests for the escape room scenario — basic structure and key-lock chain."""

from agenttown.scenarios.escape_room import build_escape_room
from agenttown.world.actions import Examine, Move, PickUp, Use
from agenttown.world.models import EntityState


def test_escape_room_builds():
    world, agent_ids = build_escape_room()
    assert len(agent_ids) == 2
    assert "alice" in agent_ids
    assert "bob" in agent_ids
    assert len(world.state.rooms) == 5
    assert len(world.state.doors) == 5


def test_key_lock_sequence():
    """Walk through the key-lock puzzle: painting → key → steel door."""
    world, _ = build_escape_room()
    alice = world.state.agents["alice"]

    # Move to workshop
    world.process_action(Move(direction="east"), alice)
    assert alice.room_id == "workshop"

    # Examine painting — reveals brass key
    world.process_action(Examine(target="Old Painting"), alice)
    workshop = world.state.rooms["workshop"]
    assert workshop.entities["brass_key"].state == EntityState.DEFAULT

    # Pick up brass key
    world.process_action(PickUp(target="Brass Key"), alice)
    assert alice.has_item("brass key") is not None

    # Use key on steel door
    assert world.state.doors["door_workshop_vault"].locked is True
    world.process_action(Use(item="Brass Key", target="Steel Door"), alice)
    assert world.state.doors["door_workshop_vault"].locked is False

    # Move to vault
    world.process_action(Move(direction="east"), alice)
    assert alice.room_id == "vault"


def test_locked_door_blocks_movement():
    world, _ = build_escape_room()
    alice = world.state.agents["alice"]

    world.process_action(Move(direction="east"), alice)
    assert alice.room_id == "workshop"

    # Steel door to vault is locked
    events = world.process_action(Move(direction="east"), alice)
    assert alice.room_id == "workshop"
    assert any("locked" in e.description.lower() for e in events)


def test_hidden_key_not_visible_before_examine():
    world, _ = build_escape_room()
    alice = world.state.agents["alice"]

    world.process_action(Move(direction="east"), alice)
    workshop = world.state.rooms["workshop"]

    assert workshop.entities["brass_key"].state == EntityState.HIDDEN
    assert "brass_key" not in [e.id for e in workshop.visible_entities()]

    events = world.process_action(PickUp(target="Brass Key"), alice)
    assert alice.has_item("brass key") is None
