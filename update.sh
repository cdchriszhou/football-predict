#!/bin/bash
# ============================================================
#  2026 World Cup Predictor — Auto-Update Script
#  Usage: /mnt/update.sh
#
#  Finds the latest production zip package in /mnt/,
#  stops services, backs up the database, deploys the new
#  version, restores data, runs migrations, and restarts.
# ============================================================

set -e

DEPLOY_DIR="/mnt/worldcup-predict"
ZIP_PATTERN="/mnt/worldcup-predict-prod-2026*.zip"
BACKUP_DIR="/mnt/backups"
SCRIPT_NAME="$(basename "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }
header(){ echo -e "${CYAN}>>>${NC} $1"; }

# ── Privilege check ─────────────────────────────────────────
if [ "$EUID" -eq 0 ]; then
    warn "Running as root — consider using a non-root user with sudo"
fi

# ── Find latest package ─────────────────────────────────────

echo "=============================================="
echo "  2026 World Cup Predictor — Auto Update"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
echo ""

header "Step 1/6: Finding latest deployment package..."

LATEST_ZIP=$(ls -t ${ZIP_PATTERN} 2>/dev/null | head -1)

if [ -z "$LATEST_ZIP" ]; then
    err "No deployment package found matching: ${ZIP_PATTERN}"
    echo "  Upload a zip file (e.g. worldcup-predict-prod-20260601-120000.zip) to /mnt/ first."
    exit 1
fi

log "Found: $(basename "$LATEST_ZIP")"

# ── Verify package ──────────────────────────────────────────

header "Step 2/6: Verifying package integrity..."

if ! unzip -t "$LATEST_ZIP" > /dev/null 2>&1; then
    err "Zip file is corrupted: $LATEST_ZIP"
    exit 1
fi
log "Package integrity verified"

# Check that the zip contains the expected directory structure.
# Path separator may differ (Windows build: backslash, Linux: forward slash).
# We check for "worldcup-predict" appearing as a directory entry.
if ! unzip -l "$LATEST_ZIP" 2>/dev/null | grep -q "worldcup-predict"; then
    err "Package does not contain 'worldcup-predict/' root directory"
    exit 1
fi
# Reject incomplete Windows builds that omit backend packages (causes ModuleNotFoundError: db)
ZIP_LIST=$(unzip -l "$LATEST_ZIP" 2>/dev/null | tr '\\' '/')
for need in \
    "worldcup-predict/backend/db/" \
    "worldcup-predict/backend/api/" \
    "worldcup-predict/backend/service/" \
    "worldcup-predict/backend/alembic/" \
    "worldcup-predict/backend/main.py"
do
    if ! echo "$ZIP_LIST" | grep -qF "$need"; then
        err "Package incomplete — missing $need (rebuild with fixed build.bat / build.sh)"
        exit 1
    fi
done
log "Package structure verified"

# ── Stop services ───────────────────────────────────────────

header "Step 3/6: Stopping current services..."

if [ -f "$DEPLOY_DIR/stop-prod.sh" ]; then
    bash "$DEPLOY_DIR/stop-prod.sh" 2>&1 | sed 's/^/  /'
else
    warn "No stop-prod.sh found — stopping via port"
    if [ "$(uname)" = "Linux" ]; then
        fuser -k 8888/tcp 2>/dev/null && echo "  Released port 8888" || true
        fuser -k 4173/tcp 2>/dev/null && echo "  Released port 4173" || true
    else
        lsof -ti tcp:8888 | xargs kill 2>/dev/null && echo "  Released port 8888" || true
        lsof -ti tcp:4173 | xargs kill 2>/dev/null && echo "  Released port 4173" || true
    fi
fi

# Extra safety: kill any remaining uvicorn/node on deploy ports
if [ "$(uname)" = "Linux" ]; then
    fuser -k 8888/tcp 2>/dev/null || true
    fuser -k 4173/tcp 2>/dev/null || true
else
    lsof -ti tcp:8888 | xargs kill 2>/dev/null || true
    lsof -ti tcp:4173 | xargs kill 2>/dev/null || true
fi
sleep 2
log "Services stopped"

