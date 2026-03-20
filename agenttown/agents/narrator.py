"""Narrator — an LLM that transforms raw game events into atmospheric storytelling."""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from agenttown.world.events import Event
from agenttown.world.models import WorldState

logger = logging.getLogger(__name__)

NARRATOR_SYSTEM_PROMPT = """\
You are the narrator of a dark, atmospheric escape room story set in Ravenwood Manor, \
an abandoned estate with a sinister history.

Your job is to take raw game events and transform them into vivid, immersive prose. \
Write in third person, present tense. Keep each narration to 2-4 sentences.

Style guidelines:
- Use sensory details: sounds, smells, textures, light
- Build tension and atmosphere — this is a mystery/horror setting
- Give each agent a distinct voice in dialogue (Alice is careful and analytical, Bob is bold and impulsive)
- When agents discover clues, make it feel like a revelation
- When puzzles are solved, convey the satisfaction and mechanical sounds
- When things fail, convey frustration or danger
- Never break the fourth wall or mention "game mechanics"
- Do NOT add events that didn't happen — only narrate what the raw events describe
"""

NARRATE_TEMPLATE = """\
## World State
Location descriptions:
{room_descriptions}

## Characters
{agent_descriptions}

## Events This Tick (Tick {tick})
{raw_events}

Transform these events into atmospheric narrative prose. Keep it concise (2-4 sentences per event). \
Write all narration in a single flowing passage.\
"""


class Narrator:
    """Transforms raw game events into narrative prose using an LLM."""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 512,
        api_key: str | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def narrate(
        self, events: list[Event], world_state: WorldState, tick: int
    ) -> str:
        """Convert a list of raw events into narrative prose."""
        if not events:
            return ""

        # Filter out boring events
        interesting = [e for e in events if e.event_type != "wait"]
        if not interesting:
            return "_The manor is silent. Dust motes drift through stale air._"

        raw_lines = "\n".join(f"- [{e.event_type}] {e.description}" for e in interesting)

        # Build room context
        rooms_involved = {e.room_id for e in interesting}
        room_descs = []
        for rid in rooms_involved:
            if rid in world_state.rooms:
                r = world_state.rooms[rid]
                room_descs.append(f"**{r.name}**: {r.description}")
        room_text = "\n".join(room_descs) if room_descs else "Unknown location."

        # Build agent context
        agent_descs = []
        for agent in world_state.agents.values():
            inv = ", ".join(i.name for i in agent.inventory) or "nothing"
            agent_descs.append(
                f"**{agent.name}** ({agent.description}) — "
                f"in {world_state.rooms.get(agent.room_id, agent.room_id)}, carrying: {inv}"
            )
        agent_text = "\n".join(agent_descs)

        prompt = NARRATE_TEMPLATE.format(
            room_descriptions=room_text,
            agent_descriptions=agent_text,
            tick=tick,
            raw_events=raw_lines,
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=NARRATOR_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Narrator error: {e}")
            # Fallback: return raw events as-is
            return "\n".join(e.description for e in interesting)
