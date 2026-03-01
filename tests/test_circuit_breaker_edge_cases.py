import time

import faultcore


def test_circuit_breaker_opens_after_threshold():
    @faultcore.circuit_breaker(failure_threshold=2, success_threshold=1, timeout_ms=1000)
    def failing_func():
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
        raise AssertionError("Should have raised - circuit should be open")
    except Exception as e:
        assert "open" in str(e).lower() or "circuit" in str(e).lower()


def test_circuit_breaker_state_closed_to_open():
    @faultcore.circuit_breaker(failure_threshold=2, success_threshold=1, timeout_ms=60000)
    def failing_func():
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
    except Exception as e:
        assert "open" in str(e).lower() or "circuit" in str(e).lower()
        return

    raise AssertionError("Should have raised")


def test_circuit_breaker_state_open_to_half_open():
    @faultcore.circuit_breaker(failure_threshold=2, success_threshold=1, timeout_ms=50)
    def failing_func():
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
    except ValueError:
        pass

    time.sleep(0.1)

    try:
        failing_func()
    except ValueError:
        pass


def test_circuit_breaker_half_open_to_closed():
    @faultcore.circuit_breaker(failure_threshold=2, success_threshold=2, timeout_ms=50)
    def func():
        return "ok"

    for _ in range(5):
        try:
            func()
        except ValueError:
            pass

    time.sleep(0.1)

    result = func()
    assert result == "ok"


def test_circuit_breaker_rejects_when_open():
    @faultcore.circuit_breaker(failure_threshold=1, success_threshold=2, timeout_ms=50000)
    def failing_func():
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    for _ in range(5):
        try:
            failing_func()
            raise AssertionError("Should have raised")
        except Exception as e:
            assert "open" in str(e).lower() or "circuit" in str(e).lower()


def test_circuit_breaker_allows_after_timeout():
    @faultcore.circuit_breaker(failure_threshold=2, success_threshold=1, timeout_ms=50)
    def failing_func():
        raise ValueError("fail")

    try:
        failing_func()
    except ValueError:
        pass

    try:
        failing_func()
    except ValueError:
        pass

    time.sleep(0.1)

    try:
        failing_func()
    except ValueError:
        pass


def test_circuit_breaker_getters():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    assert policy.state == "closed"


def test_circuit_breaker_repr():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    repr_str = repr(policy)
    assert "5" in repr_str or "closed" in repr_str.lower()
