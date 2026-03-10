# Operations and Tuning Guide

This guide focuses on practical tuning for stable long-running fault injection tests.

## Baseline Workflow

1. Measure baseline behavior without fault policies.
2. Enable one policy at a time.
3. Compare throughput, error rate, and latency deltas.

Recommended scripts:
- `examples/12_perf_baseline.py` for baseline vs policy throughput.
- `tests/integration/test_stress.py --mode smoke` for fast validation.
- `sh tests_long.sh` for long runs in a separate path.

## Policy Tuning

### Latency and Jitter

- Start with small values (`latency_ms=20..50`, `jitter_ms=2..10`).
- Increase gradually and track `p95/p99` response time impact.
- Use directional config when needed:
  - `uplink={...}` to affect client-to-server path.
  - `downlink={...}` to affect server-to-client path.

### Packet Reorder

- Begin with low probability (`packet_reorder=0.05`) and bounded window.
- Keep `reorder_window_packets` small first (`2..8`) to avoid queue pressure.
- Use `reorder_release_delay_ms` only when simulating delayed release behavior.

### Packet Duplicate and Loss

- Combine carefully:
  - `packet_duplicate` magnifies traffic volume.
  - `packet_loss` and `burst_loss_len` reduce delivery ratio.
- Validate expected side effects with protocol-specific tests (TCP vs UDP).

### DNS Faults

- `dns_delay` to simulate slow resolver behavior.
- `dns_timeout` to simulate timeout (`EAI_AGAIN` style behavior).
- `dns_nxdomain` to simulate name-not-found responses.
- Prefer isolated DNS scenarios first, then combine with transport-level faults.

### Target Rules

- Prefer explicit protocol + port when possible to reduce accidental matches.
- Use `priority` to define deterministic resolution when rules overlap.
- Keep rule sets focused; large broad CIDRs should have lower priority than exact host rules.

## Metrics and Scope

- Use `faultcore.get_fault_metrics()` for global counters.
- Use `faultcore.get_fault_metrics(scope="context")` inside `fault_context(...)` for local deltas.
- Reset global counters only between benchmark phases:
  - `faultcore.get_fault_metrics(reset=True)`

## Stress Run Profiles

- Smoke profile:
  - Short duration and low worker count.
  - Use in local iteration and pre-commit checks.
- Long profile:
  - `--mode long` with sustained concurrency.
  - Use `--max-rss-delta-kb <value>` to enforce a memory growth ceiling.
  - Use for memory stability and long-tail latency checks.
  - Current calibrated defaults: `STRESS_MAX_ERROR_RATE=0.02`, `STRESS_MAX_RSS_DELTA_KB=131072`.

## Operational Checklist

1. `sh lint.sh`
2. `sh build.sh`
3. `sh tests.sh`
4. Optional: run `sh tests_long.sh` and store results with timestamp.
