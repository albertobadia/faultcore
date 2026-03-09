# faultcore

High-performance fault injection and network simulation for Python, backed by Rust.

## Overview

`faultcore` provides Python decorators and policy management for:
- execution deadlines (`timeout`);
- network timeouts (`connect_timeout`, `recv_timeout`);
- bandwidth throttling (`rate_limit`);
- latency, jitter, packet loss, and burst loss;
- `FaultOSI`: OSI-pragmatic L1..L7 fault pipeline in `faultcore_network`;
- transparent socket interception with `LD_PRELOAD` on Linux.

This README is an index. Detailed documentation lives in `docs/`.

## Quick Start

Requirements:
- Python 3.10+
- Rust toolchain
- Linux for `LD_PRELOAD` network interception

Build:

```bash
./build.sh
```

Minimal usage:

```python
import faultcore

@faultcore.timeout(timeout_ms=200)
def slow_operation():
    return "ok"

@faultcore.rate_limit(rate="10mbps")
def network_operation():
    return "ok"
```

## Documentation Index

| Document | Scope |
|---|---|
| [`docs/api_reference.md`](docs/api_reference.md) | Public Python API, signatures, accepted value formats, sync/async behavior |
| [`docs/policies_and_context.md`](docs/policies_and_context.md) | Policy registry, `fault()`, thread policy context, and policy file loading |
| [`docs/interceptor_and_shm.md`](docs/interceptor_and_shm.md) | Linux `LD_PRELOAD` flow, interceptor behavior, and SHM integration |
| [`docs/testing_and_examples.md`](docs/testing_and_examples.md) | Build/test workflow (`sh tests.sh`) and example execution guidance |
| [`docs/shm_protocol.md`](docs/shm_protocol.md) | Binary SHM contract between Python writer and Rust interceptor |

## Project Status

- Python package metadata: `pyproject.toml`
- Public API source of truth: `src/faultcore/__init__.py`
- Decorator behavior source of truth: `src/faultcore/decorator.py`
- Unit tests: `tests/unit/`
- Integration CLI scripts: `tests/integration/`

## License

MIT
