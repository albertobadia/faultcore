# policy_context

## Purpose

Context manager that temporarily sets thread policy for `fault("auto")` resolution.

## Behavior details

- Accepts either `policy_name` or inline policy kwargs, never both.
- Inline kwargs create a temporary auto-removed policy.
- Restores previous thread policy on exit.
- Supports sync and async context manager usage.

## Example

```python
import faultcore


faultcore.register_policy(name="degraded", latency="120ms", packet_loss="1%")

with faultcore.policy_context("degraded"):
    assert faultcore.get_thread_policy() == "degraded"
```
