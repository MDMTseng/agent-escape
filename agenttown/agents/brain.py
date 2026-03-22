"""LLM-powered agent brain — uses Anthropic Claude API with tool calling.

Memory architecture (Generative Agents-inspired):
  1. Working Memory — key facts always in system prompt, updated by LLM extraction
  2. Memory Stream  — scored by recency × importance, top-K retrieved each tick
  3. Reflections    — periodic "what have I learned?" summaries
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from agenttown.auth import get_api_key
from agenttown.world.actions import Action, Wait, parse_action
from agenttown.world.models import AgentState

from .memory import AgentMemory
from .prompts import AGENT_TOOLS, build_perception_message, build_system_prompt

logger = logging.getLogger(__name__)

REFLECT_PROMPT = """\
Agent {name}, goal: {goal}. Memories: {memories}. Facts: {working_memory}.
Write 1 sentence: what to do next.\
"""

# Convert tool definitions to Anthropic format
ANTHROPIC_TOOLS = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["input_schema"],
    }
    for tool in AGENT_TOOLS
]


class LLMBrain:
    """An agent brain powered by Claude API with native tool calling."""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 1024,
        api_key: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
        self._max_tokens = max_tokens
        self._api_key_override = api_key
        self._client = anthropic.Anthropic(api_key=api_key or get_api_key())
        self._memory = AgentMemory()
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # Per-call profiling: tracks input/output tokens for each call type
        self.profile: dict[str, dict[str, int]] = {
            "decide": {"input": 0, "output": 0, "calls": 0},
            "extract": {"input": 0, "output": 0, "calls": 0},
            "reflect": {"input": 0, "output": 0, "calls": 0},
        }

    def _refresh_client(self) -> None:
        """Re-create the API client with a fresh token from credentials file."""
        from agenttown.auth import _cached_at
        import agenttown.auth as _auth_mod
        _auth_mod._cached_at = 0  # force re-read
        fresh_key = get_api_key()
        self._client = anthropic.Anthropic(api_key=fresh_key)
        logger.info("API client refreshed with new token")

    def _track_usage(self, response, call_type: str = "") -> None:
        """Accumulate token usage from an API response."""
        if hasattr(response, "usage") and response.usage:
            inp = getattr(response.usage, "input_tokens", 0) or 0
            out = getattr(response.usage, "output_tokens", 0) or 0
            self.token_usage["prompt_tokens"] += inp
            self.token_usage["completion_tokens"] += out
            self.token_usage["total_tokens"] += inp + out
            if call_type and call_type in self.profile:
                self.profile[call_type]["input"] += inp
                self.profile[call_type]["output"] += out
                self.profile[call_type]["calls"] += 1

    async def decide(self, agent: AgentState, perception: dict) -> Action:
        """Given the agent's perception, ask Claude to choose an action.

        Stateless per call — no message history. All context comes from:
        - System prompt (personality, goal, memory, reflections)
        - Single user message (current perception)
        """
        tick = perception.get("tick", 0)

        perception_text = build_perception_message(perception)

        system_prompt = build_system_prompt(
            name=agent.name,
            description=agent.description,
            goal=agent.goal,
            memory_summary=self._memory.build_memory_prompt(tick, query=perception_text),
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                tools=ANTHROPIC_TOOLS,
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": perception_text}],
            )
        except anthropic.AuthenticationError:
            # Token expired — refresh and retry once
            logger.warning(f"Auth failed for {agent.name}, refreshing token...")
            self._refresh_client()
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system_prompt,
                    tools=ANTHROPIC_TOOLS,
                    tool_choice={"type": "any"},
                    messages=[{"role": "user", "content": perception_text}],
                )
            except Exception as e2:
                logger.error(f"Retry failed for {agent.name}: {e2}")
                return Wait()
        except Exception as e:
            logger.error(f"Claude API error for {agent.name}: {e}")
            return Wait()

        self._track_usage(response, "decide")

        # Extract action from tool use
        action = self._parse_response(response, agent)

        # --- Memory processing ---
        events_text = "\n".join(perception.get("recent_events", []))
        self._memory.record(
            tick=tick,
            content=events_text or perception_text[:200],
            category="observation",
        )
        self._extract_facts(agent, events_text, str(action.type) if hasattr(action, "type") else "wait", tick)

        if self._memory.should_reflect():
            self._reflect(agent, tick)

        return action

    def _extract_facts(self, agent: AgentState, events: str, action: str, tick: int) -> None:
        """Rule-based fact extraction — no LLM call. Extracts codes, quotes, key info."""
        import re
        facts = list(self._memory.get_working_memory())
        importance = 2

        # Extract quoted text (clues, inscriptions)
        quotes = re.findall(r'"([^"]{5,80})"', events)
        for q in quotes:
            fact = q[:60]
            if fact not in facts:
                facts.append(fact)
                importance = 4

        # Extract numbers that look like codes (3+ digits)
        codes = re.findall(r'\b(\d{3,})\b', events)
        for code in codes:
            fact = f"code: {code}"
            if fact not in facts:
                facts.append(fact)
                importance = 5

        # Track key events
        if "unlock" in events.lower() or "revealed" in events.lower():
            importance = 5
        elif "picks up" in events.lower() or "examines" in events.lower():
            importance = 3

        # Cap at 10 facts, keep newest
        self._memory.update_working_memory(facts[-10:])
        if self._memory._stream:
            self._memory._stream[-1].importance = importance

    def _reflect(self, agent: AgentState, tick: int) -> None:
        """LLM reflection — compact prompt, runs every N ticks."""
        recent = self._memory.recent(10)
        if not recent:
            return
        memories_text = "; ".join(f"T{m.tick}:{m.content[:40]}" for m in recent)
        prompt = REFLECT_PROMPT.format(
            name=agent.name,
            goal=agent.goal,
            memories=memories_text,
            working_memory="; ".join(self._memory.get_working_memory()[:5]),
        )
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}],
            )
            self._track_usage(response, "reflect")
            reflection = response.content[0].text.strip() if response.content else ""
            if reflection:
                self._memory.add_reflection(tick, reflection)
                logger.info(f"{agent.name} reflects: {reflection}")
        except Exception as e:
            logger.debug(f"Reflection failed for {agent.name}: {e}")

    def _parse_response(self, response: anthropic.types.Message, agent: AgentState) -> Action:
        """Extract an Action from Claude's response."""
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input if isinstance(block.input, dict) else {}
                action_data = {"type": tool_name, **tool_input}
                logger.info(f"{agent.name} decides: {tool_name}({json.dumps(tool_input)})")
                return parse_action(action_data)

        # Claude with tool_choice=any should always return a tool call,
        # but fallback just in case
        for block in response.content:
            if block.type == "text":
                logger.info(f"{agent.name} text (no tool): {block.text[:100]}")
        return Wait()

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    # --- Persistence ---

    def snapshot(self) -> dict:
        return {
            "model": self._model,
            "memory": self._memory.snapshot(),
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> LLMBrain:
        brain = cls(model=data.get("model"))
        brain._memory = AgentMemory.from_snapshot(data["memory"])
        return brain


# Backward compat alias
ClaudeBrain = LLMBrain


def _parse_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            inner = text[start + 3 : end]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
