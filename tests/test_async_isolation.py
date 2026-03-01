import asyncio
import os
import socket

from faultcore import network_queue


def send_packet_with_tracking(sock, data, addr):
    try:
        result = sock.sendto(data, addr)
        return result > 0
    except Exception:
        return False


@network_queue(packet_loss=0.5)
async def flaky_task(id, iterations=20):
    print(f"Task {id} (FLAKY 50%) starting...")
    packets_sent = 0
    for _ in range(iterations):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _ in range(4):
            result = send_packet_with_tracking(s, b"ping", ("8.8.8.8", 53))
            if result:
                packets_sent += 1
        s.close()
        await asyncio.sleep(0.01)
    print(f"Task {id} (FLAKY) finished: {packets_sent}/{iterations * 4} packets sent")
    return packets_sent


async def stable_task(id, iterations=20):
    print(f"Task {id} (STABLE) starting...")
    packets_sent = 0
    for _ in range(iterations):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _ in range(4):
            result = send_packet_with_tracking(s, b"ping", ("8.8.8.8", 53))
            if result:
                packets_sent += 1
        s.close()
        await asyncio.sleep(0.01)
    print(f"Task {id} (STABLE) finished: {packets_sent}/{iterations * 4} packets sent")
    return packets_sent


async def main():
    print(f"PID: {os.getpid()}")
    print("Running concurrent tasks on the SAME thread...")

    results = await asyncio.gather(flaky_task(1), stable_task(2), flaky_task(3), stable_task(4))

    f1, s1, f2, s2 = results
    total_flaky = f1 + f2
    total_stable = s1 + s2
    total_packets_per_task = 20 * 4

    print("\n--- Final Results ---")
    print(f"Flaky Tasks sent: {f1}/{total_packets_per_task}, {f2}/{total_packets_per_task}")
    print(f"Stable Tasks sent: {s1}/{total_packets_per_task}, {s2}/{total_packets_per_task}")

    flaky_rate = total_flaky / (total_packets_per_task * 2)
    stable_rate = total_stable / (total_packets_per_task * 2)

    print(f"\nFlaky delivery rate: {flaky_rate * 100:.1f}%")
    print(f"Stable delivery rate: {stable_rate * 100:.1f}%")

    flaky_isolation_ok = flaky_rate < 0.7
    stable_isolation_ok = stable_rate > 0.9

    if flaky_isolation_ok and stable_isolation_ok:
        print("\n✅ SUCCESS: Async isolation verified!")
    else:
        print("\n❌ FAILURE: Limits leaked between tasks.")
        if not flaky_isolation_ok:
            print("   - Flaky tasks not experiencing enough packet loss")
        if not stable_isolation_ok:
            print("   - Stable tasks are affected by packet loss (leak!)")


if __name__ == "__main__":
    asyncio.run(main())
