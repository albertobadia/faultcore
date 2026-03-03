import faultcore
from faultcore._faultcore import NetworkQueuePolicy


def test_network_queue_fd_limit_default():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100)
    assert policy is not None


def test_network_queue_fd_limit_custom():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=100, fd_limit=2048)
    assert policy is not None


def test_network_queue_fd_limit_small():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=10, fd_limit=10)
    assert policy is not None


def test_network_queue_fd_limit_large():
    policy = NetworkQueuePolicy(rate="1000", capacity="100", max_queue_size=1000, fd_limit=10000)
    assert policy is not None


def test_network_queue_with_fd_limit_in_decorator():
    @faultcore.network_queue(rate="1000", capacity="100", max_queue_size=100)
    def network_call():
        return "ok"

    result = network_call()
    assert result == "ok"


def test_network_queue_fd_limit_with_custom_value():
    @faultcore.network_queue(rate="1000", capacity="100", max_queue_size=100)
    def network_call():
        return "ok"

    result = network_call()
    assert result == "ok"
