#!/bin/bash
# ============================================================
#  2026 World Cup Predictor — One-shot installer (Ubuntu)
#  Usage:  cd /mnt/worldcup-predict && ./install.sh
#  Then:   ./start-prod.sh
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
echo " 2026 World Cup Predictor — Install"
echo "=============================================="

if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "  Detected: $NAME $VERSION_ID"
fi
echo ""

# ── 1. System packages ───────────────────────────────────

echo "[1/6] System packages..."
sudo apt update -qq 2>&1 | tail -1
sudo apt install -y -qq python3 python3-venv python3-pip
log "Python 3 + venv + pip"
sudo apt install -y -qq redis-server
log "Redis"

if ! command -v node &> /dev/null; then
    NODE_MAJOR=20
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | sudo -E bash -
    sudo apt install -y -qq nodejs
    log "Node.js $(node -v)"
else
    log "Node.js $(node -v) (already installed)"
fi

# Playwright OS libs (best-effort; package names differ by Ubuntu version)
sudo apt install -y -qq \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libatspi2.0-0 libx11-xcb1 libxcursor1 \
    libxfixes3 libxi6 libxrender1 libxtst6 libcups2 libdbus-1-3 \
    libwayland-client0 2>/dev/null \
    || sudo apt install -y -qq \
        libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
        libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
        libasound2t64 2>/dev/null \
    || warn "Some Playwright system libs missing — crawl browser may fail later"
log "System packages ready"

# ── 2. Redis ─────────────────────────────────────────────

echo "[2/6] Redis..."
if systemctl is-active --quiet redis-server 2>/dev/null; then
    log "Redis already running"
else
    sudo systemctl start redis-server 2>/dev/null \
        || sudo service redis-server start 2>/dev/null \
        || warn "Could not start Redis (app can fall back to memory cache)"
fi
sudo systemctl enable redis-server 2>/dev/null || true

# ── 3. Python ────────────────────────────────────────────

echo "[3/6] Python dependencies..."
ensure_python_venv "$BACKEND_DIR"
log "venv ready"
pip install --upgrade pip -q
pip install -r "$BACKEND_DIR/requirements.txt" -q
log "Python packages installed"

# ── 4. Playwright browser (optional, non-fatal) ──────────

echo "[4/6] Playwright Chromium (optional)..."
if playwright install chromium; then
    log "Playwright Chromium installed"
else
    warn "Playwright install failed/skipped — app still starts; league crawl may need it later"
fi

# ── 5. Frontend (skip npm for production packages) ───────

echo "[5/6] Frontend..."
cd "$FRONTEND_DIR"
if [ -f "$FRONTEND_DIR/dist/index.html" ] && [ -f "$FRONTEND_DIR/server.js" ]; then
    log "frontend/dist ready — skip npm install"
else
    warn "No dist/ — installing npm deps via npmmirror"
    npm install --registry=https://registry.npmmirror.com
    log "Frontend packages installed"
fi

# ── 6. .env + database schema ────────────────────────────

echo "[6/6] Config & database..."
cd "$DIR"

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

# Ensure production defaults exist (do not overwrite strong secrets)
if [ -f "$DIR/.env" ]; then
    grep -q '^APP_ENV=' "$DIR/.env" 2>/dev/null || echo 'APP_ENV=production' >> "$DIR/.env"
    # shellcheck disable=SC1091
    set -a; . "$DIR/.env"; set +a
fi

ensure_python_venv "$BACKEND_DIR"
if [ -f "$BACKEND_DIR/scripts/bootstrap_schema.py" ]; then
    (cd "$BACKEND_DIR" && python scripts/bootstrap_schema.py) \
        && log "Database schema ready" \
        || warn "Schema bootstrap failed — check backend logs / .env DATABASE_URL"
else
    (cd "$BACKEND_DIR" && python -m alembic upgrade head) \
        && log "Alembic migrations applied" \
        || warn "Alembic failed — check backend logs"
fi

NEED_ENV=0
if [ -z "${ADMIN_PASSWORD:-}" ] || [ "$ADMIN_PASSWORD" = "change-me-in-production" ]; then
    NEED_ENV=1
fi
if [ -z "${JWT_SECRET:-}" ] || [ "$JWT_SECRET" = "change-me-in-production" ]; then
    NEED_ENV=1
fi

echo ""
echo "=============================================="
echo "  Install complete"
echo "=============================================="
if [ "$NEED_ENV" -eq 1 ]; then
    echo ""
    echo "  请编辑密码后再启动："
    echo "    nano $DIR/.env"
    echo "    设置 ADMIN_PASSWORD 与 JWT_SECRET，保存后执行："
    echo "    ./start-prod.sh"
else
    echo ""
    echo "  直接启动："
    echo "    ./start-prod.sh"
fi
echo ""
echo "  前端: http://<服务器IP>:4173  （登录页服务器地址留空）"
echo "  后端: http://<服务器IP>:8888/docs"
echo "  停止: ./stop-prod.sh"
echo "=============================================="
