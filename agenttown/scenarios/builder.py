"""Scenario builder — AI generates puzzles, code arranges them into solvable maps.

Architecture:
  Step 1: AI generates a list of themed puzzles (creative content)
  Step 2: Code creates rooms, places puzzles, connects doors, ensures solvability

This separates creative work (AI) from structural work (code).
"""

from __future__ import annotations

import json
import logging
import os
import random
from typing import Any

import anthropic

from agenttown.auth import get_api_key
from agenttown.world.models import (
    AgentState, Door, Entity, EntityState, Item, Room, WorldState,
)
from agenttown.world.world import World

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step 1: AI generates themed puzzles
# ---------------------------------------------------------------------------

PUZZLE_PROMPT = """\
You are a puzzle designer for escape rooms.

Theme: {theme}
{logic_section}

Generate exactly {num_puzzles} puzzles that fit this theme. For each puzzle, provide:
1. A name and short description
2. The puzzle type (pick from: combination_lock, key_lock, password_door, pressure_plate, examine_reveal)
3. The clue item (what the player finds to solve it)
4. The solution (code, password, key name, or heavy item name)
5. Room atmosphere (1 sentence describing the room this puzzle belongs in)

Return JSON array. Example:
[
  {{
    "name": "Ancient Cipher",
    "description": "A stone tablet with rotating symbols",
    "type": "combination_lock",
    "combination": "3742",
    "clue_item_name": "Torn Journal Page",
    "clue_item_description": "A page reading: the year the temple was built — 3742",
    "room_name": "The Crypt",
    "room_description": "A dark crypt with stone walls and flickering torches"
  }},
  {{
    "name": "Guardian's Lock",
    "type": "key_lock",
    "description": "A heavy iron lock on the vault door",
    "key_name": "Iron Key",
    "key_description": "A rusted iron key with a skull handle",
    "key_hidden_behind": "Cracked Statue",
    "key_hidden_behind_description": "A cracked stone statue of a warrior",
    "room_name": "The Armory",
    "room_description": "Weapons line the walls of this cold armory"
  }},
  {{
    "name": "Spirit Gate",
    "type": "password_door",
    "description": "An archway covered in glowing runes",
    "password": "eternum",
    "clue_item_name": "Dusty Grimoire",
    "clue_item_description": "The book whispers: speak ETERNUM to pass",
    "room_name": "The Sanctum",
    "room_description": "A mysterious circular room lit by blue flames"
  }},
  {{
    "name": "Weight Trigger",
    "type": "pressure_plate",
    "description": "A sunken stone tile on the floor",
    "heavy_item_name": "Bronze Idol",
    "heavy_item_description": "A surprisingly heavy bronze idol",
    "room_name": "The Treasury",
    "room_description": "Gold and jewels glitter in the dim light"
  }},
  {{
    "name": "Hidden Compartment",
    "type": "examine_reveal",
    "description": "A large ornate mirror on the wall",
    "hidden_item_name": "Secret Map",
    "hidden_item_description": "A map showing a hidden passage",
    "examine_message": "Behind the mirror, you find a hidden compartment!",
    "room_name": "The Library",
    "room_description": "Dusty bookshelves stretch to the ceiling"
  }}
]

Return ONLY the JSON array. Make puzzles creative and thematic.\
"""

PUZZLE_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "puzzles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "type": {"type": "string"},
                        "room_name": {"type": "string"},
                        "room_description": {"type": "string"},
                        # combination_lock fields
                        "combination": {"type": "string"},
                        "clue_item_name": {"type": "string"},
                        "clue_item_description": {"type": "string"},
                        # key_lock fields
                        "key_name": {"type": "string"},
                        "key_description": {"type": "string"},
                        "key_hidden_behind": {"type": "string"},
                        "key_hidden_behind_description": {"type": "string"},
                        # password_door fields
                        "password": {"type": "string"},
                        # pressure_plate fields
                        "heavy_item_name": {"type": "string"},
                        "heavy_item_description": {"type": "string"},
                        # examine_reveal fields
                        "hidden_item_name": {"type": "string"},
                        "hidden_item_description": {"type": "string"},
                        "examine_message": {"type": "string"},
                    },
                    "required": ["name", "description", "type", "room_name", "room_description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["puzzles"],
        "additionalProperties": False,
    },
}


