#!/bin/bash
# Test script for faultcore
# Runs pytest with interceptor preloaded

set -e

cd faultcore_interceptor
cargo test
cargo build --release

cd ../faultcore_network
cargo test

cd ..

ECHO_PID=""
HTTP_PID=""

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
.venv/bin/python tests/integration/servers/tcp_echo_server.py --host 127.0.0.1 --port 9000 > /tmp/echo_server.log 2>&1 &
ECHO_PID=$!
.venv/bin/python -m uvicorn tests.integration.servers.http_server:app --host 127.0.0.1 --port 8000 > /tmp/http_server.log 2>&1 &
HTTP_PID=$!

# Wait for servers to be ready
echo "Waiting for servers to start..."
sleep 2

# Run pytest with the interceptor (using python directly to ensure env vars are passed)
PYTEST=".venv/bin/python -m pytest"
echo "Running integration tests with interceptor..."
LD_PRELOAD="$INTERCEPTOR" $PYTEST tests/unit -v -s
