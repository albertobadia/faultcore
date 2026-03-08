import asyncio
import time

from faultcore import rate_limit


@rate_limit(rate=5.0)
def limited_api_call():
    return "API Response"


async def limited_async_call():
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
        except Exception as e:
            print(f"Request {i + 1}: ERROR - {e}")
    total = time.time() - start
    print(f"Total time: {total:.2f}s\n")

    print("--- Async workload (for comparison) ---")

    async def run_async_calls():
        start = time.time()
        tasks = [limited_async_call() for _ in range(8)]
        await asyncio.gather(*tasks)
        return time.time() - start

    total = asyncio.run(run_async_calls())
    print(f"Total time: {total:.2f}s\n")

    print("Tests finished.")
