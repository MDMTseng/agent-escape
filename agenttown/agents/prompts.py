"""Prompt templates and tool definitions — optimized for minimal token usage."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are {name}. {description}
Goal: {goal}

Rules: Pick up to 5 actions per turn by calling multiple tools. Never wait. Be aggressive — examine, pick up, move, and use items all in one turn. Use interact for codes/passwords/levers. Use combine to merge items. Talk to share info.

{memory_summary}\
"""

PERCEPTION_TEMPLATE = """\
Tick {tick} | {room_name}: {room_description}
See: {entities} | Exits: {exits} | Others: {others} | Inventory: {inventory}
Events: {recent_events}
{room_history}{hints}Act now. Do NOT go back to rooms you already visited unless you need something there.\
"""


def build_system_prompt(
    name: str, description: str, goal: str, memory_summary: str
) -> str:
    return SYSTEM_PROMPT.format(
        name=name,
        description=description,
        goal=goal,
        memory_summary=memory_summary,
    )


def build_perception_message(perception: dict) -> str:
    entities = ", ".join(
        f"{e['name']}({e['state']})" if e.get("state", "default") != "default"
        else e["name"]
        for e in perception.get("entities", [])
    ) or "nothing"

    exits = ", ".join(
        f"{e['direction']}"
        for e in perception.get("exits", [])
    ) or "none"

    others = ", ".join(
        o["name"] for o in perception.get("others", [])
    ) or "none"

    inventory = ", ".join(
        i["name"] for i in perception.get("inventory", [])
    ) or "empty"

    events = "; ".join(perception.get("recent_events", [])) or "none"

    hints_list = perception.get("hints", [])
    hints = "HINTS: " + "; ".join(hints_list) + "\n" if hints_list else ""

    room_hist = perception.get("room_history", [])
    room_history = "Visited rooms (in order): " + " → ".join(room_hist) + "\n" if len(room_hist) > 1 else ""

    return PERCEPTION_TEMPLATE.format(
        tick=perception.get("tick", 0),
        room_name=perception["room"]["name"],
        room_description=perception["room"].get("description", ""),
        entities=entities,
        exits=exits,
        others=others,
        inventory=inventory,
        recent_events=events,
        room_history=room_history,
        hints=hints,
    )


# Minimal tool definitions — short descriptions, no param descriptions
AGENT_TOOLS = [
    {
        "name": "move",
        "description": "Move through a door: north/south/east/west",
        "input_schema": {
            "type": "object",
            "properties": {"direction": {"type": "string"}},
            "required": ["direction"],
        },
    },
    {
        "name": "pick_up",
        "description": "Pick up an item from the room",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "drop",
        "description": "Drop an inventory item in the room",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "use",
        "description": "Use an inventory item on a target (e.g. key on door)",
        "input_schema": {
            "type": "object",
            "properties": {"item": {"type": "string"}, "target": {"type": "string"}},
            "required": ["item", "target"],
        },
    },
    {
        "name": "examine",
        "description": "Examine an object or 'room' for details",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "talk",
        "description": "Say something. Use 'to' for a specific agent",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}, "to": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "interact",
        "description": "Enter a code, password, or pull a lever",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}, "payload": {"type": "string"}},
            "required": ["target", "payload"],
        },
    },
    {
        "name": "combine",
        "description": "Combine two inventory items into a new item",
        "input_schema": {
            "type": "object",
            "properties": {"item_a": {"type": "string"}, "item_b": {"type": "string"}},
            "required": ["item_a", "item_b"],
        },
    },
]
