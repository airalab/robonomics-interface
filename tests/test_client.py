"""The client over real WebSockets, against local fake nodes."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from fake_node import recorded_runtime
from fake_server import FakeServer, Fault, free_port
from robonomicsinterface import (
    AllEndpointsFailed,
    ConnectionLost,
    RequestTimeout,
    RobonomicsClient,
    RpcError,
    TransportError,
)
from robonomicsinterface.storage import storage_prefix
from robonomicsinterface.transport import Connection

NUMBER_KEY = "0x" + storage_prefix("System", "Number").hex()


@pytest.fixture
async def server() -> AsyncIterator[FakeServer]:
    server = await FakeServer().start()
    raw = next(v["raw"] for v in server.node.samples["values"] if v["item"] == "Number")
    server.node.add_value(NUMBER_KEY, raw)
    yield server
    await server.stop()


@pytest.fixture
async def second() -> AsyncIterator[FakeServer]:
    server = await FakeServer().start()
    yield server
    await server.stop()


def client_for(*urls: str, **options: object) -> RobonomicsClient:
    options.setdefault("timeout", 2.0)
    options.setdefault("connect_timeout", 2.0)
    client = RobonomicsClient(list(urls), **options)  # type: ignore[arg-type]
    client.runtimes.add(recorded_runtime())
    return client


def dead_url() -> str:
    return f"ws://127.0.0.1:{free_port()}"


# Basics


async def test_query_over_websocket(server: FakeServer) -> None:
    async with client_for(server.url) as client:
        assert client.endpoint == server.url
        assert await client.query("System", "Number") == server.node.samples["block_number"]
        assert await client.constant("Datalog", "WindowSize") == 128
    assert client.endpoint is None


async def test_requests_are_multiplexed(server: FakeServer) -> None:
    server.delays["chain_getHeader"] = 0.3
    server.overrides["chain_getHeader"] = lambda params: {"number": "0x1"}
    async with client_for(server.url) as client:
        order: list[str] = []

        async def call(method: str, params: list[object]) -> None:
            await client.request(method, params)
            order.append(method)

        await asyncio.gather(call("chain_getHeader", []), call("chain_getBlockHash", [0]))
        assert order == ["chain_getBlockHash", "chain_getHeader"]


async def test_rpc_error_is_not_retried(server: FakeServer) -> None:
    def refuse(params: list[object]) -> object:
        raise Fault(-32601, "Method not found")

    server.overrides["author_rotateKeys"] = refuse
    async with client_for(server.url) as client:
        with pytest.raises(RpcError) as error:
            await client.request("author_rotateKeys")
        assert error.value.code == -32601
        assert not isinstance(error.value, TransportError)
    assert server.received.count("author_rotateKeys") == 1


async def test_timeout(server: FakeServer) -> None:
    server.delays["chain_getHeader"] = 1.0
    async with client_for(server.url, timeout=0.2, retries=0) as client:
        with pytest.raises(RequestTimeout, match="chain_getHeader"):
            await client.request("chain_getHeader")
        # The client reconnects for the next request.
        assert await client.request("chain_getBlockHash", [0])


async def test_runtime_version_subscription_saves_requests(server: FakeServer) -> None:
    async with client_for(server.url) as client:
        for _ in range(20):
            if client.runtimes._current is not None:
                break
            await asyncio.sleep(0.01)
        await client.query("System", "Number")
        await client.query("System", "Number")
    assert "state_getRuntimeVersion" not in server.received


# Choosing endpoints


async def test_first_usable_endpoint_wins(server: FakeServer) -> None:
    async with client_for(dead_url(), server.url) as client:
        assert client.endpoint == server.url


async def test_wrong_chain_is_skipped(server: FakeServer, second: FakeServer) -> None:
    second.overrides["chain_getBlockHash"] = lambda params: "0x" + "ab" * 32
    async with client_for(second.url, server.url) as client:
        assert client.endpoint == server.url


async def test_syncing_node_is_skipped(server: FakeServer, second: FakeServer) -> None:
    second.overrides["system_health"] = lambda params: {
        "peers": 5,
        "isSyncing": True,
        "shouldHavePeers": True,
    }
    async with client_for(second.url, server.url) as client:
        assert client.endpoint == server.url


async def test_node_without_peers_is_skipped(server: FakeServer, second: FakeServer) -> None:
    second.overrides["system_health"] = lambda params: {
        "peers": 0,
        "isSyncing": False,
        "shouldHavePeers": True,
    }
    async with client_for(second.url, server.url) as client:
        assert client.endpoint == server.url


async def test_dev_chain_accepted_when_asked(second: FakeServer) -> None:
    second.overrides["chain_getBlockHash"] = lambda params: "0x" + "ab" * 32
    second.overrides["system_health"] = lambda params: {
        "peers": 0,
        "isSyncing": False,
        "shouldHavePeers": False,
    }
    async with client_for(second.url, genesis_hash=None) as client:
        assert client.endpoint == second.url


async def test_all_endpoints_failed_says_why(second: FakeServer) -> None:
    second.overrides["chain_getBlockHash"] = lambda params: "0x" + "ab" * 32
    dead = dead_url()
    client = client_for(dead, second.url, "https://not-a-websocket.example")
    with pytest.raises(AllEndpointsFailed) as error:
        await client.connect()
    reasons = {failure.endpoint: failure.reason for failure in error.value.failures}
    assert "cannot connect" in reasons[dead]
    assert "wrong chain" in reasons[second.url]
    assert "ws://" in reasons["https://not-a-websocket.example"]
    assert error.value.retryable
    await client.close()


# Failures in flight


async def test_lost_connection_retries_on_next_endpoint(
    server: FakeServer, second: FakeServer
) -> None:
    server.drop_on.add("chain_getHeader")
    second.overrides["chain_getHeader"] = lambda params: {"number": "0x2"}
    async with client_for(server.url, second.url) as client:
        assert client.endpoint == server.url
        assert await client.request("chain_getHeader") == {"number": "0x2"}
        assert client.endpoint == second.url


async def test_no_retry_for_side_effects(server: FakeServer, second: FakeServer) -> None:
    server.drop_on.add("author_submitExtrinsic")
    async with client_for(server.url, second.url) as client:
        with pytest.raises(ConnectionLost):
            await client.request("author_submitExtrinsic", ["0x00"], retry=False)
    assert "author_submitExtrinsic" not in second.received


async def test_reconnects_after_idle_drop(server: FakeServer) -> None:
    async with client_for(server.url) as client:
        await server.drop_all()
        await asyncio.sleep(0.05)
        assert await client.query("System", "Number") == server.node.samples["block_number"]


async def test_fails_back_to_preferred_endpoint(second: FakeServer) -> None:
    preferred = FakeServer()
    async with client_for(preferred.url, second.url, failback_interval=0.2) as client:
        assert client.endpoint == second.url
        await preferred.start()
        try:
            for _ in range(50):
                if client.endpoint == preferred.url:
                    break
                await asyncio.sleep(0.05)
            assert client.endpoint == preferred.url
            await client.request("chain_getBlockHash", [0])
            for _ in range(50):  # the replaced connection is retired once idle
                if not second.connections:
                    break
                await asyncio.sleep(0.05)
            assert not second.connections
        finally:
            await preferred.stop()


# Subscriptions


async def test_subscription_and_early_notifications(server: FakeServer) -> None:
    server.notify_before_answer = True
    connection = await Connection.open(server.url)
    try:
        subscription = await connection.subscribe(
            "state_subscribeRuntimeVersion", [], "state_unsubscribeRuntimeVersion"
        )
        version = await subscription.next(timeout=1)
        assert version["specVersion"] == server.node.spec_version

        await server.notify(subscription.id, "state_runtimeVersion", {"specVersion": 99})
        assert (await subscription.next(timeout=1))["specVersion"] == 99
        await subscription.close()
        assert not connection.busy
    finally:
        await connection.close()


async def test_subscription_ends_with_connection_lost(server: FakeServer) -> None:
    connection = await Connection.open(server.url)
    subscription = await connection.subscribe(
        "state_subscribeRuntimeVersion", [], "state_unsubscribeRuntimeVersion"
    )
    await subscription.next(timeout=1)
    await server.drop_all()
    with pytest.raises(ConnectionLost):
        await subscription.next(timeout=1)
    with pytest.raises(ConnectionLost):
        await connection.request("chain_getBlockHash", [0])


async def test_subscription_timeout(server: FakeServer) -> None:
    connection = await Connection.open(server.url)
    try:
        subscription = await connection.subscribe(
            "state_subscribeRuntimeVersion", [], "state_unsubscribeRuntimeVersion"
        )
        await subscription.next(timeout=1)
        with pytest.raises(RequestTimeout):
            await subscription.next(timeout=0.05)
    finally:
        await connection.close()


# Configuration


def test_configuration_errors() -> None:
    with pytest.raises(ValueError):
        RobonomicsClient([])
    with pytest.raises(ValueError):
        RobonomicsClient(retries=-1)
    assert RobonomicsClient().endpoints == ("wss://polkadot.rpc.robonomics.network/",)
