#!/bin/bash

set -euo pipefail

INTERCEPTOR_BUILD_OUT="faultcore_interceptor/target/release/libfaultcore_interceptor.so"
NATIVE_ROOT="src/faultcore/_native"

platform_tag() {
    local system
    local machine
    system="$(uname -s)"
    machine="$(uname -m)"

    case "${system}:${machine}" in
    Linux:x86_64 | Linux:amd64)
        echo "linux-x86_64"
        ;;
    Linux:i686 | Linux:x86)
        echo "linux-i686"
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

echo "=== Building faultcore_interceptor (release) ==="
cargo build --release --manifest-path faultcore_interceptor/Cargo.toml

if [ ! -f "$INTERCEPTOR_BUILD_OUT" ]; then
    echo "Error: expected artifact not found: $INTERCEPTOR_BUILD_OUT"
    exit 1
fi

PLATFORM_TAG="$(platform_tag)"
NATIVE_PLATFORM_DIR="$NATIVE_ROOT/$PLATFORM_TAG"

echo "=== Staging native artifacts for $PLATFORM_TAG ==="
mkdir -p "$NATIVE_PLATFORM_DIR"
cp "$INTERCEPTOR_BUILD_OUT" "$NATIVE_PLATFORM_DIR/libfaultcore_interceptor.so"

echo "Native artifacts staged at: $NATIVE_PLATFORM_DIR"
