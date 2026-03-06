# faultcore

A high-performance fault injection and network simulation library for Python, built with Rust.

## Overview

`faultcore` provides decorators and policies for building network-aware applications. It includes timeout handling, rate limiting, and advanced network simulation capabilities like latency injection, packet loss, and bandwidth throttling.

## Features

- **Timeout** - Enforce execution time limits
- **Rate Limiting** - Token bucket rate limiting for bandwidth or request control
- **Network Queue** - Simulate complex network conditions (latency, packet loss, bandwidth throttling)
- **High Performance** - Core logic implemented in Rust for minimal overhead

## Installation

```bash
# Build the Rust extension
./build.sh

# Or manually:
uv run maturin develop --release
```

Requirements:
- Python 3.10+
- Rust toolchain

## Quick Start

```python
import faultcore
import time

# Timeout
@faultcore.timeout(timeout_ms=500)
def slow_operation():
    time.sleep(1)
    return "done"

# Rate Limit
@faultcore.rate_limit(rate=10.0, capacity=100)
def api_call():
    return "ok"

# Network Queue (bandwidth throttling and latency)
@faultcore.network_queue(rate="1mbps", capacity="10mb", latency_ms=50, packet_loss=0.01)
def download_file():
    # Socket calls here will be intercepted if LD_PRELOAD is used
    return "data"
```

## API Reference

### Decorators

| Decorator | Description |
|-----------|-------------|
| `@timeout(timeout_ms)` | Enforce timeout in milliseconds |
| `@rate_limit(rate, capacity)` | Token bucket rate limiting |
| `@network_queue(rate, capacity, max_queue_size, packet_loss, latency_ms, strategy, fd_limit)` | Network simulation and queuing |

### Policy Classes

| Class | Description |
|-------|-------------|
| `TimeoutPolicy` | Timeout policy implementation |
| `RateLimitPolicy` | Rate limiting with token bucket |
| `NetworkQueuePolicy` | Network simulation and bandwidth control |

### Context Management

| Function | Description |
|----------|-------------|
| `add_keys(keys)` | Add context keys for multi-tenant limiting |
| `get_keys()` | Get current context keys |
| `remove_key(key)` | Remove a context key |
| `clear_keys()` | Clear all context keys |

## Network Queue

The `network_queue` decorator simulates network conditions:

```python
@faultcore.network_queue(
    rate="10mbps",      # Bandwidth limit (supports: bps, kbps, mbps, gbps)
    capacity="50mb",    # Bucket capacity
    max_queue_size=1000,
    latency_ms=50,      # Simulated latency
    packet_loss=0.01,   # 1% packet loss
    strategy="wait",    # "wait" to queue or "reject" to fail immediately
)
def download():
    return "data"
```

## Examples

See the [`examples/`](examples/) directory for usage:

- [`01_timeout.py`](examples/01_timeout.py) - Timeout usage
- [`05_rate_limit.py`](examples/05_rate_limit.py) - Rate limiting
- [`07_context.py`](examples/07_context.py) - Context management
- [`08_bandwidth_throttle.py`](examples/08_bandwidth_throttle.py) - Bandwidth throttling
- [`09_network_timeout.py`](examples/09_network_timeout.py) - Network-level timeout (requires interceptor)

## Architecture

- **Python decorators** - User-facing API for function-level control
- **Rust core** - High-performance policy implementation using PyO3
- **Interceptor** - Process-level network interception (Linux only) for platform-agnostic fault injection

## Network Interceptor (Linux Only)

The interceptor provides transparent network-level fault injection by intercepting socket calls.

**Usage:**
```bash
# Build the interceptor
cargo build --package faultcore_interceptor --release

# Run with interceptor
LD_PRELOAD=target/release/libfaultcore_interceptor.so python your_script.py
```

The interceptor enables:
- Network timeouts (connect, recv, send)
- Latency injection at the socket level
- Packet loss simulation
- Bandwidth throttling

## License

MIT
