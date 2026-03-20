"""Server launcher — token 'qqwweerr' is in the filename for process identification."""
import logging
import os
import uvicorn

if __name__ == "__main__":
    # Set to "1" to enable LLM brains and narrator
    os.environ.setdefault("AGENTTOWN_CLAUDE", "1")
    os.environ.setdefault("AGENTTOWN_NARRATOR", "1")

    # Configure logging so game events are visible in the log file
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )

    uvicorn.run("agenttown.server:app", host="0.0.0.0", port=8741, log_level="warning")
