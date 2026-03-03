import time

import faultcore


def test_circuit_breaker_success_threshold_zero():
    policy = faultcore.CircuitBreaker(failure_threshold=2, success_threshold=0, timeout_ms=1000)

    def success_func():
        return "ok"

    result = policy(success_func, (), {})
    assert result == "ok"
    assert policy.state == "closed"


def test_circuit_breaker_success_while_closed():
    policy = faultcore.CircuitBreaker(failure_threshold=5, success_threshold=2, timeout_ms=60000)

    def success_func():
        return "ok"

    for _ in range(10):
        result = policy(success_func, (), {})
        assert result == "ok"

    assert policy.state == "closed"


def test_circuit_breaker_single_failure_opens():
    policy = faultcore.CircuitBreaker(failure_threshold=1, success_threshold=1, timeout_ms=60000)

    def failing_func():
        raise ValueError("fail")

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    assert policy.state == "open"

    try:
        policy(failing_func, (), {})
        raise AssertionError("Should have raised")
    except Exception as e:
        assert "open" in str(e).lower() or "circuit" in str(e).lower()


def test_circuit_breaker_half_open_to_closed():
    policy = faultcore.CircuitBreaker(failure_threshold=1, success_threshold=2, timeout_ms=30)

    def failing_func():
        raise ValueError("fail")

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    assert policy.state == "open"

    time.sleep(0.05)

    def success_func():
        return "ok"

    result = policy(success_func, (), {})
    assert result == "ok"
    assert policy.state == "half_open"

    result = policy(success_func, (), {})
    assert result == "ok"
    assert policy.state == "closed"


def test_circuit_breaker_with_custom_failure_threshold():
    policy = faultcore.CircuitBreaker(failure_threshold=10, success_threshold=2, timeout_ms=60000)

    def failing_func():
        raise ValueError("fail")

    for _i in range(9):
        try:
            policy(failing_func, (), {})
        except ValueError:
            pass

    assert policy.state == "closed"

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    assert policy.state == "open"


def test_circuit_breaker_multiple_success_then_failure():
    policy = faultcore.CircuitBreaker(failure_threshold=3, success_threshold=2, timeout_ms=60000)

    def success_func():
        return "ok"

    for _ in range(5):
        result = policy(success_func, (), {})
        assert result == "ok"

    def failing_func():
        raise ValueError("fail")

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    assert policy.state == "closed"

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    assert policy.state == "closed"

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    assert policy.state == "open"


def test_circuit_breaker_repr_contains_failure_count():
    policy = faultcore.CircuitBreaker(failure_threshold=5, success_threshold=2, timeout_ms=30000)

    def failing_func():
        raise ValueError("fail")

    try:
        policy(failing_func, (), {})
    except ValueError:
        pass

    repr_str = repr(policy)
    assert "CircuitBreakerPolicy" in repr_str
    assert "failure" in repr_str.lower() or "5" in repr_str


def test_circuit_breaker_state_getter():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    assert policy.state == "closed"


def test_circuit_breaker_failure_threshold_getter():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    repr_str = repr(policy)
    assert "5" in repr_str
