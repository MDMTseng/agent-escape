"""Server launcher — token 'qqwweerr' is in the filename for process identification."""
import os
import uvicorn

if __name__ == "__main__":
    # Enable Claude brains by default; set AGENTTOWN_CLAUDE=0 to disable
    os.environ.setdefault("AGENTTOWN_CLAUDE", "1")
    uvicorn.run("agenttown.server:app", host="0.0.0.0", port=8741)
