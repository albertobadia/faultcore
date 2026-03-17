import uuid
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any

from faultcore.decorator import (
    get_thread_policy,
    register_policy,
    set_thread_policy,
    unregister_policy,
)


class policy_context(AbstractContextManager, AbstractAsyncContextManager):
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

    def __enter__(self) -> "policy_context":
        self._previous = get_thread_policy()
        try:
            set_thread_policy(self._resolve_policy_name())
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        temp_policy = self._temporary_policy
        self._temporary_policy = None
        try:
            set_thread_policy(self._previous)
        finally:
            if temp_policy is not None:
                try:
                    unregister_policy(temp_policy)
                except Exception:
                    pass

    async def __aenter__(self) -> "policy_context":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


__all__ = [
    "policy_context",
]
