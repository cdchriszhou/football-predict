#!/bin/bash
# Ensure a Linux-compatible Python venv exists under backend/venv.
# Removes broken dirs (e.g. Windows Scripts-only venv copied into package).

is_linux_venv() {
    [ -f "${1}/bin/activate" ]
}

remove_invalid_venv() {
    local venv_dir="${1:?venv path required}"
    [ -d "$venv_dir" ] || return 0
    if is_linux_venv "$venv_dir"; then
        return 0
    fi
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
        if ! command -v python3 &> /dev/null; then
            echo "[ERROR] python3 not found"
            return 1
        fi
        if ! python3 -m venv "$venv_dir"; then
            echo "[ERROR] venv creation failed — install python3-venv: apt install python3-venv"
            return 1
        fi
    fi

    if [ ! -f "$venv_dir/bin/activate" ]; then
        echo "[ERROR] venv incomplete after creation — install python3-venv"
        return 1
    fi

    # shellcheck disable=SC1090
    source "$venv_dir/bin/activate"
}
