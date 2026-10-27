"""A JSON-RPC WebSocket server on localhost, answering like a Robonomics node."""

import asyncio
import contextlib
import json
import socket
from collections.abc import Callable
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

from conftest import load_fixture
from fake_node import FakeNode
from robonomicsinterface.storage import storage_prefix

EVENTS_KEY = "0x" + storage_prefix("System", "Events").hex()
BLOCKS: dict[str, Any] = load_fixture("event_samples.json")["blocks"]
VALID = "0x00" + "00" * 40


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
        # author_submitAndWatchExtrinsic: statuses sent after the subscription id.
        self.watch_script: list[Any] = []
        self.submitted: list[str] = []
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
            elif (
                method.endswith("unsubscribeRuntimeVersion") or method == "author_unwatchExtrinsic"
            ):
                reply["result"] = True
            elif method == "author_submitAndWatchExtrinsic":
                self.submitted.append(params[0])
                subscription = f"tx-{len(self.submitted)}"
                reply["result"] = subscription
                with contextlib.suppress(Exception):
                    await connection.send(json.dumps(reply))
                for status in self.watch_script:
                    await asyncio.sleep(0.01)
                    if status == "DROP":
                        await connection.close()
                        return
                    await connection.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "method": "author_extrinsicUpdate",
                                "params": {"subscription": subscription, "result": status},
                            }
                        )
                    )
                return
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


def install_chain(server: FakeServer) -> None:
    """Blocks from event_samples.json, with our extrinsic at the recorded index 2."""

    nonces = {"next": 0}

    def get_block(params: list[Any]) -> dict[str, Any]:
        block = next(b for b in BLOCKS.values() if b["hash"] == params[0])
        extrinsics = list(block["extrinsics"])
        if server.submitted:
            extrinsics[2] = server.submitted[-1]
        return {"block": {"header": {"number": hex(block["number"])}, "extrinsics": extrinsics}}

    def get_storage(params: list[Any]) -> Any:
        if params[0] == EVENTS_KEY and len(params) > 1:
            return next(b["events"] for b in BLOCKS.values() if b["hash"] == params[1])
        return server.node.storage.get(params[0])

    def next_index(params: list[Any]) -> int:
        nonce = nonces["next"]
        nonces["next"] += 1
        return nonce

    server.overrides.update(
        {
            "chain_getBlock": get_block,
            "state_getStorage": get_storage,
            "chain_getFinalizedHead": lambda params: "0x" + "22" * 32,
            "chain_getHeader": lambda params: {"number": hex(1000)},
            "system_accountNextIndex": next_index,
            "state_call": lambda params: VALID,
        }
    )
