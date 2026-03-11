#!/usr/bin/env python3
import argparse
import socket
import threading
import time
from datetime import datetime


class EchoServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9000):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.client_count = 0

    def start(self):
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        self.server_socket = socket.socket(family, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            self.server_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True

        print(f"[{datetime.now().isoformat()}] Echo server started on {self.host}:{self.port}")

        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, address = self.server_socket.accept()
                except TimeoutError:
                    continue

                self.client_count += 1
                client_id = self.client_count
                print(f"[{datetime.now().isoformat()}] Client {client_id} connected from {address}")

                thread = threading.Thread(target=self.handle_client, args=(client_socket, address, client_id))
                thread.daemon = True
                thread.start()
            except Exception as exc:
                if self.running:
                    print(f"Error accepting connection: {exc}")

    def handle_client(self, client_socket, address, client_id):
        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break

                message = data.decode("utf-8").strip()
                print(f"[{datetime.now().isoformat()}] Client {client_id}: {message}")

                if message == "STREAM":
                    self.stream_to_client(client_socket, client_id)
                    break

                response = f"ECHO: {message}\n"
                client_socket.sendall(response.encode("utf-8"))

        except Exception as exc:
            print(f"[{datetime.now().isoformat()}] Client {client_id} error: {exc}")
        finally:
            client_socket.close()
            print(f"[{datetime.now().isoformat()}] Client {client_id} disconnected")

    def stream_to_client(self, client_socket, client_id):
        chunk = b"x" * 8192
        started = time.perf_counter()
        try:
            while True:
                client_socket.sendall(chunk)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            print(f"[{datetime.now().isoformat()}] Client {client_id} stream ended after {elapsed:.2f}s: {exc}")

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TCP Echo Server for FaultCore testing")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=9000, help="Port to listen on")
    args = parser.parse_args()

    server = EchoServer(args.host, args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
