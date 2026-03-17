# Testing and Examples

This document covers build and test commands plus example execution.
For tuning guidance in longer operational runs, see `docs/operations_tuning.md`.

## Build

```bash
uv sync
./build.sh
```

This builds and stages platform-native artifacts in `src/faultcore/_native/<platform-tag>/`
before producing `dist/*.whl`.

`build.sh` enforces version alignment between:
- `pyproject.toml` (`project.version`)
- `faultcore_interceptor/Cargo.toml`
- `faultcore_network/Cargo.toml`

## Validation Path

```mermaid
flowchart LR
    L["sh lint.sh"] --> B["sh build.sh"]
    B --> T["sh tests.sh"]
    T --> O{"Need long-run confidence?"}
    O -->|Yes| TL["sh tests_long.sh"]
    O -->|No| Done["Done for fast gate"]
    TL --> Done2["Done for stress gate"]
```

Recommended execution order for fast and long validation paths.

## Primary Test Entry Point

Run:

```bash
sh tests.sh
```

`tests.sh` performs:
- Rust tests for `faultcore_interceptor`;
- Rust tests for `faultcore_network`;
- Python unit tests with interceptor preloaded;
- integration CLI scripts in `tests/integration/`.

On Linux, `tests.sh` is strict: if
`src/faultcore/_native/<platform-tag>/libfaultcore_interceptor.so` is missing,
it exits with error and asks to run `sh build.sh`.

Includes `record/replay` integration coverage via:

```bash
tests/integration/test_record_replay.py
```

## Long Stress Entry Point

Run:

```bash
sh tests_long.sh
```

`tests_long.sh` is a separate long-run stress path (not part of the regular fast gate in `tests.sh`).
It starts local servers and runs:

```bash
tests/integration/test_stress.py --mode long
```

Tune with environment variables:
- `STRESS_DURATION` (default `20`)
- `STRESS_WORKERS` (default `24`)
- `STRESS_MAX_ERROR_RATE` (default `0.02`)
- `STRESS_MAX_RSS_DELTA_KB` (default `131072`)

Reference run on **2026-03-11**:
- `stress integration: PASS`
- `baseline`: `206676 ops`, `avg_ms=2.36`
- `policy_latency`: `3420 ops`, `avg_ms=140.75`
- `rss_delta_kb=49936`

## Integration CLI Scripts

Current files in `tests/integration/` are CLI-oriented network probes (not pytest fixture-based tests).
They are invoked with explicit args from `tests.sh`, for example:

```bash
uv run python tests/integration/test_latency.py --host 127.0.0.1 --port 9000 --mode latency --count 3
uv run python tests/integration/test_timeout.py --host 127.0.0.1 --port 9000 --mode recv --timeout 500
uv run python tests/integration/test_bandwidth.py --host 127.0.0.1 --port 9000 --mode throughput --messages 20
```

## Running Examples

CLI-first:

```bash
faultcore run -- python examples/1_http_requests.py
```

Some examples expect local servers:
- TCP echo server: `uv run python tests/integration/servers/tcp_echo_server.py --host 127.0.0.1 --port 9000`
- UDP echo server: `uv run python tests/integration/servers/udp_echo_server.py --host 127.0.0.1 --port 9001`
- HTTP test server: `uv run python -m uvicorn tests.integration.servers.http_server:app --host 127.0.0.1 --port 8000`

Advanced/manual path (debugging only):

```bash
examples/run_with_preload.sh 1_http_requests.py
```

## Example Set

- `examples/1_http_requests.py`
- `examples/2_http_async.py`
- `examples/3_tcp_client.py`
- `examples/4_udp_client.py`
- `examples/5_rate_limit.py`
- `examples/6_multi_protocol.py`
- `examples/7_latency_jitter.py`
- `examples/8_bandwidth_throttle.py`
- `examples/9_network_timeout.py`
- `examples/10_target_priority.py`
- `examples/11_fault_metrics.py`
- `examples/12_perf_baseline.py`
- `examples/13_end_to_end_scenarios.py`

## Notes on Rate Semantics

`rate(rate=...)` configures bandwidth in bps (string units or numeric conversion), not request-per-second quotas.
Example output text may refer to "rate setting" or throughput effects.

## Lint Modes

`lint.sh` has two modes:
- `sh lint.sh` (or `sh lint.sh check`): verification only, runs `cargo clippy` then `ruff check` + `ruff format --check`.
- `sh lint.sh fix`: applies fixes with `cargo clippy`, `ruff check --fix` + `ruff format`.
