import asyncio
import socket
import time

from faultcore import network_queue


def demo_latency():
    print("--- Demo 1: Pure Latency (500ms) ---")
    queue = network_queue(rate="1000", capacity="1000", latency_ms=500, packet_loss=0.0)

    @queue
    def fetch_data():
        return {"status": "ok", "data": "Some payload"}

    start = time.time()
    result = fetch_data()
    duration = (time.time() - start) * 1000

    print(f"Result: {result}")
    print(f"Execution time: {duration:.2f}ms")
    print("-" * 40 + "\n")


def demo_packet_loss():
    print("--- Demo 2: Packet Loss (50%) at TCP/UDP OS Level ---")
    queue = network_queue(rate="1000", capacity="1000", latency_ms=10, packet_loss=0.5)

    @queue
    def flaky_request():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"\x00", ("8.8.8.8", 53))
        return "Success"

    success_count = 0
    failure_count = 0
    total_requests = 100

    for _ in range(total_requests):
        try:
            flaky_request()
            success_count += 1
        except Exception:
            failure_count += 1

    print(f"\nSummary: {success_count} successes, {failure_count} failures (Expected ~50%)")
    print("-" * 40 + "\n")


def demo_bandwidth_limit():
    print("--- Demo 3: Processing Rate Limit (10 req/s) ---")
    queue = network_queue(rate="10", capacity="5", latency_ms=0, packet_loss=0.0)

    @queue
    def process_chunk():
        time.sleep(0.01)
        return "Chunk processed"

    start = time.time()
    total_requests = 15
    print(f"Starting {total_requests} rapid requests with 10 req/s limit...")
    print("First few will be fast (capacity/burst), rest will be queued/delayed...")

    for i in range(total_requests):
        try:
            req_start = time.time()
            process_chunk()
            req_duration = (time.time() - req_start) * 1000
            print(f"Req {i + 1:02d}: {req_duration:6.2f}ms")
        except Exception as e:
            print(f"Req {i + 1:02d}: FAILED - {e}")

    total_duration = time.time() - start
    print(f"Total time for {total_requests} requests: {total_duration:.2f}s (Expected > 1.0s)")
    print("-" * 40 + "\n")


async def demo_combined_async():
    print("--- Demo 4: Variable Latency + Limit + Loss (Async) ---")
    queue = network_queue(
        rate="50",
        capacity="20",
        latency_ms=200,
        packet_loss=0.2,
    )

    @queue
    async def fetch_async(id):
        await asyncio.sleep(0.01)
        return f"Data {id}"

    async def worker(id):
        start = time.time()
        try:
            res = await fetch_async(id)
            duration = (time.time() - start) * 1000
            print(f"Worker {id:02d} | Success | {duration:6.2f}ms | Res: {res}")
            return True
        except Exception as e:
            duration = (time.time() - start) * 1000
            print(f"Worker {id:02d} | FAILED | {duration:6.2f}ms | Err: {e}")
            return False

    print("Launching 10 concurrent workers...")
    tasks = [worker(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    successes = sum(1 for r in results if r)
    print(f"\nTotal: {successes} successes out of 10")
    print("-" * 40 + "\n")


if __name__ == "__main__":
    print("=" * 60)
    print(" Network Tests - FaultOSI Pipeline ".center(60, "="))
    print("=" * 60 + "\n")

    demo_latency()

    time.sleep(1)

    demo_packet_loss()

    time.sleep(1)

    demo_bandwidth_limit()

    time.sleep(1)

    asyncio.run(demo_combined_async())

    print("Tests finished.")
