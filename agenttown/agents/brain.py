"""Claude-powered agent brain — perceives the world and decides actions."""

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
            # Keep the most recent turns (each turn = user + assistant message)
            self._message_history[agent_id] = history[-(max_turns * 2) :]

    async def decide(self, agent: AgentState, perception: dict) -> Action:
        """Given the agent's perception, ask Claude to choose an action."""
        system_prompt = build_system_prompt(
            name=agent.name,
            description=agent.description,
            goal=agent.goal,
            memory_summary=self._memory.summary(),
        )

        perception_text = build_perception_message(perception)
        history = self._get_history(agent.id)

        # If the last message is a user message (tool_result from previous turn),
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
                tools=AGENT_TOOLS,
                tool_choice={"type": "any"},  # force exactly one tool call
                messages=history,
            )
        except Exception as e:
            logger.error(f"Claude API error for {agent.name}: {e}")
            # Clear corrupted history to avoid cascading failures
            self._message_history[agent.id] = []
            return Wait()

        # Extract the action from tool use
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

        # Add tool_result for EVERY tool_use block — API requires it
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

        # Record memory
        self._memory.record(
            tick=perception.get("tick", 0),
            content=perception_text[:200],
            category="observation",
        )

        self._trim_history(agent.id)
        return action

    def _parse_response(
        self, response: anthropic.types.Message, agent: AgentState, perception: dict
    ) -> Action:
        """Extract an Action from Claude's response."""
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input if isinstance(block.input, dict) else {}

                action_data = {"type": tool_name, **tool_input}
                logger.info(
                    f"{agent.name} decides: {tool_name}({json.dumps(tool_input)})"
                )
                return parse_action(action_data)

        # If Claude didn't use a tool, default to wait
        for block in response.content:
            if block.type == "text":
                logger.info(f"{agent.name} thinks: {block.text[:100]}")
        return Wait()

    @property
    def memory(self) -> AgentMemory:
        return self._memory
