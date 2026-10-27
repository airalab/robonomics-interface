"""client.datalog, client.rws, client.system, client.balances, client.chain."""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from fake_node import recorded_runtime
from fake_server import BLOCKS, FakeServer, install_chain
from robonomicsinterface import (
    DecodeError,
    EncodeError,
    InvalidAddress,
    Keypair,
    Ledger,
    RobonomicsClient,
    TooManyDevices,
)
from robonomicsinterface.pallets.datalog import DatalogIndex, decode_item
from robonomicsinterface.pallets.system import AccountInfo
from robonomicsinterface.storage import storage_key

SITE = Keypair.from_uri("//Site")
OWNER = Keypair.from_uri("//Owner")
RUNTIME = recorded_runtime()
DAY_MS = 86_400_000


def compact(value: int) -> bytes:
    if value < 1 << 6:
        return bytes([value << 2])
    if value < 1 << 14:
        return ((value << 2) | 1).to_bytes(2, "little")
    if value < 1 << 30:
        return ((value << 2) | 2).to_bytes(4, "little")
    raw = value.to_bytes((value.bit_length() + 7) // 8, "little")
    return bytes([((len(raw) - 4) << 2) | 3]) + raw


def put(server: FakeServer, pallet: str, item: str, keys: list[Any], raw: bytes) -> None:
    entry = RUNTIME.storage_entry(pallet, item)
    server.node.add_value("0x" + storage_key(RUNTIME, entry, keys).hex(), "0x" + raw.hex())


def put_datalog(server: FakeServer, start: int, end: int, slots: dict[int, bytes]) -> None:
    put(server, "Datalog", "DatalogIndex", [SITE.address], compact(start) + compact(end))
    for slot, data in slots.items():
        item = compact(1_700_000_000_000 + slot) + compact(len(data)) + data
        put(server, "Datalog", "DatalogItem", [(SITE.address, slot)], item)


@pytest.fixture
async def server() -> AsyncIterator[FakeServer]:
    server = await FakeServer().start()
    install_chain(server)
    yield server
    await server.stop()


@pytest.fixture
async def client(server: FakeServer) -> AsyncIterator[RobonomicsClient]:
    client = RobonomicsClient(server.url, timeout=2, connect_timeout=2)
    client.runtimes.add(RUNTIME)
    async with client:
        yield client


# Datalog: the ring buffer


def test_index_arithmetic() -> None:
    assert DatalogIndex(0, 0, 128).count == 0
    assert DatalogIndex(0, 3, 128).positions == [0, 1, 2]
    full = DatalogIndex(94, 93, 128)
    assert full.count == 127
    assert full.positions[0] == 94
    assert full.positions[-1] == 92
    assert 93 not in full.positions  # the overwritten slot
    assert DatalogIndex(5, 0, 128).latest_position == 127  # 2.x returned None here


def test_decode_item_keeps_bytes() -> None:
    raw = compact(1234) + compact(4) + b"0x12"
    item = decode_item(7, raw)
    assert (item.index, item.timestamp_ms, item.data, item.text) == (7, 1234, b"0x12", "0x12")
    assert decode_item(0, compact(1) + compact(2) + b"\xff\xfe").text is None
    with pytest.raises(DecodeError):
        decode_item(0, compact(1) + compact(5) + b"abc")
    with pytest.raises(DecodeError):
        decode_item(0, b"")


async def test_empty_datalog(client: RobonomicsClient) -> None:
    assert (await client.datalog.index(SITE)).count == 0
    assert await client.datalog.latest(SITE) is None
    assert await client.datalog.items(SITE) == []
    assert await client.datalog.item(SITE, 0) is None


async def test_slot_zero_is_slot_zero(server: FakeServer, client: RobonomicsClient) -> None:
    put_datalog(server, 0, 3, {0: b"first", 1: b"second", 2: b"third"})
    first = await client.datalog.item(SITE, 0)
    assert first is not None
    assert first.data == b"first"
    latest = await client.datalog.latest(SITE)
    assert latest is not None
    assert latest.data == b"third"
    assert [i.data for i in await client.datalog.items(SITE)] == [b"first", b"second", b"third"]


async def test_wrapped_buffer(server: FakeServer, client: RobonomicsClient) -> None:
    slots = {slot: f"r{slot}".encode() for slot in range(128)}
    put_datalog(server, 94, 93, slots)
    items = await client.datalog.items(SITE)
    assert len(items) == 127
    assert items[0].index == 94
    assert items[-1].index == 92
    assert await client.datalog.item(SITE, 93) is None  # stale slot, still in storage
    latest = await client.datalog.latest(SITE)
    assert latest is not None
    assert latest.index == 92
    assert server.received.count("state_queryStorageAt") == 2  # items() and latest(): one each


async def test_latest_after_wrap_to_zero(server: FakeServer, client: RobonomicsClient) -> None:
    put_datalog(server, 5, 0, {127: b"newest", 5: b"oldest"})
    latest = await client.datalog.latest(SITE)
    assert latest is not None
    assert latest.data == b"newest"


async def test_record(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = [{"inBlock": BLOCKS["successful_rws_call"]["hash"]}]
    await client.datalog.record(SITE, "отчёт", subscription_owner=OWNER.address)
    submitted = bytes.fromhex(server.submitted[-1][2:])
    assert b"\x37\x00" + OWNER.public_key in submitted  # RWS.call(owner, ...)
    assert b"\x33\x00" + compact(len("отчёт".encode())) + "отчёт".encode() in submitted


async def test_record_size_is_checked_before_sending(
    server: FakeServer, client: RobonomicsClient
) -> None:
    with pytest.raises(EncodeError, match="512"):
        await client.datalog.record(SITE, b"x" * 513)
    assert not server.submitted
    assert "system_accountNextIndex" not in server.received


# RWS


def test_ledger() -> None:
    daily = Ledger.from_storage(
        {
            "free_weight": 5,
            "issue_time": 1_000 * DAY_MS,
            "last_update": 1_000 * DAY_MS,
            "kind": {"Daily": {"days": 30}},
        }
    )
    assert (daily.kind, daily.days, daily.tps) == ("Daily", 30, None)
    assert daily.is_active(now_ms=1_010 * DAY_MS)
    assert daily.days_left(now_ms=1_010 * DAY_MS) == 20
    assert not daily.is_active(now_ms=1_030 * DAY_MS)
    assert daily.days_left(now_ms=1_040 * DAY_MS) == 0
    assert daily.expires_at is not None

    lifetime = Ledger.from_storage(
        {"free_weight": 0, "issue_time": 0, "last_update": 0, "kind": {"Lifetime": {"tps": 500}}}
    )
    assert (lifetime.kind, lifetime.tps, lifetime.expires_at) == ("Lifetime", 500, None)
    assert lifetime.is_active()
    assert lifetime.days_left() is None


async def test_ledger_absent(client: RobonomicsClient) -> None:
    assert await client.rws.ledger(OWNER) is None
    assert await client.rws.devices(OWNER) == []


async def test_set_devices_normalises(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = [{"inBlock": BLOCKS["successful_rws_call"]["hash"]}]
    generic = Keypair.from_uri("//Device", ss58_format=42).address  # "5..." form
    device = Keypair.from_uri("//Device")
    await client.rws.set_devices(OWNER, [generic, device, SITE])
    submitted = bytes.fromhex(server.submitted[-1][2:])
    expected = b"\x37\x02" + compact(2) + device.public_key + SITE.public_key
    assert expected in submitted


async def test_set_devices_limits(server: FakeServer, client: RobonomicsClient) -> None:
    too_many = [Keypair.from_uri(f"//Device{i}") for i in range(33)]
    with pytest.raises(TooManyDevices):
        await client.rws.set_devices(OWNER, too_many)
    with pytest.raises(InvalidAddress):
        await client.rws.set_devices(OWNER, ["not an address"])
    assert not server.submitted


async def test_add_and_remove_devices(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = [{"inBlock": BLOCKS["successful_rws_call"]["hash"]}]
    devices_value = compact(1) + SITE.public_key
    put(server, "RWS", "Devices", [OWNER.address], devices_value)

    assert await client.rws.is_device(OWNER, SITE)
    assert await client.rws.add_devices(OWNER, SITE) is None  # already there
    assert await client.rws.remove_devices(OWNER, Keypair.from_uri("//Other")) is None
    assert not server.submitted

    await client.rws.add_devices(OWNER, Keypair.from_uri("//New"))
    added = bytes.fromhex(server.submitted[-1][2:])
    assert b"\x37\x02" + compact(2) + SITE.public_key in added

    await client.rws.remove_devices(OWNER, SITE)
    removed = bytes.fromhex(server.submitted[-1][2:])
    assert b"\x37\x02" + compact(0) in removed


# System, balances, chain


def test_account_existence() -> None:
    base = {"nonce": 0, "consumers": 0, "sufficients": 0}
    data = {"free": 0, "reserved": 0, "frozen": 0}
    assert not AccountInfo.from_storage({**base, "providers": 0, "data": data}).exists
    assert AccountInfo.from_storage({**base, "providers": 1, "data": data}).exists


async def test_system_and_chain(client: RobonomicsClient) -> None:
    info = await client.system.account(SITE)
    assert not info.exists
    assert not await client.system.exists(SITE)
    assert await client.balances.existential_deposit() == 1000
    assert await client.chain.block_number() == 1000
    assert (await client.chain.runtime_version()).spec_version == RUNTIME.version.spec_version


async def test_transfer_amount_checked(client: RobonomicsClient) -> None:
    with pytest.raises(ValueError, match="positive"):
        await client.balances.transfer_keep_alive(SITE, OWNER, 0)
