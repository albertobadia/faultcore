#!/bin/bash
# Test script for faultcore
# Runs pytest with interceptor preloaded

set -euo pipefail

cd faultcore_interceptor
cargo test
cargo build --release

cd ../faultcore_network
cargo test

cd ..

ECHO_PID=""
HTTP_PID=""
PYTHON_BIN=".venv/bin/python"

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

# Detect OS and set interceptor variables
INTERCEPTOR=""
case "$(uname)" in
    Linux)
        INTERCEPTOR="$PWD/faultcore_interceptor/target/release/libfaultcore_interceptor.so"
        if [ -f "$INTERCEPTOR" ]; then
            export LD_PRELOAD="$INTERCEPTOR"
            echo "Using interceptor: $INTERCEPTOR"
        else
            echo "Warning: Interceptor not found at $INTERCEPTOR"
        fi
        ;;
    *)
        echo "Unknown OS, skipping interceptor"
        ;;
esac

# Start local test servers for integration tests
echo "Starting local test servers..."
export ECHO_SERVER_HOST=127.0.0.1
export ECHO_SERVER_PORT=9000
export HTTP_SERVER_HOST=127.0.0.1
export HTTP_SERVER_PORT=8000

# Kill existing servers if any
pkill -f "tcp_echo_server.py" || true
pkill -f "uvicorn.*http_server" || true

# Start servers in background
"$PYTHON_BIN" tests/integration/servers/tcp_echo_server.py --host 127.0.0.1 --port 9000 > /tmp/echo_server.log 2>&1 &
ECHO_PID=$!
"$PYTHON_BIN" -m uvicorn tests.integration.servers.http_server:app --host 127.0.0.1 --port 8000 > /tmp/http_server.log 2>&1 &
HTTP_PID=$!

# Wait for servers to be ready
echo "Waiting for servers to start..."
wait_for_port "$ECHO_SERVER_HOST" "$ECHO_SERVER_PORT"
wait_for_port "$HTTP_SERVER_HOST" "$HTTP_SERVER_PORT"

# Run pytest unit tests with the interceptor (using python directly to ensure env vars are passed)
PYTEST="$PYTHON_BIN -m pytest"
echo "Running unit tests with interceptor..."
LD_PRELOAD="$INTERCEPTOR" $PYTEST tests/unit -v -s

# Run integration CLI scripts (auto-discovery; each script defines its own default suite)
echo "Running integration CLI scripts with interceptor..."
run_integration_script() {
    local script="$1"
    shift
    echo "Running integration script: $script $*"
    LD_PRELOAD="$INTERCEPTOR" "$PYTHON_BIN" "$script" \
        --host "$ECHO_SERVER_HOST" \
        --port "$ECHO_SERVER_PORT" \
        "$@"
}

shopt -s nullglob
INTEGRATION_SCRIPTS=(tests/integration/test_*.py)
shopt -u nullglob

if [ "${#INTEGRATION_SCRIPTS[@]}" -eq 0 ]; then
    echo "Warning: no integration scripts found in tests/integration/"
else
    IFS=$'\n' SORTED_SCRIPTS=($(printf "%s\n" "${INTEGRATION_SCRIPTS[@]}" | sort))
    unset IFS
    for script in "${SORTED_SCRIPTS[@]}"; do
        run_integration_script "$script"
    done
fi
