# Concepts

## Mental model

faultcore applies network faults at runtime to operations executed inside decorated functions.

Think in three layers:

1. **Decorator layer**: attach fault behavior to a function.
2. **Policy layer**: define reusable named profiles.
3. **Runtime layer**: execute process with interceptor to apply low-level effects.

## When to use decorators directly

Use direct decorators when:

- You need one-off behavior in a single test.
- You want fast local experimentation.

## When to use policies

Use policies when:

- You need consistency across many tests.
- You want scenario names like `mobile_3g` or `regional_outage`.
- You want dynamic switching via thread-local context.

## Fault family guide

- **Timing and QoS**: `timeout`, `latency`, `jitter`, `rate`
- **Loss and instability**: `packet_loss`, `burst_loss`, `correlated_loss`
- **Transport behavior**: `connection_error`, `half_open`, `packet_reorder`, `packet_duplicate`
- **Name resolution**: `dns`
- **Payload mutation**: `payload_mutation`

## Typical rollout strategy

1. Baseline with deterministic faults.
2. Add one stochastic dimension at a time.
3. Promote to policy profiles once stable.
4. Validate with reports and operational metrics.

