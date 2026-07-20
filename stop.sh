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
kill_port() {
    local port="$1"
    local name="$2"
    local pids
    if [ "$(uname)" = "Linux" ]; then
        fuser -k "${port}/tcp" 2>/dev/null && echo "  ${name} port ${port} released"
    else
        # macOS / BSD — use lsof
        pids=$(lsof -ti tcp:${port} 2>/dev/null)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill 2>/dev/null
            sleep 1
            echo "$pids" | xargs kill -9 2>/dev/null
            echo "  ${name} port ${port} released"
        fi
    fi
}

kill_port ${BACKEND_PORT}  "Backend"
kill_port ${FRONTEND_PORT} "Frontend"

echo "  Done."
