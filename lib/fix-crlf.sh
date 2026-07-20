#!/bin/bash
# Strip Windows CRLF from shell scripts and env files (safe on Linux after zip from Windows).

fix_crlf_file() {
    local f="${1:?file required}"
    if [ -f "$f" ] && grep -q $'\r' "$f" 2>/dev/null; then
        sed -i 's/\r$//' "$f"
        echo "[fix-crlf] Normalized: $f"
    fi
}

fix_crlf_dotenv() {
    local root="${1:?directory required}"
    fix_crlf_file "$root/.env"
    fix_crlf_file "$root/.env.example"
}

fix_crlf_in_tree() {
    local root="${1:?directory required}"
    local count=0
    while IFS= read -r -d '' f; do
        if grep -q $'\r' "$f" 2>/dev/null; then
            sed -i 's/\r$//' "$f"
            count=$((count + 1))
        fi
    done < <(find "$root" -type f \( -name '*.sh' \) -print0 2>/dev/null)
    if [ "$count" -gt 0 ]; then
        echo "[fix-crlf] Normalized line endings in $count shell script(s) under $root"
    fi
    fix_crlf_dotenv "$root"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    fix_crlf_in_tree "${1:-$(cd "$(dirname "$0")/.." && pwd)}"
fi
