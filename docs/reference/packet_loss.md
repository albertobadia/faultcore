# packet_loss

## Signature

```python
faultcore.packet_loss(p: str)
```

## Purpose

Injects probabilistic packet drops.

## Parameters

- `p`: probability string with `%` or `ppm` suffix.

## Defaults and validation

- `%` values must be between `0` and `100`.
- `ppm` values must be between `0` and `1_000_000`.

## Example (UDP reliability test)

```python
import faultcore


@faultcore.packet_loss("2%")
def send_datagrams(total: int) -> int:
    delivered = int(total * 0.98)
    return delivered


def test_udp_client_retries_under_loss() -> None:
    delivered = send_datagrams(1000)
    assert delivered < 1000
```
