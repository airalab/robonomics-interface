import asyncio

import pytest

from fake_node import FakeNode, recorded_metadata, recorded_runtime
from robonomicsinterface import (
    DecodeError,
    EncodeError,
    MetadataError,
    NoSuchConstant,
    NoSuchPallet,
    NoSuchStorage,
)
from robonomicsinterface.runtime import Runtime, RuntimeCache, RuntimeVersion

VERSION = RuntimeVersion("robonomics", 50, 4)


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


def test_pallets(runtime: Runtime) -> None:
    for name in ("System", "Balances", "Datalog", "RWS", "Launch", "DigitalTwin", "CPS"):
        assert name in runtime.pallet_names
    assert runtime.pallet_index("Datalog") == 51
    assert runtime.pallet_index("RWS") == 55
    assert "PubSub" not in runtime.pallet_names


def test_constants(runtime: Runtime) -> None:
    assert runtime.constant("Datalog", "WindowSize") == 128
    assert runtime.constant("RWS", "MaxDevicesAmount") == 32
    # 10u32 encodes as printable bytes ("\n\0\0\0"), which scalecodec used to turn into str.
    assert runtime.constant("RWS", "AuctionDuration") == 10
    assert runtime.constant("System", "SS58Prefix") == 32
    assert runtime.constant("Balances", "ExistentialDeposit") == 1000


def test_storage_entries(runtime: Runtime) -> None:
    item = runtime.storage_entry("Datalog", "DatalogItem")
    assert item.modifier == "Default"
    assert item.hashers == ("Twox64Concat",)
    assert len(item.key_types) == 1  # one (AccountId, u64) tuple

    assert runtime.storage_entry("RWS", "Ledger").modifier == "Optional"
    assert runtime.storage_entry("System", "Account").hashers == ("Blake2_128Concat",)
    number = runtime.storage_entry("System", "Number")
    assert not number.is_map
    assert number.key_types == ()
    assert runtime.storage_entry("Datalog", "DatalogItem") is item  # cached


def test_lookup_errors(runtime: Runtime) -> None:
    with pytest.raises(NoSuchPallet):
        runtime.storage_entry("PubSub", "Anything")
    with pytest.raises(NoSuchStorage):
        runtime.storage_entry("Datalog", "Nope")
    with pytest.raises(NoSuchConstant):
        runtime.constant("Datalog", "Nope")
    assert issubclass(NoSuchPallet, LookupError)


def test_encode_decode(runtime: Runtime) -> None:
    account = runtime.storage_entry("System", "Account").key_types[0]
    alice = "88dc3417d5058ec4b4503e0c12ea1a0a89be200fe98922423d4334014fa6b0ee"
    # Any SS58 format is accepted as input; output uses format 32.
    assert (
        runtime.encode(account, "5FA9nQDVg267DEd8m1ZypXLBnvN7SFxYwV7ndqSYGiN9TTpu").hex() == alice
    )
    assert runtime.decode(account, bytes.fromhex(alice)).startswith("4")

    with pytest.raises(EncodeError):
        runtime.encode(account, "not an address")
    with pytest.raises(DecodeError):
        runtime.decode(account, b"\x00" * 31)
    with pytest.raises(DecodeError):
        runtime.decode(account, b"\x00" * 33)  # trailing bytes are an error
    with pytest.raises(DecodeError):
        runtime.decode(account, "0xzz")


def test_bad_metadata() -> None:
    with pytest.raises(MetadataError):
        Runtime("0x1234", VERSION, "0x00")
    with pytest.raises(MetadataError):
        Runtime("0x6d657461" + "ff" * 8, VERSION, "0x00")


# Cache


class StubRuntime:
    """Stands in for Runtime where a test is about the cache, not parsing."""

    def __init__(self, metadata: str, version: RuntimeVersion, genesis: str, ss58: int) -> None:
        self.version = version
        self.genesis_hash = genesis


@pytest.fixture
def stub_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("robonomicsinterface.runtime.Runtime", StubRuntime)


async def test_cache_parses_real_metadata() -> None:
    node, cache = FakeNode(), RuntimeCache()
    runtime = await cache.get(node)
    assert isinstance(runtime, Runtime)
    assert runtime.constant("Datalog", "WindowSize") == 128


@pytest.mark.usefixtures("stub_parsing")
async def test_cache_fetches_metadata_once() -> None:
    node, cache = FakeNode(), RuntimeCache()
    first = await cache.get(node)
    second = await cache.get(node)
    assert first is second
    assert node.calls["state_getMetadata"] == 1
    assert node.calls["chain_getBlockHash"] == 2  # genesis once, the pinned block once


@pytest.mark.usefixtures("stub_parsing")
async def test_concurrent_misses_parse_once() -> None:
    node, cache = FakeNode(), RuntimeCache()
    runtimes = await asyncio.gather(*(cache.get(node) for _ in range(5)))
    assert all(r is runtimes[0] for r in runtimes)
    assert node.calls["state_getMetadata"] == 1


@pytest.mark.usefixtures("stub_parsing")
async def test_runtime_upgrade_loads_new_metadata() -> None:
    node, cache = FakeNode(), RuntimeCache()
    old = await cache.get(node)
    node.spec_version += 1
    new = await cache.get(node)
    assert new is not old
    assert new.version.spec_version == old.version.spec_version + 1
    assert node.calls["state_getMetadata"] == 2


@pytest.mark.usefixtures("stub_parsing")
async def test_cache_is_bounded() -> None:
    node, cache = FakeNode(), RuntimeCache(max_runtimes=2)
    first = await cache.get(node)
    for _ in range(2):
        node.spec_version += 1
        await cache.get(node)
    node.spec_version = first.version.spec_version
    assert await cache.get(node) is not first  # evicted, fetched again
    assert node.calls["state_getMetadata"] == 4


async def test_seeded_cache_needs_no_metadata() -> None:
    node, cache = FakeNode(), RuntimeCache()
    cache.add(recorded_runtime())
    await cache.get(node)
    assert node.calls["state_getMetadata"] == 0
    assert node.calls["chain_getBlockHash"] == 0


def test_metadata_fixture_is_v14() -> None:
    assert recorded_metadata().startswith("0x6d6574610e")
