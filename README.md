# faultcore

A high-performance fault injection and resilience library for Python, built with Rust.

## Overview

`faultcore` provides decorators and policies for building resilient applications. It includes timeout handling, retry logic with backoff, circuit breakers, rate limiting, fallback strategies, and network simulation capabilities.

## Features

- **Timeout** - Enforce execution time limits
- **Retry** - Automatic retry with configurable backoff
- **Fallback** - Provide alternative responses on failure
- **Circuit Breaker** - Prevent cascading failures
- **Rate Limiting** - Token bucket rate limiting
- **Network Queue** - Simulate network conditions (latency, packet loss, bandwidth throttling)

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

# Timeout
@faultcore.timeout(timeout_ms=500)
def slow_operation():
    time.sleep(1)
    return "done"

# Retry with backoff
@faultcore.retry(max_retries=3, backoff_ms=100)
def unreliable_api():
    if random.random() < 0.5:
        raise ConnectionError("Network error")
    return "success"

# Fallback
@faultcore.fallback(lambda: {"data": "cached"})
def fetch_data():
    raise ConnectionError("API down")

# Circuit Breaker
@faultcore.circuit_breaker(failure_threshold=5, success_threshold=2, timeout_ms=30000)
def fragile_service():
    return "ok"

# Rate Limit
@faultcore.rate_limit(rate=10.0, capacity=100)
def api_call():
    return "rate limited"

# Network Queue (bandwidth throttling)
@faultcore.network_queue(rate="1mbps", capacity="10mb", latency_ms=50, packet_loss=0.01)
def download_file():
    return "data"
```

## API Reference

### Decorators

| Decorator | Description |
|-----------|-------------|
| `@timeout(timeout_ms)` | Enforce timeout in milliseconds |
| `@retry(max_retries, backoff_ms, retry_on)` | Retry on failure with exponential backoff |
| `@fallback(fallback_func)` | Execute fallback function on failure |
| `@circuit_breaker(failure_threshold, success_threshold, timeout_ms)` | Circuit breaker pattern |
| `@rate_limit(rate, capacity)` | Token bucket rate limiting |
| `@network_queue(rate, capacity, max_queue_size, packet_loss, latency_ms)` | Network simulation |

### Policy Classes

| Class | Description |
|-------|-------------|
| `Timeout` | Timeout policy |
| `Retry` | Retry policy with backoff |
| `Fallback` | Fallback execution |
| `CircuitBreaker` | Circuit breaker states: closed, open, half_open |
| `RateLimit` | Rate limiting with token bucket |
| `NetworkQueue` | Network simulation with throttling |

### Context Management

| Function | Description |
|----------|-------------|
| `add_keys(keys)` | Add context keys for multi-tenant limiting |
| `get_keys()` | Get current context keys |
| `remove_key(key)` | Remove a context key |
| `clear_keys()` | Clear all context keys |
| `classify_exception(exc)` | Classify exception type (Timeout, RateLimit, Network, Transient) |

## Network Queue

The `network_queue` decorator simulates network conditions:

```python
@faultcore.network_queue(
    rate="10mbps",      # Bandwidth limit (supports: bps, kbps, mbps, gbps)
    capacity="50mb",    # Bucket capacity
    max_queue_size=1000,
    latency_ms=50,      # Simulated latency
    packet_loss=0.01,   # 1% packet loss
)
def download():
    return "data"
```

### Error Classification

Exceptions are automatically classified:
- **Timeout** - Contains "timeout" in name
- **RateLimit** - Contains "rate" and "limit"/"throttle"
- **Network** - Contains "connection", "network", "remote", "disconnected", "protocol"
- **Transient** - Default for all other errors

## Examples

See the [`examples/`](examples/) directory for more detailed usage:

- [`01_timeout.py`](examples/01_timeout.py) - Timeout usage
- [`02_retry.py`](examples/02_retry.py) - Retry with backoff
- [`03_fallback.py`](examples/03_fallback.py) - Fallback strategies
- [`04_circuit_breaker.py`](examples/04_circuit_breaker.py) - Circuit breaker pattern
- [`05_rate_limit.py`](examples/05_rate_limit.py) - Rate limiting
- [`06_combined.py`](examples/06_combined.py) - Combining decorators
- [`07_context.py`](examples/07_context.py) - Context management
- [`08_bandwidth_throttle.py`](examples/08_bandwidth_throttle.py) - Bandwidth throttling
- [`09_network_timeout.py`](examples/09_network_timeout.py) - Network-level timeout (requires interceptor)

## Development

```bash
# Build
./build.sh

# Lint
./lint.sh

# Test
./tests.sh
```

## Architecture

- **Python decorators** - User-facing API
- **Rust core** - High-performance policy implementation using PyO3
- **Interceptor** - Optional process-level network interception (Linux only)

## Network Interceptor (Linux Only)

The interceptor provides transparent network-level fault injection. It works at the OS level by intercepting socket calls.

**Requirements:**
- Linux only
- Requires `LD_PRELOAD`

**Usage:**
```bash
# Build the interceptor
cargo build --package faultcore_interceptor --release

# Run with interceptor
LD_PRELOAD=target/release/libfaultcore_interceptor.so python your_script.py
```

The interceptor enables:
- Network timeouts (connect, recv)
- Latency injection
- Packet loss simulation
- Bandwidth throttling

When interceptor is not available, use `@faultcore.timeout` decorator instead.

## License

MIT
