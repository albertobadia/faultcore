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

# Run pytest with the interceptor (using python directly to ensure env vars are passed)
PYTEST="uv run --no-project python -m pytest"
$PYTEST --ignore=benchmarks/ --ignore=tests/integration/ --ignore=integration_tests/ --ignore=tests/test_network_timeout.py -v
