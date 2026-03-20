"""AgentTown — main entry point and tick loop."""

from __future__ import annotations

import asyncio
import sys
from typing import Protocol

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agenttown.world.actions import Action, Wait, parse_action
from agenttown.world.events import Event
from agenttown.world.models import AgentState
from agenttown.world.world import World

console = Console()


class AgentBrain(Protocol):
    """Interface that any agent implementation must satisfy."""

    async def decide(self, agent: AgentState, perception: dict) -> Action: ...


class RandomBrain:
    """A dummy brain that picks random valid actions — for testing without Claude."""

    import random

    def __init__(self, seed: int | None = None):
        self._rng = self.random.Random(seed)

    async def decide(self, agent: AgentState, perception: dict) -> Action:
        choices: list[dict] = []

        # Can examine room
        choices.append({"type": "examine", "target": "room"})

        # Can examine any visible entity
        for entity in perception.get("entities", []):
            choices.append({"type": "examine", "target": entity["name"]})

        # Can move through exits
        for exit_info in perception.get("exits", []):
            choices.append({"type": "move", "direction": exit_info["direction"]})

        # Can pick up entities (try all, rules engine will reject non-items)
        for entity in perception.get("entities", []):
            choices.append({"type": "pick_up", "target": entity["name"]})

        # Can talk to others
        for other in perception.get("others", []):
            choices.append({"type": "talk", "message": "Hello!", "to": other["name"]})

        if not choices:
            return Wait()

        return parse_action(self._rng.choice(choices))


def render_events(events: list[Event], tick: int) -> None:
    """Render tick events to the terminal."""
    if not events:
        return

    lines = Text()
    for event in events:
        color = {
            "move": "cyan",
            "pick_up": "green",
            "drop": "yellow",
            "use": "magenta",
            "examine": "blue",
            "talk": "white",
            "fail": "red",
            "state_change": "bright_yellow",
            "wait": "dim",
        }.get(event.event_type, "white")

        lines.append(f"  {event.description}\n", style=color)

    console.print(Panel(lines, title=f"Tick {tick}", border_style="bright_blue"))


async def run_simulation(
    world: World,
    brains: dict[str, AgentBrain],
    tick_interval: float = 1.0,
    max_ticks: int = 100,
) -> None:
    """Main simulation loop."""
    console.print(
        Panel(
            "[bold]AgentTown Simulation[/bold]\n"
            f"Agents: {', '.join(a.name for a in world.state.agents.values())}\n"
            f"Rooms: {', '.join(r.name for r in world.state.rooms.values())}",
            border_style="green",
        )
    )

    while not world.finished and world.tick < max_ticks:
        agents = list(world.state.agents.values())

        # 1. Build perceptions for all agents
        perceptions = {agent.id: world.perceive(agent) for agent in agents}

        # 2. All agents decide concurrently
        decisions = await asyncio.gather(*[
            brains[agent.id].decide(agent, perceptions[agent.id])
            for agent in agents
        ])

        # 3. Execute actions sequentially (avoids conflicts)
        all_events: list[Event] = []
        for agent, action in zip(agents, decisions):
            events = world.process_action(action, agent)
            all_events.extend(events)

        # 4. Render
        render_events(all_events, world.tick)

        # 5. Advance
        world.advance_tick()

        if world.finished:
            console.print(
                Panel(
                    f"[bold green]SIMULATION COMPLETE[/bold green]\n{world.state.finish_reason}",
                    border_style="green",
                )
            )
            break

        await asyncio.sleep(tick_interval)

    if world.tick >= max_ticks:
        console.print(Panel("[bold red]Max ticks reached.[/bold red]", border_style="red"))


def main() -> None:
    """CLI entry point — runs the escape room demo with random brains."""
    from agenttown.scenarios.escape_room import build_escape_room

    world, agent_ids = build_escape_room()

    brains: dict[str, AgentBrain] = {aid: RandomBrain() for aid in agent_ids}

    try:
        asyncio.run(run_simulation(world, brains, tick_interval=0.5, max_ticks=50))
    except KeyboardInterrupt:
        console.print("\n[yellow]Simulation interrupted.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
