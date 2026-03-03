import faultcore


def test_context_manager_has_key_empty():
    faultcore.clear_keys()
    assert faultcore.ContextManager.has_key("any") is False


def test_context_manager_has_key_after_add():
    faultcore.clear_keys()
    faultcore.add_keys(["test_key"])
    assert faultcore.ContextManager.has_key("test_key") is True


def test_context_manager_has_key_case_sensitive():
    faultcore.clear_keys()
    faultcore.add_keys(["TestKey"])
    assert faultcore.ContextManager.has_key("testkey") is False
    assert faultcore.ContextManager.has_key("TestKey") is True


def test_context_manager_add_keys_duplicates():
    faultcore.clear_keys()
    faultcore.add_keys(["key"])
    faultcore.add_keys(["key"])
    keys = faultcore.get_keys()
    assert keys.count("key") == 1


def test_context_manager_remove_key_returns_false_for_empty():
    faultcore.clear_keys()
    result = faultcore.remove_key("nonexistent")
    assert result is False


def test_context_manager_add_empty_list():
    faultcore.clear_keys()
    faultcore.add_keys([])
    keys = faultcore.get_keys()
    assert keys == []


def test_context_manager_get_keys_returns_list():
    faultcore.clear_keys()
    result = faultcore.get_keys()
    assert isinstance(result, list)
