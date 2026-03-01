import time

from faultcore import network_queue


@network_queue(rate=1, capacity=10240, max_queue_size=100, latency_ms=0, packet_loss=0.0)
def send_at_1mbps(data_size: int) -> int:
    return data_size


@network_queue(rate=10, capacity=102400, max_queue_size=100, latency_ms=0, packet_loss=0.0)
def send_at_10mbps(data_size: int) -> int:
    return data_size


if __name__ == "__main__":
    print("=" * 60)
    print(" Bandwidth Throttling Examples ".center(60, "="))
    print("=" * 60 + "\n")

    chunk_size = 10 * 1024
    num_chunks = 5

    print(f"--- {chunk_size // 1024} KB chunks at 1 Mbps ---")
    print(f"Expected time: {(chunk_size * num_chunks * 8) / 1_000_000:.2f}s for {num_chunks} chunks")
    start = time.time()
    for i in range(num_chunks):
        req_start = time.time()
        result = send_at_1mbps(chunk_size)
        duration = (time.time() - req_start) * 1000
        print(f"Chunk {i + 1}: {duration:6.2f}ms")
    total = time.time() - start
    print(f"Total: {total:.2f}s\n")

    print(f"--- {chunk_size // 1024} KB chunks at 10 Mbps ---")
    print(f"Expected time: {(chunk_size * num_chunks * 8) / 10_000_000:.2f}s for {num_chunks} chunks")
    start = time.time()
    for i in range(num_chunks):
        req_start = time.time()
        result = send_at_10mbps(chunk_size)
        duration = (time.time() - req_start) * 1000
        print(f"Chunk {i + 1}: {duration:6.2f}ms")
    total = time.time() - start
    print(f"Total: {total:.2f}s\n")

    print("Note: rate parameter is in Mbps (1 = 1 Mbps, 10 = 10 Mbps)")
    print()

    print("Tests finished.")
