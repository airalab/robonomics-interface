"""The blocking wrapper, and its parity with the async API."""

import asyncio
import inspect
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from fake_node import recorded_runtime
from fake_server import BLOCKS, FakeServer, Fault, install_chain
from robonomicsinterface import Keypair, RobonomicsClient, RpcError
from robonomicsinterface.pallets import RWS, Balances, Chain, Datalog, System
from robonomicsinterface.sync import (
    RobonomicsSync,
    SyncBalances,
    SyncChain,
    SyncDatalog,
    SyncRWS,
    SyncSystem,
)

SITE = Keypair.from_uri("//Site")
OWNER = "4H13HaTutSqePohv26FB9sXwQvWbrXBEHaZYE8mYo2744qjU"

# Async-only by nature: lifecycle is covered by connect/close/with, and a
# subscription is a stream that belongs to an event loop.
ASYNC_ONLY = {"subscribe"}


def public_async_methods(cls: type) -> dict[str, inspect.Signature]:
    methods = {}
    for name, member in inspect.getmembers(cls):
        if name.startswith("_") or name in ASYNC_ONLY:
            continue
        if inspect.iscoroutinefunction(member) or name == "query_map":
            methods[name] = inspect.signature(member)
    return methods


def shape(signature: inspect.Signature) -> list[tuple[str, Any, Any]]:
    return [(p.name, p.kind, p.default) for p in signature.parameters.values()]


@pytest.mark.parametrize(
    ("async_cls", "sync_cls"),
    [
        (RobonomicsClient, RobonomicsSync),
        (Datalog, SyncDatalog),
        (RWS, SyncRWS),
        (System, SyncSystem),
        (Balances, SyncBalances),
        (Chain, SyncChain),
    ],
)
def test_every_async_method_has_a_sync_twin(async_cls: type, sync_cls: type) -> None:
    methods = public_async_methods(async_cls)
    assert methods, f"no async methods found on {async_cls.__name__}"
    for name, signature in methods.items():
        twin = getattr(sync_cls, name, None)
        assert twin is not None, f"{sync_cls.__name__} lacks {name}"
        assert not inspect.iscoroutinefunction(twin), f"{sync_cls.__name__}.{name} is async"
        assert shape(inspect.signature(twin)) == shape(signature), f"{name} differs"


def test_parity_covers_the_main_api() -> None:
    names = set(public_async_methods(RobonomicsClient))
    assert {"query", "query_map", "constant", "compose_call", "submit", "sign"} <= names


# Against a fake node running in its own thread


class ServerThread:
    """FakeServer on its own loop, so blocking calls in the test thread do not stall it."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.server: FakeServer = self.run(self._start())

    async def _start(self) -> FakeServer:
        server = await FakeServer().start()
        install_chain(server)
        return server

    def run(self, coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=10)

    def stop(self) -> None:
        self.run(self.server.stop())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()


@pytest.fixture
def node() -> Iterator[FakeServer]:
    thread = ServerThread()
    yield thread.server
    thread.stop()


@pytest.fixture
def client(node: FakeServer) -> Iterator[RobonomicsSync]:
    client = RobonomicsSync(node.url, timeout=2, connect_timeout=2)
    client.client.runtimes.add(recorded_runtime())
    with client:
        yield client


def test_reads(node: FakeServer, client: RobonomicsSync) -> None:
    assert client.endpoint == node.url
    assert client.constant("Datalog", "WindowSize") == 128
    assert client.datalog.items(SITE) == []
    assert client.rws.ledger(SITE) is None
    assert not client.system.exists(SITE)
    assert client.chain.block_number() == 1000


def test_query_map(client: RobonomicsSync) -> None:
    entries = list(client.query_map("RWS", "Devices", page_size=1))
    assert len(entries) == 3
    first = next(iter(client.query_map("RWS", "Devices", page_size=1)))  # abandoned early
    assert first == entries[0]


def test_submit(node: FakeServer, client: RobonomicsSync) -> None:
    node.watch_script = [{"inBlock": BLOCKS["successful_rws_call"]["hash"]}]
    result = client.datalog.record(SITE, b"report", subscription_owner=OWNER)
    assert result.find("Datalog", "NewRecord") is not None


def test_errors_propagate(node: FakeServer, client: RobonomicsSync) -> None:
    def refuse(params: list[Any]) -> None:
        raise Fault(-32601, "Method not found")

    node.overrides["author_rotateKeys"] = refuse
    with pytest.raises(RpcError):
        client.request("author_rotateKeys")


def test_closed_client_refuses(node: FakeServer) -> None:
    client = RobonomicsSync(node.url).connect()
    client.close()
    client.close()  # idempotent
    with pytest.raises(RuntimeError, match="closed"):
        client.constant("Datalog", "WindowSize")


async def test_refuses_to_block_an_event_loop(node: FakeServer) -> None:
    client = RobonomicsSync(node.url)
    try:
        with pytest.raises(RuntimeError, match="await"):
            client.constant("Datalog", "WindowSize")
    finally:
        await asyncio.to_thread(client.close)
