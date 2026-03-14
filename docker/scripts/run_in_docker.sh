#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="/workspace/artifacts"
RUN_JSON="${ARTIFACT_DIR}/docker_run.json"
REPORT_HTML="${ARTIFACT_DIR}/docker_report.html"
SCENARIO_METRICS_JSON="${ARTIFACT_DIR}/network_metrics.json"

mkdir -p "${ARTIFACT_DIR}"

python - <<'PY'
import socket
import time
import urllib.request


def wait_tcp(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"timeout waiting tcp {host}:{port}")


def wait_udp_echo(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    probe = b"probe"
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        try:
            sock.sendto(probe, (host, port))
            data, _ = sock.recvfrom(64)
            if data == probe:
                return
        except OSError:
            time.sleep(0.3)
        finally:
            sock.close()
    raise RuntimeError(f"timeout waiting udp {host}:{port}")


def wait_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"timeout waiting http {url}")


wait_tcp("tcp-echo", 9000)
wait_udp_echo("udp-echo", 9001)
wait_http("http://http-echo:8000/health")
print("all services ready")
PY

faultcore run --run-json "${RUN_JSON}" -- \
  python /workspace/docker/scripts/network_scenario.py \
  --tcp-host tcp-echo --tcp-port 9000 \
  --udp-host udp-echo --udp-port 9001 \
  --http-url http://http-echo:8000 --iterations 30 \
  --metrics-out "${SCENARIO_METRICS_JSON}"

faultcore report --input "${RUN_JSON}" --output "${REPORT_HTML}"

echo "Artifacts written:"
echo "- ${RUN_JSON}"
echo "- ${REPORT_HTML}"
echo "- ${SCENARIO_METRICS_JSON}"
