# dns

## Signature

```python
faultcore.dns(*, delay: str | None = None, timeout: str | None = None, nxdomain: str | None = None)
```

## Purpose

Injects resolver-side DNS behavior for tests that resolve hostnames.

## Parameters

- `delay`: duration string.
- `timeout`: duration string.
- `nxdomain`: probability string with `%` or `ppm`.

## Defaults and validation

- All fields are optional.
- Duration fields must use `ms`/`s`.

## Example (hostname resolution test)

```python
import faultcore


@faultcore.dns(delay="40ms", nxdomain="3%")
def resolve_service(host: str) -> str:
    return host


def test_dns_failure_fallback() -> None:
    primary = resolve_service("api.internal")
    assert primary == "api.internal"
```
