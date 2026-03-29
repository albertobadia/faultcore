# packet_reorder

## Signature

```python
faultcore.packet_reorder(*, prob: str = "100%", max_delay: str = "0ms", window: int = 1)
```

## Purpose

Reorders stream packets to test protocol ordering assumptions.

## Defaults and validation

- `window` must be `> 0`.
- `max_delay` is parsed as duration and converted to nanoseconds internally.

## Conceptual example (quick behavior sketch)

```python
import faultcore


@faultcore.packet_reorder(prob="20%", max_delay="30ms", window=4)
def exchange_messages() -> list[int]:
    return [1, 3, 2, 4]


def test_protocol_handles_out_of_order_frames() -> None:
    frames = exchange_messages()
    assert frames != sorted(frames)
```

## Integration example (real network path)

- Stream reordering integration scenario: [`tests/integration/test_reorder_downlink.py`](../../tests/integration/test_reorder_downlink.py)
- Practical run commands: [`docs/testing_and_examples.md`](../testing_and_examples.md)
