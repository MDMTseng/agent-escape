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
- ONLY return valid JSON, no markdown, no explanation, no text before or after the JSON
- Start your response with {{ and end with }}
- Keep it SMALL: exactly 3 rooms, 3 puzzles, 2 agents
- Keep JSON compact — short descriptions (1 sentence each)
- Total JSON should be under 2000 characters
"""


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling code fences and surrounding text."""
    text = text.strip()

    # Try to find JSON in code fences
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            inner = text[start + 3: end]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()

    # Try to find JSON object in the text
    brace_start = text.find("{")
    if brace_start > 0:
        text = text[brace_start:]

    # Find the matching closing brace
    depth = 0
    for i, c in enumerate(text):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                text = text[: i + 1]
                break

    return json.loads(text)


def generate_scenario(theme: str, logic: str = "") -> dict:
    """Use Claude to generate a scenario from user descriptions. Retries on JSON failure."""
    client = anthropic.Anthropic(api_key=get_api_key())
    model = os.environ.get("ANTHROPIC_MAP_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5"))

    prompt = GENERATE_PROMPT.format(
        theme=theme or "A mysterious abandoned mansion with dark secrets",
        logic=logic or "Designer's choice — create an interesting puzzle chain",
    )

    # Try up to 2 times
    last_error = None
    for attempt in range(2):
        messages = [{"role": "user", "content": prompt}]

        # On retry, include the error so AI can fix it
        if attempt > 0 and last_error:
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": last_raw},
                {"role": "user", "content": f"Your JSON was invalid: {last_error}. Return ONLY valid JSON, no other text. Fix the issue and try again."},
            ]

        response = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=messages,
        )

        text = response.content[0].text.strip() if response.content else ""
        last_raw = text

        try:
            return _extract_json(text)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = str(e)
            logger.warning(f"JSON parse attempt {attempt + 1} failed: {e}")
            continue

    logger.error(f"Failed to generate valid JSON after 2 attempts")
    logger.error(f"Last raw text: {last_raw[:500]}")
    raise ValueError(f"AI generated invalid JSON after 2 attempts: {last_error}")


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


# ---------------------------------------------------------------------------
# Puzzle chain validation & escape path extraction
# ---------------------------------------------------------------------------

