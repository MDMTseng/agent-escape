"""Escape Room scenario — a multi-room puzzle for agents to solve."""

from __future__ import annotations

from agenttown.world.models import (
    AgentState,
    Door,
    EntityState,
    Item,
    Entity,
    Room,
    WorldState,
)
from agenttown.world.world import World


def build_escape_room() -> tuple[World, list[str]]:
    """Build the escape room world. Returns (world, list_of_agent_ids)."""

    # --- Rooms ---
    start_room = Room(
        id="start",
        name="The Study",
        description="A dusty study with bookshelves lining the walls. A faint draft comes from somewhere.",
    )

    puzzle_room = Room(
        id="puzzle",
        name="The Workshop",
        description="A cluttered workshop with tools hanging on the walls and a heavy workbench in the center.",
    )

    exit_room = Room(
        id="exit",
        name="The Hallway",
        description="A narrow hallway leading to a heavy iron door — the way out.",
    )

    # --- Items & Entities in Start Room ---
    note = Item(
        id="note",
        name="Crumpled Note",
        description="A crumpled piece of paper with writing on it.",
        portable=True,
        properties={
            "examine_text": 'The note reads: "The painting in the workshop hides a secret. Look behind it."',
        },
    )
    start_room.add_entity(note)

    old_book = Entity(
        id="book",
        name="Old Book",
        description="A leather-bound book sitting on the desk.",
        properties={
            "examine_text": 'The book is titled "History of Ravenwood Manor, est. 1847". Most pages are too faded to read.',
        },
    )
    start_room.add_entity(old_book)

    # --- Items & Entities in Puzzle Room ---
    painting = Entity(
        id="painting",
        name="Old Painting",
        description="A large oil painting of a countryside scene, hanging slightly askew.",
        portable=False,
        properties={
            "on_examine": {
                "reveal": ["brass_key"],
                "message": "Looking behind the painting, you find a small brass key taped to the back!",
            },
        },
    )
    puzzle_room.add_entity(painting)

    brass_key = Item(
        id="brass_key",
        name="Brass Key",
        description="A small, ornate brass key.",
        state=EntityState.HIDDEN,
        portable=True,
    )
    puzzle_room.add_entity(brass_key)

    puzzle_box = Entity(
        id="puzzle_box",
        name="Puzzle Box",
        description="A wooden box with a 4-digit combination lock on the front.",
        portable=False,
        properties={
            "examine_text": "The combination lock has four dials, each numbered 0-9. It's currently locked.",
            "combination": "1847",
        },
    )
    puzzle_room.add_entity(puzzle_box)

    exit_hint = Item(
        id="exit_hint",
        name="Torn Page",
        description="A torn page from a journal.",
        state=EntityState.HIDDEN,
        portable=True,
        properties={
            "examine_text": 'The page reads: "The iron door at the end of the hallway can only be opened from this side. Simply push it open."',
        },
    )
    puzzle_room.add_entity(exit_hint)

    # --- Items in Exit Room ---
    exit_door = Entity(
        id="exit_door",
        name="Iron Door",
        description="A heavy iron door with a simple push handle. This is the way out!",
        portable=False,
        properties={
            "examine_text": "The door is heavy but has a push bar. You just need to push it to escape!",
            "on_use": {
                "finish": "The iron door swings open with a groan. Daylight floods in. You've escaped!",
                "message": "You push the heavy iron door open...",
            },
        },
    )
    exit_room.add_entity(exit_door)

    # --- Doors ---
    study_to_workshop = Door(
        id="door_study_workshop",
        name="Wooden Door",
        description="A solid wooden door connecting the study to the workshop.",
        room_a="start",
        room_b="puzzle",
        locked=False,
        state=EntityState.OPEN,
    )

    workshop_to_hallway = Door(
        id="door_workshop_hallway",
        name="Steel Door",
        description="A sturdy steel door with a brass keyhole.",
        room_a="puzzle",
        room_b="exit",
        locked=True,
        key_id="brass_key",
        state=EntityState.LOCKED,
    )

    # --- Build World State ---
    world_state = WorldState()
    world_state.add_room(start_room)
    world_state.add_room(puzzle_room)
    world_state.add_room(exit_room)

    world_state.add_door(study_to_workshop, direction_from_a="east", direction_from_b="west")
    world_state.add_door(workshop_to_hallway, direction_from_a="south", direction_from_b="north")

    # --- Agents ---
    alice = AgentState(
        id="alice",
        name="Alice",
        description="A curious and methodical explorer.",
        room_id="start",
        goal="Escape the room by finding clues and solving puzzles. Cooperate with Bob.",
    )

    bob = AgentState(
        id="bob",
        name="Bob",
        description="A bold and intuitive problem solver.",
        room_id="start",
        goal="Escape the room by finding clues and solving puzzles. Cooperate with Alice.",
    )

    world_state.add_agent(alice)
    world_state.add_agent(bob)

    world = World(state=world_state)
    return world, ["alice", "bob"]
