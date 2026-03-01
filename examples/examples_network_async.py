import asyncio
import time

import aiohttp

from faultcore import network_queue


@network_queue(packet_loss=0.5)
async def fetch_with_loss(session, url, name):
    print(f"[{name}] Started fetching {url} with 50% Packet Loss!")
    start = time.time()
    try:
        async with session.get(url, timeout=5) as response:
            await response.text()
            print(f"[{name}] Success in {time.time() - start:.2f}s!")
    except Exception as e:
        print(f"[{name}] Failed! Error: {e}")


@network_queue(latency_ms=1000)
async def fetch_with_latency(session, url, name):
    print(f"[{name}] Started fetching {url} with 1000ms Latency!")
    start = time.time()
    try:
        async with session.get(url, timeout=5) as response:
            await response.text()
            print(f"[{name}] Success in {time.time() - start:.2f}s!")
    except Exception as e:
        print(f"[{name}] Failed! Error: {e}")


async def main():
    async with aiohttp.ClientSession() as session:
        url = "http://example.com"
        await asyncio.gather(
            fetch_with_loss(session, url, "Task 1 (Loss)"),
            fetch_with_latency(session, url, "Task 2 (Latency)"),
            fetch_with_loss(session, url, "Task 3 (Loss)"),
        )


if __name__ == "__main__":
    asyncio.run(main())
