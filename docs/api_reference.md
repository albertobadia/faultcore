# API Reference

This document describes the public Python API exported by `faultcore`.

Source of truth:
- `src/faultcore/__init__.py`
- `src/faultcore/decorator.py`

## Decorators

### `timeout(timeout_ms: int)`

Apply an execution deadline to sync and async callables.

- `timeout_ms` must be `>= 0`.
- For sync functions:
  - in main thread, uses `signal.setitimer` when available;
  - otherwise checks elapsed wall time after execution.
- For async functions:
  - wraps with `asyncio.wait_for`.

Raises `TimeoutError` when deadline is exceeded.

### `connect_timeout(timeout_ms: int)`

Set socket connect timeout in shared policy state.

- `timeout_ms` must be `>= 0`.
- Writes `(connect_ms, recv_ms) = (timeout_ms, 0)`.

### `recv_timeout(timeout_ms: int)`

Set socket receive timeout in shared policy state.

- `timeout_ms` must be `>= 0`.
- Writes `(connect_ms, recv_ms) = (0, timeout_ms)`.

### `latency(latency_ms: int)`

Set fixed latency in milliseconds.

- `latency_ms` must be `>= 0`.

### `jitter(jitter_ms: int)`

Set jitter in milliseconds.

- `jitter_ms` must be `>= 0`.

### `packet_loss(loss: str | int | float)`

Set packet loss as parts-per-million (PPM) internally.

Accepted formats:
- Ratio (`0.0` to `1.0`), for example `0.25` -> `250000 ppm`.
- Percentage (`0` to `100`) as number or string, for example `25` or `"25%"`.
- PPM string, for example `"250000ppm"`.

### `burst_loss(length: int)`

Set burst packet loss length.

- `length` must be `>= 0`.

### `uplink(...)`

Apply directional network profile for send path (`send`/`sendto`).

Accepted keyword fields:
- `latency_ms`
- `jitter_ms`
- `packet_loss` (same formats as `packet_loss(...)`)
- `burst_loss_len`
- `rate` (same formats as `rate_limit(...)`)

Requires at least one field.

### `downlink(...)`

Apply directional network profile for receive path (`recv`/`recvfrom`).

Accepted keyword fields are the same as `uplink(...)`.
Requires at least one field.

### `correlated_loss(...)`

Apply correlated packet loss using a two-state model (`GOOD`/`BAD`).

Required keyword fields:
- `p_good_to_bad`
- `p_bad_to_good`
- `loss_good`
- `loss_bad`

All values accept the same formats as `packet_loss(...)`.

### `connection_error(...)`

Inject explicit socket errors.

Required keyword fields:
- `kind`: one of `"reset"`, `"refused"`, `"unreachable"`

Optional:
- `prob`: probability of injection (same formats as `packet_loss(...)`, default `"100%"`)

### `half_open(...)`

Force stream failure after a byte threshold.

Required keyword fields:
- `after_bytes`: must be `> 0`

Optional:
- `error`: one of `"reset"`, `"refused"`, `"unreachable"` (default `"reset"`)

### `packet_duplicate(...)`

Inject duplicated sends.

Optional keyword fields:
- `prob`: duplicate probability (same formats as `packet_loss(...)`, default `"100%"`)
- `max_extra`: max extra copies per successful send, must be `> 0` (default `1`)

### `packet_reorder(...)`

Inject packet reordering (MVP on `sendto` path).

Optional keyword fields:
- `prob`: reorder probability (same formats as `packet_loss(...)`, default `"100%"`)

### `rate_limit(rate: str | int)`

Set bandwidth in bits per second (bps) internally.

Accepted formats:
- Number: interpreted as megabits per second (`Mbps`) and converted to bps.
- String suffixes:
  - `"bps"`
  - `"kbps"`
  - `"mbps"`
  - `"gbps"`
- Plain numeric string is interpreted as bps.

Examples:
- `rate_limit(10)` -> `10_000_000 bps`
- `rate_limit("10mbps")` -> `10_000_000 bps`
- `rate_limit("500kbps")` -> `500_000 bps`

### `apply_policy(policy_name: str)`

Apply a named registered policy to a function.

If the policy does not exist at decoration time, the wrapped function runs without policy fields.

### `fault(policy_name: str = "auto")`

Apply policy by name.

- If `policy_name != "auto"`, uses that policy name directly.
- If `"auto"`, reads current thread policy via `get_thread_policy()`.

## Policy Registry API

### `register_policy(...)`

Register or replace a named policy.

Signature:

```python
register_policy(
    name: str,
    *,
    latency_ms: int | None = None,
    jitter_ms: int | None = None,
    packet_loss: str | int | float | None = None,
    burst_loss_len: int | None = None,
    rate: str | int | float | None = None,
    timeout_ms: int | None = None,
    connect_timeout_ms: int | None = None,
    recv_timeout_ms: int | None = None,
    uplink: dict[str, Any] | None = None,
    downlink: dict[str, Any] | None = None,
    correlated_loss: dict[str, Any] | None = None,
    connection_error: dict[str, Any] | None = None,
    half_open: dict[str, Any] | None = None,
    packet_duplicate: dict[str, Any] | None = None,
    packet_reorder: dict[str, Any] | None = None,
) -> None
```

Notes:
- `name` must be non-empty.
- `timeout_ms` sets both connect/recv.
- `connect_timeout_ms`/`recv_timeout_ms` override split timeouts when provided.

### `list_policies() -> list[str]`

Return sorted policy names.

### `get_policy(name: str) -> dict[str, Any] | None`

Return a shallow copy of policy values, or `None` if missing.

### `unregister_policy(name: str) -> bool`

Remove a policy by name. Returns `True` if removed.

### `load_policies(path: str | Path) -> int`

Load policy map from `.json`, `.yaml`, or `.yml`.

- Returns number of loaded policies.
- YAML requires `PyYAML`.

## Context and Utilities

### `fault_context(policy_name: str | None = None)`

Context manager and async context manager to set thread-local policy temporarily.

### `set_thread_policy(policy_name: str | None)`

Set current thread policy name.

### `get_thread_policy() -> str | None`

Get current thread policy name.

### `is_interceptor_loaded() -> bool`

Best-effort check for active interceptor:
- tries symbol lookup via `ctypes.CDLL(None)`;
- falls back to checking `LD_PRELOAD`.

### `get_interceptor_path() -> str | None`

Search common build paths for `libfaultcore_interceptor.so`.

## Sync/Async SHM Lifecycle

- Decorators write fields keyed by native thread id.
- SHM state is cleared in `finally` blocks for:
  - successful execution;
  - raised exceptions;
  - timeout paths.

This behavior is tested in `tests/unit/decorators/test_decorator.py`.
