import faultcore


def test_add_keys():
    faultcore.clear_keys()
    faultcore.add_keys(["key1", "key2"])
    keys = faultcore.get_keys()
    assert "key1" in keys
    assert "key2" in keys
    faultcore.clear_keys()


def test_get_keys_empty():
    faultcore.clear_keys()
    keys = faultcore.get_keys()
    assert keys == []


def test_remove_key_existing():
    faultcore.clear_keys()
    faultcore.add_keys(["key1", "key2"])
    result = faultcore.remove_key("key1")
    assert result is True
    keys = faultcore.get_keys()
    assert "key1" not in keys
    assert "key2" in keys
    faultcore.clear_keys()


def test_remove_key_non_existing():
    faultcore.clear_keys()
    faultcore.add_keys(["key1"])
    result = faultcore.remove_key("nonexistent")
    assert result is False
    faultcore.clear_keys()


def test_clear_keys():
    faultcore.clear_keys()
    faultcore.add_keys(["key1", "key2", "key3"])
    faultcore.clear_keys()
    keys = faultcore.get_keys()
    assert keys == []


def test_has_key():
    faultcore.clear_keys()
    faultcore.add_keys(["key1"])
    assert faultcore.ContextManager.has_key("key1") is True
    assert faultcore.ContextManager.has_key("nonexistent") is False
    faultcore.clear_keys()


def test_multiple_operations():
    faultcore.clear_keys()
    faultcore.add_keys(["a", "b"])
    faultcore.add_keys(["c"])
    keys = faultcore.get_keys()
    assert len(keys) == 3
    assert "a" in keys
    assert "b" in keys
    assert "c" in keys

    faultcore.remove_key("b")
    keys = faultcore.get_keys()
    assert len(keys) == 2
    assert "b" not in keys

    faultcore.clear_keys()
    assert faultcore.get_keys() == []
