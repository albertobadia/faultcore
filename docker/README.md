# Docker flow: real services + FaultCore report

This directory starts real services (TCP, UDP, HTTP), runs a network scenario in a `runner` container, and stores artifacts on the host.

## Services

- `tcp-echo`: TCP echo server on `9000`.
- `udp-echo`: UDP echo server on `9001`.
- `http-echo`: HTTP API on `8000` (`/health`, `/echo/{msg}`, etc.).
- `runner`: runs `faultcore run` + `faultcore report` inside Docker.

## Recommended usage (remote daemon)

```bash
DOCKER_HOST=tcp://your-remote-host:2375 bash docker/scripts/run_compose_and_collect.sh
```

The script:

1. Runs `docker compose up --build --abort-on-container-exit runner`.
2. Copies artifacts from the `runner` container to the local repository with `docker cp`.
3. Runs `docker compose down -v`.

## Host artifacts

Artifacts are written to `artifacts/`:

- `artifacts/docker_run.json`
- `artifacts/docker_report.html`
- `artifacts/network_metrics.json`
- `artifacts/docker_run.rr.jsonl.gz` (if the run executes in `record` mode)

## Notes

- `.dockerignore` is used to reduce build context.
- The flow does not depend on bind mounts, which is important when `DOCKER_HOST` points to a remote host.
