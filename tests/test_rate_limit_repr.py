import faultcore


def test_rate_limit_repr_contains_available_tokens():
    policy = faultcore.RateLimit(50.0, 100)
    repr_str = repr(policy)
    assert "available" in repr_str.lower() or "50" in repr_str


def test_rate_limit_repr_contains_capacity():
    policy = faultcore.RateLimit(50.0, 100)
    repr_str = repr(policy)
    assert "100" in repr_str


def test_rate_limit_repr_contains_rate():
    policy = faultcore.RateLimit(50.0, 100)
    repr_str = repr(policy)
    assert "50" in repr_str


def test_rate_limit_available_tokens_decreases():
    policy = faultcore.RateLimit(100.0, 5)

    def dummy():
        return "ok"

    initial_tokens = policy.available_tokens
    policy(dummy, (), {})
    after_call_tokens = policy.available_tokens
    assert after_call_tokens < initial_tokens


def test_rate_limit_fractional_tokens():
    policy = faultcore.RateLimit(0.1, 1)

    def dummy():
        return "ok"

    policy(dummy, (), {})


def test_rate_limit_zero_available_tokens():
    policy = faultcore.RateLimit(0.001, 1)

    def dummy():
        return "ok"

    policy(dummy, (), {})
    tokens = policy.available_tokens
    assert tokens >= 0
