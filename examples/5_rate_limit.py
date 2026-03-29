import asyncio
import time

from faultcore import rate


@rate("5mbps")
def limited_api_call() -> str:
    return "API Response"


async def limited_async_call() -> str:
    await asyncio.sleep(0.01)
    return "Async API Response"


if __name__ == "__main__":
    print("=" * 60)
    print(" Rate Limit Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Sync Rate Setting (5 Mbps equivalent) ---")
    start = time.time()
    for i in range(8):
        req_start = time.time()
        try:
            limited_api_call()
            duration = (time.time() - req_start) * 1000
            print(f"Request {i + 1}: {duration:6.2f}ms")
        except Exception as exc:
            print(f"Request {i + 1}: ERROR - {exc}")
    total = time.time() - start
    print(f"Total time: {total:.2f}s\n")

    print("--- Async workload (for comparison) ---")

    async def run_async_calls() -> float:
        start = time.time()
        tasks = [limited_async_call() for _ in range(8)]
        await asyncio.gather(*tasks)
        return time.time() - start

    total = asyncio.run(run_async_calls())
    print(f"Total time: {total:.2f}s\n")

    print("Tests finished.")
