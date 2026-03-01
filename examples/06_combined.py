import asyncio

from faultcore import circuit_breaker, fallback, retry, timeout


def get_default_data():
    return {"data": "cached", "source": "fallback"}


@retry(max_retries=2, backoff_ms=100)
@timeout(timeout_ms=500)
@fallback(get_default_data)
@circuit_breaker(failure_threshold=3, success_threshold=1, timeout_ms=1000)
def unreliable_api_call():
    import random

    if random.random() < 0.7:
        raise ConnectionError("Random failure")
    return {"data": "live", "source": "api"}


async def unreliable_api_call_async():
    import random

    await asyncio.sleep(0.01)
    if random.random() < 0.7:
        raise ConnectionError("Random failure")
    return {"data": "live", "source": "api"}


@retry(max_retries=2, backoff_ms=100)
@timeout(timeout_ms=500)
@fallback(get_default_data)
async def unreliable_async_call():
    return await unreliable_api_call_async()


if __name__ == "__main__":
    print("=" * 60)
    print(" Combined Decorators Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Combined: Retry + Timeout + Fallback + Circuit Breaker ---")
    for i in range(10):
        try:
            result = unreliable_api_call()
            print(f"Call {i + 1}: SUCCESS - {result}")
        except Exception as e:
            print(f"Call {i + 1}: {type(e).__name__} - {e}")
    print()

    print("--- Combined (Async): Retry + Timeout + Fallback ---")

    async def run_async():
        for i in range(10):
            try:
                result = await unreliable_async_call()
                print(f"Call {i + 1}: SUCCESS - {result}")
            except Exception as e:
                print(f"Call {i + 1}: {type(e).__name__} - {e}")

    asyncio.run(run_async())
    print()

    print("Tests finished.")
