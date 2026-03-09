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

Inject packet reordering on stream paths.

Current support matrix:
- `send`: supported (staging + window/flush behavior)
- `sendto`: supported (staging + window/flush behavior)
- `recv`: supported (blocking: stage-first then return next chunk; non-blocking: staging/replay with `EAGAIN`)
- `recvfrom`: supported (blocking: stage-first then return next datagram; non-blocking: staging/replay with `EAGAIN`)

Optional keyword fields:
- `prob`: reorder probability (same formats as `packet_loss(...)`, default `"100%"`)
- `max_delay_ms`: max staging delay before forced flush, must be `>= 0` (default `0`)
- `window`: max queued staged datagrams per socket, must be `> 0` (default `1`)

### `for_target(...)`

Apply faults only when destination matches a target filter.

Accepted forms:
- `for_target("tcp://10.1.2.3:443")`
- `for_target("10.1.2.3:443")`
- `for_target("10.0.0.0/8", protocol="udp", port=53)`
- `for_target(host="10.1.2.3", port=443, protocol="tcp")`
- `for_target(cidr="10.0.0.0/8", port=53)`

Current scope:
- IPv4 targets only.
- Protocol can be `tcp` or `udp`.

### `profile(...)`

Apply a temporal profile (`ramp`, `spike`, `flapping`) and optional fault values.

Examples:
- `profile("spike", every_s=30, duration_s=5, latency_ms=400)`
- `profile("flapping", on_s=2, off_s=3, packet_loss="2%")`
- `profile("ramp", ramp_s=60, latency_ms=200, packet_loss="1%")`

### `dns_delay(delay_ms: int)`

Inject DNS lookup delay (for `getaddrinfo`).
- `delay_ms` must be `>= 0`.

### `dns_timeout(timeout_ms: int)`

Inject DNS lookup timeout behavior (`EAI_AGAIN`) after waiting.
- `timeout_ms` must be `>= 0`.

### `dns_nxdomain(prob: str | int | float = "100%")`

Inject NXDOMAIN-style DNS failures (`EAI_NONAME`) with probability.

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
    dns_delay_ms: int | None = None,
    dns_timeout_ms: int | None = None,
    dns_nxdomain: str | int | float | None = None,
    target: str | dict[str, Any] | None = None,
    targets: list[str | dict[str, Any]] | None = None,
    schedule: dict[str, Any] | None = None,
) -> None
```

Notes:
- `name` must be non-empty.
- `timeout_ms` sets both connect/recv.
- `connect_timeout_ms`/`recv_timeout_ms` override split timeouts when provided.
- `packet_reorder` accepts `prob`, `max_delay_ms`, and `window`.
- `target` accepts:
  - string format: `"tcp://10.1.2.3:443"`, `"10.1.2.3:443"`, `"10.0.0.0/8"`;
  - mapping format with keys: `target`, `host`, `cidr`, `port`, `protocol`.
- `targets` accepts a non-empty list of target rules (string or mapping):
  - mapping supports: `target`, `host`, `cidr`, `port`, `protocol`, `priority`.
  - precedence: higher `priority` wins; same `priority` keeps registration order.
- `target` and `targets` are mutually exclusive.
- `schedule` mapping accepts:
  - `{"kind": "spike", "every_s": ..., "duration_s": ...}`
  - `{"kind": "flapping", "on_s": ..., "off_s": ...}`
  - `{"kind": "ramp", "ramp_s": ...}`

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

## Runtime Network Engine (Rust)

The network runtime now uses a single context-driven architecture:

- `PacketContext`: `fd`, `bytes`, `operation`, `direction`, `config`.
- `Operation`: `Connect`, `Send`, `Recv`, `DnsLookup`.
- `Direction`: `Uplink`, `Downlink`.
- `LayerDecision` (single decision contract):
  - `Continue`
  - `DelayNs(u64)`
  - `Drop`
  - `TimeoutMs(u64)`
  - `Error(String)`
  - `ConnectionErrorKind(u64)`
  - `StageReorder`
  - `Duplicate(u64)`
  - `NxDomain`

Pipeline:

- Fixed order `L1 -> L2 -> L3 -> L4 -> L5 -> L6 -> L7`.
- Each layer decides via `applies_to(context)` and `process(context)`.
- The interceptor only translates `LayerDecision` into syscall/errno behavior.

No backward compatibility layer:

- Previous type-specific internal engine APIs (`ConnectAction`, `StreamAction`, `DnsAction`) are no longer the active contract.
- SHM state is cleared in `finally` blocks for:
  - successful execution;
  - raised exceptions;
  - timeout paths.

This behavior is tested in `tests/unit/decorators/test_decorator.py`.
