#!/bin/bash
# ============================================================
#  2026 World Cup Predictor — Ubuntu Dependency Installer
#  Run once on a fresh Ubuntu system before ./start.sh
# ============================================================

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$DIR/backend"
FRONTEND_DIR="$DIR/frontend"

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
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

echo "=============================================="
echo " 2026 World Cup Predictor — Install Dependencies"
echo "=============================================="

# Check Ubuntu
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "  Detected: $NAME $VERSION_ID"
else
    echo "  Non-Ubuntu system — proceeding anyway"
fi
echo ""

# ── 1. System packages ───────────────────────────────────

echo "[1/5] Installing system packages..."

sudo apt update -qq 2>&1 | tail -1

sudo apt install -y -qq python3 python3-venv python3-pip
log "Python 3 + venv + pip"

sudo apt install -y -qq redis-server
log "Redis server"

# Node.js 20.x from NodeSource
if ! command -v node &> /dev/null; then
    NODE_MAJOR=20
    curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | sudo -E bash -
    sudo apt install -y -qq nodejs
    log "Node.js $(node -v)"
else
    log "Node.js $(node -v) (already installed)"
fi

# Playwright Chromium system deps
sudo apt install -y -qq \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2t64 libatspi2.0-0 libx11-xcb1 libxcursor1 \
    libxfixes3 libxi6 libxrender1 libxtst6 libcups2 libdbus-1-3 \
    libwayland-client0
log "Playwright system dependencies"

# ── 2. Start & enable Redis ──────────────────────────────

echo "[2/5] Configuring Redis..."

if systemctl is-active --quiet redis-server 2>/dev/null; then
    log "Redis is already running"
else
    sudo systemctl start redis-server 2>/dev/null \
        || sudo service redis-server start 2>/dev/null \
        || warn "Could not start Redis"
    log "Redis started"
fi
sudo systemctl enable redis-server 2>/dev/null || true
log "Redis enabled on boot"

# ── 3. Python venv + dependencies ────────────────────────

echo "[3/5] Installing Python dependencies..."

ensure_python_venv "$BACKEND_DIR"
log "Python venv ready"

pip install --upgrade pip -q
log "pip upgraded"

pip install -r "$BACKEND_DIR/requirements.txt"
log "Python packages installed"

# ── 4. Playwright browser ─────────────────────────────────

echo "[4/5] Installing Playwright Chromium..."
playwright install chromium
log "Playwright Chromium installed"

# ── 5. Frontend dependencies ──────────────────────────────

echo "[5/5] Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm install
log "Frontend packages installed"

# ── Environment file ───────────────────────────────────────

if [ -f "$DIR/lib/merge-env.sh" ]; then
    # shellcheck source=lib/merge-env.sh
    source "$DIR/lib/merge-env.sh"
    if [ ! -f "$DIR/.env" ] && [ -f "$DIR/.env.example" ]; then
        cp "$DIR/.env.example" "$DIR/.env"
        log "Created .env from .env.example"
    fi
    merge_env_file "$DIR/.env.example" "$DIR/.env"
fi

if [ -f "$DIR/lib/fix-crlf.sh" ]; then
    # shellcheck source=lib/fix-crlf.sh
    source "$DIR/lib/fix-crlf.sh"
    fix_crlf_dotenv "$DIR"
fi

# ── Done ──────────────────────────────────────────────────

echo ""
echo "=============================================="
echo "  Installation complete!"
echo ""
echo "  Edit .env (set APP_ENV=production, ADMIN_PASSWORD, JWT_SECRET), then:"
echo "    ./start.sh   # Launch backend + frontend"
echo "    ./stop.sh    # Stop all services"
echo ""
echo "  Development:"
echo "    ./start.sh   -> http://localhost:5173"
echo "  Production:"
echo "    cd frontend && npm run build && cd .."
echo "    ./start-prod.sh -> http://localhost:4173 (login: server URL empty)"
echo "    Backend API: http://localhost:8888/docs"
echo ""
echo "  External access — open firewall ports:"
echo "    sudo ufw allow 5173/tcp"
echo "    sudo ufw allow 8888/tcp"
echo "    (Also configure your cloud security group)"
echo "=============================================="
