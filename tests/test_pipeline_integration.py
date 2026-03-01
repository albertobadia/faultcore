import time

from faultcore import network_queue


def test_pipeline():
    queue = network_queue(rate="100", capacity="100", latency_ms=50, packet_loss=0.0)

    @queue
    def do_work():
        return "Success"

    start = time.time()
    res = do_work()
    duration = (time.time() - start) * 1000

    print(f"Result: {res}")
    print(f"Time taken: {duration:.2f}ms")
    assert duration >= 45.0, "Latency applied by pipeline is too low"


if __name__ == "__main__":
    test_pipeline()
    print("Integration test passed.")