# ── Backup database ─────────────────────────────────────────

header "Step 4/6: Backing up user data..."

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
DB_BACKUP="$BACKUP_DIR/worldcup2026-${TIMESTAMP}.db"
ENV_BACKUP="$BACKUP_DIR/.env-${TIMESTAMP}"

DB_PATH="$DEPLOY_DIR/backend/worldcup2026.db"
ENV_PATH="$DEPLOY_DIR/.env"

backed_up_db=false
if [ -f "$DB_PATH" ]; then
    # Copy the database safely (SQLite WAL checkpoint first)
    if command -v sqlite3 &> /dev/null; then
        sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
    fi
    cp "$DB_PATH" "$DB_BACKUP" 2>/dev/null || true
    # Also backup WAL/SHM files if they exist
    for ext in wal shm; do
        [ -f "${DB_PATH}-${ext}" ] && cp "${DB_PATH}-${ext}" "${DB_BACKUP}-${ext}" 2>/dev/null || true
    done
    if [ -f "$DB_BACKUP" ]; then
        log "Database backed up: $(basename "$DB_BACKUP")"
        backed_up_db=true
    else
        warn "Database backup failed"
    fi
else
    warn "No existing database found (fresh install?)"
fi

if [ -f "$ENV_PATH" ]; then
    cp "$ENV_PATH" "$ENV_BACKUP" 2>/dev/null || true
    log ".env file backed up"
fi

# ── Deploy new version ──────────────────────────────────────

header "Step 5/6: Deploying new version..."

TEMP_DIR="/tmp/worldcup-update-${TIMESTAMP}"
mkdir -p "$TEMP_DIR"

log "Extracting $(basename "$LATEST_ZIP")..."
# unzip may warn about Windows backslash paths and return non-zero on some systems.
# Temporarily disable set -e and validate by checking directory existence instead.
set +e
unzip -q -o "$LATEST_ZIP" -d "$TEMP_DIR" 2>/dev/null
set -e
if [ ! -d "$TEMP_DIR/worldcup-predict" ]; then
    err "Extraction failed — zip may be corrupted or use incompatible path format"
    rm -rf "$TEMP_DIR"
    exit 1
fi

NEW_SRC="$TEMP_DIR/worldcup-predict"

OLD_BACKUP=""
# Remove old deployment (keep .env and database in memory via backup)
if [ -d "$DEPLOY_DIR" ]; then
    # Save .env from new package if it doesn't have one but old does
    if [ ! -f "$NEW_SRC/.env" ] && [ -f "$ENV_PATH" ]; then
        cp "$ENV_PATH" "$NEW_SRC/.env" 2>/dev/null || true
    fi

    # Move old to backup (for quick rollback)
    OLD_BACKUP="${DEPLOY_DIR}.old-${TIMESTAMP}"
    mv "$DEPLOY_DIR" "$OLD_BACKUP" 2>/dev/null || {
        rm -rf "$DEPLOY_DIR"
    }
    log "Previous deployment moved to $(basename "$OLD_BACKUP")"
fi

mv "$NEW_SRC" "$DEPLOY_DIR"
log "New deployment installed at $DEPLOY_DIR"

# Windows-built zips often ship CRLF in .sh files — normalize before sourcing lib/*.sh
if [ -f "$DEPLOY_DIR/lib/fix-crlf.sh" ]; then
    sed -i 's/\r$//' "$DEPLOY_DIR/lib/fix-crlf.sh" 2>/dev/null || true
    # shellcheck source=lib/fix-crlf.sh
    source "$DEPLOY_DIR/lib/fix-crlf.sh"
    fix_crlf_in_tree "$DEPLOY_DIR"
elif command -v sed &> /dev/null; then
    find "$DEPLOY_DIR" -type f -name '*.sh' -exec sed -i 's/\r$//' {} + 2>/dev/null || true
    log "Shell scripts CRLF stripped (fallback)"
fi

# ── Restore user data ───────────────────────────────────────

