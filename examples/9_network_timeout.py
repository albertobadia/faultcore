#!/usr/bin/env python3
import time

from faultcore import timeout


def _run_case(title: str) -> float:
    print(f"\n {title} ".center(60, "="))
    started = time.perf_counter()
    simulate_network_call()
    elapsed = time.perf_counter() - started
    print(f"Completed after {elapsed:.3f}s")
    return elapsed


@timeout(connect="2000ms")
def test_latency_2000ms() -> float:
    return _run_case("Test 1: 2000ms Latency")


def simulate_network_call() -> str:
    time.sleep(0.1)
    return "data"


@timeout(connect="500ms")
def test_latency_500ms() -> float:
    return _run_case("Test 2: 500ms Latency")


@timeout(connect="100ms")
def test_latency_100ms() -> float:
    return _run_case("Test 3: 100ms Latency")


def test_no_latency() -> float:
    return _run_case("Test 4: No Latency (baseline)")


if __name__ == "__main__":
    print("\nNetwork Timeout Examples using faultcore")
    print("Uses @faultcore.timeout decorator to configure network timeout policy via SHM")
    print("Make sure to run with LD_PRELOAD (Linux)")
    print()

    test_latency_2000ms()
    test_latency_500ms()
    test_latency_100ms()
    test_no_latency()

    print("\n" + "=" * 60)
    print(" All tests completed! ".center(60, "="))
    print("=" * 60)
