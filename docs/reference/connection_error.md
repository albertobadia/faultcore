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

## Conceptual example (quick behavior sketch)

```python
import faultcore


@faultcore.connection_error(kind="refused", prob="40%")
def open_connection() -> None:
    raise ConnectionRefusedError("simulated")


def test_client_handles_refused_connection() -> None:
    try:
        open_connection()
        assert False, "expected connection failure"
    except ConnectionRefusedError:
        assert True
```

## Integration example (real network path)

- Transport integration coverage: [`tests/integration/test_targets_hostname_transport.py`](../../tests/integration/test_targets_hostname_transport.py)
- End-to-end execution guidance: [`docs/testing_and_examples.md`](../testing_and_examples.md)
