#!/bin/bash

set -e

echo "=== Building faultcore Python package ==="
uv run python -m build

echo "=== Building faultcore_interceptor ==="
cd faultcore_interceptor
cargo build --release
cd ..

echo "=== Build complete ==="
echo "Python package: dist/"
echo "Interceptor: faultcore_interceptor/target/release/libfaultcore_interceptor.so"
