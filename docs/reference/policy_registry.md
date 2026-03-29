# Policy Registry

## Public APIs

- `register_policy(...)`
- `list_policies()`
- `get_policy(name)`
- `unregister_policy(name)`
- `load_policies(path)`
- `set_thread_policy(name | None)`
- `get_thread_policy()`

## Validation details

- Policy `name` must be non-empty.
- `targets` must be a list when provided.
- `load_policies` accepts `.json`, `.yaml`, `.yml`.
- Loaded file must be a mapping keyed by policy name.

## Example

```python
import faultcore


faultcore.register_policy(name="mobile", latency="150ms", jitter="40ms", packet_loss="1%", rate="2mbps")
assert "mobile" in faultcore.list_policies()

faultcore.set_thread_policy("mobile")
assert faultcore.get_thread_policy() == "mobile"


def test_policy_registry_lifecycle() -> None:
    loaded = faultcore.get_policy("mobile")
    assert loaded is not None
    assert faultcore.unregister_policy("mobile") is True
```
