"""One JSON-RPC connection over a WebSocket, multiplexed.

A single reader task owns the socket: answers are matched to their requests by
id, and subscription notifications are routed to their :class:`Subscription`.
Many requests can be in flight at once, from any number of tasks. When the
socket closes, every pending request and open subscription fails with
:class:`~robonomicsinterface.errors.ConnectionLost`.

This module knows nothing about endpoints, retries or node health; the client
builds those on top.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
import ssl as ssl_module
from collections import deque
from typing import Any, Self

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from .errors import ConnectionFailed, ConnectionLost, RequestTimeout, RpcError

__all__ = ["Connection", "Subscription"]

LOGGER = logging.getLogger(__name__)

# Runtime metadata alone is well over the websockets default of 1 MiB.
DEFAULT_MAX_MESSAGE_BYTES = 64 * 1024 * 1024
# Notifications that arrive before their subscription is registered.
_EARLY_PER_SUBSCRIPTION = 64
_EARLY_SUBSCRIPTIONS = 32


class Subscription:
    """A stream of notifications for one server-side subscription.

    Iterate with ``async for``; iteration ends with ``ConnectionLost`` if the
    connection drops. Close it (or use ``async with``) to unsubscribe.
    """

    def __init__(self, connection: Connection, subscription_id: str, unsubscribe: str) -> None:
        self.connection = connection
        self.id = subscription_id
        self._unsubscribe = unsubscribe
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._closed = False

    def _push(self, item: Any) -> None:
        if not self._closed:
            self._queue.put_nowait(item)

    async def next(self, timeout: float | None = None) -> Any:
        """The next notification; ``RequestTimeout`` if none arrives in time."""

        if self._closed and self._queue.empty():
            raise ConnectionLost("the subscription is closed")
        try:
            async with asyncio.timeout(timeout):
                item = await self._queue.get()
        except TimeoutError:
            raise RequestTimeout(f"no notification within {timeout}s") from None
        if isinstance(item, BaseException):
            raise item
        return item

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Any:
        return await self.next()

    async def close(self) -> None:
        """Unsubscribe; errors are ignored, as the connection may already be gone."""

        if self._closed:
            return
        self._closed = True
        self.connection._forget(self.id)
        if not self.connection.closed:
            with contextlib.suppress(ConnectionLost, RequestTimeout, RpcError):
                await self.connection.request(self._unsubscribe, [self.id], timeout=5)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


class Connection:
    """A WebSocket to one node; build it with :meth:`open`."""

    def __init__(self, endpoint: str, socket: ClientConnection, timeout: float) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._socket = socket
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._early: dict[str, deque[Any]] = {}
        self._finished: deque[str] = deque(maxlen=_EARLY_SUBSCRIPTIONS)
        self._closed = asyncio.Event()
        self._reader = asyncio.create_task(self._read(), name=f"robonomics-reader {endpoint}")

    @classmethod
    async def open(
        cls,
        endpoint: str,
        *,
        timeout: float = 30.0,
        connect_timeout: float = 10.0,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
        ssl: ssl_module.SSLContext | None = None,
        user_agent: str | None = None,
    ) -> Connection:
        """Open a WebSocket; failures are reported as ``ConnectionFailed``."""

        options: dict[str, Any] = {
            "open_timeout": connect_timeout,
            "max_size": max_message_bytes,
            "close_timeout": 5,
        }
        if user_agent:
            options["user_agent_header"] = user_agent
        if ssl is not None and endpoint.startswith("wss://"):
            options["ssl"] = ssl
        try:
            socket = await connect(endpoint, **options)
        except InvalidURI:
            raise ConnectionFailed(endpoint, "not a ws:// or wss:// URL") from None
        except TimeoutError:
            raise ConnectionFailed(endpoint, f"no connection within {connect_timeout}s") from None
        except (OSError, InvalidHandshake) as e:
            raise ConnectionFailed(endpoint, f"cannot connect ({e})") from e
        return cls(endpoint, socket, timeout)

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    @property
    def busy(self) -> bool:
        """Whether requests or subscriptions are still in flight."""

        return bool(self._pending or self._subscriptions)

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def request(
        self, method: str, params: list[Any] | None = None, timeout: float | None = None
    ) -> Any:
        """Send one request and wait for its answer."""

        if self.closed:
            raise ConnectionLost(f"the connection to {self.endpoint} is closed")
        request_id = next(self._ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or []}
        )
        limit = self.timeout if timeout is None else timeout
        try:
            async with asyncio.timeout(limit):
                try:
                    await self._socket.send(payload)
                except ConnectionClosed:
                    raise ConnectionLost(f"the connection to {self.endpoint} closed") from None
                answer = await future
        except TimeoutError:
            raise RequestTimeout(f"{method}: no answer from {self.endpoint} in {limit}s") from None
        finally:
            self._pending.pop(request_id, None)

        if "error" in answer:
            error = answer["error"] if isinstance(answer["error"], dict) else {}
            raise RpcError(
                method,
                error.get("code"),
                str(error.get("message", "unknown error")),
                error.get("data"),
            )
        return answer.get("result")

    async def subscribe(
        self, method: str, params: list[Any] | None, unsubscribe: str
    ) -> Subscription:
        """Start a subscription (``author_submitAndWatchExtrinsic`` and the like)."""

        subscription_id = await self.request(method, params)
        if not isinstance(subscription_id, (str, int)):
            raise RpcError(method, None, "the node returned no subscription id")
        key = str(subscription_id)
        subscription = Subscription(self, key, unsubscribe)
        self._subscriptions[key] = subscription
        for item in self._early.pop(key, ()):
            subscription._push(item)
        if self.closed:
            subscription._push(ConnectionLost(f"the connection to {self.endpoint} closed"))
        return subscription

    def _forget(self, subscription_id: str) -> None:
        # Notifications may still arrive after unsubscribing; remember the id
        # so they are dropped instead of filling the early-notification buffer.
        self._subscriptions.pop(subscription_id, None)
        self._finished.append(subscription_id)

    async def close(self) -> None:
        await self._socket.close()
        with contextlib.suppress(asyncio.CancelledError):
            await self._reader

    # Reading

    async def _read(self) -> None:
        try:
            async for raw in self._socket:
                self._dispatch(raw)
        except ConnectionClosed:
            pass
        except Exception:  # never let the reader die silently
            LOGGER.exception("reader for %s failed", self.endpoint)
        finally:
            self._closed.set()
            lost = ConnectionLost(f"the connection to {self.endpoint} closed")
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(lost)
            for subscription in list(self._subscriptions.values()):
                subscription._push(lost)
            self._pending.clear()

    def _dispatch(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            LOGGER.warning("ignoring a non-JSON message from %s", self.endpoint)
            return
        if not isinstance(message, dict):
            return

        request_id = message.get("id")
        if request_id is not None:
            future = self._pending.get(request_id) if isinstance(request_id, int) else None
            if future is not None and not future.done():
                future.set_result(message)
            return

        params = message.get("params")
        if not isinstance(params, dict) or "subscription" not in params:
            return
        key = str(params["subscription"])
        result = params.get("result")
        subscription = self._subscriptions.get(key)
        if subscription is not None:
            subscription._push(result)
        elif key in self._finished:
            return
        elif key in self._early or len(self._early) < _EARLY_SUBSCRIPTIONS:
            self._early.setdefault(key, deque(maxlen=_EARLY_PER_SUBSCRIPTION)).append(result)
