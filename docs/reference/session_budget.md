# session_budget

## Signature

```python
faultcore.session_budget(
    *,
    max_tx: str | None = None,
    max_rx: str | None = None,
    max_ops: int | None = None,
    max_duration: str | None = None,
    action: str = "drop",
    budget_timeout: str | None = None,
    error: str | None = None,
)
```

## Purpose

Enforces session-level limits and triggers a terminal action once exhausted.

## Defaults and validation

- At least one limit is required (`max_tx`, `max_rx`, `max_ops`, or `max_duration`).
- `max_ops` must be `> 0` when provided.
- `action` must be one of: `drop`, `timeout`, `connection_error`.
- For `action=timeout`, `budget_timeout` is required and must be `> 0`.

## Example (budget exhaustion test)

```python
import faultcore


@faultcore.session_budget(max_tx="1mb", action="timeout", budget_timeout="2s")
def stream_upload(bytes_out: int) -> int:
    return bytes_out


def test_session_budget_limit() -> None:
    consumed = stream_upload(1_200_000)
    assert consumed > 1_000_000
```
