# faultcore

High-performance fault injection and network simulation for Python, backed by Rust.

## Overview

`faultcore` provides Python decorators and policy management for:
- network timeouts (`timeout`);
- bandwidth throttling (`rate`);
- latency, jitter, packet loss, and burst loss;
- `FaultOSI`: OSI-pragmatic L1..L7 fault pipeline in `faultcore_network`;
- transparent socket interception on Linux via `faultcore run`.

Detailed documentation lives in `docs/`.

## Quick Start

Requirements:
- Python 3.10+
- Rust toolchain
- Linux for network interception

Install development dependencies and build native artifacts:

```bash
uv sync --group dev
./build.sh
```

`build.sh` expects `.venv/bin/python` to exist, validates version alignment across
`pyproject.toml`, `faultcore_interceptor/Cargo.toml`, and `faultcore_network/Cargo.toml`,
then stages Linux interceptor artifacts into `src/faultcore/_native/<platform-tag>/` before building wheels.

Fast validation path:

```bash
sh lint.sh
sh build.sh
sh tests.sh
```

Long stress path (optional):

```bash
sh tests_long.sh
```

CLI-first execution:

```bash
uv run faultcore doctor
uv run faultcore run -- python -c "import socket; print('ok')"
uv run faultcore run --run-json artifacts/run.json -- pytest -q
uv run faultcore report --input artifacts/run.json --output artifacts/report.html
uv run faultcore report --input artifacts/run.json --output artifacts/report.latest.html --max-events 200 --reverse-events
```

Notes:
- `faultcore run` defaults to strict mode on Linux and exits with code `2` when interceptor probing fails.
- Use `--no-strict` only for debugging environments where preload activation is intentionally unavailable.
- With `--run-json`, CLI enables record/replay capture mode automatically when mode is unset/off and writes `<run-json>.rr.jsonl.gz` when `FAULTCORE_RECORD_REPLAY_PATH` is unset.
- `faultcore report` supports optional event rendering controls: `--max-events` and `--reverse-events`.

Manual `LD_PRELOAD` execution is still available for advanced debugging.

Platform behavior:
- Linux: `faultcore run` configures `LD_PRELOAD` automatically and probes interceptor activation in strict mode.
- Non-Linux: decorators and policy APIs are still callable, but interceptor-level network effects are not active.

Minimal usage:

```python
import faultcore

@faultcore.timeout(connect="200ms")
def slow_operation():
    return "ok"

@faultcore.rate("10mbps")
def network_operation():
    return "ok"
```

## Documentation Index

| Document | Scope |
|---|---|
| [`docs/api_reference.md`](docs/api_reference.md) | Public Python API and decorator families |
| [`docs/architecture.md`](docs/architecture.md) | System architecture with module layout and FaultOSI |
| [`docs/policies_and_context.md`](docs/policies_and_context.md) | Policy lifecycle and application patterns |
| [`docs/interceptor_and_shm.md`](docs/interceptor_and_shm.md) | CLI runtime and SHM/interceptor details |
| [`docs/testing_and_examples.md`](docs/testing_and_examples.md) | Build, test commands and examples |
| [`docs/shm_protocol.md`](docs/shm_protocol.md) | SHM binary layout and consistency protocol |
| [`docs/operations_tuning.md`](docs/operations_tuning.md) | Baseline/tuning/stress operational guidance |

## Project Status

- Python package metadata: `pyproject.toml`
- Public API source of truth: `src/faultcore/__init__.py`
- Decorator behavior source of truth: `src/faultcore/decorator.py`
- Unit tests: `tests/unit/`
- Integration CLI scripts: `tests/integration/`

## License

MIT
