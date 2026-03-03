import faultcore


def test_context_manager_get_keys():
    faultcore.clear_keys()
    faultcore.add_keys(["key1", "key2"])

    keys = faultcore.ContextManager.get_keys()
    assert "key1" in keys
    assert "key2" in keys

    faultcore.clear_keys()


def test_context_manager_add_keys():
    faultcore.clear_keys()
    faultcore.ContextManager.add_keys(["key3", "key4"])

    keys = faultcore.get_keys()
    assert "key3" in keys
    assert "key4" in keys

    faultcore.clear_keys()


def test_context_manager_remove_key():
    faultcore.clear_keys()
    faultcore.add_keys(["key1"])

    result = faultcore.ContextManager.remove_key("key1")
    assert result is True

    keys = faultcore.get_keys()
    assert "key1" not in keys

    faultcore.clear_keys()


def test_context_manager_clear_keys():
    faultcore.add_keys(["key1", "key2", "key3"])
    faultcore.ContextManager.clear_keys()

    keys = faultcore.get_keys()
    assert keys == []


def test_context_manager_has_key():
    faultcore.clear_keys()
    faultcore.add_keys(["key1"])

    assert faultcore.ContextManager.has_key("key1") is True
    assert faultcore.ContextManager.has_key("key2") is False

    faultcore.clear_keys()


def test_context_keys_are_shared():
    faultcore.clear_keys()
    faultcore.add_keys(["shared_key"])

    keys1 = faultcore.get_keys()
    keys2 = faultcore.ContextManager.get_keys()

    assert keys1 == keys2
    assert "shared_key" in keys1

    faultcore.clear_keys()


def test_context_add_empty_list():
    faultcore.clear_keys()
    faultcore.add_keys([])

    keys = faultcore.get_keys()
    assert keys == []

    faultcore.clear_keys()


def test_context_add_duplicate_keys():
    faultcore.clear_keys()
    faultcore.add_keys(["key1", "key1", "key2"])

    keys = faultcore.get_keys()
    assert len(keys) == 2

    faultcore.clear_keys()


def test_context_remove_nonexistent_key():
    faultcore.clear_keys()
    faultcore.add_keys(["key1"])

    result = faultcore.ContextManager.remove_key("nonexistent")
    assert result is False

    keys = faultcore.get_keys()
    assert "key1" in keys

    faultcore.clear_keys()


def test_context_multiple_operations():
    faultcore.clear_keys()

    faultcore.add_keys(["a"])
    assert "a" in faultcore.get_keys()

    faultcore.add_keys(["b", "c"])
    assert len(faultcore.get_keys()) == 3

    faultcore.remove_key("b")
    assert "b" not in faultcore.get_keys()
    assert len(faultcore.get_keys()) == 2

    faultcore.ContextManager.clear_keys()
    assert faultcore.get_keys() == []
