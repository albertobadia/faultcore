# uplink

## Signature

```python
faultcore.uplink(*, latency: str | None = None, jitter: str | None = None, packet_loss: str | None = None, burst_loss: str | None = None, rate: str | None = None)
```

## Purpose

Applies directional profile controls only to uplink traffic (client -> service).

## Defaults and validation

- All fields are optional.
- Duration/rate/loss fields follow the same validation as their standalone decorators.

## Example (TCP client upload path)

```python
import faultcore


@faultcore.uplink(latency="60ms", rate="4mbps", packet_loss="1%")
def send_frames(payload: bytes) -> int:
    return len(payload)


def test_uplink_profile_applies_to_client_send() -> None:
    sent = send_frames(b"frame")
    assert sent == 5
```
