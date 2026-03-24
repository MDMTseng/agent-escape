#!/usr/bin/env bash
# ============================================================================
# AgentTown Start/Stop Script
# Token: qqwweerr (embedded in filename for process identification)
#
# CAVEATS:
# - On Windows/MSYS2, `ps aux` does NOT show script arguments — only the
#   bare executable (e.g. /c/dlcv/python). So `ps aux | grep qqwweerr` won't
#   work. Use `wmic` instead to match by command line.
# - For tunnels, use the /tunnel skill or WebTunnelHub directly.
# ============================================================================

PORT=8741
TOKEN="qqwweerr"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load keys from .env — export each KEY=VALUE line
if [ -f "$PROJECT_DIR/.env" ]; then
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        export "$key=$value"
    done < "$PROJECT_DIR/.env"
fi

# Auto-read fresh OAuth token from Claude CLI credentials (overrides .env)
CREDS_FILE="$HOME/.claude/.credentials.json"
if [ -f "$CREDS_FILE" ]; then
    FRESH_TOKEN=$(python -c "import json; print(json.load(open('$(cygpath -w "$CREDS_FILE")'))['claudeAiOauth']['accessToken'])" 2>/dev/null)
    if [ -n "$FRESH_TOKEN" ]; then
        export ANTHROPIC_API_KEY="$FRESH_TOKEN"
        echo "Using fresh OAuth token from Claude CLI"
    fi
fi

start_server() {
    echo "Starting AgentTown server on port $PORT..."
    cd "$PROJECT_DIR"
    ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-haiku-4-5}" \
    AGENTTOWN_CLAUDE="1" \
    AGENTTOWN_NARRATOR="1" \
    AGENTTOWN_SCENARIO="${AGENTTOWN_SCENARIO:-escape_room}" \
    nohup python run_qqwweerr.py > /tmp/agenttown_server.log 2>&1 &
    sleep 5

    if curl -s "http://localhost:$PORT/api/state" > /dev/null 2>&1; then
        echo "Server is up at http://localhost:$PORT"
    else
        echo "ERROR: Server failed to start!"
        return 1
    fi
}

stop_server() {
    # Kill server — must use wmic on Windows since ps aux doesn't show args
    PID=$(wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null \
        | grep "$TOKEN" \
        | awk '{print $NF}')

    if [ -n "$PID" ]; then
        taskkill //F //PID "$PID" > /dev/null 2>&1
        echo "Server stopped (PID $PID)"
    else
        echo "Server not found"
    fi
}

case "${1:-start}" in
    start)         start_server ;;
    stop)          stop_server ;;
    restart)       stop_server; sleep 1; start_server ;;
    *)             echo "Usage: $0 {start|stop|restart}" ;;
esac