def generate_puzzles(theme: str, logic: str = "", num_puzzles: int = 4) -> list[dict]:
    """Ask AI to generate themed puzzles. Returns list of puzzle dicts."""
    client = anthropic.Anthropic(api_key=get_api_key())
    model = os.environ.get("ANTHROPIC_MAP_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5"))

    logic_section = f"\nAdditional design notes:\n{logic}" if logic else ""

    prompt = PUZZLE_PROMPT.format(
        theme=theme,
        logic_section=logic_section,
        num_puzzles=num_puzzles,
    )

    logger.info(f"Generating {num_puzzles} puzzles for theme: {theme[:60]}...")

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip() if response.content else "[]"

    # Extract JSON array from response
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            inner = text[start + 3: end]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()

    # Find array or object with puzzles key
    try:
        data = json.loads(text)
        if isinstance(data, list):
            puzzles = data
        elif isinstance(data, dict):
            puzzles = data.get("puzzles", [])
        else:
            puzzles = []
    except json.JSONDecodeError:
        # Try to find JSON array in text
        bracket_start = text.find("[")
        if bracket_start >= 0:
            try:
                data = json.loads(text[bracket_start:])
                puzzles = data if isinstance(data, list) else []
            except json.JSONDecodeError:
                logger.error(f"Failed to parse puzzles JSON: {text[:200]}")
                puzzles = []
        else:
            puzzles = []

    logger.info(f"Generated {len(puzzles)} puzzles: {[p['name'] for p in puzzles]}")
    return puzzles


# ---------------------------------------------------------------------------
# Step 2: Code arranges puzzles into a solvable map
# ---------------------------------------------------------------------------

