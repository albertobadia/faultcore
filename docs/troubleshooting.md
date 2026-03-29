# Troubleshooting

## Build issues

If docs build fails, run:

```bash
uv run sphinx-build -M html docs docs/_build
```

Check for:

- Missing pages referenced by `toctree`
- Broken relative links
- Invalid Mermaid blocks

## Runtime issues in fault injection

- Confirm Linux for interceptor-level effects.
- Validate with `uv run faultcore doctor`.
- Use `faultcore run` strict mode first.

## Symptom-based troubleshooting

| Symptom | Likely cause | Recommended action |
|---|---|---|
| Decorator has no visible runtime effect | Interceptor not active for process | Run with `uv run faultcore run -- ...` and confirm strict probe passes |
| Tests became flaky after enabling many faults | Multiple stochastic decorators combined | Isolate one fault family first, then combine gradually |
| Expected timeout not observed | Timeout values too high vs operation duration | Lower timeout values and assert elapsed time bounds |
| DNS faults not triggering | Scenario does not perform DNS lookup path | Validate target performs hostname resolution |
| Packet reordering has no effect | Protocol/test path not sensitive to ordering | Use stream cases with order-dependent message framing |

## Documentation quality gate before merge

- Dedicated page exists for each public decorator.
- Each page has at least one minimal executable example.
- Each feature page links related APIs.
- Sphinx build is green without warnings.

## Documentation quality checklist

- Each feature has a dedicated page.
- Each page includes signature, parameters, and example.
- Examples are short, copy-paste friendly, and executable.
- Pages link related features for discoverability.
