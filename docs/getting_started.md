# Getting Started

This tutorial gets you from zero to a working fault-injection scenario.

## 1) Prerequisites

- Python 3.10+
- Rust toolchain
- Linux for interceptor-level network effects

## 2) Install and build

If you want to install the published package directly:

```bash
pip install faultcore
```

PyPI: https://pypi.org/project/faultcore/

If you are developing faultcore from source:

```bash
uv sync --group dev
./build.sh
```

## 3) Validate runtime health

```bash
uv run faultcore doctor
```

## 4) Run your process with interceptor enabled

```bash
uv run faultcore run -- python -c "import socket; print('faultcore ready')"
```

## 5) Apply your first decorator

```python
import faultcore


@faultcore.timeout(connect="250ms", recv="750ms")
def call_service() -> str:
    return "ok"
```

## 6) Move to reusable policies

```python
import faultcore


faultcore.register_policy(name="slow_and_lossy", latency="120ms", packet_loss="1%")


@faultcore.fault("slow_and_lossy")
def request_api() -> str:
    return "ok"
```

## 7) Generate a run report

```bash
uv run faultcore run --run-json artifacts/run.json -- pytest -q
uv run faultcore report --input artifacts/run.json --output artifacts/report.html
```

## Next steps

- Conceptual model: [concepts.md](concepts.md)
- Full decorator menu: [index.md](index.md)
- Examples by objective: [examples.md](examples.md)
