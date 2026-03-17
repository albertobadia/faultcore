import uuid
from typing import Any

from faultcore.decorator import (
    burst_loss,
    connection_error,
    correlated_loss,
    dns,
    downlink,
    fault,
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
    rate,
    register_policy,
    session_budget,
    set_thread_policy as _set_thread_policy,
    timeout,
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
        try:
            _set_thread_policy(self._resolve_policy_name())
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_args):
        temp_policy = self._temporary_policy
        self._temporary_policy = None
        try:
            _set_thread_policy(self._previous)
        finally:
            if temp_policy is not None:
                try:
                    unregister_policy(temp_policy)
                except Exception:
                    pass

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        self.__exit__(*args)


def set_thread_policy(policy_name: str | None) -> None:
    _set_thread_policy(policy_name)


__all__ = [
    "latency",
    "jitter",
    "packet_loss",
    "burst_loss",
    "rate",
    "timeout",
    "uplink",
    "downlink",
    "correlated_loss",
    "connection_error",
    "half_open",
    "packet_duplicate",
    "packet_reorder",
    "dns",
    "session_budget",
    "register_policy",
    "list_policies",
    "get_policy",
    "unregister_policy",
    "load_policies",
    "fault",
    "policy_context",
    "set_thread_policy",
    "get_thread_policy",
]
