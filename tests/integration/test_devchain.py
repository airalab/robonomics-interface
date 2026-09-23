"""End to end against a Robonomics development node.

Run a node first (see scripts/devchain.sh) and point the tests at it:

    ROBONOMICS_DEV_URL=ws://127.0.0.1:9944 uv run pytest -m integration

The chain spec must be patched by scripts/dev_chain_spec.py: ED25519 //Alice
is sudo and //Alice..//Dave are endowed. Every test derives fresh accounts
from them, so the tests can run repeatedly against one node.
"""

import asyncio
import os
import secrets
from collections.abc import AsyncIterator

import pytest

from robonomicsinterface import (
    XRT,
    ExtrinsicFailed,
    InvalidTransaction,
    Keypair,
    RobonomicsClient,
    RobonomicsSync,
)

URL = os.environ.get("ROBONOMICS_DEV_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="ROBONOMICS_DEV_URL is not set"),
]

SUDO = Keypair.from_uri("//Alice")


def fresh(name: str) -> Keypair:
    """An account nobody has used yet, derived from a known dev account."""

    return Keypair.from_uri(f"//{name}//{secrets.token_hex(4)}")


@pytest.fixture
async def client() -> AsyncIterator[RobonomicsClient]:
    assert URL is not None
    async with RobonomicsClient(URL, genesis_hash=None, require_healthy=False) as client:
        yield client


async def fund(client: RobonomicsClient, *accounts: Keypair, amount: int = 100 * XRT) -> None:
    for account in accounts:
        await client.balances.transfer_keep_alive(SUDO, account, amount)


async def make_oracle(client: RobonomicsClient) -> None:
    set_oracle = await client.compose_call("RWS", "set_oracle", {"new": {"Id": SUDO.address}})
    sudo = await client.compose_call("Sudo", "sudo", {"call": set_oracle})
    result = await client.submit(sudo, SUDO)
    assert result.find("Sudo", "Sudid") is not None


async def subscribe(client: RobonomicsClient, owner: Keypair, kind: dict[str, object]) -> None:
    call = await client.compose_call(
        "RWS", "set_subscription", {"target": owner.address, "subscription": kind}
    )
    await client.submit(call, SUDO)


# Accounts and balances


async def test_chain_is_the_current_runtime(client: RobonomicsClient) -> None:
    version = await client.chain.runtime_version()
    assert version.spec_name == "robonomics"
    assert await client.constant("Datalog", "WindowSize") == 128


async def test_transfer(client: RobonomicsClient) -> None:
    receiver = fresh("Bob")
    assert not await client.system.exists(receiver)
    result = await client.balances.transfer_keep_alive(SUDO, receiver, 5 * XRT)
    assert result.find("Balances", "Transfer") is not None
    info = await client.system.account(receiver)
    assert info.exists
    assert info.free == 5 * XRT


async def test_account_that_does_not_exist(client: RobonomicsClient) -> None:
    ghost = fresh("Eve")
    with pytest.raises(InvalidTransaction) as error:
        await client.datalog.record(ghost, b"hello")
    assert error.value.kind == "Payment"
    assert "existential deposit" in error.value.explanation


# Datalog


async def test_datalog_round_trip(client: RobonomicsClient) -> None:
    site = fresh("Charlie")
    await fund(client, site)
    for data in (b"\x00\x01binary", "текст", "0x12"):
        await client.datalog.record(site, data)

    first = await client.datalog.item(site, 0)
    assert first is not None
    assert first.data == b"\x00\x01binary"
    items = await client.datalog.items(site)
    assert [i.data for i in items] == [b"\x00\x01binary", "текст".encode(), b"0x12"]
    latest = await client.datalog.latest(site)
    assert latest is not None
    assert latest.text == "0x12"  # a str starting with 0x stays text

    await client.datalog.erase(site)
    assert await client.datalog.items(site) == []


# RWS


async def test_rws_subscription_flow(client: RobonomicsClient) -> None:
    owner, device, stranger = fresh("Bob"), fresh("Charlie"), fresh("Dave")
    await fund(client, owner, device, stranger)
    await make_oracle(client)
    await subscribe(client, owner, {"Lifetime": {"tps": 10**9}})

    ledger = await client.rws.ledger(owner)
    assert ledger is not None
    assert ledger.kind == "Lifetime"
    assert ledger.is_active()

    await client.rws.set_devices(owner, [device])
    assert await client.rws.devices(owner) == [device.address]
    assert await client.rws.add_devices(owner, device) is None

    await asyncio.sleep(2)  # let the subscription accrue free weight
    result = await client.datalog.record(device, b"via subscription", subscription_owner=owner)
    new_call = result.find("RWS", "NewCall")
    assert new_call is not None
    assert result.find("Datalog", "NewRecord") is not None
    latest = await client.datalog.latest(device)
    assert latest is not None
    assert latest.data == b"via subscription"

    with pytest.raises(ExtrinsicFailed) as error:
        await client.datalog.record(stranger, b"not mine", subscription_owner=owner)
    assert (error.value.pallet, error.value.error) == ("RWS", "NotLinkedDevice")


async def test_fresh_daily_subscription_has_no_allowance(client: RobonomicsClient) -> None:
    owner, device = fresh("Bob"), fresh("Charlie")
    await fund(client, owner, device)
    await make_oracle(client)
    await subscribe(client, owner, {"Daily": {"days": 30}})
    await client.rws.set_devices(owner, [device])

    with pytest.raises(ExtrinsicFailed) as error:
        await client.datalog.record(device, b"too soon", subscription_owner=owner)
    assert (error.value.pallet, error.value.error) == ("RWS", "FreeWeightIsNotEnough")


# The blocking wrapper, end to end


def test_sync_wrapper() -> None:
    assert URL is not None
    site = fresh("Charlie")
    with RobonomicsSync(URL, genesis_hash=None, require_healthy=False) as client:
        client.balances.transfer_keep_alive(SUDO, site, 10 * XRT)
        client.datalog.record(site, b"sync")
        latest = client.datalog.latest(site)
        assert latest is not None
        assert latest.data == b"sync"
