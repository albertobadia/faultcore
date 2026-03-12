#!/bin/bash

set -euo pipefail

PYTHON_BIN=".venv/bin/python"
INTERCEPTOR_BUILD_OUT="faultcore_interceptor/target/release/libfaultcore_interceptor.so"
NATIVE_ROOT="src/faultcore/_native"

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

read_version_from_toml() {
    local file="$1"
    awk -F'"' '/^version = "/ {print $2; exit}' "$file"
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
        echo "Error: unsupported platform '${system}/${machine}' for native packaging."
        exit 1
        ;;
    esac
}

require_cmd uv
require_cmd cargo
require_path "$PYTHON_BIN"

PY_VERSION="$(read_version_from_toml pyproject.toml)"
INTERCEPTOR_VERSION="$(read_version_from_toml faultcore_interceptor/Cargo.toml)"
NETWORK_VERSION="$(read_version_from_toml faultcore_network/Cargo.toml)"

if [ -z "$PY_VERSION" ] || [ -z "$INTERCEPTOR_VERSION" ] || [ -z "$NETWORK_VERSION" ]; then
    echo "Error: failed to parse versions from metadata files."
    exit 1
fi

if [ "$PY_VERSION" != "$INTERCEPTOR_VERSION" ] || [ "$PY_VERSION" != "$NETWORK_VERSION" ]; then
    echo "Error: version mismatch detected."
    echo "  pyproject.toml: $PY_VERSION"
    echo "  faultcore_interceptor/Cargo.toml: $INTERCEPTOR_VERSION"
    echo "  faultcore_network/Cargo.toml: $NETWORK_VERSION"
    exit 1
fi

PLATFORM_TAG="$(platform_tag)"
NATIVE_PLATFORM_DIR="$NATIVE_ROOT/$PLATFORM_TAG"

echo "=== Building faultcore_interceptor (release) ==="
cargo build --release --manifest-path faultcore_interceptor/Cargo.toml
require_path "$INTERCEPTOR_BUILD_OUT"

echo "=== Staging native artifacts for $PLATFORM_TAG ==="
mkdir -p "$NATIVE_PLATFORM_DIR"
cp "$INTERCEPTOR_BUILD_OUT" "$NATIVE_PLATFORM_DIR/libfaultcore_interceptor.so"

if [ -f "src/faultcore/_faultcore.abi3.so" ]; then
    cp "src/faultcore/_faultcore.abi3.so" "$NATIVE_PLATFORM_DIR/_faultcore.abi3.so"
else
    echo "Warning: src/faultcore/_faultcore.abi3.so was not found."
fi

echo "=== Building faultcore Python package ==="
uv run python -m build

echo "=== Build complete ==="
echo "Python package: dist/"
echo "Native artifacts staged at: $NATIVE_PLATFORM_DIR"
