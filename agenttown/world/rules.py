"""Rules engine — validates and executes actions against the world state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .actions import (
    Action, Combine, Drop, Examine, Interact, Move, PickUp, Talk, Use, Wait,
)
from .events import Event
from .models import Door, EntityState, Item

if TYPE_CHECKING:
    from .models import AgentState, Entity, Room, WorldState


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


# ---------------------------------------------------------------------------
# Shared solve handler — used by all puzzle types
# ---------------------------------------------------------------------------

def _handle_solve(
    on_solve: dict,
    agent: AgentState,
    room: Room,
    world: WorldState,
    tick: int,
    target: Entity | None = None,
    item: Item | None = None,
) -> list[Event]:
    """Handle solve/trigger effects defined in entity properties.

    Supported keys:
        reveal       — list of entity IDs to unhide in the room
        set_state    — change target entity state
        message      — emit a descriptive event
        consume_item — remove the used item from inventory
        unlock_door  — unlock a door by ID
        spawn_item   — dict describing a new Item to add to the room
        finish       — end the simulation with a reason string
    """
    events: list[Event] = []

    if "reveal" in on_solve:
        for reveal_id in on_solve["reveal"]:
            for entity in room.entities.values():
                if entity.id == reveal_id and entity.state == EntityState.HIDDEN:
                    entity.state = EntityState.DEFAULT
                    events.append(
                        _make_event(tick, "state_change", agent, room.id,
                                    f"{entity.name} is revealed!", world)
                    )

    if "set_state" in on_solve and target is not None:
        target.state = EntityState(on_solve["set_state"])
        events.append(
            _make_event(tick, "state_change", agent, room.id,
                        f"{target.name} is now {target.state.value}.", world)
        )

    if "unlock_door" in on_solve:
        door_id = on_solve["unlock_door"]
        if door_id in world.doors:
            door = world.doors[door_id]
            door.locked = False
            door.state = EntityState.UNLOCKED
            events.append(
                _make_event(tick, "state_change", agent, room.id,
                            f"{door.name} unlocks with a click!", world)
            )

    if "spawn_item" in on_solve:
        item_data = on_solve["spawn_item"]
        new_item = Item(**item_data)
        room.add_entity(new_item)
        events.append(
            _make_event(tick, "state_change", agent, room.id,
                        f"{new_item.name} appears!", world)
        )

    if "message" in on_solve:
        prefix = ""
        if item and target:
            prefix = f"{agent.name} uses {item.name} on {target.name}. "
        elif target:
            prefix = f"{agent.name} interacts with {target.name}. "
        events.append(
            _make_event(tick, "use", agent, room.id,
                        f"{prefix}{on_solve['message']}", world)
        )

    if "consume_item" in on_solve and on_solve["consume_item"] and item:
        agent.remove_item(item.id)

    if "finish" in on_solve:
        world.finished = True
        world.finish_reason = on_solve["finish"]
        events.append(
            _make_event(tick, "state_change", agent, room.id,
                        on_solve["finish"], world)
        )

    return events


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

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
        case Interact():
            return _execute_interact(action, agent, world, tick)
        case Combine():
            return _execute_combine(action, agent, world, tick)
        case Wait():
            return ActionResult(
                success=True,
                events=[
                    _make_event(tick, "wait", agent, agent.room_id,
                                f"{agent.name} waits.", world)
                ],
            )
        case _:
            return ActionResult(success=False, events=[], reason="Unknown action type")


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------

def _execute_move(action: Move, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)
    door_id = room.doors.get(action.direction)

    if door_id is None:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} tries to go {action.direction} but there is no exit that way.",
                                world)],
            reason=f"No exit {action.direction}",
        )

    door = world.doors[door_id]

    if door.locked:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} tries to go {action.direction} but the door is locked.",
                                world)],
            reason="Door is locked",
        )

    old_room_id = agent.room_id
    new_room_id = door.other_side(room.id)
    agent.room_id = new_room_id
    new_room = world.get_room(new_room_id)

    events = [
        _make_event(tick, "move", agent, old_room_id,
                    f"{agent.name} leaves through the {action.direction} door.", world),
        _make_event(tick, "move", agent, new_room_id,
                    f"{agent.name} enters {new_room.name}.", world),
    ]
    return ActionResult(success=True, events=events)


# ---------------------------------------------------------------------------
# PickUp
# ---------------------------------------------------------------------------

def _execute_pick_up(action: PickUp, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)
    matches = room.get_entities_by_name(action.target)

    items = [e for e in matches if isinstance(e, Item) and e.state != EntityState.HIDDEN]
    if not items:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} looks for '{action.target}' but can't find anything to pick up.",
                                world)],
            reason=f"No pickable item '{action.target}' found",
        )

    item = items[0]
    if not item.portable:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} tries to pick up {item.name} but it's too heavy or fixed in place.",
                                world)],
            reason="Item is not portable",
        )

    room.remove_entity(item.id)
    agent.add_item(item)

    return ActionResult(
        success=True,
        events=[_make_event(tick, "pick_up", agent, room.id,
                            f"{agent.name} picks up {item.name}.", world)],
    )


# ---------------------------------------------------------------------------
# Drop — with pressure plate trigger
# ---------------------------------------------------------------------------

def _execute_drop(action: Drop, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    item = agent.has_item(action.target)
    if item is None:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, agent.room_id,
                                f"{agent.name} tries to drop '{action.target}' but doesn't have it.",
                                world)],
            reason="Item not in inventory",
        )

    agent.remove_item(item.id)
    room = world.get_agent_room(agent)
    room.add_entity(item)

    events = [_make_event(tick, "drop", agent, room.id,
                          f"{agent.name} drops {item.name}.", world)]

    # --- Mechanism 2: Pressure Plate ---
    trigger_events = _check_pressure_plates(item, agent, room, world, tick)
    events.extend(trigger_events)

    return ActionResult(success=True, events=events)


def _check_pressure_plates(
    dropped_item: Item, agent: AgentState, room: Room, world: WorldState, tick: int
) -> list[Event]:
    """After dropping, check if any pressure plate in the room is triggered."""
    events: list[Event] = []
    for entity in list(room.entities.values()):
        if entity.properties.get("puzzle_type") != "pressure_plate":
            continue
        if entity.state == EntityState.SOLVED:
            continue
        required = entity.properties.get("required_weight", "heavy")
        item_weight = dropped_item.properties.get("weight", "light")
        if item_weight == required:
            on_solve = entity.properties.get("on_solve", {})
            events.append(
                _make_event(tick, "state_change", agent, room.id,
                            f"The {entity.name} sinks under the weight of {dropped_item.name}!",
                            world)
            )
            solve_events = _handle_solve(on_solve, agent, room, world, tick, target=entity)
            events.extend(solve_events)
    return events


# ---------------------------------------------------------------------------
# Use (key on door, custom on_use)
# ---------------------------------------------------------------------------

def _execute_use(action: Use, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    item = agent.has_item(action.item)
    if item is None:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, agent.room_id,
                                f"{agent.name} tries to use '{action.item}' but doesn't have it.",
                                world)],
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
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} tries to use {item.name} on '{action.target}' but can't find it.",
                                world)],
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
            events=[_make_event(tick, "use", agent, room.id,
                                f"{agent.name} uses {item.name} on {target.name}. The door unlocks with a click!",
                                world)],
        )

    # Generic usable_on check
    if item.usable_on and target.name.lower() not in [n.lower() for n in item.usable_on]:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} tries to use {item.name} on {target.name} but nothing happens.",
                                world)],
            reason="Item can't be used on this target",
        )

    # Custom interaction via properties
    on_use = target.properties.get("on_use")
    if on_use:
        events = _handle_solve(on_use, agent, room, world, tick, target=target, item=item)
        if not events:
            events = [_make_event(tick, "use", agent, room.id,
                                  f"{agent.name} uses {item.name} on {target.name}.", world)]
        return ActionResult(success=True, events=events)

    return ActionResult(
        success=False,
        events=[_make_event(tick, "fail", agent, room.id,
                            f"{agent.name} tries to use {item.name} on {target.name} but nothing interesting happens.",
                            world)],
        reason="No interaction defined",
    )


# ---------------------------------------------------------------------------
# Examine
# ---------------------------------------------------------------------------

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
            events=[_make_event(tick, "examine", agent, room.id,
                                f"{agent.name} looks around. {desc}", world)],
        )

    # Examine inventory item
    inv_item = agent.has_item(action.target)
    if inv_item:
        desc = inv_item.describe()
        extra = inv_item.properties.get("examine_text", "")
        full_desc = f"{desc} {extra}".strip()
        return ActionResult(
            success=True,
            events=[_make_event(tick, "examine", agent, room.id,
                                f"{agent.name} examines {inv_item.name}: {full_desc}", world)],
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
                events=[_make_event(tick, "examine", agent, room.id,
                                    f"{agent.name} examines {door.name}: {door.description} It is {lock_status}.",
                                    world)],
            )

    if not visible:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} looks for '{action.target}' but can't find it.",
                                world)],
            reason=f"'{action.target}' not found",
        )

    entity = visible[0]
    desc = entity.describe()
    extra = entity.properties.get("examine_text", "")
    full_desc = f"{desc} {extra}".strip()

    events = [
        _make_event(tick, "examine", agent, room.id,
                    f"{agent.name} examines {entity.name}: {full_desc}", world)
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
                            _make_event(tick, "state_change", agent, room.id,
                                        f"Something was hidden behind {entity.name}! {e.name} is now visible.",
                                        world)
                        )
        if "message" in on_examine:
            events.append(
                _make_event(tick, "examine", agent, room.id,
                            on_examine["message"], world)
            )

    return ActionResult(success=True, events=events)


# ---------------------------------------------------------------------------
# Talk — with password door trigger (Mechanism 4)
# ---------------------------------------------------------------------------

def _execute_talk(action: Talk, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)
    agents_here = world.agents_in_room(room.id)

    if action.to:
        target_agent = None
        for a in agents_here:
            if a.id != agent.id and action.to.lower() in a.name.lower():
                target_agent = a
                break

        if target_agent is None:
            return ActionResult(
                success=False,
                events=[_make_event(tick, "fail", agent, room.id,
                                    f"{agent.name} tries to talk to '{action.to}' but they're not here.",
                                    world)],
                reason=f"Agent '{action.to}' not in room",
            )

        events = [
            Event(
                tick=tick,
                event_type="talk",
                actor_id=agent.id,
                room_id=room.id,
                description=f'{agent.name} says to {target_agent.name}: "{action.message}"',
                visible_to=[agent.id, target_agent.id],
                data={"to": target_agent.id, "message": action.message},
            )
        ]
    else:
        events = [
            _make_event(tick, "talk", agent, room.id,
                        f'{agent.name} says: "{action.message}"', world)
        ]

    # --- Mechanism 4: Password Door ---
    password_events = _check_speech_triggers(action.message, agent, room, world, tick)
    events.extend(password_events)

    return ActionResult(success=True, events=events)


def _check_speech_triggers(
    message: str, agent: AgentState, room: Room, world: WorldState, tick: int
) -> list[Event]:
    """Check if spoken words trigger any password-protected entities."""
    events: list[Event] = []
    msg_lower = message.lower()

    # Check room entities
    for entity in list(room.entities.values()):
        if entity.properties.get("puzzle_type") != "password_door":
            continue
        if entity.state == EntityState.SOLVED:
            continue
        password = entity.properties.get("password", "").lower()
        case_sensitive = entity.properties.get("case_sensitive", False)
        check_msg = message if case_sensitive else msg_lower
        check_pwd = entity.properties["password"] if case_sensitive else password

        if check_pwd and check_pwd in check_msg:
            on_solve = entity.properties.get("on_solve", {})
            events.append(
                _make_event(tick, "state_change", agent, room.id,
                            f'The magic words "{entity.properties["password"]}" echo through the room!',
                            world)
            )
            solve_events = _handle_solve(on_solve, agent, room, world, tick, target=entity)
            events.extend(solve_events)

    return events


# ---------------------------------------------------------------------------
# Interact — combination lock, password, levers (Mechanisms 1, 4 alt, 5)
# ---------------------------------------------------------------------------

def _execute_interact(action: Interact, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    room = world.get_agent_room(agent)

    # Find target entity
    matches = room.get_entities_by_name(action.target)
    visible = [e for e in matches if e.state != EntityState.HIDDEN]

    if not visible:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} looks for '{action.target}' but can't find it.",
                                world)],
            reason=f"'{action.target}' not found",
        )

    target = visible[0]
    puzzle_type = target.properties.get("puzzle_type", "")

    if puzzle_type == "combination_lock":
        return _interact_combination_lock(action, target, agent, room, world, tick)
    elif puzzle_type == "lever":
        return _interact_lever(action, target, agent, room, world, tick)
    elif puzzle_type == "password_door":
        return _interact_password(action, target, agent, room, world, tick)
    else:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} tries to interact with {target.name} but doesn't know how.",
                                world)],
            reason="No interaction defined for this entity",
        )


def _interact_combination_lock(
    action: Interact, target: Entity, agent: AgentState, room: Room,
    world: WorldState, tick: int,
) -> ActionResult:
    """Mechanism 1: Combination Lock — enter a code to solve."""
    if target.state == EntityState.SOLVED:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{target.name} is already solved.", world)],
            reason="Already solved",
        )

    correct_code = str(target.properties.get("combination", ""))
    entered_code = action.payload.strip()

    if entered_code == correct_code:
        on_solve = target.properties.get("on_solve", {})
        events = [
            _make_event(tick, "use", agent, room.id,
                        f'{agent.name} enters "{entered_code}" on {target.name}. It\'s correct!',
                        world)
        ]
        events.extend(_handle_solve(on_solve, agent, room, world, tick, target=target))
        return ActionResult(success=True, events=events)
    else:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f'{agent.name} enters "{entered_code}" on {target.name}. Wrong code!',
                                world)],
            reason="Wrong combination",
        )


def _interact_password(
    action: Interact, target: Entity, agent: AgentState, room: Room,
    world: WorldState, tick: int,
) -> ActionResult:
    """Mechanism 4 (alt): Password via direct interaction instead of talking."""
    if target.state == EntityState.SOLVED:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{target.name} is already solved.", world)],
            reason="Already solved",
        )

    password = target.properties.get("password", "")
    case_sensitive = target.properties.get("case_sensitive", False)
    check_input = action.payload if case_sensitive else action.payload.lower()
    check_pwd = password if case_sensitive else password.lower()

    if check_pwd and check_pwd in check_input:
        on_solve = target.properties.get("on_solve", {})
        events = [
            _make_event(tick, "state_change", agent, room.id,
                        f'{agent.name} speaks the password to {target.name}. The magic words take effect!',
                        world)
        ]
        events.extend(_handle_solve(on_solve, agent, room, world, tick, target=target))
        return ActionResult(success=True, events=events)
    else:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f'{agent.name} tries "{action.payload}" on {target.name}. Nothing happens.',
                                world)],
            reason="Wrong password",
        )


def _interact_lever(
    action: Interact, target: Entity, agent: AgentState, room: Room,
    world: WorldState, tick: int,
) -> ActionResult:
    """Mechanism 5: Sequential Levers — pull levers in correct order."""
    controller_id = target.properties.get("controller")
    if not controller_id or controller_id not in room.entities:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"{agent.name} pulls {target.name} but nothing is connected.",
                                world)],
            reason="No controller",
        )

    controller = room.entities[controller_id]
    if controller.state == EntityState.SOLVED:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, room.id,
                                f"The lever mechanism is already solved.", world)],
            reason="Already solved",
        )

    sequence = controller.properties.get("sequence", [])
    progress = controller.properties.get("progress", [])

    # Add this lever to progress
    progress.append(target.id)
    controller.properties["progress"] = progress
    target.state = EntityState.ACTIVATED

    events = [
        _make_event(tick, "use", agent, room.id,
                    f"{agent.name} pulls {target.name}. *CLUNK*", world)
    ]

    # Check if sequence matches so far
    for i, lever_id in enumerate(progress):
        if i >= len(sequence) or lever_id != sequence[i]:
            # Wrong order — reset everything
            controller.properties["progress"] = []
            for lid in sequence:
                if lid in room.entities:
                    room.entities[lid].state = EntityState.DEFAULT
            on_reset = controller.properties.get("on_reset", {})
            reset_msg = on_reset.get("message", "Wrong order! All levers snap back.")
            events.append(
                _make_event(tick, "state_change", agent, room.id, reset_msg, world)
            )
            return ActionResult(success=False, events=events, reason="Wrong lever order")

    # Correct so far — check if complete
    if len(progress) == len(sequence):
        controller.state = EntityState.SOLVED
        on_solve = controller.properties.get("on_solve", {})
        events.append(
            _make_event(tick, "state_change", agent, room.id,
                        "All levers lock into place!", world)
        )
        events.extend(_handle_solve(on_solve, agent, room, world, tick, target=controller))
        return ActionResult(success=True, events=events)

    # Partial progress
    remaining = len(sequence) - len(progress)
    events.append(
        _make_event(tick, "state_change", agent, room.id,
                    f"The lever clicks into place. {remaining} more to go.", world)
    )
    return ActionResult(success=True, events=events)


# ---------------------------------------------------------------------------
# Combine — merge two inventory items (Mechanism 3)
# ---------------------------------------------------------------------------

def _execute_combine(action: Combine, agent: AgentState, world: WorldState, tick: int) -> ActionResult:
    item_a = agent.has_item(action.item_a)
    item_b = agent.has_item(action.item_b)

    if item_a is None:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, agent.room_id,
                                f"{agent.name} doesn't have '{action.item_a}'.", world)],
            reason=f"Item '{action.item_a}' not in inventory",
        )
    if item_b is None:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, agent.room_id,
                                f"{agent.name} doesn't have '{action.item_b}'.", world)],
            reason=f"Item '{action.item_b}' not in inventory",
        )

    # Check if either item has a recipe for the other
    recipe = _find_recipe(item_a, item_b)
    if recipe is None:
        recipe = _find_recipe(item_b, item_a)

    if recipe is None:
        return ActionResult(
            success=False,
            events=[_make_event(tick, "fail", agent, agent.room_id,
                                f"{agent.name} tries to combine {item_a.name} and {item_b.name} but they don't fit together.",
                                world)],
            reason="No recipe for these items",
        )

    # Remove both items, add result
    agent.remove_item(item_a.id)
    agent.remove_item(item_b.id)

    result_data = recipe["combine_result"]
    new_item = Item(**result_data)
    agent.add_item(new_item)

    combine_msg = recipe.get("combine_message",
                             f"{agent.name} combines {item_a.name} and {item_b.name} into {new_item.name}!")

    return ActionResult(
        success=True,
        events=[_make_event(tick, "use", agent, agent.room_id, combine_msg, world)],
    )


def _find_recipe(item_a: Item, item_b: Item) -> dict | None:
    """Check if item_a has a combine recipe targeting item_b."""
    combine_with = item_a.properties.get("combine_with")
    if combine_with and combine_with.lower() in item_b.name.lower():
        if "combine_result" in item_a.properties:
            return item_a.properties
    return None
