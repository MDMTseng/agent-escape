"""LLM-powered agent brain — uses OpenAI-compatible API (Featherless, etc.)

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

from openai import OpenAI

from agenttown.world.actions import Action, Wait, parse_action
from agenttown.world.models import AgentState

from .memory import AgentMemory
from .prompts import AGENT_TOOLS, build_perception_message, build_system_prompt

logger = logging.getLogger(__name__)

# Lightweight prompt for fact extraction — runs after each action
EXTRACT_PROMPT = """\
You are a memory assistant. Given what just happened, extract key facts worth remembering.

Current working memory:
{working_memory}

What just happened:
{events}

Action taken: {action}

Rules:
- Return a JSON object with two fields:
  "facts": list of short key facts to remember (max 10 total, merge with existing)
  "importance": integer 1-5 rating of how important this turn was (1=routine, 5=major discovery)
- Keep facts short (under 15 words each)
- Prioritize: codes, passwords, clue content, item locations, what others said, puzzle states
- Drop facts that are no longer relevant (e.g. "key is in room" after picking it up)
- If nothing important happened, return existing facts unchanged with importance 1
"""

REFLECT_PROMPT = """\
You are a reflection assistant. Review the agent's recent memories and produce a brief insight.

Agent: {name}
Goal: {goal}

Recent memories:
{memories}

Current working memory:
{working_memory}

