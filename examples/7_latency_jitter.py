#!/usr/bin/env python3
"""Example 07: Latency and jitter injection.

This example demonstrates how to inject latency and jitter into network operations
using faultcore decorators.
"""

import time

import faultcore


@faultcore.latency("100ms")
def slow_request():
    """Simulate a request with 100ms latency."""
    time.sleep(0.05)
    return "slow response"


@faultcore.jitter("50ms")
def jittery_request():
    """Simulate a request with 50ms jitter."""
    time.sleep(0.01)
    return "jittery response"


@faultcore.latency("50ms")
@faultcore.jitter("25ms")
def latency_plus_jitter():
    """Combine latency and jitter for realistic network simulation."""
    time.sleep(0.02)
    return "latency + jitter response"


def main():
    print("=== Latency and Jitter Example ===\n")

    print("1. Pure latency (100ms):")
    start = time.perf_counter()
    result = slow_request()
    elapsed = (time.perf_counter() - start) * 1000
    print(f"   Result: {result}")
    print(f"   Elapsed: {elapsed:.1f}ms\n")

    print("2. Pure jitter (50ms):")
    start = time.perf_counter()
    result = jittery_request()
    elapsed = (time.perf_counter() - start) * 1000
    print(f"   Result: {result}")
    print(f"   Elapsed: {elapsed:.1f}ms\n")

    print("3. Combined latency (50ms) + jitter (25ms):")
    start = time.perf_counter()
    result = latency_plus_jitter()
    elapsed = (time.perf_counter() - start) * 1000
    print(f"   Result: {result}")
    print(f"   Elapsed: {elapsed:.1f}ms\n")

    print("=== Context Manager Example ===\n")

    with faultcore.policy_context(latency="75ms", jitter="15ms"):
        print("Inside fault context (latency=75ms, jitter=15ms):")
        start = time.perf_counter()
        time.sleep(0.02)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"   Elapsed: {elapsed:.1f}ms")

    print("\nDone!")


if __name__ == "__main__":
    main()
