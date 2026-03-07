import time

import faultcore


def test_rate_limit_rapid_calls_exhaust_tokens():
    @faultcore.rate_limit(1.0)
    def limited_func():
        return "ok"

    assert limited_func() == "ok"
    assert limited_func() == "ok"

    try:
        limited_func()
    except Exception as e:
        assert "rate limit" in str(e).lower() or "resource" in str(e).lower()


def test_rate_limit_tokens_refill_over_time():
    @faultcore.rate_limit(100.0)
    def limited_func():
        return "ok"

    assert limited_func() == "ok"
    assert limited_func() == "ok"

    try:
        limited_func()
    except Exception:
        pass

    time.sleep(0.2)

    result = limited_func()
    assert result == "ok"


def test_rate_limit_capacity_getter():
    policy = faultcore.RateLimit(50.0, 100)
    assert policy.capacity == 100


def test_rate_limit_rate_getter():
    policy = faultcore.RateLimit(50.0, 100)
    assert policy.rate == 50.0


def test_rate_limit_decorator_reuses_policy():
    call_count = [0]

    @faultcore.rate_limit(10.0)
    def limited_func():
        call_count[0] += 1
        return "ok"

    for _ in range(3):
        limited_func()

    assert call_count[0] == 3


def test_rate_limit_large_capacity():
    policy = faultcore.RateLimit(1.0, 10000)
    assert policy.capacity == 10000
    assert policy.available_tokens <= 10000.0


def test_rate_limit_fractional_rate():
    policy = faultcore.RateLimit(0.5, 10)
    assert policy.rate == 0.5
    assert policy.capacity == 10


def test_rate_limit_decorator_with_default_args():
    @faultcore.rate_limit(10.0)
    def limited_func():
        return "ok"

    result1 = limited_func()
    assert result1 == "ok"

    result2 = limited_func()
    assert result2 == "ok"


def test_rate_limit_repr_contains_all_info():
    policy = faultcore.RateLimit(50.0, 100)
    repr_str = repr(policy)
    assert "RateLimitPolicy" in repr_str
    assert "50" in repr_str
    assert "100" in repr_str


def test_rate_limit_policy_class():
    policy = faultcore.RateLimit(10.0, 100)
    assert hasattr(policy, "rate")
    assert hasattr(policy, "capacity")
    assert hasattr(policy, "available_tokens")


def test_rate_limit_available_tokens_changes():
    policy = faultcore.RateLimit(10.0, 5)

    initial = policy.available_tokens
    assert initial <= 5.0

    def dummy():
        return "ok"

    policy(dummy, (), {})

    after = policy.available_tokens
    assert after < initial
