"""The one thing the chain-facing modules need from a connection."""

from typing import Any, Protocol

__all__ = ["RpcRequester"]


class RpcRequester(Protocol):
    """Anything that can send a JSON-RPC request to a node and return its result.

    The transport implements it; tests implement it with recorded answers.
    Errors are raised as :class:`~robonomicsinterface.errors.RobonomicsError`
    subclasses by the implementation.
    """

    async def request(self, method: str, params: list[Any] | None = None) -> Any: ...
