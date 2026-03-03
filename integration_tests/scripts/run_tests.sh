#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "FaultCore Integration Test Suite"
echo "============================================"
echo ""

ECHO_SERVER_HOST="${ECHO_SERVER_HOST:-localhost}"
ECHO_SERVER_PORT="${ECHO_SERVER_PORT:-9000}"
HTTP_SERVER_HOST="${HTTP_SERVER_HOST:-localhost}"
HTTP_SERVER_PORT="${HTTP_SERVER_PORT:-8000}"

echo "Configuration:"
echo "  Echo Server: $ECHO_SERVER_HOST:$ECHO_SERVER_PORT"
echo "  HTTP Server: $HTTP_SERVER_HOST:$HTTP_SERVER_PORT"
echo ""

test_latency() {
    echo ">>> Testing Latency"
    python3 "$PROJECT_DIR/clients/test_latency.py" \
        --host "$ECHO_SERVER_HOST" \
        --port "$ECHO_SERVER_PORT" \
        --message "Test latency" \
        --count 5
    echo ""
}

test_bandwidth() {
    echo ">>> Testing Bandwidth"
    python3 "$PROJECT_DIR/clients/test_bandwidth.py" \
        --host "$ECHO_SERVER_HOST" \
        --port "$ECHO_SERVER_PORT" \
        --mode send \
        --size 1024 \
        --duration 3
    echo ""
}

test_throughput() {
    echo ">>> Testing Throughput"
    python3 "$PROJECT_DIR/clients/test_bandwidth.py" \
        --host "$ECHO_SERVER_HOST" \
        --port "$ECHO_SERVER_PORT" \
        --mode throughput \
        --messages 50
    echo ""
}

test_timeout_connect() {
    echo ">>> Testing Connect Timeout"
    python3 "$PROJECT_DIR/clients/test_timeout.py" \
        --host "$ECHO_SERVER_HOST" \
        --port "$ECHO_SERVER_PORT" \
        --mode connect \
        --timeout 5000
    echo ""
}

test_timeout_recv() {
    echo ">>> Testing Receive Timeout"
    python3 "$PROJECT_DIR/clients/test_timeout.py" \
        --host "$ECHO_SERVER_HOST" \
        --port "$ECHO_SERVER_PORT" \
        --mode recv \
        --timeout 3000
    echo ""
}

wait_for_server() {
    local host=$1
    local port=$2
    local name=$3
    local max_attempts=30
    local attempt=0
    
    echo "Waiting for $name at $host:$port..."
    
    while [ $attempt -lt $max_attempts ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo "$name is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    echo "ERROR: $name did not start in time"
    return 1
}

if [ "${1:-}" = "--with-servers" ]; then
    echo "Starting test servers..."
    
    echo "Starting TCP Echo Server..."
    python3 "$PROJECT_DIR/servers/tcp_echo_server.py" \
        --host "0.0.0.0" \
        --port 9000 &
    ECHO_PID=$!
    
    echo "Starting HTTP Server..."
    python3 "$PROJECT_DIR/servers/http_server.py" &
    HTTP_PID=$!
    
    sleep 2
    
    wait_for_server localhost 9000 "TCP Echo Server"
    wait_for_server localhost 8000 "HTTP Server"
    
    trap "kill $ECHO_PID $HTTP_PID 2>/dev/null; exit" INT TERM
fi

echo "Running tests..."
echo ""

if [ "${1:-}" = "--latency-only" ]; then
    test_latency
elif [ "${1:-}" = "--bandwidth-only" ]; then
    test_bandwidth
elif [ "${1:-}" = "--timeout-only" ]; then
    test_timeout_connect
    test_timeout_recv
else
    test_latency
    test_bandwidth
    test_throughput
    test_timeout_connect
    test_timeout_recv
fi

echo "============================================"
echo "Test Suite Complete"
echo "============================================"

if [ -n "${ECHO_PID:-}" ]; then
    kill $ECHO_PID $HTTP_PID 2>/dev/null || true
fi
