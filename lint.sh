#!/bin/bash

set -euo pipefail

MODE="${1:-check}"

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: required command '$cmd' was not found."
        exit 1
    fi
}

require_cmd uv
require_cmd cargo

run_clippy() {
    (
        cd faultcore_network
        uv run cargo clippy --all-targets --all-features -- -D warnings
    )
    (
        cd faultcore_interceptor
        uv run cargo clippy --all-targets --all-features -- -D warnings
    )
}

case "$MODE" in
check)
    echo "=== Lint mode: check (no file mutations) ==="
    run_clippy
    uv run ruff check .
    uv run ruff format --check .
    ;;
fix)
    echo "=== Lint mode: fix (modifies files) ==="
    run_clippy
    uv run ruff check . --fix
    uv run ruff format .
    ;;
*)
    echo "Usage: sh lint.sh [check|fix]"
    exit 2
    ;;
esac
