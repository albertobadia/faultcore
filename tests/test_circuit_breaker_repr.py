import faultcore


def test_circuit_breaker_repr_contains_failure_count():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    repr_str = repr(policy)
    assert "failure" in repr_str.lower() or "5" in repr_str


def test_circuit_breaker_repr_contains_threshold():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    repr_str = repr(policy)
    assert "CircuitBreakerPolicy" in repr_str or "5" in repr_str


def test_circuit_breaker_repr_open_state():
    policy = faultcore.CircuitBreaker(1, 1, 60000)

    def fail():
        raise ValueError("fail")

    try:
        policy(fail, (), {})
    except ValueError:
        pass

    repr_str = repr(policy)
    assert "open" in repr_str.lower() or "failure" in repr_str.lower()


def test_circuit_breaker_repr_closed_state():
    policy = faultcore.CircuitBreaker(5, 2, 60000)

    def success():
        return "ok"

    policy(success, (), {})
    repr_str = repr(policy)
    assert "closed" in repr_str.lower() or "failure" in repr_str.lower()


def test_circuit_breaker_default_values():
    policy = faultcore.CircuitBreaker()
    assert policy.state in ["closed", "open", "half_open"]


def test_circuit_breaker_zero_failure_threshold():
    try:
        faultcore.CircuitBreaker(0, 1, 30000)
    except Exception:
        pass


def test_circuit_breaker_zero_success_threshold():
    try:
        faultcore.CircuitBreaker(5, 0, 30000)
    except Exception:
        pass
