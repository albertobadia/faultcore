# downlink

## Signature

```python
faultcore.downlink(*, latency: str | None = None, jitter: str | None = None, packet_loss: str | None = None, burst_loss: str | None = None, rate: str | None = None)
```

## Purpose

Applies directional profile controls only to downlink traffic (service -> client).

## Example (HTTP response path)

```python
import faultcore


@faultcore.downlink(latency="120ms", jitter="20ms")
def read_responses() -> int:
    return 200


def test_downlink_profile_applies_to_response_path() -> None:
    status = read_responses()
    assert status == 200
```