def build_map(theme: str, puzzles: list[dict]) -> tuple[World, list[str], list[dict]]:
    """Arrange puzzles into rooms with guaranteed solvable connections.

    Layout: linear chain of rooms
      Start Room → Puzzle Room 1 → Puzzle Room 2 → ... → Exit Room

    Each puzzle unlocks the door to the next room.
    Clues for puzzle N are placed in room N-1 (so you find clue before the lock).

    Returns: (world, agent_ids, escape_chain)
    """
    ws = WorldState()
    escape_chain = []

    if not puzzles:
        puzzles = [_default_puzzle()]

    # --- Create rooms ---
    # Start room (no puzzle, has first clue)
    start_id = "start"
    start_room = Room(
        id=start_id,
        name=puzzles[0].get("room_name", "Entrance") if len(puzzles) > 0 else "Entrance",
        description=puzzles[0].get("room_description", "The starting area."),
    )
    ws.add_room(start_room)

    # One room per puzzle
    puzzle_rooms = []
    for i, puzzle in enumerate(puzzles):
        room_id = f"room_{i}"
        room = Room(
            id=room_id,
            name=puzzle.get("room_name", f"Room {i+1}"),
            description=puzzle.get("room_description", f"A mysterious room."),
        )
        ws.add_room(room)
        puzzle_rooms.append(room_id)

    # Exit room
    exit_id = "exit_room"
    exit_room = Room(id=exit_id, name="Exit", description="A room with the way out.")
    ws.add_room(exit_room)

    # --- Place puzzles and create doors ---
    all_room_ids = [start_id] + puzzle_rooms + [exit_id]
    directions = ["east", "west"]  # alternate for variety

    step = 0

    for i in range(len(all_room_ids) - 1):
        from_room = all_room_ids[i]
        to_room = all_room_ids[i + 1]
        door_id = f"door_{i}"

        # Is this door locked by a puzzle?
        if i < len(puzzles):
            puzzle = puzzles[i]
            puzzle_type = puzzle.get("type", "combination_lock")
            locked = True

            # Place the puzzle mechanism in the "from" room (or the room before)
            # Place the clue in the room BEFORE the puzzle
            clue_room = all_room_ids[max(0, i - 1)] if i > 0 else from_room

            # --- Build puzzle entities based on type ---
            if puzzle_type == "combination_lock":
                code = puzzle.get("combination", str(random.randint(1000, 9999)))

                # Clue item (in previous room)
                clue = Item(
                    id=f"clue_{i}",
                    name=puzzle.get("clue_item_name", f"Clue Note {i+1}"),
                    description=puzzle.get("clue_item_description", f"Contains the code {code}"),
                    portable=True,
                    properties={"examine_text": puzzle.get("clue_item_description", f"The code is {code}")},
                )
                ws.rooms[clue_room].add_entity(clue)

                step += 1
                escape_chain.append({
                    "step": step, "action": "examine", "target": clue.name,
                    "entity_id": clue.id, "room": ws.rooms[clue_room].name,
                    "room_id": clue_room, "description": f"Find clue: {clue.name}",
                    "status": "pending", "check_type": "examine",
                })

                # Lock mechanism (in current room)
                lock = Entity(
                    id=f"lock_{i}",
                    name=puzzle.get("name", f"Lock {i+1}"),
                    description=puzzle.get("description", "A combination lock"),
                    properties={
                        "puzzle_type": "combination_lock",
                        "combination": code,
                        "examine_text": puzzle.get("description", "Enter the code"),
                        "on_solve": {
                            "set_state": "solved",
                            "unlock_door": door_id,
                            "message": f"{puzzle['name']} solved! The door unlocks!",
                        },
                    },
                )
                ws.rooms[from_room].add_entity(lock)

                step += 1
                escape_chain.append({
                    "step": step, "action": "solve", "target": lock.name,
                    "entity_id": lock.id, "room": ws.rooms[from_room].name,
                    "room_id": from_room, "description": f"Enter code {code} on {lock.name}",
                    "status": "pending", "check_type": "solve",
                })

            elif puzzle_type == "key_lock":
                key_id = f"key_{i}"

                # Hidden key (behind something in previous room)
                hider = Entity(
                    id=f"hider_{i}",
                    name=puzzle.get("key_hidden_behind", f"Old Object {i+1}"),
                    description=puzzle.get("key_hidden_behind_description", "Something suspicious"),
                    properties={
                        "on_examine": {
                            "reveal": [key_id],
                            "message": puzzle.get("examine_message", "You found a key!"),
                        },
                    },
                )
                ws.rooms[clue_room].add_entity(hider)

                key_item = Item(
                    id=key_id,
                    name=puzzle.get("key_name", f"Key {i+1}"),
                    description=puzzle.get("key_description", "A key"),
                    state=EntityState.HIDDEN,
                    portable=True,
                )
                ws.rooms[clue_room].add_entity(key_item)

                step += 1
                escape_chain.append({
                    "step": step, "action": "reveal", "target": key_item.name,
                    "entity_id": key_id, "room": ws.rooms[clue_room].name,
                    "room_id": clue_room, "description": f"Find {key_item.name} behind {hider.name}",
                    "status": "pending", "check_type": "reveal",
                })

                # Door uses key_id directly
                locked = True

                # Create door with key
                door = Door(
                    id=door_id,
                    name=puzzle.get("name", f"Locked Door {i+1}"),
                    description=puzzle.get("description", "A locked door"),
                    room_a=from_room,
                    room_b=to_room,
                    locked=True,
                    key_id=key_id,
                    state=EntityState.LOCKED,
                )
                ws.add_door(door, "east", "west")

                step += 1
                escape_chain.append({
                    "step": step, "action": "unlock", "target": door.name,
                    "entity_id": door_id, "room": f"{ws.rooms[from_room].name} → {ws.rooms[to_room].name}",
                    "room_id": from_room, "description": f"Use {key_item.name} on {door.name}",
                    "status": "pending", "check_type": "door",
                })
                continue  # door already created

            elif puzzle_type == "password_door":
                password = puzzle.get("password", "opensesame")

                # Clue with password
                clue = Item(
                    id=f"clue_{i}",
                    name=puzzle.get("clue_item_name", f"Ancient Text {i+1}"),
                    description=puzzle.get("clue_item_description", f"Speaks of the word: {password}"),
                    portable=True,
                    properties={"examine_text": puzzle.get("clue_item_description", f"The password is {password}")},
                )
                ws.rooms[clue_room].add_entity(clue)

                # Password listener in current room
                listener = Entity(
                    id=f"listener_{i}",
                    name=puzzle.get("name", f"Magic Gate {i+1}"),
                    description=puzzle.get("description", "Responds to spoken words"),
                    properties={
                        "puzzle_type": "password_door",
                        "password": password,
                        "examine_text": "It seems to be listening...",
                        "on_solve": {
                            "set_state": "solved",
                            "unlock_door": door_id,
                            "message": f"The word '{password}' echoes! The way opens!",
                        },
                    },
                )
                ws.rooms[from_room].add_entity(listener)

                step += 1
                escape_chain.append({
                    "step": step, "action": "solve", "target": listener.name,
                    "entity_id": listener.id, "room": ws.rooms[from_room].name,
                    "room_id": from_room, "description": f"Say '{password}' to {listener.name}",
                    "status": "pending", "check_type": "solve",
                })

            elif puzzle_type == "pressure_plate":
                heavy_name = puzzle.get("heavy_item_name", f"Heavy Object {i+1}")

                # Heavy item in previous room
                heavy = Item(
                    id=f"heavy_{i}",
                    name=heavy_name,
                    description=puzzle.get("heavy_item_description", "Very heavy"),
                    portable=True,
                    properties={"weight": "heavy"},
                )
                ws.rooms[clue_room].add_entity(heavy)

                # Pressure plate in current room
                plate = Entity(
                    id=f"plate_{i}",
                    name=puzzle.get("name", f"Floor Plate {i+1}"),
                    description=puzzle.get("description", "A sunken stone tile"),
                    properties={
                        "puzzle_type": "pressure_plate",
                        "required_weight": "heavy",
                        "examine_text": "Needs something heavy.",
                        "on_solve": {
                            "set_state": "solved",
                            "unlock_door": door_id,
                            "message": "The plate sinks! A door grinds open!",
                        },
                    },
                )
                ws.rooms[from_room].add_entity(plate)

                step += 1
                escape_chain.append({
                    "step": step, "action": "solve", "target": plate.name,
                    "entity_id": plate.id, "room": ws.rooms[from_room].name,
                    "room_id": from_room, "description": f"Drop {heavy_name} on {plate.name}",
                    "status": "pending", "check_type": "solve",
                })

            elif puzzle_type == "examine_reveal":
                revealed_id = f"revealed_{i}"

                examiner = Entity(
                    id=f"examiner_{i}",
                    name=puzzle.get("name", f"Mysterious Object {i+1}"),
                    description=puzzle.get("description", "Something worth examining"),
                    properties={
                        "examine_text": puzzle.get("description", "Look closer..."),
                        "on_examine": {
                            "reveal": [revealed_id],
                            "message": puzzle.get("examine_message", "You discover something!"),
                        },
                    },
                )
                ws.rooms[from_room].add_entity(examiner)

                revealed = Item(
                    id=revealed_id,
                    name=puzzle.get("hidden_item_name", f"Hidden Item {i+1}"),
                    description=puzzle.get("hidden_item_description", "A hidden discovery"),
                    state=EntityState.HIDDEN,
                    portable=True,
                    usable_on=[f"door_{i}_lock"],
                    properties={
                        "examine_text": puzzle.get("hidden_item_description", "Useful for something"),
                    },
                )
                ws.rooms[from_room].add_entity(revealed)

                # This type unlocks via using the item on a lock entity
                lock_entity = Entity(
                    id=f"door_{i}_lock",
                    name=f"{puzzle.get('name', 'Lock')} Mechanism",
                    description="A mechanism that needs an item",
                    properties={
                        "on_use": {
                            "unlock_door": door_id,
                            "set_state": "solved",
                            "consume_item": True,
                            "message": "The mechanism activates! The door opens!",
                        },
                    },
                )
                ws.rooms[from_room].add_entity(lock_entity)

                step += 1
                escape_chain.append({
                    "step": step, "action": "solve", "target": examiner.name,
                    "entity_id": examiner.id, "room": ws.rooms[from_room].name,
                    "room_id": from_room, "description": f"Examine {examiner.name}, use {revealed.name}",
                    "status": "pending", "check_type": "solve",
                })

            # Create locked door (for non-key_lock types)
            if puzzle_type != "key_lock":
                door = Door(
                    id=door_id,
                    name=f"Door to {ws.rooms[to_room].name}",
                    description=f"A door leading to {ws.rooms[to_room].name}",
                    room_a=from_room,
                    room_b=to_room,
                    locked=True,
                    state=EntityState.LOCKED,
                )
                ws.add_door(door, "east", "west")

                step += 1
                escape_chain.append({
                    "step": step, "action": "unlock", "target": door.name,
                    "entity_id": door_id, "room": f"{ws.rooms[from_room].name} → {ws.rooms[to_room].name}",
                    "room_id": from_room, "description": f"Door unlocks to {ws.rooms[to_room].name}",
                    "status": "pending", "check_type": "door",
                })
        else:
            # No puzzle — open door
            door = Door(
                id=door_id,
                name=f"Door to {ws.rooms[to_room].name}",
                description="An open doorway",
                room_a=from_room,
                room_b=to_room,
                locked=False,
                state=EntityState.OPEN,
            )
            ws.add_door(door, "east", "west")

    # --- Exit entity ---
    exit_entity = Entity(
        id="exit_entity",
        name="Exit Door",
        description="The way out! Freedom awaits.",
        properties={
            "examine_text": "A heavy door. Push it to escape!",
            "on_use": {
                "finish": f"You escaped! The {theme[:50]} is behind you.",
                "message": "The door swings open. Daylight floods in.",
            },
        },
    )
    ws.rooms[exit_id].add_entity(exit_entity)

    step += 1
    escape_chain.append({
        "step": step, "action": "escape", "target": "Exit Door",
        "entity_id": "exit_entity", "room": "Exit",
        "room_id": exit_id, "description": "Escape through the Exit Door!",
        "status": "pending", "check_type": "finish",
    })

    # --- Agents ---
    agent_ids = ["agent_a", "agent_b"]
    puzzle_names = ", ".join(p["name"] for p in puzzles)
    chain_desc = " → ".join(f"Step {s['step']}: {s['description']}" for s in escape_chain)

    ws.add_agent(AgentState(
        id="agent_a", name="Alice",
        description="Clue finder. Examines everything carefully.",
        room_id=start_id,
        goal=f"Escape! Puzzles to solve: {puzzle_names}. Plan: {chain_desc}",
    ))
    ws.add_agent(AgentState(
        id="agent_b", name="Bob",
        description="Action taker. Carries items and uses them on puzzles.",
        room_id=start_id,
        goal=f"Escape! Help Alice. Carry heavy items, use keys on doors. Plan: {chain_desc}",
    ))

    world = World(state=ws)
    logger.info(f"Built map: {len(ws.rooms)} rooms, {sum(len(r.entities) for r in ws.rooms.values())} entities, {len(ws.doors)} doors, {len(escape_chain)} chain steps")
    return world, agent_ids, escape_chain


def _default_puzzle() -> dict:
    return {
        "name": "Simple Lock",
        "description": "A basic combination lock",
        "type": "combination_lock",
        "combination": "1234",
        "clue_item_name": "Note",
        "clue_item_description": "The code is 1234",
        "room_name": "The Room",
        "room_description": "A simple room.",
    }
