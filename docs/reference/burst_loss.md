# burst_loss

## Signature

```python
faultcore.burst_loss(n: str)
```

## Purpose

Drops consecutive packets in bursts.

## Parameters

- `n`: burst length as integer string.

## Defaults and validation

- Must parse as integer.
- Must be `>= 0`.

## Example (bursty network test)

```python
import faultcore


@faultcore.packet_loss("1%")
@faultcore.burst_loss("4")
def run_bursty_path() -> list[int]:
    return [1, 1, 0, 0, 0, 0, 1]


def test_burst_drop_pattern_detected() -> None:
    stream = run_bursty_path()
    assert stream.count(0) >= 4
```
