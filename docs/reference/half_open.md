# half_open

## Signature

```python
faultcore.half_open(*, after: str, error: str = "reset")
```

## Purpose

Forces failure after crossing a byte threshold (useful for partial transfer tests).

## Defaults and validation

- `after` is required, parsed as size, and must be `> 0`.
- `error` accepts `reset`, `refused`, `unreachable`.

## Example (TCP frame stream cut)

```python
import faultcore


@faultcore.half_open(after="32kb", error="reset")
def stream_frames() -> tuple[int, bool]:
    return 32 * 1024, True


def test_partial_transfer_recovery() -> None:
    transferred, cut = stream_frames()
    assert transferred >= 32 * 1024
    assert cut is True
```
