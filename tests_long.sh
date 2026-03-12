#!/bin/bash

set -euo pipefail

PYTHON_BIN=".venv/bin/python"
ECHO_PID=""
HTTP_PID=""

STRESS_DURATION="${STRESS_DURATION:-20}"
STRESS_WORKERS="${STRESS_WORKERS:-24}"
STRESS_MAX_ERROR_RATE="${STRESS_MAX_ERROR_RATE:-0.02}"
STRESS_MAX_RSS_DELTA_KB="${STRESS_MAX_RSS_DELTA_KB:-131072}"

cleanup() {
    echo "Cleaning up servers..."
    if [ -n "$ECHO_PID" ]; then
        kill "$ECHO_PID" 2>/dev/null || true
    fi
    if [ -n "$HTTP_PID" ]; then
        kill "$HTTP_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT

wait_for_port() {
    local host="$1"
    local port="$2"
    local attempts="${3:-40}"
    local i=0
    while [ "$i" -lt "$attempts" ]; do
        if (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1; then
            return 0
        fi
        i=$((i + 1))
        sleep 0.1
    done
    return 1
}

INTERCEPTOR="$PWD/faultcore_interceptor/target/release/libfaultcore_interceptor.so"
if [ ! -f "$INTERCEPTOR" ]; then
    echo "Error: interceptor not found at $INTERCEPTOR"
    echo "Build it first with: sh build.sh"
    exit 1
fi

echo "Using interceptor: $INTERCEPTOR"

export ECHO_SERVER_HOST=127.0.0.1
export ECHO_SERVER_PORT=9000
export HTTP_SERVER_HOST=127.0.0.1
export HTTP_SERVER_PORT=8000

echo "Starting local test servers..."
pkill -f "tcp_echo_server.py" || true
pkill -f "uvicorn.*http_server" || true

"$PYTHON_BIN" tests/integration/servers/tcp_echo_server.py --host "$ECHO_SERVER_HOST" --port "$ECHO_SERVER_PORT" > /tmp/echo_server.log 2>&1 &
ECHO_PID=$!
"$PYTHON_BIN" -m uvicorn tests.integration.servers.http_server:app --host "$HTTP_SERVER_HOST" --port "$HTTP_SERVER_PORT" > /tmp/http_server.log 2>&1 &
HTTP_PID=$!

echo "Waiting for servers to start..."
wait_for_port "$ECHO_SERVER_HOST" "$ECHO_SERVER_PORT"
wait_for_port "$HTTP_SERVER_HOST" "$HTTP_SERVER_PORT"

echo "Running long stress integration..."
LD_PRELOAD="$INTERCEPTOR" "$PYTHON_BIN" tests/integration/test_stress.py \
    --host "$ECHO_SERVER_HOST" \
    --port "$ECHO_SERVER_PORT" \
    --mode long \
    --duration "$STRESS_DURATION" \
    --workers "$STRESS_WORKERS" \
    --max-error-rate "$STRESS_MAX_ERROR_RATE" \
    --max-rss-delta-kb "$STRESS_MAX_RSS_DELTA_KB"
