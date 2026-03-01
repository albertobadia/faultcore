import asyncio

call_counter = {"sync": 0, "async": 0}


def flaky_function():
    call_counter["sync"] += 1
    print(f"Attempt {call_counter['sync']}")
    if call_counter["sync"] < 3:
        raise ConnectionError("Network error")
    return "Success!"


async def flaky_function_async():
    call_counter["async"] += 1
    print(f"Async Attempt {call_counter['async']}")
    if call_counter["async"] < 3:
        raise ConnectionError("Network error")
    return "Success!"


if __name__ == "__main__":
    print("=" * 60)
    print(" Retry Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Sync Function with Retry ---")
    call_counter["sync"] = 0
    try:
        result = flaky_function()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed! Error: {e}")
    print()

    print("--- Async Function with Retry ---")
    call_counter["async"] = 0
    try:
        result = asyncio.run(flaky_function_async())
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed! Error: {e}")
    print()

    print("--- Retry with Specific Exception Types ---")
    print("(retry_on parameter not fully supported yet)")
    print()

    print("Tests finished.")
