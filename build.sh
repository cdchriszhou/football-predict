#!/bin/bash
# ============================================================
#  2026 World Cup Predictor — Build & Package for Production
#  Usage: bash build.sh   (Linux / macOS / Git Bash on Windows)
#  Output: worldcup-predict-prod-YYYYMMDD-HHMMSS.zip
# ============================================================

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
ZIP_NAME="worldcup-predict-prod-${TIMESTAMP}.zip"
BUILD_DIR="$DIR/.build-tmp"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${CYAN}[..]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo "=============================================="
echo " 2026 World Cup Predictor — Build & Package"
echo "=============================================="

# ── 1. Build frontend ────────────────────────────────────

info "Building frontend..."

cd "$DIR/frontend"

if [ ! -d "node_modules" ]; then
    npm install
fi

npm run build
log "Frontend built -> frontend/dist/"

# ── 2. Prepare staging directory ─────────────────────────

info "Packaging deployment files..."

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/worldcup-predict"

STAGE="$BUILD_DIR/worldcup-predict"

# ── 3. Copy backend (source only) ────────────────────────

cp -r "$DIR/backend" "$STAGE/backend"

# Strip venv, caches, db files
rm -rf "$STAGE/backend/venv"           2>/dev/null || true
rm -rf "$STAGE/backend/.venv"          2>/dev/null || true
find "$STAGE/backend" -type d \( -name "venv" -o -name ".venv" \) -exec rm -rf {} + 2>/dev/null || true
rm -rf "$STAGE/backend/__pycache__"    2>/dev/null || true
find "$STAGE/backend" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/backend" -name "*.pyc" -delete 2>/dev/null || true
find "$STAGE/backend" -name "*.db" -delete 2>/dev/null || true
find "$STAGE/backend" -name "*.db-shm" -delete 2>/dev/null || true
find "$STAGE/backend" -name "*.db-wal" -delete 2>/dev/null || true
find "$STAGE/backend" -name ".DS_Store" -delete 2>/dev/null || true

log "Backend staged"

# ── 4. Copy frontend (dist + server.js only) ─────────────

mkdir -p "$STAGE/frontend"
cp -r "$DIR/frontend/dist"      "$STAGE/frontend/dist"
cp    "$DIR/frontend/server.js"  "$STAGE/frontend/server.js"
cp    "$DIR/frontend/package.json" "$STAGE/frontend/package.json"

log "Frontend staged"

# ── 5. Copy scripts & config ─────────────────────────────

cp "$DIR/install.sh"       "$STAGE/install.sh"
cp "$DIR/start-prod.sh"    "$STAGE/start-prod.sh"
cp "$DIR/stop-prod.sh"     "$STAGE/stop-prod.sh"
cp "$DIR/update.sh"        "$STAGE/update.sh"
mkdir -p "$STAGE/lib"
cp "$DIR/lib/ensure-venv.sh" "$STAGE/lib/ensure-venv.sh"
cp "$DIR/lib/merge-env.sh" "$STAGE/lib/merge-env.sh"
cp "$DIR/lib/health-check.sh" "$STAGE/lib/health-check.sh"
cp "$DIR/lib/fix-crlf.sh" "$STAGE/lib/fix-crlf.sh"
cp "$DIR/lib/reset-admin.sh" "$STAGE/lib/reset-admin.sh"
chmod +x "$STAGE/lib/"*.sh 2>/dev/null || true

# LF line endings for Linux (Git Bash / WSL build on Windows)
for f in "$STAGE"/*.sh "$STAGE"/lib/*.sh; do
    [ -f "$f" ] && sed -i 's/\r$//' "$f" 2>/dev/null || perl -pi -e 's/\r\n/\n/g' "$f" 2>/dev/null || true
done

if [ -f "$DIR/.env.example" ]; then
    cp "$DIR/.env.example" "$STAGE/.env.example"
    sed -i 's/\r$//' "$STAGE/.env.example" 2>/dev/null || perl -pi -e 's/\r\n/\n/g' "$STAGE/.env.example" 2>/dev/null || true
fi

# Never bundle secrets — operators copy .env.example to .env on server

chmod +x "$STAGE"/*.sh 2>/dev/null || true

log "Scripts staged"

# ── 5b. Verify no venv slipped into the package ──────────

if find "$STAGE/backend" -type d \( -name "venv" -o -name ".venv" \) 2>/dev/null | grep -q .; then
    err "Package still contains venv/ — build aborted (remove backend/venv before packaging)"
fi
log "Verified: backend/venv not in package"

# ── 6. Create ZIP ────────────────────────────────────────

info "Creating $ZIP_NAME..."

cd "$BUILD_DIR"
zip -qr "$DIR/$ZIP_NAME" "worldcup-predict"

# Cleanup
rm -rf "$BUILD_DIR"

# ── 7. Done ──────────────────────────────────────────────

SIZE=$(ls -lh "$DIR/$ZIP_NAME" | awk '{print $5}')

echo ""
echo "=============================================="
echo "  Build complete!"
echo ""
echo "  Package: $ZIP_NAME ($SIZE)"
echo ""
echo "  Deploy to server:"
echo "    1. Upload $ZIP_NAME to server"
echo "    2. unzip $ZIP_NAME"
echo "    3. cd worldcup-predict"
echo "    4. ./install.sh      (first time only)"
echo "    5. ./start-prod.sh"
echo ""
echo "  Services (recommended: open :4173, login server URL empty):"
echo "    Frontend: http://<ip>:4173  (/api proxied to backend)"
echo "    Backend:  http://<ip>:8888"
echo "=============================================="
