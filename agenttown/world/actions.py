"""Action definitions — the interface agents use to affect the world."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Move(BaseModel):
    type: Literal["move"] = "move"
    direction: str  # "north", "south", "east", "west"


class PickUp(BaseModel):
    type: Literal["pick_up"] = "pick_up"
    target: str  # entity name


class Drop(BaseModel):
    type: Literal["drop"] = "drop"
    target: str  # item name from inventory


class Use(BaseModel):
    type: Literal["use"] = "use"
    item: str  # item name from inventory
    target: str  # entity name in room


class Examine(BaseModel):
    type: Literal["examine"] = "examine"
    target: str  # entity name in room, or "room" for room description


class Talk(BaseModel):
    type: Literal["talk"] = "talk"
    message: str
    to: str | None = None  # agent name, or None for everyone in room


class Wait(BaseModel):
    type: Literal["wait"] = "wait"


Action = Move | PickUp | Drop | Use | Examine | Talk | Wait


def parse_action(data: dict) -> Action:
    """Parse a dict into the correct Action type."""
    action_map = {
        "move": Move,
        "pick_up": PickUp,
        "drop": Drop,
        "use": Use,
        "examine": Examine,
        "talk": Talk,
        "wait": Wait,
    }
    action_type = data.get("type", "wait")
    cls = action_map.get(action_type)
    if cls is None:
        return Wait()
    return cls(**data)
