#!/usr/bin/env python3
import argparse
import socket
from datetime import datetime


def main() -> int:
    parser = argparse.ArgumentParser(description="UDP echo server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((args.host, args.port))
        print(f"[{datetime.now().isoformat()}] UDP echo server on {args.host}:{args.port}")
        while True:
            data, addr = sock.recvfrom(65535)
            if not data:
                continue
            sock.sendto(data, addr)


if __name__ == "__main__":
    raise SystemExit(main())
