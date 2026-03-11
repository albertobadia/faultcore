from faultcore.decorator import (
    apply_policy,
    burst_loss,
    connect_timeout,
    connection_error,
    correlated_loss,
    dns_delay,
    dns_nxdomain,
    dns_timeout,
    downlink,
    fault,
    for_target,
    get_policy,
    get_thread_policy,
    half_open,
    jitter,
    latency,
    list_policies,
    load_policies,
    packet_duplicate,
    packet_loss,
    packet_reorder,
    profile,
    rate_limit,
    recv_timeout,
    register_policy,
    set_thread_policy as _set_thread_policy,
    unregister_policy,
    uplink,
)


class fault_context:
    def __init__(self, policy_name: str | None = None, **_kwargs):
        self.policy_name = policy_name
        self._previous: str | None = None

    def __enter__(self):
        self._previous = get_thread_policy()
        _set_thread_policy(self.policy_name)
        return self

    def __exit__(self, *_args):
        _set_thread_policy(self._previous)

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        self.__exit__(*args)


def set_thread_policy(policy_name: str | None):
    _set_thread_policy(policy_name)


__all__ = [
    "connect_timeout",
    "recv_timeout",
    "latency",
    "jitter",
    "packet_loss",
    "burst_loss",
    "correlated_loss",
    "connection_error",
    "half_open",
    "dns_delay",
    "dns_timeout",
    "dns_nxdomain",
    "for_target",
    "packet_duplicate",
    "packet_reorder",
    "profile",
    "uplink",
    "downlink",
    "rate_limit",
    "register_policy",
    "list_policies",
    "get_policy",
    "unregister_policy",
    "load_policies",
    "apply_policy",
    "fault",
    "fault_context",
    "set_thread_policy",
]
