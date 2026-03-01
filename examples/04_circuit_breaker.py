import time

from faultcore import circuit_breaker

call_counter = {"value": 0}


@circuit_breaker(failure_threshold=3, success_threshold=2, timeout_ms=2000)
def fragile_service():
    call_counter["value"] += 1
    if call_counter["value"] % 4 != 0:
        raise ConnectionError("Service unavailable")
    return "Success!"


if __name__ == "__main__":
    print("=" * 60)
    print(" Circuit Breaker Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Circuit Breaker State Transitions ---")
    call_counter["value"] = 0

    for i in range(10):
        try:
            result = fragile_service()
            print(f"Call {i + 1}: SUCCESS - {result}")
        except ConnectionError as e:
            print(f"Call {i + 1}: FAILED - {e}")
        except Exception as e:
            print(f"Call {i + 1}: CIRCUIT OPEN - {type(e).__name__}")
        time.sleep(0.1)
    print()

    print("--- Circuit Breaker Recovery ---")
    print("Waiting for timeout to allow half-open state...")
    time.sleep(2.5)

    call_counter["value"] = 0
    for i in range(5):
        try:
            result = fragile_service()
            print(f"Call {i + 1}: SUCCESS - {result}")
        except ConnectionError as e:
            print(f"Call {i + 1}: FAILED - {e}")
        except Exception as e:
            print(f"Call {i + 1}: {type(e).__name__} - {e}")
    print()

    print("Tests finished.")
