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
import re
from typing import Any

import anthropic

from agenttown.auth import get_api_key
from agenttown.world.actions import Action, Wait, parse_action
from agenttown.world.models import AgentState

from .memory import AgentMemory
from .prompts import AGENT_TOOLS, build_perception_message, build_system_prompt

logger = logging.getLogger(__name__)

REFLECT_PROMPT = """\
You are {name}. Goal: {goal}.
Facts: {working_memory}
Recent: {memories}
{action_history}
Think about: What puzzles remain unsolved? What information am I missing? \
What have others told me that I haven't acted on? What actions FAILED or were REPEATED — stop doing those! \
What NEW action should I try next?
IMPORTANT: Reply as an internal plan for yourself (not a message to another character). \
Start with "I should..." or "My plan:". Keep to 1-2 sentences.\
"""

REEVALUATE_PROMPT = """\
You are {name}. Goal: {goal}.
Your facts: {working_memory}

STEP BACK and re-evaluate everything. Cross-reference ALL your clues:
1. List every CODE, KEYWORD, and CLUE you know. Which puzzle might each one solve?
2. List every UNSOLVED puzzle or LOCKED door. What clue/item could help?
3. Any FAILED attempts — do you now have NEW info that makes them worth retrying?
4. Any rooms or objects you haven't examined yet?
5. Any items you're carrying that you haven't tried using?

Think like a detective connecting evidence. A code found in Room A might solve a lock in Room B.
A keyword from a book might be a password for a door.

Reply with a SHORT action plan: what to try next and WHY. Start with "My plan:". Max 3 sentences.\
"""

_KEY_OUTCOME_PATTERNS = re.compile(
    r'(solv|fail|unlock|lock|discov|reveal|open|can\'t|tries to|says|told|talk)',
    re.IGNORECASE,
)


