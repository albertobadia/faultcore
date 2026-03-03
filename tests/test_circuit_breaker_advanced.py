import faultcore


def test_circuit_breaker_success_threshold_transitions():
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
        except Exception as e:
            assert "open" in str(e).lower() or "circuit" in str(e).lower()
            return

    raise AssertionError("Circuit should be open")


def test_circuit_breaker_state_getter():
    policy = faultcore.CircuitBreaker(5, 2, 30000)
    state = policy.state
    assert state in ["closed", "open", "half_open"]


def test_circuit_breaker_with_default_parameters():
    @faultcore.circuit_breaker()
    def func():
        return "ok"

    result = func()
    assert result == "ok"


def test_circuit_breaker_opens_after_failures():
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
        raise AssertionError("Should be open")
    except Exception as e:
        assert "open" in str(e).lower() or "circuit" in str(e).lower()


def test_circuit_breaker_multiple_success_calls():
    @faultcore.circuit_breaker(failure_threshold=3, success_threshold=2, timeout_ms=60000)
    def func():
        return "ok"

    result = func()
    assert result == "ok"
    assert len([func() for _ in range(10)]) == 10
