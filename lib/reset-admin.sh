#!/bin/bash
# Reset admin password to match /mnt/worldcup-predict/.env (run on production server).
set -e
DIR="${1:-/mnt/worldcup-predict}"
cd "$DIR"
if [ -f .env ]; then
  grep -q $'\r' .env 2>/dev/null && sed -i 's/\r$//' .env
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
# shellcheck source=lib/ensure-venv.sh
source "$DIR/lib/ensure-venv.sh"
ensure_python_venv "$DIR/backend"
cd "$DIR/backend"
python scripts/reset_admin_password.py
echo "Try logging in with ADMIN_USERNAME + ADMIN_PASSWORD from .env"
