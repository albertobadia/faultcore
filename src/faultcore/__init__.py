import uuid
from typing import Any

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


class policy_context:
    def __init__(self, policy_name: str | None = None, **policy_kwargs: Any):
        if policy_name is not None and policy_kwargs:
            raise ValueError("policy_context accepts either policy_name or policy kwargs, not both")
        self.policy_name = policy_name
        self.policy_kwargs = policy_kwargs
        self._previous: str | None = None
        self._temporary_policy: str | None = None

    def _resolve_policy_name(self) -> str | None:
        if self.policy_name is not None:
            return self.policy_name
        if not self.policy_kwargs:
            return None
        self._temporary_policy = f"__faultcore_temp_{uuid.uuid4().hex}"
        register_policy(self._temporary_policy, **self.policy_kwargs)
        return self._temporary_policy

    def __enter__(self):
        self._previous = get_thread_policy()
        _set_thread_policy(self._resolve_policy_name())
        return self

    def __exit__(self, *_args):
        try:
            _set_thread_policy(self._previous)
        finally:
            if self._temporary_policy is not None:
                unregister_policy(self._temporary_policy)
                self._temporary_policy = None

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        self.__exit__(*args)


class fault_context(policy_context):
    pass


def set_thread_policy(policy_name: str | None) -> None:
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
    "policy_context",
    "fault_context",
    "set_thread_policy",
]
