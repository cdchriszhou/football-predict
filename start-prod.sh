#!/bin/bash
# ============================================================
#  2026 World Cup Predictor — Production Launcher
#  Serves built frontend (dist/) + backend API
#  Run "npm run build" in frontend/ first, then deploy dist/
# ============================================================

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$DIR/backend"
FRONTEND_DIR="$DIR/frontend"
BACKEND_PORT=8888
FRONTEND_PORT=4173

if [ -f "$DIR/lib/ensure-venv.sh" ]; then
    # shellcheck source=lib/ensure-venv.sh
    source "$DIR/lib/ensure-venv.sh"
else
    remove_invalid_venv() {
        local venv_dir="${1:?}"
        [ -d "$venv_dir" ] || return 0
        [ -f "$venv_dir/bin/activate" ] && return 0
        if [ -d "$venv_dir/Scripts" ]; then
            echo "[WARN] Windows venv at $venv_dir cannot run on Linux — recreating"
        else
            echo "[WARN] Invalid venv at $venv_dir — recreating"
        fi
        rm -rf "$venv_dir"
    }
    ensure_python_venv() {
        local backend_dir="${1:?backend dir required}"
        local venv_dir="$backend_dir/venv"
        remove_invalid_venv "$venv_dir"
        if [ ! -f "$venv_dir/bin/activate" ]; then
            python3 -m venv "$venv_dir" || {
                echo "[ERROR] venv creation failed — install python3-venv: apt install python3-venv"
                return 1
            }
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

echo "=============================================="
echo " 2026 World Cup Predictor — Production Mode"
echo "=============================================="

# ── Prerequisite checks ──────────────────────────────────

if ! command -v python3 &> /dev/null; then
    err "Python 3 not found. Run ./install.sh first."
    exit 1
fi

if ! command -v node &> /dev/null; then
    err "Node.js not found. Run ./install.sh first."
    exit 1
fi

if [ ! -d "$FRONTEND_DIR/dist" ]; then
    err "frontend/dist/ not found. Run 'cd frontend && npm run build' first."
    exit 1
fi

if [ ! -f "$FRONTEND_DIR/server.js" ]; then
    err "frontend/server.js not found."
    exit 1
fi

log "Checks passed"

# ── Redis ────────────────────────────────────────────────

if command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null; then
    log "Redis is running"
elif systemctl is-active --quiet redis-server 2>/dev/null; then
    log "Redis is running (systemd)"
else
    warn "Redis not running — attempting to start..."
    sudo -n systemctl start redis-server 2>/dev/null \
        || sudo -n service redis-server start 2>/dev/null \
        || warn "Redis unavailable — using in-memory cache"
fi

# ── Backend setup ────────────────────────────────────────

echo ""
echo "[1/2] Starting backend API (port $BACKEND_PORT)..."

# Load project .env so ADMIN_PASSWORD / JWT_SECRET reach uvicorn (not only Python dotenv)
if [ -f "$DIR/.env" ]; then
    if grep -q $'\r' "$DIR/.env" 2>/dev/null; then
        sed -i 's/\r$//' "$DIR/.env"
        warn "Stripped Windows CRLF from .env"
    fi
    set -a
    # shellcheck disable=SC1091
    . "$DIR/.env"
    set +a
    log "Loaded $DIR/.env"
fi

ensure_python_venv "$BACKEND_DIR"
log "Python venv ready"
pip install -r "$BACKEND_DIR/requirements.txt" -q
log "Python dependencies up to date"

# Kill old process on backend port
fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
sleep 1

cd "$BACKEND_DIR"
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT \
    > "$DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$DIR/.backend.pid"
log "Backend started (PID $BACKEND_PID)"

sleep 2

# ── Frontend prod server ─────────────────────────────────

echo "[2/2] Starting frontend server (port $FRONTEND_PORT)..."

# Kill old process on frontend port
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true
sleep 1

cd "$FRONTEND_DIR"
nohup node server.js > "$DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$DIR/.frontend.pid"
log "Frontend started (PID $FRONTEND_PID)"

sleep 1

# ── Access info ──────────────────────────────────────────

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
                 curl -s --connect-timeout 3 icanhazip.com 2>/dev/null)
fi

sleep 2
if [ -f "$DIR/lib/health-check.sh" ]; then
    # shellcheck source=lib/health-check.sh
    source "$DIR/lib/health-check.sh"
    check_service_health "$BACKEND_PORT" "$FRONTEND_PORT" || warn "Health check reported issues — see logs"
fi

echo ""
echo "=============================================="
echo "  Production server started!"
echo ""
echo "  Open in browser: http://localhost:$FRONTEND_PORT"
echo "  Login -> server URL: leave EMPTY (uses /api proxy)"
echo ""
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT"
echo "  API docs: http://localhost:$BACKEND_PORT/docs"
if [ -n "$PUBLIC_IP" ]; then
    echo ""
    echo "  External: http://$PUBLIC_IP"
    echo ""
    echo "  Ensure firewall allows TCP $BACKEND_PORT and $FRONTEND_PORT"
fi
echo ""
echo "  Run ./stop-prod.sh to stop all services"
echo "=============================================="
