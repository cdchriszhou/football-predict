#!/bin/bash
# ===================================================
#  2026 World Cup Predictor — Linux (Ubuntu) Launcher
# ===================================================

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$DIR/backend"
FRONTEND_DIR="$DIR/frontend"
BACKEND_PORT=8888
FRONTEND_PORT=5173

if [ -f "$DIR/lib/ensure-venv.sh" ]; then
    # shellcheck source=lib/ensure-venv.sh
    source "$DIR/lib/ensure-venv.sh"
else
    ensure_python_venv() {
        local backend_dir="${1:?backend dir required}"
        local venv_dir="$backend_dir/venv"
        if [ -d "$venv_dir" ] && [ ! -f "$venv_dir/bin/activate" ]; then
            rm -rf "$venv_dir"
        fi
        if [ ! -f "$venv_dir/bin/activate" ]; then
            python3 -m venv "$venv_dir" || return 1
        fi
        # shellcheck disable=SC1090
        source "$venv_dir/bin/activate"
    }
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

echo "======================================"
echo "  2026 World Cup Predictor — Starting"
echo "======================================"

# ── Prerequisite checks ──────────────────────────────────

if ! command -v python3 &> /dev/null; then
    err "Python 3 not found. Run ./install.sh first."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    err "Python 3.10+ required, found $PY_VER"
    exit 1
fi
log "Python $PY_VER"

if ! command -v node &> /dev/null; then
    err "Node.js not found. Run ./install.sh first."
    exit 1
fi
log "Node.js $(node -v)"

# ── Check Redis ──────────────────────────────────────────

REDIS_OK=0
if command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null; then
    log "Redis is running"
    REDIS_OK=1
elif systemctl is-active --quiet redis-server 2>/dev/null; then
    log "Redis is running (systemd)"
    REDIS_OK=1
else
    warn "Redis not running — attempting to start..."
    if sudo -n systemctl start redis-server 2>/dev/null; then
        log "Redis started via systemctl"
        REDIS_OK=1
    elif sudo -n service redis-server start 2>/dev/null; then
        log "Redis started via service"
        REDIS_OK=1
    else
        warn "Redis unavailable — using in-memory cache fallback"
    fi
fi

# ── Backend setup ────────────────────────────────────────

echo ""
echo "[1/4] Setting up backend..."

ensure_python_venv "$BACKEND_DIR"
log "Python venv ready"

pip install -r "$BACKEND_DIR/requirements.txt" -q
log "Python dependencies up to date"

# Playwright browser (skip if already installed)
if ! playwright install chromium --with-deps 2>/dev/null; then
    warn "Playwright browser check skipped"
fi

# ── Frontend setup ───────────────────────────────────────

echo "[2/4] Setting up frontend..."

cd "$FRONTEND_DIR"
npm install --silent 2>&1 | tail -1
log "Frontend dependencies up to date"

# ── Start backend ────────────────────────────────────────

echo "[3/4] Starting backend (port $BACKEND_PORT)..."

cd "$BACKEND_DIR"
source "$BACKEND_DIR/venv/bin/activate"

# Kill existing process on backend port
fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
sleep 1

nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT \
    > "$DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$DIR/.backend.pid"
log "Backend started (PID $BACKEND_PID)"

# Wait for backend to be ready
sleep 3
if grep -q "ADMIN LOGIN" "$DIR/backend.log" 2>/dev/null; then
    echo ""
    grep "ADMIN LOGIN" "$DIR/backend.log" | while read -r line; do
        echo -e "  ${CYAN}$line${NC}"
    done
    echo ""
fi

# ── Start frontend ───────────────────────────────────────

echo "[4/4] Starting frontend (port $FRONTEND_PORT)..."

cd "$FRONTEND_DIR"

# Kill existing process on frontend port
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true
sleep 1

nohup npm run dev -- --host 0.0.0.0 > "$DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$DIR/.frontend.pid"
log "Frontend started (PID $FRONTEND_PID)"

sleep 2

# ── Print access info ────────────────────────────────────

LAN_IP=""
if command -v hostname &> /dev/null; then
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$LAN_IP" ] && command -v ip &> /dev/null; then
    LAN_IP=$(ip -4 addr show scope global 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
fi

PUBLIC_IP=""
if command -v curl &> /dev/null; then
    PUBLIC_IP=$(curl -s --connect-timeout 3 ifconfig.me 2>/dev/null || \
                 curl -s --connect-timeout 3 icanhazip.com 2>/dev/null || \
                 curl -s --connect-timeout 3 ipinfo.io/ip 2>/dev/null)
fi

echo ""
echo "======================================"
echo "  System started successfully!"
echo ""
echo "  Local access:"
echo "    Frontend: http://localhost:$FRONTEND_PORT"
echo "    Backend:  http://localhost:$BACKEND_PORT"
echo "    API docs: http://localhost:$BACKEND_PORT/docs"
if [ -n "$LAN_IP" ]; then
    echo ""
    echo "  LAN access:"
    echo "    Frontend: http://$LAN_IP:$FRONTEND_PORT"
    echo "    Backend:  http://$LAN_IP:$BACKEND_PORT"
fi
if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "$LAN_IP" ]; then
    echo ""
    echo "  External access:"
    echo "    Frontend: http://$PUBLIC_IP:$FRONTEND_PORT"
    echo "    Backend:  http://$PUBLIC_IP:$BACKEND_PORT"
    echo ""
    echo "  NOTE: Ensure firewall/security group allows TCP ports $FRONTEND_PORT and $BACKEND_PORT"
fi
echo ""
echo "  Run ./stop.sh to stop all services"
echo "======================================"
