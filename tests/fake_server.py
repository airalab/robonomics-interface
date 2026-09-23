"""A JSON-RPC WebSocket server on localhost, answering like a Robonomics node."""

import asyncio
import contextlib
import json
import socket
from collections.abc import Callable
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

from fake_node import FakeNode


class Fault(Exception):
    """Raise from an override to answer with a JSON-RPC error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class FakeServer:
    def __init__(self, node: FakeNode | None = None) -> None:
        self.node = node or FakeNode()
        self.port = free_port()
        self.overrides: dict[str, Callable[[list[Any]], Any]] = {}
        self.delays: dict[str, float] = {}
        self.drop_on: set[str] = set()
        self.notify_before_answer = False
        self.received: list[str] = []
        self.connections: list[ServerConnection] = []
        self._server: Server | None = None
        self._subscriptions = 0

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    async def start(self) -> "FakeServer":
        self._server = await serve(self._handle, "127.0.0.1", self.port, max_size=None)
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def drop_all(self) -> None:
        for connection in list(self.connections):
            await connection.close()

    async def notify(self, subscription: str, method: str, result: Any) -> None:
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {"subscription": subscription, "result": result},
        }
        for connection in list(self.connections):
            with contextlib.suppress(Exception):
                await connection.send(json.dumps(message))

    async def _handle(self, connection: ServerConnection) -> None:
        self.connections.append(connection)
        tasks: set[asyncio.Task[None]] = set()
        try:
            async for raw in connection:
                message = json.loads(raw)
                self.received.append(message["method"])
                if message["method"] in self.drop_on:
                    await connection.close()
                    return
                task = asyncio.create_task(self._answer(connection, message))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        finally:
            self.connections.remove(connection)
            for task in tasks:
                task.cancel()

    async def _answer(self, connection: ServerConnection, message: dict[str, Any]) -> None:
        method, params = message["method"], message.get("params") or []
        await asyncio.sleep(self.delays.get(method, 0))
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
        notification: dict[str, Any] | None = None
        try:
            if method in self.overrides:
                reply["result"] = self.overrides[method](params)
            elif method == "state_subscribeRuntimeVersion":
                self._subscriptions += 1
                subscription = f"rv-{self._subscriptions}"
                reply["result"] = subscription
                notification = {
                    "jsonrpc": "2.0",
                    "method": "state_runtimeVersion",
                    "params": {
                        "subscription": subscription,
                        "result": self.node._state_getRuntimeVersion(),
                    },
                }
            elif method.endswith("unsubscribeRuntimeVersion"):
                reply["result"] = True
            else:
                reply["result"] = await self.node.request(method, params)
        except Fault as fault:
            reply = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": fault.code, "message": fault.message},
            }
        with contextlib.suppress(Exception):
            if notification is not None and self.notify_before_answer:
                await connection.send(json.dumps(notification))
                notification = None
            await connection.send(json.dumps(reply))
            if notification is not None:
                await connection.send(json.dumps(notification))
