import asyncio
import time

from faultcore import timeout


@timeout(timeout_ms=500)
def slow_function_sync():
    time.sleep(1)
    return "Done"


@timeout(timeout_ms=500)
async def slow_function_async():
    await asyncio.sleep(1)
    return "Done"


if __name__ == "__main__":
    print("=" * 60)
    print(" Timeout Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Sync Function with Timeout ---")
    try:
        result = slow_function_sync()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Timeout! Error: {e}")
    print()

    print("--- Async Function with Timeout ---")
    try:
        result = asyncio.run(slow_function_async())
        print(f"Result: {result}")
    except Exception as e:
        print(f"Timeout! Error: {e}")
    print()

    print("Tests finished.")
