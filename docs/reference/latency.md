# latency

## Signature

```python
faultcore.latency(t: str)
```

## Purpose

Adds fixed delay to network operations in the decorated execution.

## Parameters

- `t`: duration string (`ms` or `s`).

## Defaults and validation

- Duration must be non-negative.

## Example (API latency test)

```python
import faultcore
import time


@faultcore.latency("80ms")
def fetch_resource() -> str:
    return "ok"


def test_latency_injection() -> None:
    start = time.perf_counter()
    _ = fetch_resource()
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms >= 60
```
