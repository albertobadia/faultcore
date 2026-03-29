# rate

## Signature

```python
faultcore.rate(r: str)
```

## Purpose

Applies bandwidth throttling to traffic in the decorated execution.

## Parameters

- `r`: bandwidth string with suffix `bps`, `kbps`, `mbps`, or `gbps`.

## Defaults and validation

- Unit suffix is required.
- Value must be non-negative.

## Example (throughput test)

```python
import faultcore


@faultcore.rate("2mbps")
def upload_payload() -> int:
    return 2_000_000


def test_bandwidth_cap_applies() -> None:
    measured_bps = upload_payload()
    assert measured_bps <= 2_000_000
```

## Common errors

- Missing suffix (`"2000"` instead of `"2000bps"`).
