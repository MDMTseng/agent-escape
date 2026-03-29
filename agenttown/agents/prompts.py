"""Prompt templates and tool definitions — optimized for minimal token usage."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are {name}. {description}
Goal: {goal}

Rules:
- Pick 1-3 actions per turn. Actions execute in order.
- PRIORITY: Move to unexplored rooms whenever possible. Don't stay in one room too long.
- Examine objects to find clues — clues hide in descriptions and examine results.
- When you find a code, USE it immediately (interact). When you find a key, USE it on a door.
- Talk to share discoveries with your partner, but keep it brief — one message, then act.
- NEVER examine the same object twice. If you examined it before, the result won't change.
- NEVER ask the same question twice. If your partner didn't answer, they don't know — move on.
- If you're stuck, go to a DIFFERENT room or examine something you haven't tried yet.
- If all exits are locked, look for clues in the current room you haven't examined yet.

{memory_summary}
{action_history}\
"""

PERCEPTION_TEMPLATE = """\
Tick {tick} | {room_name}: {room_description}
See: {entities} | Exits: {exits} | Others: {others} | Inventory: {inventory}
{last_results}Events: {recent_events}
{changes}{messages_for_agent}{room_exploration}{hints}Think before acting. What do you know? What do you need?\
"""


def build_system_prompt(
    name: str, description: str, goal: str, memory_summary: str,
    action_history: str = "",
) -> str:
    return SYSTEM_PROMPT.format(
        name=name,
        description=description,
        goal=goal,
        memory_summary=memory_summary,
        action_history=action_history,
    )


def build_perception_message(perception: dict) -> str:
    entities = ", ".join(
        f"{e['name']}({e['state']})" if e.get("state", "default") != "default"
        else e["name"]
        for e in perception.get("entities", [])
    ) or "nothing"

    exits = ", ".join(
        f"{e['direction']}{' [locked]' if 'locked' in e.get('name', '') else ''}"
        for e in perception.get("exits", [])
    ) or "none"

    others = ", ".join(
        o["name"] for o in perception.get("others", [])
    ) or "none"

    inventory = ", ".join(
        i["name"] for i in perception.get("inventory", [])
    ) or "empty"

    events = "; ".join(perception.get("recent_events", [])) or "none"

    # Last tick's action results — what happened when you acted
    last_results_list = perception.get("last_results", [])
    last_results = "Your last actions: " + "; ".join(last_results_list) + "\n" if last_results_list else ""

    hints_list = perception.get("hints", [])
    hints = "Observations: " + "; ".join(hints_list) + "\n" if hints_list else ""

    # Changes since last tick
    changes_list = perception.get("changes", [])
    changes = "Changes: " + "; ".join(changes_list) + "\n" if changes_list else ""

    # Messages directed to this agent
    msg_list = perception.get("messages_for_agent", [])
    messages_for_agent = "Messages for you: " + "; ".join(msg_list) + "\n" if msg_list else ""

    # Room exploration info (visited vs fully explored)
    visited_rooms = perception.get("visited_rooms", [])
    explored_rooms = perception.get("explored_rooms", [])
    room_exploration_parts = []
    if visited_rooms:
        room_exploration_parts.append("Visited rooms: " + ", ".join(visited_rooms))
    if explored_rooms:
        room_exploration_parts.append("Fully explored rooms: " + ", ".join(explored_rooms))
    room_exploration = " | ".join(room_exploration_parts) + "\n" if room_exploration_parts else ""

    return PERCEPTION_TEMPLATE.format(
        tick=perception.get("tick", 0),
        room_name=perception["room"]["name"],
        room_description=perception["room"].get("description", ""),
        entities=entities,
        exits=exits,
        others=others,
        inventory=inventory,
        recent_events=events,
        last_results=last_results,
        changes=changes,
        messages_for_agent=messages_for_agent,
        room_exploration=room_exploration,
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