def validate_and_extract_chain(data: dict) -> dict:
    """Validate a scenario is solvable and extract the escape chain.

    Returns:
        {
            "valid": bool,
            "errors": [str],
            "warnings": [str],
            "escape_chain": [
                {"step": 1, "action": "examine", "target": "Note", "room": "Study",
                 "description": "Read the note to find code 1847", "status": "pending"}
            ]
        }
    """
    errors = []
    warnings = []
    chain = []

    rooms = {r["id"]: r for r in data.get("rooms", [])}
    entities = {e["id"]: e for e in data.get("entities", [])}
    doors = {d["id"]: d for d in data.get("doors", [])}
    agents = data.get("agents", [])

    if not rooms:
        errors.append("No rooms defined")
    if not agents:
        warnings.append("No agents defined — defaults will be used")

    # Check all rooms referenced by entities exist
    for e in data.get("entities", []):
        if e.get("room") and e["room"] not in rooms:
            errors.append(f"Entity '{e['name']}' references missing room '{e['room']}'")

    # Check all rooms referenced by doors exist
    for d in data.get("doors", []):
        if d["room_a"] not in rooms:
            errors.append(f"Door '{d['name']}' references missing room '{d['room_a']}'")
        if d["room_b"] not in rooms:
            errors.append(f"Door '{d['name']}' references missing room '{d['room_b']}'")

    # Check key_ids reference existing entities
    for d in data.get("doors", []):
        if d.get("key_id") and d["key_id"] not in entities:
            errors.append(f"Door '{d['name']}' needs key '{d['key_id']}' which doesn't exist")

    # Check agent start rooms exist
    for a in agents:
        if a["room_id"] not in rooms:
            errors.append(f"Agent '{a['name']}' starts in missing room '{a['room_id']}'")

    # Find the finish entity
    finish_entity = None
    for e in data.get("entities", []):
        props = e.get("properties", {})
        for key in ("on_use", "on_solve", "on_examine"):
            if isinstance(props.get(key), dict) and "finish" in props[key]:
                finish_entity = e
                break
    if not finish_entity:
        errors.append("No entity with a 'finish' action — game can never end")

    # --- Build escape chain by tracing puzzle dependencies ---
    step = 0

    # Find all locked doors and what unlocks them
    locked_doors = [d for d in data.get("doors", []) if d.get("locked")]

    # Step through: find clues → solve puzzles → unlock doors → reach exit
    # 1. Items that need to be examined (have examine_text with clues)
    for e in data.get("entities", []):
        props = e.get("properties", {})
        if props.get("examine_text") and e.get("state") != "hidden":
            room_name = rooms.get(e.get("room", ""), {}).get("name", "?")
            step += 1
            chain.append({
                "step": step,
                "action": "examine",
                "target": e["name"],
                "entity_id": e["id"],
                "room": room_name,
                "room_id": e.get("room", ""),
                "description": f"Examine {e['name']} for clues",
                "status": "pending",
                "check_type": "examine",
            })

    # 2. Hidden items that need to be revealed (via on_examine.reveal)
    for e in data.get("entities", []):
        props = e.get("properties", {})
        on_examine = props.get("on_examine", {})
        if on_examine.get("reveal"):
            for reveal_id in on_examine["reveal"]:
                revealed = entities.get(reveal_id)
                if revealed:
                    room_name = rooms.get(e.get("room", ""), {}).get("name", "?")
                    step += 1
                    chain.append({
                        "step": step,
                        "action": "reveal",
                        "target": revealed["name"],
                        "entity_id": reveal_id,
                        "room": room_name,
                        "room_id": e.get("room", ""),
                        "description": f"Find {revealed['name']} (hidden behind {e['name']})",
                        "status": "pending",
                        "check_type": "reveal",
                    })

    # 3. Puzzles to solve
    for e in data.get("entities", []):
        props = e.get("properties", {})
        pt = props.get("puzzle_type", "")
        if pt and pt not in ("lever",):  # skip individual levers, only track controllers
            room_name = rooms.get(e.get("room", ""), {}).get("name", "?")
            desc_map = {
                "combination_lock": f"Enter code on {e['name']}",
                "pressure_plate": f"Activate {e['name']} with heavy item",
                "password_door": f"Speak password to {e['name']}",
                "sequential": f"Pull levers in correct order",
            }
            step += 1
            chain.append({
                "step": step,
                "action": "solve",
                "target": e["name"],
                "entity_id": e["id"],
                "room": room_name,
                "room_id": e.get("room", ""),
                "description": desc_map.get(pt, f"Solve {e['name']}"),
                "status": "pending",
                "check_type": "solve",
            })

    # 4. Locked doors to unlock
    for d in locked_doors:
        room_a_name = rooms.get(d["room_a"], {}).get("name", "?")
        room_b_name = rooms.get(d["room_b"], {}).get("name", "?")
        step += 1
        chain.append({
            "step": step,
            "action": "unlock",
            "target": d["name"],
            "entity_id": d["id"],
            "room": f"{room_a_name} → {room_b_name}",
            "room_id": d["room_a"],
            "description": f"Unlock {d['name']} ({room_a_name} → {room_b_name})",
            "status": "pending",
            "check_type": "door",
        })

    # 5. Final escape
    if finish_entity:
        room_name = rooms.get(finish_entity.get("room", ""), {}).get("name", "?")
        step += 1
        chain.append({
            "step": step,
            "action": "escape",
            "target": finish_entity["name"],
            "entity_id": finish_entity["id"],
            "room": room_name,
            "room_id": finish_entity.get("room", ""),
            "description": f"Use {finish_entity['name']} to escape!",
            "status": "pending",
            "check_type": "finish",
        })

    # Check reachability — is there a path from start to finish room?
    if agents and finish_entity:
        start_room = agents[0].get("room_id")
        finish_room = finish_entity.get("room")
        if start_room and finish_room:
            reachable = _find_reachable_rooms(start_room, doors, include_locked=True)
            if finish_room not in reachable:
                errors.append(f"Exit room '{finish_room}' is not reachable from start '{start_room}' even with all doors unlocked")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "escape_chain": chain,
    }


def _find_reachable_rooms(start: str, doors: list[dict], include_locked: bool = False) -> set[str]:
    """BFS to find all reachable rooms."""
    visited = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        for d in doors:
            if not include_locked and d.get("locked"):
                continue
            if d["room_a"] == current and d["room_b"] not in visited:
                visited.add(d["room_b"])
                queue.append(d["room_b"])
            elif d["room_b"] == current and d["room_a"] not in visited:
                visited.add(d["room_a"])
                queue.append(d["room_a"])
    return visited


def update_chain_status(chain: list[dict], world_state: dict) -> list[dict]:
    """Update escape chain step statuses from live world state."""
    rooms = world_state.get("rooms", {})
    doors = world_state.get("doors", {})
    finished = world_state.get("finished", False)

    for step in chain:
        eid = step.get("entity_id", "")
        check = step.get("check_type", "")

        if finished and check == "finish":
            step["status"] = "complete"
            continue

        if check == "door":
            door = doors.get(eid, {})
            if door and not door.get("locked", True):
                step["status"] = "complete"
            continue

        if check == "reveal":
            # Check if entity is no longer hidden
            for room in rooms.values():
                entity = room.get("entities", {}).get(eid)
                if entity and entity.get("state") != "hidden":
                    step["status"] = "complete"
                    break
            continue

        if check == "solve":
            for room in rooms.values():
                entity = room.get("entities", {}).get(eid)
                if entity and entity.get("state") == "solved":
                    step["status"] = "complete"
                    break
            continue

        if check == "examine":
            # Can't easily track if examined — mark as complete if agent has been in that room
            # For now just leave as pending unless we track it differently
            pass

    return chain
