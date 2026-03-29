# CLI Usage

This page documents the recommended command-line workflow.

## Command overview

- `faultcore doctor`: validates runtime health and interceptor probing.
- `faultcore run`: executes a command with runtime setup for fault injection.
- `faultcore report`: renders an HTML report from a run artifact.

## Quick start

```bash
uv run faultcore doctor
uv run faultcore run -- python -c "print('faultcore ready')"
uv run faultcore run --run-json artifacts/run.json -- pytest -q
uv run faultcore report --input artifacts/run.json --output artifacts/report.html
```

## `faultcore doctor`

```bash
uv run faultcore doctor
```

- On Linux, exit code `0` means interceptor probing succeeded.
- Use this command first when diagnosing runtime setup issues.

## `faultcore run`

```bash
uv run faultcore run -- <command ...>
```

Common patterns:

```bash
uv run faultcore run -- python examples/1_http_requests.py
uv run faultcore run --run-json artifacts/run.json -- pytest -q
uv run faultcore run --no-strict -- python your_script.py
```

Behavior notes:

- Linux default is strict probing mode.
- `--no-strict` is intended for preload/debug scenarios.
- With `--run-json`, metadata is written for report generation.

## `faultcore report`

```bash
uv run faultcore report --input artifacts/run.json --output artifacts/report.html
```

Optional event controls:

```bash
uv run faultcore report --input artifacts/run.json --output artifacts/report.latest.html --max-events 200 --reverse-events
```

## CI-friendly flow

```bash
sh lint.sh
sh build.sh
uv run faultcore run --run-json artifacts/run.json -- pytest -q
uv run faultcore report --input artifacts/run.json --output artifacts/report.html
```

## Related

- Testing and examples: [testing_and_examples.md](testing_and_examples.md)
- Interceptor and SHM details: [interceptor_and_shm.md](interceptor_and_shm.md)
- Troubleshooting: [troubleshooting.md](troubleshooting.md)
