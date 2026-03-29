# jitter

## Signature

```python
faultcore.jitter(t: str)
```

## Purpose

Adds timing variability to network operations.

## Parameters

- `t`: jitter duration (`ms` or `s`).

## Defaults and validation

- Duration must be non-negative.

## Example (unstable link test)

```python
import faultcore
import time


@faultcore.latency("50ms")
@faultcore.jitter("15ms")
def call_dependency() -> str:
    return "ok"


def test_latency_variability_window() -> None:
    samples_ms = []
    for _ in range(3):
        start = time.perf_counter()
        _ = call_dependency()
        samples_ms.append((time.perf_counter() - start) * 1000)
    assert max(samples_ms) - min(samples_ms) >= 1
```
