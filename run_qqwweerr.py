"""Server launcher — token 'qqwweerr' is in the filename for process identification."""
import os
import uvicorn

if __name__ == "__main__":
    # Enable Claude brains and narrator by default
    os.environ.setdefault("AGENTTOWN_CLAUDE", "1")
    os.environ.setdefault("AGENTTOWN_NARRATOR", "1")
    uvicorn.run("agenttown.server:app", host="0.0.0.0", port=8741)
