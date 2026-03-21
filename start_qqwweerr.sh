#!/usr/bin/env bash
# ============================================================================
# AgentTown Start/Stop Script
# Token: qqwweerr (embedded in filename for process identification)
#
# CAVEATS:
# - On Windows/MSYS2, `ps aux` does NOT show script arguments — only the
#   bare executable (e.g. /c/dlcv/python). So `ps aux | grep qqwweerr` won't
#   work. Use `wmic` instead to match by command line.
# - Cloudflare quick tunnels get a new random URL each time they start.
#   Do NOT kill/restart the tunnel unless necessary — the user would have
#   to use the new URL. On restart, only the server process is recycled;
#   the tunnel stays up and keeps proxying to the same localhost port.
# - The tunnel must be started AFTER the server is up, so we sleep 2s first.
# - Only use `start_tunnel` or `stop_tunnel` when you explicitly need to
#   create or destroy the tunnel.
# ============================================================================

PORT=8741
TOKEN="qqwweerr"
TUNNEL_LOG="/tmp/agenttown_tunnel.log"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load keys from .env — export each KEY=VALUE line
if [ -f "$PROJECT_DIR/.env" ]; then
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        export "$key=$value"
    done < "$PROJECT_DIR/.env"
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

start_tunnel() {
    echo "Starting Cloudflare tunnel..."
    nohup cloudflared tunnel --url "http://localhost:$PORT" > "$TUNNEL_LOG" 2>&1 &
    sleep 5

    PUBLIC_URL=$(grep -o 'https://[^ |]*trycloudflare.com' "$TUNNEL_LOG")
    if [ -n "$PUBLIC_URL" ]; then
        echo "Tunnel is up at $PUBLIC_URL"
    else
        echo "WARNING: Could not get tunnel URL. Check $TUNNEL_LOG"
    fi
}

stop_tunnel() {
    taskkill //F //IM cloudflared.exe > /dev/null 2>&1
    echo "Tunnel stopped"
}

case "${1:-start}" in
    start)         start_server; start_tunnel ;;
    stop)          stop_server; stop_tunnel ;;
    restart)       stop_server; sleep 1; start_server ;;   # tunnel stays up
    start_tunnel)  start_tunnel ;;
    stop_tunnel)   stop_tunnel ;;
    stop_all)      stop_server; stop_tunnel ;;
    *)             echo "Usage: $0 {start|stop|restart|start_tunnel|stop_tunnel|stop_all}" ;;
esac
