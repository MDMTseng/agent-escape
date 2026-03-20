"""Server launcher — token 'qqwweerr' is in the filename for process identification."""
import os
import uvicorn

if __name__ == "__main__":
    # Set to "1" to enable Claude brains and narrator (needs ANTHROPIC_API_KEY in .env)
    os.environ.setdefault("AGENTTOWN_CLAUDE", "1")
    os.environ.setdefault("AGENTTOWN_NARRATOR", "1")
    uvicorn.run("agenttown.server:app", host="0.0.0.0", port=8741)
