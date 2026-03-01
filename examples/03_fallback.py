import asyncio

from faultcore import fallback


def primary_service():
    raise ConnectionError("Primary service unavailable")


def fallback_service():
    return "Fallback response - cached data"


@fallback(fallback_service)
def service_with_fallback():
    return primary_service()


@fallback(lambda: "Default value")
async def async_service_with_fallback():
    raise TimeoutError("Service timeout")


if __name__ == "__main__":
    print("=" * 60)
    print(" Fallback Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Sync Function with Fallback ---")
    try:
        result = service_with_fallback()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
    print()

    print("--- Async Function with Fallback ---")
    try:
        result = asyncio.run(async_service_with_fallback())
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
    print()

    print("Tests finished.")
