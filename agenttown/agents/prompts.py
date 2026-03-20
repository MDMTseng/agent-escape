"""Prompt templates and tool definitions for Claude-powered agents."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are {name}, an agent in a virtual world called AgentTown.

## Who You Are
{description}

## Your Goal
{goal}

## How the World Works
- You exist in a room-based environment. Each turn (tick), you observe your surroundings and choose ONE action.
- You can only interact with things in your current room or your inventory.
- Other agents may be in the same room — you can talk to them to share information and coordinate.
- Some objects may be hidden until you examine other objects.
- Doors may be locked — you'll need to find keys or solve puzzles to progress.

## Your Memory
Below is a summary of what you remember from recent ticks:
{memory_summary}

## Strategy Tips
- Examine everything — objects often have hidden clues or reveal new items.
- Talk to other agents to share discoveries and coordinate.
- Keep track of clues — numbers, words, and patterns may be puzzle solutions.
- Try using items on objects that seem related (keys on doors, etc.).
- Think step by step before acting.
"""

PERCEPTION_TEMPLATE = """\
## Current Situation (Tick {tick})

**Location**: {room_name}
{room_description}

**You see**: {entities}

**Exits**: {exits}

**Others here**: {others}

**Your inventory**: {inventory}

**What just happened**:
{recent_events}

Choose your next action. Think about what you know and what you still need to figure out.\
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
        f"{e['name']} ({e['state']})" if e.get("state", "default") != "default"
        else e["name"]
        for e in perception.get("entities", [])
    ) or "nothing notable"

    exits = ", ".join(
        f"{e['direction']} ({e['name']})"
        for e in perception.get("exits", [])
    ) or "no visible exits"

    others = ", ".join(
        o["name"] for o in perception.get("others", [])
    ) or "nobody"

    inventory = ", ".join(
        i["name"] for i in perception.get("inventory", [])
    ) or "empty"

    events = "\n".join(
        f"- {e}" for e in perception.get("recent_events", [])
    ) or "- Nothing happened recently."

    return PERCEPTION_TEMPLATE.format(
        tick=perception.get("tick", 0),
        room_name=perception["room"]["name"],
        room_description=perception["room"].get("description", ""),
        entities=entities,
        exits=exits,
        others=others,
        inventory=inventory,
        recent_events=events,
    )


# Tool definitions matching our Action types — sent to Claude as tools
AGENT_TOOLS = [
    {
        "name": "move",
        "description": "Move through a door in the specified direction to enter another room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "The direction to move (e.g. 'north', 'south', 'east', 'west')",
                }
            },
            "required": ["direction"],
        },
    },
    {
        "name": "pick_up",
        "description": "Pick up an item from the current room and add it to your inventory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "The name of the item to pick up",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "drop",
        "description": "Drop an item from your inventory into the current room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "The name of the item to drop",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "use",
        "description": "Use an item from your inventory on a target object or door in the room. For example, use a key on a locked door.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "The name of the item from your inventory to use",
                },
                "target": {
                    "type": "string",
                    "description": "The name of the object or door to use the item on",
                },
            },
            "required": ["item", "target"],
        },
    },
    {
        "name": "examine",
        "description": "Examine something closely to get more details. Use 'room' to look around the whole room, or specify an object/item name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "What to examine: 'room' for surroundings, or the name of a specific object/item",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "talk",
        "description": "Say something out loud. Other agents in the room will hear you. Optionally direct your message to a specific agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "What to say",
                },
                "to": {
                    "type": "string",
                    "description": "Name of a specific agent to talk to (optional — omit to speak to everyone in the room)",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "interact",
        "description": "Interact with a puzzle or mechanism by providing input. Use this to: enter a combination code on a lock, speak a password to a magic door, or pull a lever. The payload is the input you provide (a code, a password, or 'pull').",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "The name of the puzzle or mechanism to interact with",
                },
                "payload": {
                    "type": "string",
                    "description": "The input to provide: a combination code (e.g. '1847'), a password (e.g. 'open sesame'), or 'pull' for a lever",
                },
            },
            "required": ["target", "payload"],
        },
    },
    {
        "name": "combine",
        "description": "Combine two items from your inventory to create something new. Some items can be combined together to form a new useful item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_a": {
                    "type": "string",
                    "description": "Name of the first item from your inventory",
                },
                "item_b": {
                    "type": "string",
                    "description": "Name of the second item from your inventory",
                },
            },
            "required": ["item_a", "item_b"],
        },
    },
    {
        "name": "wait",
        "description": "Do nothing this turn. Use when you want to observe or let others act first.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]
