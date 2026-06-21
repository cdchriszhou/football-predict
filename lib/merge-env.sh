#!/bin/bash
# Merge missing keys from .env.example into .env (never overwrite existing values).

merge_env_file() {
    local example="${1:?example .env path required}"
    local target="${2:?target .env path required}"

    if [ ! -f "$example" ]; then
        echo "[merge-env] Skip: no $example"
        return 0
    fi

    touch "$target"
    local added=0

    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [ -z "$line" ] && continue
        case "$line" in
            *=*) ;;
            *) continue ;;
        esac
        local key="${line%%=*}"
        key="$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [ -z "$key" ] && continue
        if grep -qE "^[[:space:]]*${key}=" "$target" 2>/dev/null; then
            continue
        fi
        echo "$line" >> "$target"
        added=$((added + 1))
    done < "$example"

    if [ "$added" -gt 0 ]; then
        echo "[merge-env] Added $added key(s) to $(basename "$target") from $(basename "$example")"
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    ROOT="$(cd "$(dirname "$0")/.." && pwd)"
    merge_env_file "$ROOT/.env.example" "$ROOT/.env"
fi
