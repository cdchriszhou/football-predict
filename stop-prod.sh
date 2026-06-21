#!/bin/bash
# ============================================================
#  2026 World Cup Predictor — Production Stopper
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8888
FRONTEND_PORT=4173

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
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            echo "  $name (PID $pid) stopped"
        fi
        rm -f "$pid_file"
    fi
}

stop_by_pid "$DIR/.backend.pid"  "Backend API"
stop_by_pid "$DIR/.frontend.pid" "Frontend server"

# Fallback: release ports
fuser -k ${BACKEND_PORT}/tcp  2>/dev/null && echo "  Released port $BACKEND_PORT"
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null && echo "  Released port $FRONTEND_PORT"

echo "  Done."
