#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INTERCEPTOR_PATHS=(
    "$PROJECT_ROOT/faultcore_interceptor/target/release/libfaultcore_interceptor.so"
    "$PROJECT_ROOT/faultcore_interceptor/target/debug/libfaultcore_interceptor.so"
    "$PROJECT_ROOT/target/release/libfaultcore_interceptor.so"
    "$PROJECT_ROOT/target/debug/libfaultcore_interceptor.so"
    "./target/release/libfaultcore_interceptor.so"
    "./target/debug/libfaultcore_interceptor.so"
)

find_interceptor() {
    for path in "${INTERCEPTOR_PATHS[@]}"; do
        if [ -f "$path" ]; then
            echo "$path"
            return 0
        fi
    done
    return 1
}

INTERCEPTOR=$(find_interceptor)

if [ -z "$INTERCEPTOR" ]; then
    echo "Error: libfaultcore_interceptor.so not found."
    echo "Build it first with: cd $PROJECT_ROOT && ./build.sh"
    exit 1
fi

echo "Using interceptor: $INTERCEPTOR"
echo ""

if [ $# -eq 0 ]; then
    echo "Usage: $0 <example> [args...]"
    echo ""
    echo "Available examples:"
    echo "  01_http_requests.py   - HTTP with requests library"
    echo "  02_http_async.py      - Async HTTP with aiohttp"
    echo "  03_tcp_client.py     - TCP socket client"
    echo "  04_udp_client.py     - UDP socket client"
    echo "  05_rate_limit.py     - Rate limiting demo"
    echo "  06_multi_protocol.py - Multiple protocols combined"
    echo "  08_bandwidth_throttle.py - Bandwidth throttling"
    echo "  09_network_timeout.py   - Network latency injection"
    echo "  10_target_priority.py   - Target precedence behavior"
    echo "  11_fault_metrics.py     - Policy application example"
    echo "  12_perf_baseline.py     - Baseline vs policy throughput"
    echo "  13_end_to_end_scenarios.py - TCP/UDP/HTTP/DNS scenarios"
    echo ""
    echo "Examples that need a server running:"
    echo "  03_tcp_client.py     - requires TCP echo server on port 9000"
    echo "  04_udp_client.py     - requires UDP echo server on port 9001"
    echo "  13_end_to_end_scenarios.py - TCP 9000, UDP 9001, HTTP 8000"
    echo ""
    echo "Example: $0 01_http_requests.py"
    exit 1
fi

EXAMPLE="$1"
shift

if [ ! -f "$SCRIPT_DIR/$EXAMPLE" ]; then
    echo "Error: Example not found: $EXAMPLE"
    exit 1
fi

export LD_PRELOAD="$INTERCEPTOR"
export FAULTCORE_WRAPPER_MODE="shm"

echo "Running: uv run python $EXAMPLE $@"
echo "LD_PRELOAD=$LD_PRELOAD"
echo "----------------------------------------"
cd "$PROJECT_ROOT" && uv run python "$SCRIPT_DIR/$EXAMPLE" "$@"