def _extract_key_outcomes(events: list[str]) -> str:
    """Extract the most important event descriptions for structured memory."""
    key = [e.strip()[:80] for e in events if _KEY_OUTCOME_PATTERNS.search(e)]
    return "; ".join(key[:4]) if key else ""


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
        # Action history for deduplication (tracks recent action signatures)
        self._action_history: list[str] = []
        self._max_action_history = 30
        self._last_regex_importance = 2

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

    async def decide(self, agent: AgentState, perception: dict) -> list[Action]:
        """Given the agent's perception, ask Claude to choose up to 5 actions.

        Returns a list of actions to execute sequentially this tick.
        """
        tick = perception.get("tick", 0)

        perception_text = build_perception_message(perception)

        # Build action history string for anti-repetition
        action_hist = ""
        if self._action_history:
            recent_actions = self._action_history[-12:]
            action_hist = "Your recent actions: " + ", ".join(recent_actions)
            # Detect and flag repetition
            from collections import Counter
            action_sigs = [a.split(" ", 1)[-1] for a in recent_actions]
            counts = Counter(action_sigs)
            repeated = [k for k, v in counts.items() if v >= 2]
            if repeated:
                action_hist += f"\nSTOP REPEATING: {', '.join(repeated)} — do something DIFFERENT."

        system_prompt = build_system_prompt(
            name=agent.name,
            description=agent.description,
            goal=agent.goal,
            memory_summary=self._memory.build_memory_prompt(tick, query=perception_text),
            action_history=action_hist,
        )

        def _call_api():
            return self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                tools=ANTHROPIC_TOOLS,
                messages=[{"role": "user", "content": perception_text}],
                timeout=30.0,
            )

        try:
            response = _call_api()
        except anthropic.AuthenticationError:
            logger.warning(f"Auth failed for {agent.name}, refreshing token...")
            self._refresh_client()
            try:
                response = _call_api()
            except Exception as e2:
                logger.error(f"Retry failed for {agent.name}: {e2}")
                return [Wait()]
        except Exception as e:
            logger.error(f"Claude API error for {agent.name}: {e}")
            return [Wait()]

        self._track_usage(response, "decide")

        # Extract ALL tool calls (up to 5 actions per tick)
        actions = self._parse_all_actions(response, agent)

        # --- Track action history for deduplication ---
        # Include payload/message so retrying with a DIFFERENT code isn't flagged
        for a in actions:
            if hasattr(a, "type"):
                sig = a.type
                if hasattr(a, "target"):
                    sig += f":{getattr(a, 'target', '')}"
                elif hasattr(a, "direction"):
                    sig += f":{getattr(a, 'direction', '')}"
                # Distinguish different payloads (codes, passwords, messages)
                if hasattr(a, "payload") and getattr(a, "payload", ""):
                    sig += f":{getattr(a, 'payload', '')[:20]}"
                elif hasattr(a, "message") and getattr(a, "message", ""):
                    sig += f":{getattr(a, 'message', '')[:20]}"
                elif hasattr(a, "item") and getattr(a, "item", ""):
                    sig += f":{getattr(a, 'item', '')[:20]}"
                self._action_history.append(f"T{tick} {sig}")
        if len(self._action_history) > self._max_action_history:
            self._action_history = self._action_history[-self._max_action_history:]

        # --- Memory processing ---
        events_text = "\n".join(perception.get("recent_events", []))
        action_names = ", ".join(a.type for a in actions if hasattr(a, "type"))

        # Build structured memory summary instead of raw events
        key_outcomes = _extract_key_outcomes(perception.get("recent_events", []))
        if key_outcomes:
            summary = f"Tick {tick}: {action_names}. Results: {key_outcomes}"
        elif action_names:
            summary = f"Tick {tick}: {action_names}."
        else:
            summary = perception_text[:200]

        self._memory.record(
            tick=tick,
            content=summary,
            category="observation",
        )
        room_name = perception.get("room", {}).get("name", "")
        structured = perception.get("structured_events", [])
        self._extract_facts(agent, events_text, action_names, tick, room_name,
                            structured_events=structured)

        # Reflect on schedule, OR force reflection when stalled
        if self._memory.should_reflect() or self._is_stalled():
            self._reflect(agent, tick)

        return actions

    def _extract_facts(self, agent: AgentState, events: str, action: str, tick: int,
                        room: str = "", structured_events: list[dict] | None = None) -> None:
        """Extract actionable facts from events into working memory.

        Uses structured events (from world engine) when available — no regex needed.
        Falls back to LLM distillation for prose, or regex for tests.
        """
        import re
        import unittest.mock
        facts = list(self._memory.get_working_memory())
        room_tag = f"[{room[:20]}] " if room else ""
        importance = 2
        dropped_items: set[str] = set()

        # --- Structured path: dispatch on event_type + data fields ---
        if structured_events:
            for evt in structured_events:
                etype = evt.get("type", "")
                data_target = evt.get("target", "")
                data_item = evt.get("item", "")
                data_text = evt.get("text", "")
                data_reason = evt.get("reason", "")
                data_result = evt.get("result", "")
                data_code = evt.get("code", "")
                data_state = evt.get("state", "")
                data_change = evt.get("change", "")
                data_room = evt.get("room_name", "")

                if etype == "pick_up" and data_item:
                    fact = f"HAVE: {data_item[:35]}"
                    if not any(data_item[:15].lower() in f.lower() and "HAVE:" in f for f in facts):
                        facts.append(room_tag + fact)
                        importance = max(importance, 4)

                elif etype == "drop" and data_item:
                    dropped_items.add(data_item.lower()[:25])

                elif etype == "move" and data_room:
                    fact = f"VISITED: {data_room[:30]}"
                    if not any(data_room[:15].lower() in f.lower() for f in facts if "VISITED:" in f):
                        facts.append(fact)

                elif etype == "examine" and data_text:
                    # Extract clues: quoted text
                    for q in re.findall(r'"([^"]{5,120})"', data_text):
                        source_tag = f" (from {data_target})" if data_target else ""
                        fact = f"CLUE{source_tag}: \"{q[:75]}\""
                        if not any(q[:25] in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = max(importance, 4)
                    # Extract keywords: single-quoted
                    for kw in re.findall(r"'([^']{3,40})'", data_text):
                        source_tag = f" (from {data_target})" if data_target else ""
                        fact = f"KEYWORD{source_tag}: '{kw}'"
                        if not any(kw in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = 5
                    # Extract codes: 3+ digit numbers
                    for code in re.findall(r'\b(\d{3,})\b', data_text):
                        source_tag = f" (from {data_target})" if data_target else ""
                        fact = f"CODE{source_tag}: {code}"
                        if not any(code in f and "CODE" in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = 5
                    # Track object state
                    if data_state and data_target:
                        obj_prefix = data_target[:15]
                        fact = f"STATE: {data_target[:30]} is {data_state}"
                        facts = [f for f in facts if not ("STATE:" in f and obj_prefix in f)]
                        facts.append(room_tag + fact)
                        importance = max(importance, 3)

                elif etype == "use":
                    if data_result == "solved" and data_target:
                        fact = f"SOLVED: {data_target[:40]}"
                        if not any("SOLVED" in f and data_target[:12].lower() in f.lower() for f in facts):
                            facts.append(room_tag + fact)
                            importance = 5
                    if data_result == "unlocked" and data_target:
                        fact = f"SOLVED: {data_target[:40]}"
                        if not any("SOLVED" in f and data_target[:12].lower() in f.lower() for f in facts):
                            facts.append(room_tag + fact)
                            importance = 5
                    if evt.get("consumed") and data_item:
                        dropped_items.add(data_item.lower()[:25])

                elif etype == "fail":
                    if data_reason == "wrong_code" and data_target:
                        fact = f"FAILED: code \"{data_code}\" on {data_target[:25]} — wrong"
                        if not any(fact[:25] in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = max(importance, 3)
                    elif data_reason == "wrong_password" and data_target:
                        fact = f"FAILED: password \"{evt.get('password', '')[:20]}\" on {data_target[:25]} — wrong"
                        if not any(fact[:25] in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = max(importance, 3)
                    elif data_reason == "locked" and data_target:
                        fact = f"BLOCKED: {data_target[:25]} is locked"
                        if not any(fact[:25] in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = max(importance, 3)
                    elif data_reason == "not_found" and data_target:
                        fact = f"FAILED: '{data_target[:30]}' not found"
                        if not any(fact[:25] in f for f in facts):
                            facts.append(room_tag + fact)
                            importance = max(importance, 3)
                    # Generic fails without enriched data — skip silently.
                    # The LLM sees the prose in the perception prompt anyway.

                elif etype == "state_change":
                    if data_change == "revealed" and data_target:
                        fact = f"FOUND: {data_target[:40]}"
                        if not any(data_target[:20].lower() in f.lower() for f in facts):
                            facts.append(room_tag + fact)
                            importance = 5
                    elif data_change == "unlocked" and data_target:
                        fact = f"SOLVED: {data_target[:40]} unlocked"
                        if not any("SOLVED" in f and data_target[:12].lower() in f.lower() for f in facts):
                            facts.append(room_tag + fact)
                            importance = 5
                    elif data_change == "set_state" and data_target and data_state:
                        obj_prefix = data_target[:15]
                        fact = f"STATE: {data_target[:30]} is {data_state}"
                        facts = [f for f in facts if not ("STATE:" in f and obj_prefix in f)]
                        facts.append(room_tag + fact)
                        importance = max(importance, 3)

                # talk events: structured data has "message" and "to" — no fact extraction needed
                # (the LLM sees messages via messages_for_agent in the prompt)

        else:
            # --- Fallback for prose-only events ---
            if events.strip():
                # Try LLM distillation; fall back to regex if client unavailable
                llm_ok = False
                try:
                    if hasattr(self._client, 'messages') and not isinstance(
                        self._client, unittest.mock.MagicMock
                    ):
                        llm_facts, llm_importance, llm_drops = self._distill_facts_llm(
                            agent, events, room_tag)
                        for f in llm_facts:
                            if not any(f[:20] in existing for existing in facts):
                                facts.append(f)
                        importance = max(importance, llm_importance)
                        dropped_items.update(llm_drops)
                        llm_ok = True
                except Exception:
                    pass
                if not llm_ok:
                    # Regex fallback for tests / mocked clients
                    self._extract_facts_regex(agent, events, action, tick, room,
                                              facts, room_tag, dropped_items)
                    importance = self._last_regex_importance

        # --- Clean up stale facts ---
        cleaned_facts = []
        for fact in facts:
            # Remove FAILED facts if the puzzle was later solved
            if "FAILED:" in fact:
                after_failed = fact.split("FAILED:", 1)[1].strip()[:20].lower()
                on_target = ""
                if " on " in fact.lower():
                    on_target = fact.lower().split(" on ", 1)[1].split("—")[0].strip()[:20]
                if any("SOLVED" in f and (after_failed[:10] in f.lower() or (on_target and on_target[:10] in f.lower())) for f in facts):
                    continue
            # Remove BLOCKED if door was later unlocked
            if "BLOCKED:" in fact:
                after_blocked = fact.split("BLOCKED:", 1)[1].strip().lower()
                obj_name = after_blocked.split(" is ")[0].strip()[:20] if " is " in after_blocked else after_blocked[:15]
                if any("STATE:" in f and obj_name in f.lower() and "unlocked" in f.lower() for f in facts):
                    continue
            # Remove HAVE facts for items that were dropped or used
            if "HAVE:" in fact and dropped_items:
                item_name = fact.split("HAVE:", 1)[1].strip().lower()[:25]
                if any(item_name[:10] in d for d in dropped_items):
                    continue
            cleaned_facts.append(fact)

        # Cap at 10 facts, keep newest
        self._memory.update_working_memory(cleaned_facts[-10:])
        if self._memory._stream:
            self._memory._stream[-1].importance = importance

    _DISTILL_PROMPT = """\
Extract ONLY actionable facts from these game events. Return one fact per line.
Use these prefixes:
- CODE: for number codes (e.g. "CODE (from Book): 1847")
- KEYWORD: for passwords/keywords (e.g. "KEYWORD: 'lumina'")
- CLUE: for quoted clue text (e.g. 'CLUE (from Painting): "seek the light"')
- HAVE: for items picked up (e.g. "HAVE: brass key")
- DROPPED: for items dropped or used up
- SOLVED: for puzzles solved or doors unlocked
- FOUND: for hidden things revealed
- STATE: for object states (e.g. "STATE: Iron Door is locked")
- FAILED: ONLY for specific failures worth remembering (e.g. "FAILED: code 1234 on Safe — wrong")
- VISITED: for rooms entered

Skip: greetings, chitchat, vague failures, waiting, routine movement.
If nothing actionable happened, reply with just: NONE

Events:
{events}
"""

    def _distill_facts_llm(self, agent: AgentState, events: str,
                           room_tag: str) -> tuple[list[str], int, set[str]]:
        """Use LLM to extract actionable facts from prose events.

        Returns (facts, importance, dropped_items).
        """
        facts: list[str] = []
        importance = 2
        dropped: set[str] = set()

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=150,
                messages=[{"role": "user",
                           "content": self._DISTILL_PROMPT.format(events=events[:500])}],
            )
            self._track_usage(response, "extract")
            text = response.content[0].text.strip() if response.content else ""

            if not text or text.upper() == "NONE":
                return facts, importance, dropped

            for line in text.split("\n"):
                line = line.strip().lstrip("- ")
                if not line or len(line) < 5:
                    continue
                # Determine importance from prefix
                if any(line.startswith(p) for p in ["CODE:", "KEYWORD:", "SOLVED:", "FOUND:"]):
                    importance = 5
                elif any(line.startswith(p) for p in ["CLUE:", "HAVE:"]):
                    importance = max(importance, 4)
                elif any(line.startswith(p) for p in ["FAILED:", "STATE:", "BLOCKED:"]):
                    importance = max(importance, 3)

                # Track dropped items
                if line.startswith("DROPPED:"):
                    item = line.split(":", 1)[1].strip().lower()[:25]
                    dropped.add(item)
                    continue  # Don't add DROPPED as a fact

                facts.append(room_tag + line)

        except Exception as e:
            logger.debug(f"LLM fact distillation failed for {agent.name}: {e}")

        return facts, importance, dropped

    def _extract_facts_regex(self, agent: AgentState, events: str, action: str,
                             tick: int, room: str, facts: list[str],
                             room_tag: str, dropped_items: set[str]) -> None:
        """Regex fallback for fact extraction from prose event strings.

        Used when structured_events are not available (tests, legacy callers).
        Modifies facts and dropped_items in place, sets self._last_regex_importance.
        """
        import re
        importance = 2
        events_lower = events.lower()

        # Strip agent speech (capitalized name only, not system narration)
        system_events = re.sub(
            r'(?<!\w)[A-Z]\w+\s+says(?:\s+to\s+[A-Z]\w+)?:\s*"?[^"\n]*"?', '', events
        )
        system_lower = system_events.lower()

        def _find_source_object(clue_text: str) -> str:
            lines = system_events.split('\n')
            for i, line in enumerate(lines):
                if clue_text[:20] in line:
                    for j in range(max(0, i - 1), i + 1):
                        m = re.search(r'examines?\s+(.+?):', lines[j], re.IGNORECASE)
                        if m:
                            return m.group(1).strip()[:25]
            return ""

        # Extract quoted clues
        for q in re.findall(r'"([^"]{5,120})"', system_events):
            source = _find_source_object(q)
            source_tag = f" (from {source})" if source else ""
            fact = f"CLUE{source_tag}: \"{q[:75]}\""
            if not any(q[:25] in f for f in facts):
                facts.append(room_tag + fact)
                importance = max(importance, 4)

        # Extract keywords
        for kw in re.findall(r"'([^']{3,40})'", system_events):
            source = _find_source_object(kw)
            source_tag = f" (from {source})" if source else ""
            fact = f"KEYWORD{source_tag}: '{kw}'"
            if not any(kw in f for f in facts):
                facts.append(room_tag + fact)
                importance = 5

        # Extract codes
        for code in re.findall(r'\b(\d{3,})\b', system_events):
            source = _find_source_object(code)
            source_tag = f" (from {source})" if source else ""
            fact = f"CODE{source_tag}: {code}"
            if not any(code in f and "CODE" in f for f in facts):
                facts.append(room_tag + fact)
                importance = 5

        # Examine results
        for obj_name, description in re.findall(
            r'(?:examines?)\s+(.+?):\s+(.{5,100})', system_events, re.IGNORECASE
        ):
            obj = obj_name.strip()[:30]
            desc_clean = description.strip()[:60]
            if any(w in desc_clean.lower() for w in [
                'unlock', 'lock', 'code', 'hidden', 'secret', 'reveal',
                'inscription', 'read', 'key', 'clue', 'password', 'note',
            ]):
                fact = f"EXAMINED {obj}: {desc_clean}"
                if not any(obj[:15] in f for f in facts):
                    facts.append(room_tag + fact)
                    importance = max(importance, 3)

        # Object states
        for obj_name, state in re.findall(
            r'examines?\s+(.+?):\s+It is (unlocked|locked|open|closed|sealed)',
            system_events, re.IGNORECASE
        ):
            obj_clean = obj_name.strip()[:30]
            fact = f"STATE: {obj_clean} is {state}"
            obj_prefix = obj_clean[:15]
            facts[:] = [f for f in facts if not ("STATE:" in f and obj_prefix in f)]
            facts.append(room_tag + fact)
            importance = max(importance, 3)

        # Failed actions
        fail_patterns = [
            (r"looks for '(.+?)' but can't (.+)", lambda m: f"FAILED: pick up '{m[0][:30]}' — {m[1].strip()[:25]}"),
            (r'enters\s+"(.+?)"\s+on\s+(.+?)\.\s*wrong', lambda m: f"FAILED: code \"{m[0]}\" on {m[1][:25]} — wrong"),
            (r"(\w+) tries to (.{5,50})", lambda m: f"FAILED: {m[0]} tried to {m[1].strip()[:35]}"),
            (r"(\w+) can't (.{5,50})", lambda m: f"FAILED: can't {m[1].strip()[:40]}"),
            (r"the (.{3,30}) is locked", lambda m: f"BLOCKED: {m[0].strip()[:25]} is locked"),
        ]
        for pattern, formatter in fail_patterns:
            for match in re.findall(pattern, events_lower):
                if isinstance(match, str):
                    match = (match,)
                fact = formatter(match)
                if not any(fact[:25] in f for f in facts):
                    facts.append(room_tag + fact)
                    importance = max(importance, 3)

        # Discoveries
        if re.search(r'\b(reveals?|discovers?)\b', system_lower):
            for pattern in [
                r'(\w+)\s+reveals?\s+(?:a\s+)?(.{5,60})',
                r'discovers?\s+(?:a\s+)?(.{5,60})',
            ]:
                for match in re.findall(pattern, system_lower):
                    desc = match if isinstance(match, str) else " ".join(match)
                    fact = f"FOUND: {desc.strip()[:50]}"
                    if not any(desc[:20] in f for f in facts):
                        facts.append(room_tag + fact)
            importance = 5

        # Solved/unlocked
        for match in re.findall(r'(?:is now|has been)\s+(unlocked|solved|opened)', system_lower):
            name = match.strip()
            fact = f"SOLVED: {name[:40]}"
            if not any("SOLVED" in f and name[:12] in f for f in facts):
                facts.append(room_tag + fact)
                importance = 5
        for match in re.findall(r'([A-Z]\w+)\s+(?:unlocks?|solves?)\s+(?:the\s+)?(.{3,30})', system_events):
            name = " ".join(match).strip()
            fact = f"SOLVED: {name[:40]}"
            if not any("SOLVED" in f and name[:12] in f.lower() for f in facts):
                facts.append(room_tag + fact)
                importance = 5

        # Items picked up
        for item in re.findall(r'picks up (?:the\s+)?(.{3,40})', system_lower):
            fact = f"HAVE: {item.strip().rstrip('.;,')[:35]}"
            if not any(item[:15] in f for f in facts):
                facts.append(room_tag + fact)
                importance = max(importance, 4)

        # Rooms entered
        for rm in re.findall(
            rf'{re.escape(agent.name.lower())}\s+enters\s+(.{{3,40}})', events_lower
        ):
            rm_clean = rm.strip().rstrip('.;,')
            fact = f"VISITED: {rm_clean[:30]}"
            if not any(rm_clean[:15] in f for f in facts):
                facts.append(fact)

        # Items dropped or used (for HAVE cleanup)
        for m in re.findall(r'drops?\s+(?:the\s+)?(.{3,40})', system_lower):
            dropped_items.add(m.strip().rstrip('.;,')[:25])
        for m in re.findall(r'uses?\s+(.{3,30})\s+on\s+', system_lower):
            dropped_items.add(m.strip().rstrip('.;,')[:25])

        # Overall importance
        if "unlock" in system_lower or "revealed" in system_lower:
            importance = 5
        elif "picks up" in system_lower or "examines" in system_lower:
            importance = max(importance, 3)

        self._last_regex_importance = importance

    def _is_stalled(self) -> bool:
        """Detect if the agent is stuck (mostly waiting or repeating)."""
        if len(self._action_history) < 6:
            return False
        recent = self._action_history[-6:]
        wait_count = sum(1 for a in recent if "wait" in a.lower())
        if wait_count >= 4:
            return True
        # Check if all recent actions are identical
        sigs = [a.split(" ", 1)[-1] for a in recent]
        if len(set(sigs)) <= 2:
            return True
        return False

    def _reflect(self, agent: AgentState, tick: int) -> None:
        """LLM reflection — alternates between quick plans and deep re-evaluations.

        Quick reflection: every reflect_every ticks (default 5)
        Deep re-evaluation: every 3rd reflection OR when stalled
        """
        recent = self._memory.recent(10)
        if not recent:
            return
        memories_text = "; ".join(f"T{m.tick}:{m.content[:60]}" for m in recent)

        # Build action history summary to detect repetition
        action_hist = ""
        if self._action_history:
            recent_actions = self._action_history[-15:]
            action_hist = "Recent actions: " + ", ".join(recent_actions)
            from collections import Counter
            action_types = [a.split(" ", 1)[-1] for a in recent_actions]
            counts = Counter(action_types)
            repeated = [f"{k}(x{v})" for k, v in counts.items() if v >= 3]
            if repeated:
                action_hist += f"\nWARNING — REPEATED ACTIONS: {', '.join(repeated)}. STOP doing these and try something NEW."

        # Choose reflection depth: deep re-evaluation every 3rd time or when stalled
        reflection_count = len(self._memory.get_reflections())
        use_deep = (reflection_count > 0 and reflection_count % 3 == 0) or self._is_stalled()

        if use_deep:
            prompt = REEVALUATE_PROMPT.format(
                name=agent.name,
                goal=agent.goal,
                working_memory="; ".join(self._memory.get_working_memory()),
            )
            max_tokens = 150
            logger.info(f"{agent.name} doing deep re-evaluation (stalled={self._is_stalled()})")
        else:
            prompt = REFLECT_PROMPT.format(
                name=agent.name,
                goal=agent.goal,
                memories=memories_text,
                working_memory="; ".join(self._memory.get_working_memory()[:5]),
                action_history=action_hist,
            )
            max_tokens = 80

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            self._track_usage(response, "reflect")
            reflection = response.content[0].text.strip() if response.content else ""
            if reflection:
                self._memory.add_reflection(tick, reflection)
                logger.info(f"{agent.name} {'re-evaluates' if use_deep else 'reflects'}: {reflection}")
        except Exception as e:
            logger.debug(f"Reflection failed for {agent.name}: {e}")

    def _parse_all_actions(self, response: anthropic.types.Message, agent: AgentState, max_actions: int = 5) -> list[Action]:
        """Extract up to max_actions from Claude's response."""
        actions = []
        for block in response.content:
            if block.type == "tool_use" and len(actions) < max_actions:
                tool_name = block.name
                tool_input = block.input if isinstance(block.input, dict) else {}
                action_data = {"type": tool_name, **tool_input}
                logger.info(f"{agent.name} decides: {tool_name}({json.dumps(tool_input)})")
                actions.append(parse_action(action_data))

        if not actions:
            for block in response.content:
                if block.type == "text":
                    logger.info(f"{agent.name} text (no tool): {block.text[:100]}")
            actions.append(Wait())

        return actions

    def _parse_response(self, response: anthropic.types.Message, agent: AgentState) -> Action:
        """Extract a single Action (backward compat)."""
        return self._parse_all_actions(response, agent, max_actions=1)[0]

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    # --- Persistence ---

    def snapshot(self) -> dict:
        return {
            "model": self._model,
            "memory": self._memory.snapshot(),
            "action_history": list(self._action_history),
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> LLMBrain:
        brain = cls(model=data.get("model"))
        brain._memory = AgentMemory.from_snapshot(data["memory"])
        brain._action_history = data.get("action_history", [])
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
