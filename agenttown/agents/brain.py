"""Claude-powered agent brain — perceives the world and decides actions.

Memory architecture (Generative Agents-inspired):
  1. Working Memory — key facts always in system prompt, updated by LLM extraction
  2. Memory Stream  — scored by recency × importance, top-K retrieved each tick
  3. Reflections    — periodic "what have I learned?" summaries
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

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


class ClaudeBrain:
    """An agent brain powered by Claude. Uses tool calling to select actions."""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
        api_key: str | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._memory = AgentMemory()
        self._message_history: dict[str, list[dict[str, Any]]] = {}

    def _get_history(self, agent_id: str) -> list[dict[str, Any]]:
        if agent_id not in self._message_history:
            self._message_history[agent_id] = []
        return self._message_history[agent_id]

    def _trim_history(self, agent_id: str, max_turns: int = 40) -> None:
        """Keep message history from growing unbounded."""
        history = self._get_history(agent_id)
        if len(history) > max_turns * 2:
            self._message_history[agent_id] = history[-(max_turns * 2) :]

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
        history = self._get_history(agent.id)

        # Merge with tool_result if last message is user
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
                tools=AGENT_TOOLS,
                tool_choice={"type": "any"},
                messages=history,
            )
        except Exception as e:
            logger.error(f"Claude API error for {agent.name}: {e}")
            self._message_history[agent.id] = []
            return Wait()

        # Extract the action
        action = self._parse_response(response, agent, perception)

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

        # Tool results
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
        # Record observation in stream
        events_text = "\n".join(perception.get("recent_events", []))
        action_text = f"{action.type}" if hasattr(action, "type") else "wait"
        self._memory.record(tick=tick, content=events_text or perception_text[:200], category="observation")

        # Extract key facts (lightweight LLM call)
        self._extract_facts(agent, events_text, action_text, tick)

        # Periodic reflection
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
            response = self._client.messages.create(
                model=self._model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            # Parse JSON from response
            parsed = _parse_json(text)
            if parsed:
                facts = parsed.get("facts", [])
                importance = parsed.get("importance", 3)
                if facts:
                    self._memory.update_working_memory(facts)
                # Update the last stream entry's importance
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
            response = self._client.messages.create(
                model=self._model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            reflection = response.content[0].text.strip()
            self._memory.add_reflection(tick, reflection)
            logger.info(f"{agent.name} reflects: {reflection}")
        except Exception as e:
            logger.debug(f"Reflection failed for {agent.name}: {e}")

    def _parse_response(
        self, response: anthropic.types.Message, agent: AgentState, perception: dict
    ) -> Action:
        """Extract an Action from Claude's response."""
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input if isinstance(block.input, dict) else {}
                action_data = {"type": tool_name, **tool_input}
                logger.info(f"{agent.name} decides: {tool_name}({json.dumps(tool_input)})")
                return parse_action(action_data)

        for block in response.content:
            if block.type == "text":
                logger.info(f"{agent.name} thinks: {block.text[:100]}")
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
    def from_snapshot(cls, data: dict) -> ClaudeBrain:
        """Restore brain from a saved snapshot."""
        brain = cls(model=data.get("model", "claude-haiku-4-5-20251001"))
        brain._memory = AgentMemory.from_snapshot(data["memory"])
        brain._message_history = data.get("message_history", {})
        return brain


def _parse_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if "```" in text:
        # Extract from code fence
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
