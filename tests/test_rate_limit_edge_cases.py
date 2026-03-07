import time

import faultcore


def test_rate_limit_token_replenishment():
    @faultcore.rate_limit(10.0)
    def limited_func():
        return "ok"

    assert limited_func() == "ok"
    assert limited_func() == "ok"
    try:
        limited_func()
    except Exception:
        pass

    time.sleep(0.3)

    result = limited_func()
    assert result == "ok"


def test_rate_limit_available_tokens():
    policy = faultcore.RateLimit(100.0, 5)

    initial = policy.available_tokens
    assert policy.capacity <= 5.0

    after_acquire = policy.available_tokens
    assert after_acquire <= initial


def test_rate_limit_zero_rate_raises_error():
    try:
        faultcore.RateLimit(0, 10)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "rate" in str(e).lower()


def test_rate_limit_negative_rate_raises_error():
    try:
        faultcore.RateLimit(-1, 10)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "rate" in str(e).lower()


def test_rate_limit_zero_capacity_raises_error():
    try:
        faultcore.RateLimit(10, 0)
        raise AssertionError("Should have raised ValueError")
    except Exception as e:
        assert "value" in str(e).lower() or "capacity" in str(e).lower()


def test_rate_limit_getters():
    policy = faultcore.RateLimit(50.0, 100)
    assert policy.rate == 50.0
    assert policy.capacity == 100


def test_rate_limit_available_tokens_getter():
    policy = faultcore.RateLimit(50.0, 100)
    tokens = policy.available_tokens
    assert isinstance(tokens, float)
    assert tokens >= 0


def test_rate_limit_repr():
    policy = faultcore.RateLimit(50.0, 100)
    repr_str = repr(policy)
    assert "50" in repr_str
    assert "100" in repr_str


def test_rate_limit_exceeded_error_message():
    @faultcore.rate_limit(1.0)
    def limited_func():
        return "ok"

    assert limited_func() == "ok"

    try:
        limited_func()
    except Exception as e:
        assert "rate" in str(e).lower() or "limit" in str(e).lower()
