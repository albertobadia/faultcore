# connection_error

## Signature

```python
faultcore.connection_error(*, kind: str, prob: str = "100%")
```

## Purpose

Injects explicit transport connection errors.

## Defaults and validation

- `kind` must be one of `reset`, `refused`, `unreachable`.
- `prob` uses packet loss parser (`%` or `ppm`).

## Unit test example (pytest)

```python
import faultcore
import pytest


def test_client_handles_refused_connection() -> None:
    @faultcore.connection_error(kind="refused", prob="40%")
    def connect() -> None:
        raise ConnectionRefusedError("simulated")

    with pytest.raises(ConnectionRefusedError):
        connect()
```

## Integration example (real network path)

- Transport integration coverage: [`tests/integration/test_targets_hostname_transport.py`](../../tests/integration/test_targets_hostname_transport.py)
- End-to-end execution guidance: [`docs/testing_and_examples.md`](../testing_and_examples.md)
