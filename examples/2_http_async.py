#!/usr/bin/env python3
import asyncio
import time

try:
    import aiohttp
except ImportError:
    print("aiohttp not installed. Install with: pip install aiohttp")
    raise

from faultcore import rate, timeout


@rate("10mbps")
async def fetch_url(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        return await response.json()


@timeout(connect="300ms")
async def fetch_with_latency(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        return await response.text()


async def fetch_plain(session: aiohttp.ClientSession, url: str):
    async with session.get(url) as response:
        return await response.json()


async def main():
    print("=" * 60)
    print(" Async HTTP Examples with faultcore ".center(60, "="))
    print("=" * 60 + "\n")

    async with aiohttp.ClientSession() as session:
        print("--- Plain Async HTTP Request ---")
        start = time.time()
        try:
            result = await fetch_plain(session, "https://httpbin.org/get")
            print(f"Status: OK - {result.get('origin', 'N/A')}")
        except Exception as e:
            print(f"Error: {e}")
        print(f"Time: {time.time() - start:.3f}s\n")

        print("--- Rate Setting (10 Mbps equivalent) ---")
        start = time.time()
        tasks = [fetch_url(session, "https://httpbin.org/get") for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Request {i + 1}: Error - {type(result).__name__}")
            else:
                print(f"Request {i + 1}: OK")
        print(f"Total time: {time.time() - start:.3f}s\n")

        print("--- Concurrent Requests with Latency (300ms) ---")
        start = time.time()
        tasks = [fetch_with_latency(session, "https://httpbin.org/delay/1") for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Request {i + 1}: Error - {type(result).__name__}")
            else:
                print(f"Request {i + 1}: OK")
        print(f"Total time: {time.time() - start:.3f}s\n")

    print("These examples require the interceptor loaded via LD_PRELOAD.")
    print("Build the interceptor first: ./build.sh")
    print("Run with: faultcore run -- python examples/2_http_async.py")
    print("Or use: examples/run_with_preload.sh 2_http_async.py")
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
