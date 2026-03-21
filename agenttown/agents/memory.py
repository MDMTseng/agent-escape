"""Agent memory — Generative Agents-style memory with working memory, stream, and reflections.

Architecture:
  Working Memory  — always in prompt, key facts the agent self-manages (~10 items)
  Memory Stream   — append-only log, scored by recency × importance × relevance
  Reflections     — periodic higher-level summaries ("what have I learned?")

Retrieval scoring (Stanford Generative Agents):
  score = recency × importance × relevance
  - recency:    exponential decay (0.95^age)
  - importance: 1-5 scale from LLM extraction
  - relevance:  embedding cosine similarity (local model, no API calls)
               falls back to keyword overlap if embeddings unavailable
"""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding model — loaded once, shared across all agents
# ---------------------------------------------------------------------------

_embedder = None
_EMBED_DIM = 384


def _get_embedder():
    """Lazy-load the sentence-transformers model (once)."""
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded: all-MiniLM-L6-v2")
        except Exception as e:
            logger.warning(f"Embedding model unavailable, using keyword fallback: {e}")
    return _embedder


def _embed(text: str) -> np.ndarray | None:
    """Embed a text string. Returns 384-dim vector or None."""
    model = _get_embedder()
    if model is None:
        return None
    return model.encode(text, normalize_embeddings=True)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two normalized vectors."""
    return float(np.dot(a, b))


# ---------------------------------------------------------------------------
# Keyword fallback (used when embeddings unavailable)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "and", "but", "or", "nor", "not", "no", "so",
    "if", "then", "than", "that", "this", "it", "its", "i", "you", "he",
    "she", "they", "we", "my", "your", "his", "her", "their", "our",
    "me", "him", "them", "us", "what", "which", "who", "whom", "how",
    "when", "where", "why", "all", "each", "every", "both", "few",
    "more", "most", "some", "any", "also", "just", "about", "up",
    "out", "very", "here", "there", "now", "then", "room", "see",
})


def _extract_keywords(text: str) -> set[str]:
    words = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))
    return words - _STOPWORDS


def _keyword_relevance(memory_text: str, query_keywords: set[str]) -> float:
    if not query_keywords:
        return 0.5
    mem_keywords = _extract_keywords(memory_text)
    if not mem_keywords:
        return 0.1
    overlap = len(mem_keywords & query_keywords)
    return min(overlap / max(len(query_keywords) * 0.3, 1.0), 1.0)


class MemoryEntry(BaseModel):
    """A single memory record in the stream."""

    tick: int
    content: str
    category: str = "observation"
    importance: int = 3  # 1-5 scale
    embedding: list[float] | None = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def compute_embedding(self) -> None:
        """Compute and cache the embedding for this entry."""
        vec = _embed(self.content)
        if vec is not None:
            self.embedding = vec.tolist()

    def recency_score(self, current_tick: int, decay: float = 0.95) -> float:
        age = max(current_tick - self.tick, 0)
        return decay ** age

    def relevance_score(self, query_embedding: np.ndarray | None = None,
                        query_keywords: set[str] | None = None) -> float:
        """Compute relevance: embedding similarity if available, keyword fallback otherwise."""
        # Prefer embedding similarity
        if query_embedding is not None and self.embedding is not None:
            sim = _cosine_similarity(np.array(self.embedding), query_embedding)
            # Shift from [-1,1] to [0,1] range
            return max((sim + 1.0) / 2.0, 0.0)

        # Keyword fallback
        if query_keywords:
            return _keyword_relevance(self.content, query_keywords)

        return 0.5  # neutral

    def retrieval_score(self, current_tick: int,
                        query_embedding: np.ndarray | None = None,
                        query_keywords: set[str] | None = None) -> float:
        """Score = recency × importance × relevance."""
        recency = self.recency_score(current_tick)
        importance = self.importance / 5.0
        relevance = self.relevance_score(query_embedding, query_keywords)
        return recency * importance * relevance


class AgentMemory:
    """Three-tier memory: working memory, memory stream, reflections."""

    def __init__(
        self,
        max_stream: int = 200,
        max_working: int = 10,
        reflect_every: int = 5,
    ) -> None:
        # Working memory — key facts always in prompt
        self._working: list[str] = []
        self._max_working = max_working

        # Memory stream — append-only log
        self._stream: list[MemoryEntry] = []
        self._max_stream = max_stream

        # Reflections — periodic summaries
        self._reflections: list[MemoryEntry] = []

        # Reflection tracking
        self._reflect_every = reflect_every
        self._ticks_since_reflect = 0

    # --- Working Memory ---

    def get_working_memory(self) -> list[str]:
        return list(self._working)

    def update_working_memory(self, facts: list[str]) -> None:
        """Replace working memory with new facts from LLM extraction."""
        self._working = facts[: self._max_working]

    def working_memory_text(self) -> str:
        if not self._working:
            return "No key facts yet."
        return "\n".join(f"- {fact}" for fact in self._working)

    # --- Memory Stream ---

    def record(
        self, tick: int, content: str, category: str = "observation", importance: int = 3
    ) -> None:
        """Add an entry to the memory stream with embedding."""
        entry = MemoryEntry(tick=tick, content=content, category=category, importance=importance)
        entry.compute_embedding()
        self._stream.append(entry)
        if len(self._stream) > self._max_stream:
            self._stream = self._stream[-self._max_stream :]
        self._ticks_since_reflect += 1

    def retrieve(self, current_tick: int, query: str = "", top_k: int = 8) -> list[MemoryEntry]:
        """Retrieve memories by recency × importance × relevance.

        Uses embedding cosine similarity for relevance if available,
        falls back to keyword overlap otherwise.
        """
        query_emb = _embed(query) if query else None
        query_kw = _extract_keywords(query) if query and query_emb is None else None

        scored = [
            (entry, entry.retrieval_score(current_tick, query_emb, query_kw))
            for entry in self._stream
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in scored[:top_k]]

    def should_reflect(self) -> bool:
        """Check if it's time for a reflection."""
        return self._ticks_since_reflect >= self._reflect_every and len(self._stream) > 0

    # --- Reflections ---

    def add_reflection(self, tick: int, content: str) -> None:
        """Store a reflection (high-importance summary)."""
        entry = MemoryEntry(tick=tick, content=content, category="reflection", importance=5)
        entry.compute_embedding()
        self._reflections.append(entry)
        self._stream.append(entry)
        self._ticks_since_reflect = 0

    def get_reflections(self, n: int = 5) -> list[MemoryEntry]:
        return self._reflections[-n:]

    # --- Prompt Building ---

    def build_memory_prompt(self, current_tick: int, query: str = "") -> str:
        """Build the full memory section for the system prompt.

        Args:
            current_tick: current world tick for recency scoring
            query: current perception text for relevance scoring
        """
        sections = []

        # Working memory
        sections.append("### Key Facts (Working Memory)")
        sections.append(self.working_memory_text())

        # Recent reflections
        reflections = self.get_reflections(3)
        if reflections:
            sections.append("\n### Reflections")
            for r in reflections:
                sections.append(f"[Tick {r.tick}] {r.content}")

        # Retrieved memories — scored by recency × importance × relevance
        retrieved = self.retrieve(current_tick, query=query, top_k=6)
        if retrieved:
            sections.append("\n### Relevant Memories")
            for m in retrieved:
                sections.append(f"[Tick {m.tick}] ({m.category}) {m.content}")

        return "\n".join(sections)

    # --- Legacy compat ---

    def summary(self, n: int = 10) -> str:
        """Legacy method — now delegates to build_memory_prompt."""
        return self.build_memory_prompt(current_tick=self._stream[-1].tick if self._stream else 0)

    def recent(self, n: int = 20) -> list[MemoryEntry]:
        return self._stream[-n:]

    def by_category(self, category: str) -> list[MemoryEntry]:
        return [e for e in self._stream if e.category == category]

    def all_entries(self) -> list[MemoryEntry]:
        return list(self._stream)

    def clear(self) -> None:
        self._stream.clear()
        self._working.clear()
        self._reflections.clear()
        self._ticks_since_reflect = 0

    # --- Persistence ---

    def snapshot(self) -> dict:
        """Serialize full memory state for saving."""
        return {
            "working": list(self._working),
            "stream": [e.model_dump() for e in self._stream],
            "reflections": [e.model_dump() for e in self._reflections],
            "ticks_since_reflect": self._ticks_since_reflect,
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> AgentMemory:
        """Restore memory from a saved snapshot."""
        mem = cls()
        mem._working = data.get("working", [])
        mem._stream = [MemoryEntry.model_validate(e) for e in data.get("stream", [])]
        mem._reflections = [MemoryEntry.model_validate(e) for e in data.get("reflections", [])]
        mem._ticks_since_reflect = data.get("ticks_since_reflect", 0)
        return mem
