# faultcore

A high-performance fault injection and network simulation library for Python, built with Rust.

## Overview

`faultcore` provides decorators and policies for building network-aware applications. It includes timeout handling, rate limiting, and advanced network simulation capabilities like latency injection, packet loss, and bandwidth throttling—all applied transparently via a high-performance Rust core and an optional network interceptor.

## Features

- **Timeout** - Enforce execution time limits (function-level) or network timeouts (socket-level).
- **Rate Limiting** - Bandwidth and request throttling using an optimized token bucket.
- **Network Chaos** - Inject latency and packet loss transparently at the socket level.
- **High Performance** - Core logic implemented in Rust for minimal overhead.
- **Transparent Interception** - Use `LD_PRELOAD` to apply network policies without changing your application code.

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

# Timeout (Function level)
@faultcore.timeout(timeout_ms=500)
def slow_operation():
    time.sleep(1)
    return "done"

# Bandwidth Rate Limit (Socket level via Interceptor)
# When the interceptor is loaded, this applies a real bandwidth cap
@faultcore.rate_limit(rate="10mbps", capacity=100)
def download_large_file():
    # Socket calls here will be throttled to 10Mbps if LD_PRELOAD is used
    return "data"

# Latency & Packet Loss
# Configure these via the Policy Registry for transparent injection
```

## API Reference

### Decorators

| Decorator | Description |
|-----------|-------------|
| `@timeout(timeout_ms)` | Enforce timing limits |
| `@rate_limit(rate, capacity)` | Token bucket for requests or bandwidth (supports "mbps", "gbps") |
| `@fault(policy_name)` | Apply a complex policy by name from the registry |

### Policy Classes

| Class | Description |
|-------|-------------|
| `TimeoutPolicy` | Enforces execution deadlines |
| `RateLimitPolicy` | Manages token-bucket based throttling |
| `PolicyRegistry` | Central management for complex multi-layer policies |

### Context Management

| Function | Description |
|----------|-------------|
| `add_keys(keys)` | Add context keys for scoped policies |
| `get_keys()` | Get current context keys |
| `remove_key(key)` | Remove a context key |
| `clear_keys()` | Clear all context keys |

## Architecture

- **Python Decorators**: High-level API for defining policies.
- **Shared Memory (SHM)**: High-speed bridge between Python and the network layer.
- **Faultcore Network (`ChaosEngine`)**: Unified Rust engine for applying network effects (QoS, Latency, Loss).
- **Network Interceptor**: Transparent `LD_PRELOAD` library that intercepts syscalls and delegates to the `ChaosEngine`.

## Network Interceptor (Linux Only)

The interceptor provides transparent network-level fault injection by intercepting socket calls (`send`, `recv`, `connect`, etc.).

**Usage:**
```bash
# Build the interceptor
cargo build --package faultcore_interceptor --release

# Run with interceptor
LD_PRELOAD=target/release/libfaultcore_interceptor.so FAULTCORE_ENABLED=1 python your_script.py
```

The interceptor enables:
- **Packet Loss**: Inject random packet drops.
- **Latency**: Add delays to network operations.
- **Bandwidth Throttling**: Real-time rate limiting for socket data using a centralized `ChaosEngine`.
- **Network Timeouts**: Precise per-socket deadlines for connection and reception.

## License

MIT
