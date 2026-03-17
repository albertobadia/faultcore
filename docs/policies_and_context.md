# Policies and Context

This document focuses on policy registration, selection, and scoped application.

## Policy Model

A policy is a named set of optional fields:
- `latency` (duration string like "50ms")
- `jitter` (duration string like "10ms")
- `packet_loss` (percentage or ppm)
- `burst_loss` (string like "3")
- `rate` (bandwidth string like "10mbps")
- `timeout` (dict with `connect` and/or `recv` keys)
- `session_budget` (max tx/rx, operations, or duration limits with terminal action; action=timeout requires budget_timeout, action=connection_error accepts optional error)
- `targets` (list of target rules for selective fault application)
- `schedule` (temporal profile: ramp, spike, or flapping)
- `seed` (optional random seed for deterministic behavior)

Policies are stored in a process-local registry protected by a lock.

### Policy Lifecycle Sequence

```mermaid
sequenceDiagram
    participant User as User code
    participant Reg as Policy registry
    participant Ctx as Thread policy context
    participant Wrap as Decorator wrapper
    participant SHM as SHM writer

    User->>Reg: register_policy(name, fields)
    alt Explicit binding
        User->>Wrap: @apply_policy(name)
        Wrap->>Reg: resolve name
    else Auto binding
        User->>Ctx: with policy_context(name)
        User->>Wrap: @fault()
        Wrap->>Ctx: read current thread policy
        Wrap->>Reg: resolve policy by context
    end
    Wrap->>SHM: write selected fields
    Wrap->>SHM: clear on exit/finally
```

Diagram focus: registration, selection path, and cleanup behavior.

## Register and Inspect Policies

```python
import faultcore

faultcore.register_policy(
    "slow_link",
    latency="50ms",
    jitter="10ms",
    packet_loss="1%",
    burst_loss="3",
    rate="2mbps",
    timeout={"connect": "20ms", "recv": "20ms"},
)

print(faultcore.list_policies())      # ["slow_link"]
print(faultcore.get_policy("slow_link"))
```

Remove a policy:

```python
faultcore.unregister_policy("slow_link")
```

## Apply Policy Explicitly

```python
@faultcore.fault("slow_link")
def op():
    return "ok"
```

If the policy is missing when decoration runs, the wrapper still executes the function with no policy fields applied.

## Auto Policy with Thread Context

`fault()` defaults to `policy_name="auto"` and reads thread-local policy.

```python
import faultcore

faultcore.register_policy("inner", packet_loss="0.1%")

with faultcore.policy_context("inner"):
    @faultcore.fault()
    def op():
        return "ok"
    op()
```

The previous thread policy is restored on context exit.

## Inline Policy Context

`policy_context` allows inline policy definition without registering a named policy:

```python
import faultcore

with faultcore.policy_context(latency="50ms", jitter="10ms", packet_loss="1%"):
    @faultcore.fault()
    def op():
        return "ok"
    op()
```

This creates a temporary policy that is automatically unregistered on context exit.

## Load Policies from File

JSON and YAML are supported:

```python
count = faultcore.load_policies("policies.json")
print(count)
```

File format:

```json
{
  "policy_name": {
    "latency": "7ms",
    "jitter": "3ms",
    "packet_loss": "0.2%",
    "burst_loss": "2",
    "rate": "1mbps",
    "timeout": {"connect": "9ms", "recv": "9ms"},
    "targets": [
      {"target": "tcp://10.0.0.0/8:9000", "priority": 10},
      {"target": "tcp://127.0.0.1:9000", "priority": 100}
    ],
    "schedule": {"kind": "spike", "every": "30s", "duration": "5s"}
  }
}
```

Notes:
- YAML support requires `PyYAML`.
- Root value must be an object keyed by policy name.

## Timeout Notes

- Use the `timeout` parameter with a dict containing `connect` and/or `recv` keys.
- Example: `timeout={"connect": "200ms", "recv": "500ms"}`
- Missing timeout fields are omitted from the policy.

## Related

- API details: `docs/api_reference.md`
- Interceptor behavior and SHM: `docs/interceptor_and_shm.md`
