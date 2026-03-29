# timeout

## Signature

```python
faultcore.timeout(*, connect: str | None = None, recv: str | None = None)
```

## Purpose

Sets connect and/or receive timeout behavior for operations executed inside the decorated function.

## Parameters

- `connect`: duration in `ms` or `s`.
- `recv`: duration in `ms` or `s`.

## Defaults and validation

- Both parameters are optional.
- Duration must be non-negative and use suffix (`ms` or `s`).

## Unit test example (pytest)

```python
import faultcore
import pytest


def test_http_client_timeout_path() -> None:
    @faultcore.timeout(connect="250ms", recv="900ms")
    def call() -> str:
        raise TimeoutError("simulated")

    with pytest.raises(TimeoutError):
        call()
```

## Integration example (real network path)

- Scripted integration check: [`tests/integration/test_timeout.py`](../../tests/integration/test_timeout.py)
- End-to-end run flow: [`docs/testing_and_examples.md`](../testing_and_examples.md)

## Common errors

- Missing unit suffix (`"250"` instead of `"250ms"`).
- Empty duration values.