if $backed_up_db; then
    header "Step 6/6: Restoring user data..."

    # Only restore database if new deployment doesn't have one
    if [ ! -f "$DEPLOY_DIR/backend/worldcup2026.db" ] || [ ! -s "$DEPLOY_DIR/backend/worldcup2026.db" ]; then
        cp "$DB_BACKUP" "$DEPLOY_DIR/backend/worldcup2026.db"
        for ext in wal shm; do
            [ -f "${DB_BACKUP}-${ext}" ] && cp "${DB_BACKUP}-${ext}" "$DEPLOY_DIR/backend/worldcup2026.db-${ext}" 2>/dev/null || true
        done
        log "User database restored (${TIMESTAMP})"
    else
        log "New deployment has its own database — keeping backed-up copy at $DB_BACKUP for reference"
    fi
fi

# Restore .env if new deployment overwrote it
if [ -f "$ENV_BACKUP" ] && [ ! -f "$DEPLOY_DIR/.env" ]; then
    cp "$ENV_BACKUP" "$DEPLOY_DIR/.env"
    log ".env restored"
fi

# Merge new keys from .env.example (CORS_ORIGINS, APP_ENV, etc.) without overwriting secrets
if [ -f "$DEPLOY_DIR/lib/merge-env.sh" ]; then
    sed -i 's/\r$//' "$DEPLOY_DIR/lib/merge-env.sh" 2>/dev/null || true
    # shellcheck source=lib/merge-env.sh
    source "$DEPLOY_DIR/lib/merge-env.sh"
    if [ ! -f "$DEPLOY_DIR/.env" ] && [ -f "$DEPLOY_DIR/.env.example" ]; then
        cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
        warn "Created .env from .env.example — set ADMIN_PASSWORD and JWT_SECRET before production use"
    fi
    merge_env_file "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
fi

# .env is often edited on Windows — CRLF breaks "source .env" in start-prod.sh
if [ -f "$DEPLOY_DIR/lib/fix-crlf.sh" ]; then
    # shellcheck source=lib/fix-crlf.sh
    source "$DEPLOY_DIR/lib/fix-crlf.sh"
    fix_crlf_dotenv "$DEPLOY_DIR"
elif [ -f "$DEPLOY_DIR/.env" ]; then
    sed -i 's/\r$//' "$DEPLOY_DIR/.env" 2>/dev/null || true
    [ -f "$DEPLOY_DIR/.env.example" ] && sed -i 's/\r$//' "$DEPLOY_DIR/.env.example" 2>/dev/null || true
fi

# Drop Windows/broken venv dirs from the new tree (must use bin/activate on Linux)
if [ -d "$DEPLOY_DIR/backend/venv" ] && [ ! -f "$DEPLOY_DIR/backend/venv/bin/activate" ]; then
    warn "Removing incompatible backend/venv from deployment package"
    rm -rf "$DEPLOY_DIR/backend/venv"
fi

# Restore Python venv from previous deployment only when it is a valid Linux venv
if [ -n "$OLD_BACKUP" ] && [ -f "$OLD_BACKUP/backend/venv/bin/activate" ] \
    && [ ! -f "$DEPLOY_DIR/backend/venv/bin/activate" ]; then
    cp -a "$OLD_BACKUP/backend/venv" "$DEPLOY_DIR/backend/venv"
    log "Python venv restored from previous deployment"
elif [ -n "$OLD_BACKUP" ] && [ -d "$OLD_BACKUP/backend/venv" ] \
    && [ ! -f "$OLD_BACKUP/backend/venv/bin/activate" ]; then
    warn "Skipped restoring backend/venv — previous copy is Windows/invalid; will create fresh Linux venv"
fi

# ── Install/update dependencies ─────────────────────────────

log "Checking dependencies..."

