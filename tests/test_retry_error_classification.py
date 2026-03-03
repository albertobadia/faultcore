import faultcore


def test_retry_with_key_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise KeyError("key not found")

    try:
        failing_func()
    except KeyError:
        pass

    assert call_count == 3


def test_retry_with_oserror():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise OSError("system error")

    try:
        failing_func()
    except OSError:
        pass

    assert call_count == 3


def test_retry_with_ioerror():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise OSError("io error")

    try:
        failing_func()
    except OSError:
        pass

    assert call_count == 3


def test_retry_with_attribute_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise AttributeError("attribute error")

    try:
        failing_func()
    except AttributeError:
        pass

    assert call_count == 3


def test_retry_error_classification_key_error():
    class KeyNotFoundError(Exception):
        pass

    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise KeyNotFoundError("key not found")

    try:
        failing_func()
    except KeyNotFoundError:
        pass

    assert call_count == 3


def test_retry_error_classification_io_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OSError("io error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_error_classification_os_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OSError("os error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3


def test_retry_error_classification_permission_error():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise PermissionError("permission denied")

    try:
        failing_func()
    except PermissionError:
        pass

    assert call_count == 3


def test_retry_error_classification_file_not_found():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        raise FileNotFoundError("file not found")

    try:
        failing_func()
    except FileNotFoundError:
        pass

    assert call_count == 3


def test_retry_error_classification_exception_chain():
    call_count = 0

    @faultcore.retry(2, backoff_ms=10)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("original error")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3
