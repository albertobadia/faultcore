# Policy Application

## Typical flow

1. Register policy with `register_policy`.
2. Apply directly with `fault("name")` or indirectly with `fault("auto")` + `policy_context`.
3. Assert behavior in HTTP/TCP/UDP client tests.

## Minimal integration example

```python
import faultcore


faultcore.register_policy(name="client_degraded", timeout={"connect": "250ms", "recv": "900ms"}, packet_loss="1%")


@faultcore.fault("client_degraded")
def call_service() -> str:
    return "ok"


def test_http_client_policy_profile() -> None:
    assert call_service() == "ok"
```

## Common errors

- Using `fault("auto")` without setting thread policy.
- Defining policy names inconsistently across test suite.