# Python dependencies
if [ -f "$DEPLOY_DIR/backend/requirements.txt" ]; then
    if [ -f "$DEPLOY_DIR/lib/ensure-venv.sh" ]; then
        sed -i 's/\r$//' "$DEPLOY_DIR/lib/ensure-venv.sh" 2>/dev/null || true
        # shellcheck source=lib/ensure-venv.sh
        source "$DEPLOY_DIR/lib/ensure-venv.sh"
        ensure_python_venv "$DEPLOY_DIR/backend"
    else
        if [ -d "$DEPLOY_DIR/backend/venv" ] && [ ! -f "$DEPLOY_DIR/backend/venv/bin/activate" ]; then
            rm -rf "$DEPLOY_DIR/backend/venv"
        fi
        if [ ! -f "$DEPLOY_DIR/backend/venv/bin/activate" ]; then
            python3 -m venv "$DEPLOY_DIR/backend/venv"
        fi
        # shellcheck disable=SC1090
        source "$DEPLOY_DIR/backend/venv/bin/activate"
    fi
    pip install -r "$DEPLOY_DIR/backend/requirements.txt" -q 2>&1 | tail -3
    log "Python dependencies up to date"
fi

# Database migrations
if [ -f "$DEPLOY_DIR/backend/alembic.ini" ]; then
    log "Running database migrations..."
    if [ -f "$DEPLOY_DIR/lib/ensure-venv.sh" ]; then
        source "$DEPLOY_DIR/lib/ensure-venv.sh"
        ensure_python_venv "$DEPLOY_DIR/backend"
    elif [ -f "$DEPLOY_DIR/backend/venv/bin/activate" ]; then
        # shellcheck disable=SC1090
        source "$DEPLOY_DIR/backend/venv/bin/activate"
    fi
    (cd "$DEPLOY_DIR/backend" && python -m alembic upgrade head) 2>&1 | sed 's/^/  /' || warn "Alembic migration failed — check logs"
fi


# ── Restart services ────────────────────────────────────────

log "Starting services..."
if [ -f "$DEPLOY_DIR/start-prod.sh" ]; then
    bash "$DEPLOY_DIR/start-prod.sh" 2>&1 | sed 's/^/  /'
else
    warn "No start-prod.sh found — start services manually"
fi

# Health check (frontend proxies /api -> backend; 401 on competitions without token is OK)
if [ -f "$DEPLOY_DIR/lib/health-check.sh" ]; then
    sed -i 's/\r$//' "$DEPLOY_DIR/lib/health-check.sh" 2>/dev/null || true
    # shellcheck source=lib/health-check.sh
    source "$DEPLOY_DIR/lib/health-check.sh"
    if wait_for_backend_health 8888 45 2 && check_service_health 8888 4173; then
        log "Service health checks passed"
    else
        warn "Some health checks failed — see backend.log / frontend.log"
    fi
elif command -v curl &> /dev/null; then
    curl -sf "http://127.0.0.1:8888/" > /dev/null 2>&1 && log "Backend OK" || warn "Backend check failed"
    curl -sf "http://127.0.0.1:4173/health" > /dev/null 2>&1 && log "Frontend OK" || warn "Frontend check failed"
fi

# ── Cleanup old temp files ──────────────────────────────────

rm -rf "$TEMP_DIR"

# Keep only the last 5 backups
OLD_BACKUPS=$(ls -dt ${DEPLOY_DIR}.old-* 2>/dev/null | tail -n +6)
for b in $OLD_BACKUPS; do
    rm -rf "$b"
    log "Cleaned up old backup: $(basename "$b")"
done

echo ""
echo "=============================================="
echo "  Update complete!"
echo ""
echo "  Deployment:  $DEPLOY_DIR"
echo "  DB backup:   $DB_BACKUP"
echo "  Rollback:    mv ${DEPLOY_DIR}.old-${TIMESTAMP} $DEPLOY_DIR && restart"
echo ""
echo "  Verify (browser: leave login server URL empty):"
echo "    Frontend: http://localhost:4173  (proxies /api -> :8888)"
echo "    Backend:  http://localhost:8888"
echo "    API docs: http://localhost:8888/docs"
echo "  Production .env: set APP_ENV=production; optional CORS_ORIGINS for split ports"
echo "=============================================="

# Self-update update.sh from new deployment (safe — at end of script)
if [ -f "$DEPLOY_DIR/update.sh" ] && ! cmp -s "$DEPLOY_DIR/update.sh" "/mnt/update.sh"; then
    cp "$DEPLOY_DIR/update.sh" "/mnt/update.sh"
    chmod +x "/mnt/update.sh"
    log "Update script self-updated"
fi
