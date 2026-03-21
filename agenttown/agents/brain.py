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

from agenttown.world.actions import Action, Wait, parse_action
from agenttown.world.models import AgentState

from .memory import AgentMemory
from .prompts import AGENT_TOOLS, build_perception_message, build_system_prompt

logger = logging.getLogger(__name__)

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
- Drop facts that are no longer relevant
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
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )
        self._memory = AgentMemory()
        self._message_history: dict[str, list[dict[str, Any]]] = {}
        self._history_summary: dict[str, str] = {}  # agent_id -> summary of old turns
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self._keep_turns = 3  # only keep last N turns in raw history

    def _get_history(self, agent_id: str) -> list[dict[str, Any]]:
        if agent_id not in self._message_history:
            self._message_history[agent_id] = []
        return self._message_history[agent_id]

    def _track_usage(self, response) -> None:
        """Accumulate token usage from an API response."""
        if hasattr(response, "usage") and response.usage:
            self.token_usage["prompt_tokens"] += getattr(response.usage, "input_tokens", 0) or 0
            self.token_usage["completion_tokens"] += getattr(response.usage, "output_tokens", 0) or 0
            self.token_usage["total_tokens"] += (
                (getattr(response.usage, "input_tokens", 0) or 0)
                + (getattr(response.usage, "output_tokens", 0) or 0)
            )

    def _trim_history(self, agent: AgentState) -> None:
        """Keep only last N turns. Summarize evicted turns into a compact summary."""
        history = self._get_history(agent.id)
        max_msgs = self._keep_turns * 3  # each turn ~ user + assistant + user(tool_result)

        if len(history) <= max_msgs:
            return

        # Extract old turns to summarize
        old_msgs = history[:-max_msgs]
        self._message_history[agent.id] = history[-max_msgs:]

        # Build summary from old messages
        old_actions = []
        for msg in old_msgs:
            if msg["role"] == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            old_actions.append(f"{block['name']}({json.dumps(block.get('input', {}))})")
                elif isinstance(content, str) and content:
                    old_actions.append(content[:80])

        if old_actions:
            new_summary = "Previous actions: " + " → ".join(old_actions[-10:])
            self._history_summary[agent.id] = new_summary

    async def decide(self, agent: AgentState, perception: dict) -> Action:
        """Given the agent's perception, ask Claude to choose an action."""
        tick = perception.get("tick", 0)

        system_prompt = build_system_prompt(
            name=agent.name,
            description=agent.description,
            goal=agent.goal,
            memory_summary=self._memory.build_memory_prompt(tick),
        )

        perception_text = build_perception_message(perception)

        # Inject history summary into perception if we have one
        summary = self._history_summary.get(agent.id, "")
        if summary:
            perception_text = f"[{summary}]\n\n{perception_text}"

        history = self._get_history(agent.id)

        # If last message is user (tool_result from previous turn),
        # merge the new perception into it to avoid consecutive user messages.
        if history and history[-1]["role"] == "user":
            last_content = history[-1]["content"]
            if isinstance(last_content, list):
                last_content.append({"type": "text", "text": perception_text})
            else:
                history[-1]["content"] = [
                    {"type": "text", "text": last_content},
                    {"type": "text", "text": perception_text},
                ]
        else:
            history.append({"role": "user", "content": perception_text})

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                tools=ANTHROPIC_TOOLS,
                tool_choice={"type": "any"},
                messages=history,
            )
        except Exception as e:
            logger.error(f"Claude API error for {agent.name}: {e}")
            self._message_history[agent.id] = []
            return Wait()

        self._track_usage(response)

        # Extract action from tool use
        action = self._parse_response(response, agent)

        # Record assistant response in history
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        history.append({"role": "assistant", "content": assistant_content})

        # Add tool_result for EVERY tool_use block
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Action submitted. You will see the results next turn.",
                })
        if tool_results:
            history.append({"role": "user", "content": tool_results})

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

        self._trim_history(agent)
        return action

    def _extract_facts(self, agent: AgentState, events: str, action: str, tick: int) -> None:
        prompt = EXTRACT_PROMPT.format(
            working_memory=self._memory.working_memory_text(),
            events=events or "Nothing notable happened.",
            action=action,
        )
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            self._track_usage(response)
            text = response.content[0].text.strip() if response.content else ""
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
            response = self._client.messages.create(
                model=self._model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            self._track_usage(response)
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
            "message_history": dict(self._message_history),
            "history_summary": dict(self._history_summary),
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> LLMBrain:
        brain = cls(model=data.get("model"))
        brain._memory = AgentMemory.from_snapshot(data["memory"])
        brain._message_history = data.get("message_history", {})
        brain._history_summary = data.get("history_summary", {})
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
