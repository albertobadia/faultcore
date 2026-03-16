#!/usr/bin/env python3
import time

from faultcore import connect_timeout


@connect_timeout(timeout_ms=2000)
def test_latency_2000ms():
    print(" Test 1: 2000ms Latency ".center(60, "="))
    start = time.time()
    simulate_network_call()
    elapsed = time.time() - start
    print(f"Completed after {elapsed:.3f}s")
    return elapsed


def simulate_network_call():
    time.sleep(0.1)
    return "data"


@connect_timeout(timeout_ms=500)
def test_latency_500ms():
    print("\n Test 2: 500ms Latency ".center(60, "="))
    start = time.time()
    simulate_network_call()
    elapsed = time.time() - start
    print(f"Completed after {elapsed:.3f}s")
    return elapsed


@connect_timeout(timeout_ms=100)
def test_latency_100ms():
    print("\n Test 3: 100ms Latency ".center(60, "="))
    start = time.time()
    simulate_network_call()
    elapsed = time.time() - start
    print(f"Completed after {elapsed:.3f}s")
    return elapsed


def test_no_latency():
    print("\n Test 4: No Latency (baseline) ".center(60, "="))
    start = time.time()
    simulate_network_call()
    elapsed = time.time() - start
    print(f"Completed after {elapsed:.3f}s")
    return elapsed


if __name__ == "__main__":
    print("\nNetwork Timeout Examples using faultcore")
    print("Uses @faultcore.connect_timeout decorator to configure network timeout policy via SHM")
    print("Make sure to run with LD_PRELOAD (Linux)")
    print()

    test_latency_2000ms()
    test_latency_500ms()
    test_latency_100ms()
    test_no_latency()

    print("\n" + "=" * 60)
    print(" All tests completed! ".center(60, "="))
    print("=" * 60)
