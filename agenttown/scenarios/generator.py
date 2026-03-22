"""AI-powered scenario generator — creates escape room maps from user descriptions."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from agenttown.auth import get_api_key
from agenttown.world.models import (
    AgentState, Door, Entity, EntityState, Item, Room, WorldState,
)
from agenttown.world.world import World

logger = logging.getLogger(__name__)

# The rules reference that users can copy
MAP_RULES_REFERENCE = """\
## Room Rules
- Each room has: id, name, description
- Rooms connect via doors with directions (north/south/east/west)

## Entity Types
- Entity: non-portable object (painting, statue, inscription)
- Item: portable object (key, note, torch)
- Door: connects two rooms, can be locked with a key_id

## Puzzle Types (set via properties.puzzle_type)
- "combination_lock": needs interact(target, code). Set properties.combination and properties.on_solve
- "pressure_plate": triggers when heavy item dropped. Set properties.required_weight="heavy" and properties.on_solve
- "password_door": triggers when password spoken via talk or interact. Set properties.password and properties.on_solve
- "lever" + "sequential": multiple levers pulled in order. Set controller with properties.sequence
- Item combination: set properties.combine_with and properties.combine_result on an Item

## on_solve / on_use / on_examine Actions
- "reveal": ["entity_id"] — unhide hidden entities
- "unlock_door": "door_id" — unlock a door
- "set_state": "solved" — mark entity as solved
- "message": "text" — show message
- "finish": "reason" — end the game
- "consume_item": true — remove the used item
- "spawn_item": {item_data} — create new item in room

## Entity States
- "default", "hidden", "locked", "unlocked", "open", "closed", "solved", "activated"
- Hidden entities are invisible until revealed by on_examine or on_solve

## Agent Properties
- id, name, description, room_id (starting room), goal (detailed instructions)
"""

GENERATE_PROMPT = """\
You are a game designer. Create an escape room scenario as JSON.

## User's Theme & Story
{theme}

## User's Map Logic (if provided)
{logic}

## Output Format
Return a single JSON object with this exact structure:
```json
{{
  "title": "Scenario Title",
  "rooms": [
    {{"id": "room1", "name": "Display Name", "description": "Atmospheric description"}}
  ],
  "doors": [
    {{"id": "door1", "name": "Door Name", "description": "...", "room_a": "room1", "room_b": "room2", "direction_a": "east", "direction_b": "west", "locked": false}},
    {{"id": "door2", "name": "Locked Door", "description": "...", "room_a": "room2", "room_b": "room3", "direction_a": "south", "direction_b": "north", "locked": true, "key_id": "silver_key"}}
  ],
  "entities": [
    {{"id": "painting", "room": "room1", "type": "entity", "name": "Old Painting", "description": "...", "properties": {{"examine_text": "...", "on_examine": {{"reveal": ["hidden_key"], "message": "Found something!"}}}}}},
    {{"id": "hidden_key", "room": "room1", "type": "item", "name": "Silver Key", "description": "...", "state": "hidden", "portable": true}},
    {{"id": "lockbox", "room": "room2", "type": "entity", "name": "Lock Box", "description": "...", "properties": {{"puzzle_type": "combination_lock", "combination": "4521", "examine_text": "A 4-digit lock.", "on_solve": {{"set_state": "solved", "reveal": ["prize"], "message": "It opens!"}}}}}},
    {{"id": "exit_door", "room": "room3", "type": "entity", "name": "Exit", "description": "The way out!", "properties": {{"on_use": {{"finish": "You escaped!", "message": "Freedom!"}}}}}}
  ],
  "agents": [
    {{"id": "agent1", "name": "Agent Name", "description": "Role description", "room_id": "room1", "goal": "Detailed step-by-step escape plan"}}
  ]
}}
```

Rules:
- Create 3-6 rooms with interesting connections
- Include at least 3 different puzzle types
- Hide clues in item descriptions and examine_text
- Make puzzles interconnected (solving one reveals info for another)
- Include at least one item that can be picked up and used
- One entity must have on_use.finish to end the game
- Create 2 agents with complementary roles and detailed goals
- Make descriptions atmospheric and fitting the theme
- ONLY return the JSON, no other text
"""


def generate_scenario(theme: str, logic: str = "") -> dict:
    """Use Claude to generate a scenario from user descriptions. Returns parsed JSON."""
    client = anthropic.Anthropic(api_key=get_api_key())
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

    prompt = GENERATE_PROMPT.format(
        theme=theme or "A mysterious abandoned mansion with dark secrets",
        logic=logic or "Designer's choice — create an interesting puzzle chain",
    )

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip() if response.content else ""

    # Extract JSON from response
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            inner = text[start + 3: end]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse generated JSON: {e}")
        logger.error(f"Raw text: {text[:500]}")
        raise ValueError(f"AI generated invalid JSON: {e}")


def build_from_json(data: dict) -> tuple[World, list[str]]:
    """Build a World from a generated JSON scenario."""
    ws = WorldState()

    # Create rooms
    for r in data.get("rooms", []):
        room = Room(id=r["id"], name=r["name"], description=r.get("description", ""))
        ws.add_room(room)

    # Create entities and items
    for e in data.get("entities", []):
        room_id = e.get("room")
        if room_id not in ws.rooms:
            continue

        state = EntityState(e.get("state", "default"))
        props = e.get("properties", {})

        if e.get("type") == "item":
            entity = Item(
                id=e["id"],
                name=e["name"],
                description=e.get("description", ""),
                state=state,
                portable=e.get("portable", True),
                usable_on=e.get("usable_on", []),
                properties=props,
            )
        else:
            entity = Entity(
                id=e["id"],
                name=e["name"],
                description=e.get("description", ""),
                state=state,
                properties=props,
            )

        ws.rooms[room_id].add_entity(entity)

    # Create doors
    for d in data.get("doors", []):
        door = Door(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            room_a=d["room_a"],
            room_b=d["room_b"],
            locked=d.get("locked", False),
            key_id=d.get("key_id"),
            state=EntityState.LOCKED if d.get("locked") else EntityState.OPEN,
        )
        dir_a = d.get("direction_a", "east")
        dir_b = d.get("direction_b", "west")
        ws.add_door(door, dir_a, dir_b)

    # Create agents
    agent_ids = []
    for a in data.get("agents", []):
        agent = AgentState(
            id=a["id"],
            name=a["name"],
            description=a.get("description", ""),
            room_id=a["room_id"],
            goal=a.get("goal", "Escape!"),
        )
        ws.add_agent(agent)
        agent_ids.append(a["id"])

    # Fallback: create default agents if none specified
    if not agent_ids:
        room_ids = list(ws.rooms.keys())
        start_room = room_ids[0] if room_ids else "room1"
        for aid, name in [("alice", "Alice"), ("bob", "Bob")]:
            agent = AgentState(id=aid, name=name, room_id=start_room, goal="Escape!")
            ws.add_agent(agent)
            agent_ids.append(aid)

    world = World(state=ws)
    return world, agent_ids
