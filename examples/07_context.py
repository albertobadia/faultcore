import asyncio

from faultcore import add_keys, clear_keys, get_keys, remove_key


def fetch_user_data(user_id: str):
    keys = get_keys()
    print(f"Current context keys: {keys}")
    return {"user_id": user_id, "tier": "premium"}


async def fetch_async_data(item_id: str):
    keys = get_keys()
    print(f"Async context keys: {keys}")
    await asyncio.sleep(0.01)
    return {"item_id": item_id, "available": True}


if __name__ == "__main__":
    print("=" * 60)
    print(" Context Management Examples ".center(60, "="))
    print("=" * 60 + "\n")

    print("--- Basic Context Keys ---")
    print(f"Initial keys: {get_keys()}")
    print()

    print("--- Adding Keys ---")
    add_keys(["tenant_id:acme", "region:us-east"])
    print(f"After add_keys: {get_keys()}")
    print()

    print("--- Function with Context ---")
    result = fetch_user_data("user123")
    print(f"Result: {result}")
    print()

    print("--- Adding More Keys ---")
    add_keys(["user_role:admin"])
    print(f"After more keys: {get_keys()}")
    print()

    print("--- Removing Key ---")
    remove_key("user_role")
    print(f"After remove_key: {get_keys()}")
    print()

    print("--- Clear All Keys ---")
    clear_keys()
    print(f"After clear_keys: {get_keys()}")
    print()

    print("--- Async Context ---")
    add_keys(["request_id:abc123"])
    result = asyncio.run(fetch_async_data("item456"))
    print(f"Result: {result}")
    clear_keys()
    print()

    print("Tests finished.")
