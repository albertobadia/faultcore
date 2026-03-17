#!/usr/bin/env python3
import argparse
import gzip
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime

import faultcore
from faultcore.shm_writer import SHM_SIZE

ATTEMPTS = 30
SOCKET_TIMEOUT_SEC = 0.35
PAYLOAD = b"RR"
POLICY_PACKET_LOSS = "40%"


def ensure_shm_ready() -> str:
    name = os.environ.get("FAULTCORE_CONFIG_SHM", f"/faultcore_{os.getpid()}_config")
    os.environ["FAULTCORE_CONFIG_SHM"] = name
    path = f"/dev/shm/{name.lstrip('/')}"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.ftruncate(fd, SHM_SIZE)
    finally:
        os.close(fd)
    return name


def try_roundtrip(host: str, port: int, idx: int) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SOCKET_TIMEOUT_SEC)
    try:
        sock.connect((host, port))
        sock.sendall(PAYLOAD + str(idx).encode("ascii"))
        data = sock.recv(64)
        if not data:
            return "empty"
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__
    finally:
        try:
            sock.close()
        except Exception:  # noqa: BLE001
            pass


def run_probe(host: str, port: int, with_policy: bool) -> list[str]:
    if with_policy:
        faultcore.register_policy(
            "record_replay_probe_policy",
            packet_loss=POLICY_PACKET_LOSS,
        )

        faultcore.set_thread_policy("record_replay_probe_policy")

        @faultcore.fault()
        def one(idx: int) -> str:
            return try_roundtrip(host, port, idx)
    else:

        def one(idx: int) -> str:
            return try_roundtrip(host, port, idx)

    return [one(i) for i in range(ATTEMPTS)]


def run_worker(args: argparse.Namespace) -> int:
    ensure_shm_ready()
    outcomes = run_probe(args.host, args.port, with_policy=args.with_policy)
    print(json.dumps({"outcomes": outcomes}, separators=(",", ":")))
    return 0


def run_phase(
    *,
    phase_name: str,
    host: str,
    port: int,
    mode: str,
    path: str,
    with_policy: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        __file__,
        "--phase",
        "worker",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if with_policy:
        cmd.append("--with-policy")

    env = os.environ.copy()
    env["FAULTCORE_RECORD_REPLAY_MODE"] = mode
    env["FAULTCORE_RECORD_REPLAY_PATH"] = path
    env["FAULTCORE_CONFIG_SHM"] = f"/faultcore_rr_{os.getpid()}_{phase_name}"

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{phase_name}: worker failed\nstdout={proc.stdout}\nstderr={proc.stderr}")

    last_line = proc.stdout.strip().splitlines()[-1]
    payload = json.loads(last_line)
    return payload["outcomes"]


def load_recorded_events(path: str) -> list[dict]:
    events: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def run_controller(args: argparse.Namespace) -> int:
    print(f"[{datetime.now().isoformat()}] record/replay integration host={args.host} port={args.port}")
    ensure_shm_ready()

    with tempfile.TemporaryDirectory(prefix="faultcore_rr_") as tmpdir:
        rr_path = os.path.join(tmpdir, "session.jsonl.gz")

        record_outcomes = run_phase(
            phase_name="record",
            host=args.host,
            port=args.port,
            mode="record",
            path=rr_path,
            with_policy=True,
        )
        replay_outcomes = run_phase(
            phase_name="replay",
            host=args.host,
            port=args.port,
            mode="replay",
            path=rr_path,
            with_policy=True,
        )

        if record_outcomes != replay_outcomes:
            raise RuntimeError(f"record/replay mismatch: record={record_outcomes} replay={replay_outcomes}")

        if not os.path.exists(rr_path):
            raise RuntimeError("record/replay output file was not created")

        events = load_recorded_events(rr_path)
        if not events:
            raise RuntimeError("record/replay output file is empty")

        sites = {event.get("site", "") for event in events}
        if "connect_pre" not in sites:
            raise RuntimeError("record/replay log missing expected site: connect_pre")

        unique_outcomes = sorted(set(record_outcomes))
        print(f"record outcomes: {unique_outcomes}")
        print(f"recorded events: {len(events)}")
        print("record/replay integration: PASS")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FaultCore record/replay integration probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--phase", choices=["controller", "worker"], default="controller")
    parser.add_argument("--with-policy", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.phase == "worker":
        return run_worker(args)
    return run_controller(args)


if __name__ == "__main__":
    sys.exit(main())
