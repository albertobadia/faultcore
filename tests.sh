#!/bin/bash

set -euo pipefail

ECHO_PID=""
HTTP_PID=""
PYTHON_BIN=".venv/bin/python"

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: required command '$cmd' was not found."
        exit 1
    fi
}

require_path() {
    local path="$1"
    if [ ! -e "$path" ]; then
        echo "Error: required path '$path' was not found."
        exit 1
    fi
}

platform_tag() {
    local system
    local machine
    system="$(uname -s)"
    machine="$(uname -m)"

    case "${system}:${machine}" in
    Linux:x86_64 | Linux:amd64)
        echo "linux-x86_64"
        ;;
    Linux:aarch64 | Linux:arm64)
        echo "linux-aarch64"
        ;;
    *)
        echo "unsupported"
        ;;
    esac
}

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

require_cmd cargo
require_path "$PYTHON_BIN"

echo "Running Rust tests..."
cargo test --manifest-path faultcore_interceptor/Cargo.toml
cargo test --manifest-path faultcore_network/Cargo.toml

INTERCEPTOR=""
PRELOAD_ENV=""
if [ "$(uname -s)" = "Linux" ]; then
    PLATFORM_TAG="$(platform_tag)"
    if [ "$PLATFORM_TAG" = "unsupported" ]; then
        echo "Error: unsupported Linux architecture '$(uname -m)'."
        exit 1
    fi
    INTERCEPTOR="$PWD/src/faultcore/_native/$PLATFORM_TAG/libfaultcore_interceptor.so"
    if [ ! -f "$INTERCEPTOR" ]; then
        echo "Error: interceptor not found at $INTERCEPTOR"
        echo "Run 'sh build.sh' before running tests."
        exit 1
    fi
    PRELOAD_ENV="${INTERCEPTOR}${LD_PRELOAD:+ ${LD_PRELOAD}}"
    echo "Using interceptor: $INTERCEPTOR"
else
    echo "Non-Linux host detected, skipping LD_PRELOAD setup."
fi

echo "Starting local test servers..."
export ECHO_SERVER_HOST=127.0.0.1
export ECHO_SERVER_PORT=9000
export HTTP_SERVER_HOST=127.0.0.1
export HTTP_SERVER_PORT=8000

pkill -f "tcp_echo_server.py" || true
pkill -f "uvicorn.*http_server" || true

"$PYTHON_BIN" tests/integration/servers/tcp_echo_server.py --host 127.0.0.1 --port 9000 > /tmp/echo_server.log 2>&1 &
ECHO_PID=$!
"$PYTHON_BIN" -m uvicorn tests.integration.servers.http_server:app --host 127.0.0.1 --port 8000 > /tmp/http_server.log 2>&1 &
HTTP_PID=$!

echo "Waiting for servers to start..."
wait_for_port "$ECHO_SERVER_HOST" "$ECHO_SERVER_PORT"
wait_for_port "$HTTP_SERVER_HOST" "$HTTP_SERVER_PORT"

run_with_optional_preload() {
    if [ -n "$PRELOAD_ENV" ]; then
        LD_PRELOAD="$PRELOAD_ENV" "$@"
    else
        "$@"
    fi
}

echo "Running unit tests with interceptor..."
run_with_optional_preload "$PYTHON_BIN" -m pytest tests/unit -v -s

echo "Running integration CLI scripts with interceptor..."
run_integration_script() {
    local script="$1"
    shift
    echo "Running integration script: $script $*"
    run_with_optional_preload "$PYTHON_BIN" "$script" \
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