Write 1-2 sentences summarizing what the agent has learned and what they should focus on next. \
Be specific about puzzle progress and unsolved mysteries.\
"""

# Convert our tool definitions to OpenAI function format
def _tools_to_openai_functions() -> list[dict]:
    """Convert AGENT_TOOLS to OpenAI function calling format."""
    functions = []
    for tool in AGENT_TOOLS:
        functions.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        })
    return functions


OPENAI_TOOLS = _tools_to_openai_functions()


class LLMBrain:
    """An agent brain powered by any OpenAI-compatible LLM API."""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 1024,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("FEATHERLESS_MODEL", "Qwen/Qwen3-8B")
        self._max_tokens = max_tokens
        self._client = OpenAI(
            api_key=api_key or os.environ.get("FEATHERLESS_API_KEY", ""),
            base_url=base_url or os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
        )
        self._memory = AgentMemory()
        self._message_history: dict[str, list[dict[str, Any]]] = {}
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self._consecutive_waits: dict[str, int] = {}  # agent_id -> count

    def _get_history(self, agent_id: str) -> list[dict[str, Any]]:
        if agent_id not in self._message_history:
            self._message_history[agent_id] = []
        return self._message_history[agent_id]

    def _track_usage(self, response) -> None:
        """Accumulate token usage from an API response."""
        if hasattr(response, "usage") and response.usage:
            self.token_usage["prompt_tokens"] += getattr(response.usage, "prompt_tokens", 0) or 0
            self.token_usage["completion_tokens"] += getattr(response.usage, "completion_tokens", 0) or 0
            self.token_usage["total_tokens"] += getattr(response.usage, "total_tokens", 0) or 0

    def _trim_history(self, agent_id: str, max_turns: int = 30) -> None:
        """Keep message history from growing unbounded."""
        history = self._get_history(agent_id)
        if len(history) > max_turns * 2:
            self._message_history[agent_id] = history[-(max_turns * 2) :]

    async def decide(self, agent: AgentState, perception: dict) -> Action:
        """Given the agent's perception, ask the LLM to choose an action."""
        tick = perception.get("tick", 0)

        system_prompt = build_system_prompt(
            name=agent.name,
            description=agent.description,
            goal=agent.goal,
            memory_summary=self._memory.build_memory_prompt(tick),
        )

        perception_text = build_perception_message(perception)

        # Stuck detection — nudge if agent has been waiting
        waits = self._consecutive_waits.get(agent.id, 0)
        if waits >= 2:
            nudge = (
                f"\n\n**WARNING: You have waited {waits} turns in a row. "
                "You MUST take a different action NOW. "
                "Suggestions: examine an object, pick up an item, move to another room, "
                "or talk to another agent. Do NOT wait again.**"
            )
            perception_text += nudge

        history = self._get_history(agent.id)

        # Build messages — OpenAI format uses system + user/assistant alternation
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": perception_text})

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="required",
            )
        except Exception as e:
            logger.error(f"LLM API error for {agent.name}: {e}")
            self._message_history[agent.id] = []
            return Wait()

        self._track_usage(response)

        # Extract action from response
        choice = response.choices[0]
        action = self._parse_response(choice, agent)

        # Track consecutive waits for stuck detection
        if hasattr(action, "type") and action.type == "wait":
            self._consecutive_waits[agent.id] = self._consecutive_waits.get(agent.id, 0) + 1
        else:
            self._consecutive_waits[agent.id] = 0

        # Update conversation history (simplified — just user + assistant text)
        history.append({"role": "user", "content": perception_text})
        if choice.message.content:
            history.append({"role": "assistant", "content": choice.message.content})
        elif choice.message.tool_calls:
            # Store tool call as assistant message
            tc = choice.message.tool_calls[0]
            history.append({
                "role": "assistant",
                "content": f"Action: {tc.function.name}({tc.function.arguments})",
            })

        # --- Memory processing ---
        events_text = "\n".join(perception.get("recent_events", []))
        action_text = f"{action.type}" if hasattr(action, "type") else "wait"
        self._memory.record(tick=tick, content=events_text or perception_text[:200], category="observation")

        self._extract_facts(agent, events_text, action_text, tick)

        if self._memory.should_reflect():
            self._reflect(agent, tick)

        self._trim_history(agent.id)
        return action

    def _extract_facts(self, agent: AgentState, events: str, action: str, tick: int) -> None:
        """Ask the LLM to extract key facts from what just happened."""
        prompt = EXTRACT_PROMPT.format(
            working_memory=self._memory.working_memory_text(),
            events=events or "Nothing notable happened.",
            action=action,
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            self._track_usage(response)
            text = response.choices[0].message.content or ""
            parsed = _parse_json(text)
            if parsed:
                facts = parsed.get("facts", [])
                importance = parsed.get("importance", 3)
                if facts:
                    self._memory.update_working_memory(facts)
                if self._memory._stream:
                    self._memory._stream[-1].importance = min(max(importance, 1), 5)
        except Exception as e:
            logger.debug(f"Fact extraction failed for {agent.name}: {e}")

    def _reflect(self, agent: AgentState, tick: int) -> None:
        """Generate a reflection — high-level summary of recent progress."""
        recent = self._memory.recent(15)
        if not recent:
            return

        memories_text = "\n".join(
            f"[Tick {m.tick}] ({m.category}) {m.content}" for m in recent
        )
        prompt = REFLECT_PROMPT.format(
            name=agent.name,
            goal=agent.goal,
            memories=memories_text,
            working_memory=self._memory.working_memory_text(),
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            self._track_usage(response)
            reflection = (response.choices[0].message.content or "").strip()
            if reflection:
                self._memory.add_reflection(tick, reflection)
                logger.info(f"{agent.name} reflects: {reflection}")
        except Exception as e:
            logger.debug(f"Reflection failed for {agent.name}: {e}")

    def _parse_response(self, choice, agent: AgentState) -> Action:
        """Extract an Action from the LLM response."""
        msg = choice.message

        # Check for tool calls (function calling)
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            tool_name = tc.function.name
            try:
                tool_input = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                tool_input = {}

            action_data = {"type": tool_name, **tool_input}
            logger.info(f"{agent.name} decides: {tool_name}({json.dumps(tool_input)})")
            return parse_action(action_data)

        # Fallback: try to parse action from text response
        if msg.content:
            logger.info(f"{agent.name} says: {msg.content[:100]}")
            parsed = _parse_json(msg.content)
            if parsed and "type" in parsed:
                return parse_action(parsed)

        return Wait()

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    # --- Persistence ---

    def snapshot(self) -> dict:
        """Serialize brain state for saving."""
        return {
            "model": self._model,
            "memory": self._memory.snapshot(),
            "message_history": dict(self._message_history),
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> LLMBrain:
        """Restore brain from a saved snapshot."""
        brain = cls(model=data.get("model"))
        brain._memory = AgentMemory.from_snapshot(data["memory"])
        brain._message_history = data.get("message_history", {})
        return brain


# Keep backward compat alias
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
