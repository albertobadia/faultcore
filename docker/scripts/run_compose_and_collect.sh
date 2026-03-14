#!/usr/bin/env bash
set -euo pipefail

DOCKER_HOST="${DOCKER_HOST:-tcp://host.orb.internal:2375}"
export DOCKER_HOST

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker/docker-compose.yml"
ARTIFACTS_DIR="${ROOT_DIR}/artifacts"

mkdir -p "${ARTIFACTS_DIR}"

docker compose -f "${COMPOSE_FILE}" up --build --abort-on-container-exit runner

RUNNER_CONTAINER_ID="$(docker compose -f "${COMPOSE_FILE}" ps -a -q runner)"
if [[ -z "${RUNNER_CONTAINER_ID}" ]]; then
  echo "runner container id not found" >&2
  exit 1
fi

docker cp "${RUNNER_CONTAINER_ID}:/workspace/artifacts/docker_run.json" "${ARTIFACTS_DIR}/docker_run.json"
docker cp "${RUNNER_CONTAINER_ID}:/workspace/artifacts/docker_report.html" "${ARTIFACTS_DIR}/docker_report.html"
docker cp "${RUNNER_CONTAINER_ID}:/workspace/artifacts/network_metrics.json" "${ARTIFACTS_DIR}/network_metrics.json"
docker cp "${RUNNER_CONTAINER_ID}:/workspace/artifacts/docker_run.rr.jsonl.gz" \
  "${ARTIFACTS_DIR}/docker_run.rr.jsonl.gz" >/dev/null 2>&1 || true

docker compose -f "${COMPOSE_FILE}" down -v

echo "Artifacts copied to host:"
echo "- ${ARTIFACTS_DIR}/docker_run.json"
echo "- ${ARTIFACTS_DIR}/docker_report.html"
echo "- ${ARTIFACTS_DIR}/network_metrics.json"
if [[ -f "${ARTIFACTS_DIR}/docker_run.rr.jsonl.gz" ]]; then
  echo "- ${ARTIFACTS_DIR}/docker_run.rr.jsonl.gz"
fi
