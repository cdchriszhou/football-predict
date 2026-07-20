#!/bin/bash
# Quick production health checks after start/update.

# Wait until backend responds (lifespan may still be running Alembic/bcrypt).
wait_for_backend_health() {
    local backend_port="${1:-8888}"
    local max_attempts="${2:-30}"
    local sleep_sec="${3:-2}"
    local attempt=1

    while [ "$attempt" -le "$max_attempts" ]; do
        if curl -sf "http://127.0.0.1:${backend_port}/api/v1/system/health" > /dev/null 2>&1; then
            return 0
        fi
        sleep "$sleep_sec"
        attempt=$((attempt + 1))
    done
    return 1
}

check_service_health() {
    local backend_port="${1:-8888}"
    local frontend_port="${2:-4173}"
    local ok=true

    if command -v curl &> /dev/null; then
        if curl -sf "http://127.0.0.1:${backend_port}/api/v1/system/health" > /dev/null 2>&1; then
            echo "[health] Backend :${backend_port} OK (system/health)"
        elif curl -sf "http://127.0.0.1:${backend_port}/" > /dev/null 2>&1; then
            echo "[health] Backend :${backend_port} OK (root)"
        else
            echo "[health] Backend :${backend_port} FAILED"
            ok=false
        fi

        if curl -sf "http://127.0.0.1:${frontend_port}/health" > /dev/null 2>&1; then
            echo "[health] Frontend :${frontend_port} OK"
        else
            echo "[health] Frontend :${frontend_port} FAILED"
            ok=false
        fi

        # API via frontend proxy (same-origin path used by browser)
        local api_code
        api_code=$(curl -s -o /dev/null -w "%{http_code}" \
            "http://127.0.0.1:${frontend_port}/api/v1/competitions" 2>/dev/null || echo "000")
        case "$api_code" in
            200|401|403)
                echo "[health] API proxy /api/v1/competitions -> HTTP ${api_code} (reachable)"
                ;;
            502|000)
                echo "[health] API proxy FAILED (HTTP ${api_code}) — check backend.log"
                ok=false
                ;;
            *)
                echo "[health] API proxy HTTP ${api_code}"
                ;;
        esac
    else
        echo "[health] curl not installed — skip HTTP checks"
    fi

    $ok
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_service_health "${1:-8888}" "${2:-4173}"
fi
