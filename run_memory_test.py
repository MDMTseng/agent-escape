"""Run the memory test scenario with Claude agents and display memory state."""

import asyncio
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agenttown.agents.brain import ClaudeBrain
from agenttown.scenarios.memory_test import build_memory_test
from agenttown.world.events import Event

console = Console()


def render_tick(tick: int, events: list[Event], brains: dict[str, ClaudeBrain]) -> None:
    """Render one tick: events + memory state for each agent."""

    # Events
    if events:
        lines = Text()
        for e in events:
            color = {
                "move": "cyan", "pick_up": "green", "use": "magenta",
                "examine": "blue", "talk": "white", "fail": "red",
                "state_change": "bright_yellow", "wait": "dim", "drop": "yellow",
            }.get(e.event_type, "white")
            lines.append(f"  {e.description}\n", style=color)
        console.print(Panel(lines, title=f"Tick {tick}", border_style="bright_blue"))

    # Memory state for each agent
    for agent_id, brain in brains.items():
        mem = brain.memory
        table = Table(title=f"{agent_id} — Memory", show_lines=True, border_style="dim")
        table.add_column("Section", style="bold", width=15)
        table.add_column("Content", ratio=1)

        # Working memory
        wm = mem.working_memory_text()
        table.add_row("Working Memory", wm)

        # Reflections
        refs = mem.get_reflections(3)
        if refs:
            ref_text = "\n".join(f"[Tick {r.tick}] {r.content}" for r in refs)
        else:
            ref_text = "(none yet)"
        table.add_row("Reflections", ref_text)

        # Recent stream (last 3)
        recent = mem.recent(3)
        if recent:
            stream_text = "\n".join(
                f"[T{r.tick}] imp={r.importance} ({r.category}) {r.content[:80]}"
                for r in recent
            )
        else:
            stream_text = "(empty)"
        table.add_row("Stream (last 3)", stream_text)

        console.print(table)


async def main() -> None:
    world, agent_ids = build_memory_test()

    brains: dict[str, ClaudeBrain] = {aid: ClaudeBrain() for aid in agent_ids}

    console.print(Panel(
        "[bold]Memory Test Scenario[/bold]\n"
        "Agent A: Library (has the code note)\n"
        "Agent B: Lab (has the lock box)\n\n"
        "Goal: A reads code → tells B → one of them enters code → speak password",
        border_style="green",
    ))

    max_ticks = 30
    for tick_num in range(max_ticks):
        if world.finished:
            break

        agents = list(world.state.agents.values())
        perceptions = {a.id: world.perceive(a) for a in agents}

        decisions = await asyncio.gather(*[
            brains[a.id].decide(a, perceptions[a.id]) for a in agents
        ])

        all_events: list[Event] = []
        for agent, action in zip(agents, decisions):
            events = world.process_action(action, agent)
            all_events.extend(events)

        render_tick(tick_num, all_events, brains)
        world.advance_tick()

        if world.finished:
            console.print(Panel(
                f"[bold green]COMPLETE![/bold green]\n{world.state.finish_reason}",
                border_style="green",
            ))
            break

        await asyncio.sleep(0.5)

    if not world.finished:
        console.print(Panel("[bold red]Timed out — agents couldn't solve it[/bold red]", border_style="red"))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
