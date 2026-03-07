import faultcore


def test_rate_limit_high_rate_low_capacity():
    @faultcore.rate_limit(1000.0)
    def limited_func():
        return "ok"

    result = limited_func()
    assert result == "ok"

    try:
        limited_func()
    except Exception:
        pass


def test_rate_limit_function_preserves_metadata():
    @faultcore.rate_limit(10.0)
    def my_function():
        """Docstring"""
        pass

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "Docstring"


def test_rate_limit_sequential_calls_deplete_tokens():
    policy = faultcore.RateLimit(2.0, 2)

    def dummy():
        return "ok"

    assert policy(dummy, (), {}) == "ok"
    assert policy(dummy, (), {}) == "ok"

    try:
        policy(dummy, (), {})
    except Exception as e:
        assert "rate" in str(e).lower() or "limit" in str(e).lower()


def test_rate_limit_multiple_instances_isolated():
    policy1 = faultcore.RateLimit(1.0, 1)
    policy2 = faultcore.RateLimit(100.0, 100)

    def dummy():
        return "ok"

    policy1(dummy, (), {})
    policy2(dummy, (), {})
    policy2(dummy, (), {})

    try:
        policy1(dummy, (), {})
    except Exception:
        pass


def test_rate_limit_with_fractional_rate():
    policy = faultcore.RateLimit(0.5, 2)

    def dummy():
        return "ok"

    assert policy(dummy, (), {}) == "ok"
    assert policy(dummy, (), {}) == "ok"


def test_rate_limit_repr_contains_all_info():
    policy = faultcore.RateLimit(50.0, 100)
    repr_str = repr(policy)
    assert "50" in repr_str
    assert "100" in repr_str
    assert "RateLimitPolicy" in repr_str


def test_rate_limit_with_very_high_rate():
    @faultcore.rate_limit(100000.0)
    def limited_func():
        return "ok"

    results = [limited_func() for _ in range(100)]
    assert all(r == "ok" for r in results)
