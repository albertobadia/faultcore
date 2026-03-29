# correlated_loss

## Signature

```python
faultcore.correlated_loss(*, p_good_to_bad: str, p_bad_to_good: str, loss_good: str, loss_bad: str)
```

## Purpose

Models loss with GOOD/BAD state transitions (clustered failures instead of purely random drops).

## Defaults and validation

- All probability fields use `%` or `ppm` parser.

## Example (stateful transport degradation)

```python
import faultcore


@faultcore.correlated_loss(p_good_to_bad="1%", p_bad_to_good="25%", loss_good="0.1%", loss_bad="15%")
def unstable_stream() -> list[bool]:
    return [True, True, False, False, True]


def test_retry_behavior_under_clustered_loss() -> None:
    sequence = unstable_stream()
    assert sequence.count(False) >= 1
```
