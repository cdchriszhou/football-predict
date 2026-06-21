#!/bin/bash
# ===================================================
#  2026 World Cup Predictor — Linux (Ubuntu) Stopper
# ===================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8888
FRONTEND_PORT=5173

echo "======================================"
echo "  Stopping 2026 World Cup Predictor..."
echo "======================================"

stop_by_pid() {
    local pid_file="$1"
    local name="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            sleep 1
            # Force kill if still alive
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            echo "  $name (PID $pid) stopped"
        fi
        rm -f "$pid_file"
    fi
}

stop_by_pid "$DIR/.backend.pid"  "Backend"
stop_by_pid "$DIR/.frontend.pid" "Frontend"

# Fallback: kill any remaining processes on these ports
fuser -k ${BACKEND_PORT}/tcp  2>/dev/null && echo "  Backend port $BACKEND_PORT released"
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null && echo "  Frontend port $FRONTEND_PORT released"

echo "  Done."
