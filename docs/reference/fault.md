# fault

## Signature

```python
faultcore.fault(policy_name: str = "auto")
```

## Purpose

Applies a registered policy by name. With `"auto"`, resolves the current thread policy.

## Defaults and validation

- If no resolved policy exists, wrapped function executes without injected profile.

## Example (named test profile)

```python
import faultcore


faultcore.register_policy(name="slow_api", latency="100ms", packet_loss="1%")


@faultcore.fault("slow_api")
def request_api() -> int:
    return 200


def test_named_policy_application() -> None:
    status = request_api()
    assert status == 200
```
