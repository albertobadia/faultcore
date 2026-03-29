# Examples

## Testing scenario map

| Test objective | Primary decorators | Suggested script |
|---|---|---|
| HTTP client resilience | `timeout`, `session_budget` | `examples/1_http_requests.py` and `examples/9_network_timeout.py` |
| Async HTTP client | `latency`, `jitter`, `packet_loss` | `examples/2_http_async.py` |
| TCP protocol client | `packet_reorder`, `packet_duplicate`, `half_open` | `examples/3_tcp_client.py` |
| UDP protocol client | `packet_loss`, `burst_loss`, `dns` | `examples/4_udp_client.py` |
| Throughput testing | `rate`, `latency`, `jitter` | `examples/8_bandwidth_throttle.py` |
| End-to-end test run | `fault`, policies, reporting | `examples/13_end_to_end_scenarios.py` |

## Pattern: deterministic baseline first

Start with fixed latency or timeout before adding randomness:

```python
import faultcore


@faultcore.latency("50ms")
def baseline() -> str:
    return "ok"
```

Then add jitter/loss in a second scenario to isolate the source of failures.

## Pattern: one fault family per test

Avoid mixing many fault types in a single test initially. Build confidence in layers:

1. Timeout-only behavior
2. Throughput-only behavior
3. Loss/reorder behavior
4. Combined scenario

## Pattern: reusable policy profiles

```python
import faultcore


faultcore.register_policy(name="mobile_3g", latency="150ms", jitter="40ms", packet_loss="1%", rate="2mbps")
```

Use `faultcore.fault("mobile_3g")` in multiple tests to maintain consistency.

## Pattern: explicit assertions

For each testing scenario, assert one primary behavior:

- timeout raised
- retry path executed
- fallback endpoint used
- total duration within expected budget

## Example: HTTP client test

```python
import faultcore


@faultcore.timeout(connect="250ms", recv="800ms")
@faultcore.packet_loss("1%")
def call_http_api() -> dict[str, str]:
    return {"status": "ok"}
```

## Example: TCP protocol client test

```python
import faultcore


@faultcore.packet_reorder(prob="20%", max_delay="25ms", window=3)
@faultcore.half_open(after="16kb", error="reset")
def exchange_tcp_frames() -> str:
    return "ok"
```

## Example: UDP protocol client test

```python
import faultcore


@faultcore.packet_loss("3%")
@faultcore.burst_loss("4")
def send_udp_datagrams() -> str:
    return "ok"
```
