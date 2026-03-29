# packet_duplicate

## Signature

```python
faultcore.packet_duplicate(*, prob: str = "100%", max_extra: int = 1)
```

## Purpose

Duplicates packets to test idempotency and dedup logic.

## Defaults and validation

- `max_extra` must be `> 0`.
- `prob` uses `%` or `ppm`.

## Example (idempotent handler test)

```python
import faultcore


@faultcore.packet_duplicate(prob="15%", max_extra=2)
def send_command() -> list[str]:
    return ["cmd", "cmd"]


def test_duplicate_packets_do_not_break_idempotency() -> None:
    messages = send_command()
    assert len(messages) >= 1
```
