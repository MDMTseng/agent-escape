"""Rules engine — validates and executes actions against the world state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .actions import Action, Drop, Examine, Move, PickUp, Talk, Use, Wait
from .events import Event
from .models import Door, EntityState, Item

if TYPE_CHECKING:
    from .models import AgentState, WorldState


class ActionResult:
    def __init__(self, success: bool, events: list[Event], reason: str = ""):
        self.success = success
        self.events = events
        self.reason = reason


def _visible_agents(world: WorldState, room_id: str) -> list[str]:
    """Get IDs of all agents in a room."""
    return [a.id for a in world.agents_in_room(room_id)]


def _make_event(
    tick: int,
    event_type: str,
    actor: AgentState,
    room_id: str,
    description: str,
    world: WorldState,
    **data: object,
) -> Event:
    return Event(
        tick=tick,
        event_type=event_type,
        actor_id=actor.id,
        room_id=room_id,
        description=description,
        visible_to=_visible_agents(world, room_id),
        data=dict(data),
    )


def execute_action(
    action: Action, agent: AgentState, world: WorldState, tick: int
) -> ActionResult:
    """Validate and execute an action, returning events."""
    match action:
        case Move():
            return _execute_move(action, agent, world, tick)
        case PickUp():
            return _execute_pick_up(action, agent, world, tick)
        case Drop():
            return _execute_drop(action, agent, world, tick)
        case Use():
            return _execute_use(action, agent, world, tick)
        case Examine():
            return _execute_examine(action, agent, world, tick)
        case Talk():
            return _execute_talk(action, agent, world, tick)
        case Wait():
            return ActionResult(
                success=True,
                events=[
                    _make_event(tick, "wait", agent, agent.room_id, f"{agent.name} waits.", world)
                ],
            )
        case _:
            return ActionResult(success=False, events=[], reason="Unknown action type")


def _execute_move(action: Move, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)
    door_id = room.doors.get(action.direction)

    if door_id is None:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} tries to go {action.direction} but there is no exit that way.",
                    world,
                )
            ],
            reason=f"No exit {action.direction}",
        )

    door = world.doors[door_id]

    if door.locked:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} tries to go {action.direction} but the door is locked.",
                    world,
                )
            ],
            reason="Door is locked",
        )

    old_room_id = agent.room_id
    new_room_id = door.other_side(room.id)
    agent.room_id = new_room_id
    new_room = world.get_room(new_room_id)

    events = [
        _make_event(
            tick, "move", agent, old_room_id,
            f"{agent.name} leaves through the {action.direction} door.",
            world,
        ),
        _make_event(
            tick, "move", agent, new_room_id,
            f"{agent.name} enters {new_room.name}.",
            world,
        ),
    ]
    return ActionResult(success=True, events=events)


def _execute_pick_up(action: PickUp, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)
    matches = room.get_entities_by_name(action.target)

    items = [e for e in matches if isinstance(e, Item) and e.state != EntityState.HIDDEN]
    if not items:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} looks for '{action.target}' but can't find anything to pick up.",
                    world,
                )
            ],
            reason=f"No pickable item '{action.target}' found",
        )

    item = items[0]
    if not item.portable:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} tries to pick up {item.name} but it's too heavy or fixed in place.",
                    world,
                )
            ],
            reason="Item is not portable",
        )

    room.remove_entity(item.id)
    agent.add_item(item)

    return ActionResult(
        success=True,
        events=[
            _make_event(
                tick, "pick_up", agent, room.id,
                f"{agent.name} picks up {item.name}.",
                world,
            )
        ],
    )


def _execute_drop(action: Drop, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    item = agent.has_item(action.target)
    if item is None:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, agent.room_id,
                    f"{agent.name} tries to drop '{action.target}' but doesn't have it.",
                    world,
                )
            ],
            reason="Item not in inventory",
        )

    agent.remove_item(item.id)
    room = world.get_agent_room(agent)
    room.add_entity(item)

    return ActionResult(
        success=True,
        events=[
            _make_event(
                tick, "drop", agent, room.id,
                f"{agent.name} drops {item.name}.",
                world,
            )
        ],
    )


def _execute_use(action: Use, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    item = agent.has_item(action.item)
    if item is None:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, agent.room_id,
                    f"{agent.name} tries to use '{action.item}' but doesn't have it.",
                    world,
                )
            ],
            reason="Item not in inventory",
        )

    room = world.get_agent_room(agent)

    # Check room entities
    targets = room.get_entities_by_name(action.target)
    visible_targets = [t for t in targets if t.state != EntityState.HIDDEN]

    # Check doors
    for door_id in room.doors.values():
        door = world.doors[door_id]
        if action.target.lower() in door.name.lower():
            visible_targets.append(door)

    if not visible_targets:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} tries to use {item.name} on '{action.target}' but can't find it.",
                    world,
                )
            ],
            reason=f"Target '{action.target}' not found",
        )

    target = visible_targets[0]

    # Key + locked door interaction
    if isinstance(target, Door) and target.locked and target.key_id == item.id:
        target.locked = False
        target.state = EntityState.UNLOCKED
        agent.remove_item(item.id)
        return ActionResult(
            success=True,
            events=[
                _make_event(
                    tick, "use", agent, room.id,
                    f"{agent.name} uses {item.name} on {target.name}. The door unlocks with a click!",
                    world,
                )
            ],
        )

    # Generic usable_on check
    if item.usable_on and target.name.lower() not in [n.lower() for n in item.usable_on]:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} tries to use {item.name} on {target.name} but nothing happens.",
                    world,
                )
            ],
            reason="Item can't be used on this target",
        )

    # Custom interaction via properties
    on_use = target.properties.get("on_use")
    if on_use:
        return _handle_custom_use(on_use, item, target, agent, room, world, tick)

    return ActionResult(
        success=False,
        events=[
            _make_event(
                tick, "fail", agent, room.id,
                f"{agent.name} tries to use {item.name} on {target.name} but nothing interesting happens.",
                world,
            )
        ],
        reason="No interaction defined",
    )


def _handle_custom_use(
    on_use: dict, item: Item, target, agent: AgentState, room, world: WorldState, tick: int
) -> ActionResult:
    """Handle custom use interactions defined in entity properties."""
    events = []

    if "reveal" in on_use:
        for reveal_id in on_use["reveal"]:
            for entity in room.entities.values():
                if entity.id == reveal_id and entity.state == EntityState.HIDDEN:
                    entity.state = EntityState.DEFAULT
                    events.append(
                        _make_event(
                            tick, "state_change", agent, room.id,
                            f"{entity.name} is revealed!",
                            world,
                        )
                    )

    if "set_state" in on_use:
        target.state = EntityState(on_use["set_state"])
        events.append(
            _make_event(
                tick, "state_change", agent, room.id,
                f"{target.name} is now {target.state.value}.",
                world,
            )
        )

    if "message" in on_use:
        events.append(
            _make_event(
                tick, "use", agent, room.id,
                f"{agent.name} uses {item.name} on {target.name}. {on_use['message']}",
                world,
            )
        )

    if "consume_item" in on_use and on_use["consume_item"]:
        agent.remove_item(item.id)

    if "finish" in on_use:
        world.finished = True
        world.finish_reason = on_use["finish"]
        events.append(
            _make_event(
                tick, "state_change", agent, room.id,
                on_use["finish"],
                world,
            )
        )

    if not events:
        events.append(
            _make_event(
                tick, "use", agent, room.id,
                f"{agent.name} uses {item.name} on {target.name}.",
                world,
            )
        )

    return ActionResult(success=True, events=events)


def _execute_examine(action: Examine, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)

    # Examine the room itself
    if action.target.lower() in ("room", "around", "surroundings"):
        entities_desc = ", ".join(e.name for e in room.visible_entities()) or "nothing notable"
        doors_desc = ", ".join(f"{d} door" for d in room.doors.keys()) or "no exits"
        others = [a.name for a in world.agents_in_room(room.id) if a.id != agent.id]
        others_desc = ", ".join(others) if others else "nobody else"

        desc = (
            f"{room.name}: {room.description} "
            f"You see: {entities_desc}. "
            f"Exits: {doors_desc}. "
            f"Also here: {others_desc}."
        )
        return ActionResult(
            success=True,
            events=[
                _make_event(
                    tick, "examine", agent, room.id,
                    f"{agent.name} looks around. {desc}",
                    world,
                )
            ],
        )

    # Examine inventory item
    inv_item = agent.has_item(action.target)
    if inv_item:
        desc = inv_item.describe()
        extra = inv_item.properties.get("examine_text", "")
        full_desc = f"{desc} {extra}".strip()
        return ActionResult(
            success=True,
            events=[
                _make_event(
                    tick, "examine", agent, room.id,
                    f"{agent.name} examines {inv_item.name}: {full_desc}",
                    world,
                )
            ],
        )

    # Examine room entity
    matches = room.get_entities_by_name(action.target)
    visible = [e for e in matches if e.state != EntityState.HIDDEN]

    # Also check doors
    for direction, door_id in room.doors.items():
        door = world.doors[door_id]
        if action.target.lower() in door.name.lower():
            lock_status = "locked" if door.locked else "unlocked"
            return ActionResult(
                success=True,
                events=[
                    _make_event(
                        tick, "examine", agent, room.id,
                        f"{agent.name} examines {door.name}: {door.description} It is {lock_status}.",
                        world,
                    )
                ],
            )

    if not visible:
        return ActionResult(
            success=False,
            events=[
                _make_event(
                    tick, "fail", agent, room.id,
                    f"{agent.name} looks for '{action.target}' but can't find it.",
                    world,
                )
            ],
            reason=f"'{action.target}' not found",
        )

    entity = visible[0]
    desc = entity.describe()
    extra = entity.properties.get("examine_text", "")
    full_desc = f"{desc} {extra}".strip()

    events = [
        _make_event(
            tick, "examine", agent, room.id,
            f"{agent.name} examines {entity.name}: {full_desc}",
            world,
        )
    ]

    # Examining can reveal hidden things
    on_examine = entity.properties.get("on_examine")
    if on_examine:
        if "reveal" in on_examine:
            for reveal_id in on_examine["reveal"]:
                for e in room.entities.values():
                    if e.id == reveal_id and e.state == EntityState.HIDDEN:
                        e.state = EntityState.DEFAULT
                        events.append(
                            _make_event(
                                tick, "state_change", agent, room.id,
                                f"Something was hidden behind {entity.name}! {e.name} is now visible.",
                                world,
                            )
                        )
        if "message" in on_examine:
            events.append(
                _make_event(
                    tick, "examine", agent, room.id,
                    on_examine["message"],
                    world,
                )
            )

    return ActionResult(success=True, events=events)


def _execute_talk(action: Talk, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)
    agents_here = world.agents_in_room(room.id)

    if action.to:
        # Direct message to a specific agent
        target_agent = None
        for a in agents_here:
            if a.id != agent.id and action.to.lower() in a.name.lower():
                target_agent = a
                break

        if target_agent is None:
            return ActionResult(
                success=False,
                events=[
                    _make_event(
                        tick, "fail", agent, room.id,
                        f"{agent.name} tries to talk to '{action.to}' but they're not here.",
                        world,
                    )
                ],
                reason=f"Agent '{action.to}' not in room",
            )

        return ActionResult(
            success=True,
            events=[
                Event(
                    tick=tick,
                    event_type="talk",
                    actor_id=agent.id,
                    room_id=room.id,
                    description=f'{agent.name} says to {target_agent.name}: "{action.message}"',
                    visible_to=[agent.id, target_agent.id],
                    data={"to": target_agent.id, "message": action.message},
                )
            ],
        )

    # Broadcast to room
    return ActionResult(
        success=True,
        events=[
            _make_event(
                tick, "talk", agent, room.id,
                f'{agent.name} says: "{action.message}"',
                world,
            )
        ],
    )
