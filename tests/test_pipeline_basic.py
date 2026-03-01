import time

from faultcore import network_queue


def test_qos_and_chaos():
    queue = network_queue(rate="100", capacity="100", latency_ms=50, packet_loss=0.0)

    start = time.time()

    # We simulate a decorated call
    @queue
    def network_call():
        return True

    res = network_call()
    duration = (time.time() - start) * 1000

    assert res is True
    print(f"Request took {duration:.2f}ms")
    assert duration >= 45.0, "Latency less than minimum"
    assert duration <= 150.0, "Latency too high"


if __name__ == "__main__":
    test_qos_and_chaos()
