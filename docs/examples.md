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


def test_deterministic_latency_baseline() -> None:
    @faultcore.latency("50ms")
    def baseline() -> str:
        return "ok"

    assert baseline() == "ok"
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


def test_reusable_mobile_3g_profile_registration() -> None:
    faultcore.register_policy(name="mobile_3g", latency="150ms", jitter="40ms", packet_loss="1%", rate="2mbps")
    assert "mobile_3g" in faultcore.list_policies()
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


def test_http_client_profile_stack() -> None:
    @faultcore.timeout(connect="250ms", recv="800ms")
    @faultcore.packet_loss("1%")
    def call_http_api() -> dict[str, str]:
        return {"status": "ok"}

    assert call_http_api()["status"] == "ok"
```

## Example: TCP protocol client test

```python
import faultcore


def test_tcp_ordering_and_partial_transfer_profile() -> None:
    @faultcore.packet_reorder(prob="20%", max_delay="25ms", window=3)
    @faultcore.half_open(after="16kb", error="reset")
    def exchange_tcp_frames() -> str:
        return "ok"

    assert exchange_tcp_frames() == "ok"
```

## Example: UDP protocol client test

```python
import faultcore


def test_udp_loss_and_burst_profile() -> None:
    @faultcore.packet_loss("3%")
    @faultcore.burst_loss("4")
    def send_udp_datagrams() -> str:
        return "ok"

    assert send_udp_datagrams() == "ok"
```
