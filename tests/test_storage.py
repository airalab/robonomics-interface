from typing import Any

import pytest

from fake_node import FakeNode, recorded_runtime
from robonomicsinterface import (
    DecodeError,
    EncodeError,
    Keypair,
    NoSuchPallet,
    NoSuchStorage,
    is_valid_address,
)
from robonomicsinterface.runtime import Runtime, RuntimeCache
from robonomicsinterface.storage import (
    HASHERS,
    constant,
    decode_storage_key,
    decode_storage_value,
    query,
    query_map,
    storage_key,
    storage_prefix,
    twox128,
)


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


@pytest.fixture
def node() -> FakeNode:
    return FakeNode()


@pytest.fixture
def cache() -> RuntimeCache:
    cache = RuntimeCache()
    cache.add(recorded_runtime())
    return cache


# Hashers and keys


def test_well_known_prefixes() -> None:
    assert twox128(b"System").hex() == "26aa394eea5630e07c48ae0c9558cef7"
    assert storage_prefix("System", "Number").hex() == (
        "26aa394eea5630e07c48ae0c9558cef702a5c1b19ab7a04f536c519aca4983ac"
    )
    assert storage_prefix("Timestamp", "Now").hex() == (
        "f0c365c3cf59d671eb72da0e7a4113c49f1f0515f462cdcf84e0f1d6045dfcbb"
    )


def test_hasher_shapes() -> None:
    data = b"robonomics"
    assert HASHERS["Identity"](data) == data
    assert HASHERS["Twox64Concat"](data)[8:] == data
    assert HASHERS["Blake2_128Concat"](data)[16:] == data
    assert len(HASHERS["Twox128"](data)) == 16
    assert len(HASHERS["Twox256"](data)) == 32
    assert HASHERS["Twox256"](data)[:16] == HASHERS["Twox128"](data)
    assert len(HASHERS["Blake2_128"](data)) == 16
    assert len(HASHERS["Blake2_256"](data)) == 32
    assert HASHERS["Twox64Concat"](b"")[:8].hex() == "99e9d85137db46ef"  # xxh64("", 0), LE


def test_recorded_keys_round_trip(runtime: Runtime, node: FakeNode) -> None:
    """Every key recorded from mainnet decodes, and rebuilds to the same bytes."""

    for item in node.samples["maps"]:
        entry = runtime.storage_entry(item["pallet"], item["item"])
        assert item["entries"], f"no samples for {item['pallet']}.{item['item']}"
        for key, raw in item["entries"]:
            keys = decode_storage_key(runtime, entry, key)
            assert "0x" + storage_key(runtime, entry, keys).hex() == key
            decode_storage_value(runtime, entry, raw)


def test_tuple_key_takes_parts_or_tuple(runtime: Runtime) -> None:
    entry = runtime.storage_entry("Datalog", "DatalogItem")
    address = Keypair.from_uri("//Alice").address
    assert storage_key(runtime, entry, [address, 5]) == storage_key(runtime, entry, [(address, 5)])


def test_partial_key_is_a_prefix(runtime: Runtime) -> None:
    entry = runtime.storage_entry("RWS", "Devices")
    assert storage_key(runtime, entry, []) == storage_prefix("RWS", "Devices")


def test_key_errors(runtime: Runtime) -> None:
    entry = runtime.storage_entry("RWS", "Devices")
    with pytest.raises(EncodeError):
        storage_key(runtime, entry, ["not an address"])
    with pytest.raises(DecodeError, match="not under"):
        decode_storage_key(runtime, entry, "0x" + storage_prefix("RWS", "Ledger").hex())


def test_absent_values(runtime: Runtime) -> None:
    assert decode_storage_value(runtime, runtime.storage_entry("RWS", "Ledger"), None) is None
    index = decode_storage_value(runtime, runtime.storage_entry("Datalog", "DatalogIndex"), None)
    assert index == {"start": 0, "end": 0}
    assert decode_storage_value(runtime, runtime.storage_entry("RWS", "Devices"), None) == []


# Queries against recorded state


async def test_plain_value(node: FakeNode, cache: RuntimeCache) -> None:
    raw = next(v["raw"] for v in node.samples["values"] if v["item"] == "Number")
    node.add_value("0x" + storage_prefix("System", "Number").hex(), raw)
    assert await query(node, cache, "System", "Number") == node.samples["block_number"]


async def test_map_values(node: FakeNode, cache: RuntimeCache, runtime: Runtime) -> None:
    ledger = next(i for i in node.samples["maps"] if i["item"] == "Ledger")
    (owner,) = decode_storage_key(
        runtime, runtime.storage_entry("RWS", "Ledger"), ledger["entries"][0][0]
    )

    value = await query(node, cache, "RWS", "Ledger", owner)
    assert set(value) == {"free_weight", "issue_time", "last_update", "kind"}
    assert await query(node, cache, "RWS", "Ledger", Keypair.from_uri("//Nobody").address) is None


async def test_datalog_item(node: FakeNode, cache: RuntimeCache, runtime: Runtime) -> None:
    items = next(i for i in node.samples["maps"] if i["item"] == "DatalogItem")
    entry = runtime.storage_entry("Datalog", "DatalogItem")
    ((address, index),) = decode_storage_key(runtime, entry, items["entries"][0][0])

    by_parts = await query(node, cache, "Datalog", "DatalogItem", address, index)
    by_tuple = await query(node, cache, "Datalog", "DatalogItem", (address, index))
    assert by_parts == by_tuple
    timestamp, _record = by_parts
    assert timestamp > 1_600_000_000_000  # milliseconds


async def test_query_map_all_pages(node: FakeNode, cache: RuntimeCache) -> None:
    whole = [entry async for entry in query_map(node, cache, "RWS", "Devices")]
    paged = [entry async for entry in query_map(node, cache, "RWS", "Devices", page_size=1)]
    assert whole == paged
    assert len(whole) == 3
    for (owner,), devices in whole:
        assert is_valid_address(owner)
        assert all(is_valid_address(device) for device in devices)
    assert node.calls["state_getKeysPaged"] == 1 + 4  # one page, then 3 pages of 1 and an empty one


async def test_query_map_pins_one_block(node: FakeNode, cache: RuntimeCache) -> None:
    seen: list[Any] = []
    original = node._state_getKeysPaged

    def spy(prefix: str, count: int, start: str | None, at: str | None = None) -> list[str]:
        seen.append(at)
        return original(prefix, count, start, at)

    node._state_getKeysPaged = spy  # type: ignore[method-assign]
    _ = [entry async for entry in query_map(node, cache, "System", "Account", page_size=1)]
    assert set(seen) == {node.samples["block_hash"]}


async def test_constant(node: FakeNode, cache: RuntimeCache) -> None:
    assert await constant(node, cache, "Datalog", "WindowSize") == 128


async def test_query_errors(node: FakeNode, cache: RuntimeCache) -> None:
    with pytest.raises(NoSuchPallet):
        await query(node, cache, "PubSub", "Topics")
    with pytest.raises(NoSuchStorage):
        await query(node, cache, "Datalog", "Nope")
    with pytest.raises(EncodeError, match="takes 1 key"):
        await query(node, cache, "RWS", "Ledger")
    with pytest.raises(EncodeError, match="plain value"):
        _ = [entry async for entry in query_map(node, cache, "System", "Number")]
    with pytest.raises(ValueError, match="page_size"):
        _ = [entry async for entry in query_map(node, cache, "RWS", "Devices", page_size=0)]
