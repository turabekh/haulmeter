#!/usr/bin/env bash
# AI-CONTEXT: Compose preflight (HANDOFF section 2). Verifies every host port
# LONGHAUL will publish is free BEFORE any container starts. Fails loudly with
# the conflicting PID/command. Wired ahead of `docker compose up` via the
# Makefile. The three LOCKED ports (5438 API-db, 8008 API, 9008 UI) are never
# reassigned without the owner.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/infra/.env"
[ -f "$ENV_FILE" ] || ENV_FILE="$ROOT_DIR/infra/.env.example"

get_var() {
    { grep -E "^$1=" "$ENV_FILE" || true; } | tail -1 | cut -d= -f2- | tr -d '[:space:]'
}

pid_on_port() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        { lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true; } | head -1
    elif command -v ss >/dev/null 2>&1; then
        { ss -ltnp 2>/dev/null || true; } | awk -v p=":$port" '$4 ~ p"$" {print}' \
            | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2
    else
        if (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1; then echo "unknown"; fi
    fi
}

proc_name() {
    local pid="$1"
    if [ -z "$pid" ] || [ "$pid" = "unknown" ]; then echo "?"; return; fi
    ps -p "$pid" -o comm= 2>/dev/null || echo "?"
}

PORT_VARS="POSTGRES_PORT API_PORT UI_PORT REDIS_PORT MINIO_API_PORT MINIO_CONSOLE_PORT MAILPIT_SMTP_PORT MAILPIT_UI_PORT"

echo "LONGHAUL port preflight — env: $ENV_FILE"
conflicts=0
for var in $PORT_VARS; do
    port="$(get_var "$var")"
    [ -n "$port" ] || { echo "  ! $var not set in env"; conflicts=$((conflicts + 1)); continue; }
    pid="$(pid_on_port "$port")"
    if [ -n "$pid" ]; then
        echo "  ✗ $var=$port BUSY — held by PID $pid ($(proc_name "$pid"))"
        if [ "$var" = "UI_PORT" ]; then
            fb="$(get_var UI_PORT_FALLBACK)"
            fbpid="$(pid_on_port "$fb")"
            [ -z "$fbpid" ] && echo "      -> fallback $fb is free: set UI_PORT=$fb in infra/.env"
        fi
        conflicts=$((conflicts + 1))
    else
        echo "  ✓ $var=$port free"
    fi
done

if [ "$conflicts" -gt 0 ]; then
    echo ""
    echo "PREFLIGHT FAILED: $conflicts port conflict(s). Resolve before 'docker compose up'."
    exit 1
fi
echo "All ports free."
