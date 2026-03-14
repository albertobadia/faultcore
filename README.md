# faultcore

High-performance fault injection and network simulation for Python, backed by Rust.

## Overview

`faultcore` provides Python decorators and policy management for:
- network timeouts (`connect_timeout`, `recv_timeout`);
- bandwidth throttling (`rate_limit`);
- latency, jitter, packet loss, and burst loss;
- `FaultOSI`: OSI-pragmatic L1..L7 fault pipeline in `faultcore_network`;
- transparent socket interception on Linux via `faultcore run`.

This README is an index. Detailed documentation lives in `docs/`.

## Quick Start

Requirements:
- Python 3.10+
- Rust toolchain
- Linux for network interception

Build:

```bash
./build.sh
```

CLI-first execution:

```bash
faultcore doctor
faultcore run -- python -c "import socket; print('ok')"
faultcore run --run-json artifacts/run.json -- pytest -q
faultcore report --input artifacts/run.json --output artifacts/report.html
```

Manual `LD_PRELOAD` execution remains supported for advanced/debug use.

Minimal usage:

```python
import faultcore

@faultcore.connect_timeout(timeout_ms=200)
def slow_operation():
    return "ok"

@faultcore.rate_limit(rate="10mbps")
def network_operation():
    return "ok"
```

## Documentation Index

| Document | Scope |
|---|---|
| [`docs/api_reference.md`](docs/api_reference.md) | Public Python API and a decorator-family map (Mermaid) for quick navigation |
| [`docs/architecture.md`](docs/architecture.md) | System architecture with module layout, runtime sequence, and FaultOSI decision diagrams |
| [`docs/policies_and_context.md`](docs/policies_and_context.md) | Policy lifecycle and timeout precedence flowcharts |
| [`docs/interceptor_and_shm.md`](docs/interceptor_and_shm.md) | CLI-first Linux runtime sequence (`faultcore run`) and SHM/interceptor details |
| [`docs/testing_and_examples.md`](docs/testing_and_examples.md) | Validation path diagram (`lint -> build -> tests.sh -> tests_long.sh`) and execution guidance |
| [`docs/shm_protocol.md`](docs/shm_protocol.md) | SHM region layout, consistency sequence, and compatibility update flow |
| [`docs/operations_tuning.md`](docs/operations_tuning.md) | Baseline/tuning/stress operational flowchart for long-running scenarios |
| [`docs/binary_compatibility.md`](docs/binary_compatibility.md) | Native artifact policy (platform tags + glibc/manylinux objective) |
| [`docs/release_local_checklist.md`](docs/release_local_checklist.md) | Reproducible local binary release checklist |

## Mermaid Conventions

- Use fenced code blocks with language tag `mermaid` for all diagrams.
- Keep titles short and keep each diagram focused on one question.
- Use `flowchart` for process/ownership, `sequenceDiagram` for runtime interaction, and `stateDiagram-v2` for decision states.
- Prefer complementary diagrams over duplicated prose.

## Project Status

- Python package metadata: `pyproject.toml`
- Public API source of truth: `src/faultcore/__init__.py`
- Decorator behavior source of truth: `src/faultcore/decorator.py`
- Unit tests: `tests/unit/`
- Integration CLI scripts: `tests/integration/`

## License

MIT
