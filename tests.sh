#!/bin/bash
# Test script for faultcore
# Runs cargo tests and pytest with interceptor preloaded

set -e

# Detect OS and set interceptor variables
INTERCEPTOR=""
case "$(uname)" in
    Linux)
        INTERCEPTOR="$PWD/target/release/libfaultcore_interceptor.so"
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
.venv/bin/python integration_tests/servers/tcp_echo_server.py --host 127.0.0.1 --port 9000 > /tmp/echo_server.log 2>&1 &
ECHO_PID=$!
.venv/bin/python -m uvicorn integration_tests.servers.http_server:app --host 127.0.0.1 --port 8000 > /tmp/http_server.log 2>&1 &
HTTP_PID=$!

# Wait for servers to be ready
echo "Waiting for servers to start..."
sleep 2

# Run pytest with the interceptor (using python directly to ensure env vars are passed)
PYTEST=".venv/bin/python -m pytest"
echo "Running tests with interceptor..."
# Run full suite including integration tests (but only the ones in tests/ directory)
LD_PRELOAD="$INTERCEPTOR" $PYTEST tests/ -v -s

# Cleanup
echo "Cleaning up servers..."
kill $ECHO_PID || true
kill $HTTP_PID || true
