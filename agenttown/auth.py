"""Auto-refreshing Anthropic API key from Claude CLI OAuth credentials."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache token briefly — CLI may refresh it at any time
_TOKEN_CACHE_SECS = 30
_cached_token: str | None = None
_cached_at: float = 0


def _find_credentials_file() -> Path | None:
    """Find Claude CLI credentials file."""
    candidates = [
        Path.home() / ".claude" / ".credentials.json",
        Path(os.environ.get("USERPROFILE", "")) / ".claude" / ".credentials.json",
        Path("C:/Users") / os.environ.get("USERNAME", "") / ".claude" / ".credentials.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def get_api_key() -> str:
    """Get a fresh API key, auto-reading from Claude CLI credentials if available.

    Priority:
    1. ANTHROPIC_API_KEY env var (if it starts with sk-ant-api, it's a real API key — use as-is)
    2. Fresh OAuth token from ~/.claude/.credentials.json (re-read every 5 min)
    """
    global _cached_token, _cached_at

    # If env var is a real API key (not OAuth), use it directly
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key.startswith("sk-ant-api"):
        return env_key

    # Check cache
    now = time.time()
    if _cached_token and (now - _cached_at) < _TOKEN_CACHE_SECS:
        return _cached_token

    # Read fresh token from credentials file
    creds_file = _find_credentials_file()
    if creds_file:
        try:
            data = json.loads(creds_file.read_text(encoding="utf-8"))
            token = data.get("claudeAiOauth", {}).get("accessToken", "")
            expires_at = data.get("claudeAiOauth", {}).get("expiresAt", 0)

            if token:
                _cached_token = token
                _cached_at = now

                # Check if expired
                if expires_at and expires_at < now * 1000:
                    logger.warning("OAuth token is expired — Claude CLI may need to refresh it")
                else:
                    remaining = (expires_at / 1000 - now) / 60 if expires_at else 0
                    logger.debug(f"OAuth token valid, {remaining:.0f} min remaining")

                return token
        except Exception as e:
            logger.error(f"Failed to read credentials: {e}")

    # Fallback to whatever is in env
    if env_key:
        return env_key

    logger.error("No API key found — set ANTHROPIC_API_KEY or log into Claude CLI")
    return ""
