"""End to end against a Robonomics development node.

Run a node first (see scripts/devchain.sh) and point the tests at it:

    ROBONOMICS_DEV_URL=ws://127.0.0.1:9944 uv run pytest -m integration

The development preset funds the sr25519 dev accounts and makes sr25519 //Alice
sudo. Every test derives fresh accounts of both key types from it and funds them
by transfer, so the tests can run repeatedly against one node.
"""

import asyncio
import os
import secrets
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import pytest

from robonomicsinterface import (
    ED25519,
    ROBONOMICS_GENESIS_HASH,
    SR25519,
    XRT,
    ExtrinsicFailed,
    InvalidTransaction,
    Keypair,
    RobonomicsClient,
    RobonomicsSync,
    decrypt_package,
    encrypt_for_recipients,
    parse_decrypted,
)

URL = os.environ.get("ROBONOMICS_DEV_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="ROBONOMICS_DEV_URL is not set"),
]

SUDO = Keypair.from_uri("//Alice", crypto_type=SR25519)
both_key_types = pytest.mark.parametrize(
    "crypto_type", [SR25519, ED25519], ids=["sr25519", "ed25519"]
)
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
PRODUCTION_GENESIS = {
    ROBONOMICS_GENESIS_HASH,
    "0x631ccc82a078481584041656af292834e1ae6daab61d2875b4dd0c14bb9b17bc",  # Kusama (legacy)
}


@pytest.fixture(scope="module", autouse=True)
def only_a_development_chain() -> None:
    """These tests send transactions: refuse anything that is not a local dev chain.

    A remote node needs ROBONOMICS_DEV_ALLOW_REMOTE=1; a production chain is
    refused whatever the settings.
    """

    assert URL is not None
    host = urlsplit(URL).hostname or ""
    if host not in LOOPBACK and os.environ.get("ROBONOMICS_DEV_ALLOW_REMOTE") != "1":
        pytest.fail(f"{URL} is not a loopback address; set ROBONOMICS_DEV_ALLOW_REMOTE=1 to allow")
    with RobonomicsSync(URL, genesis_hash=None, require_healthy=False) as client:
        genesis = client.request("chain_getBlockHash", [0])
    if genesis in PRODUCTION_GENESIS:
        pytest.fail(f"{URL} is a production Robonomics chain; these tests send transactions")


def fresh(name: str, crypto_type: int = SR25519) -> Keypair:
    """An account nobody has used yet, derived from a known dev account."""

    return Keypair.from_uri(f"//{name}//{secrets.token_hex(4)}", crypto_type=crypto_type)


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


@both_key_types
async def test_transfer(client: RobonomicsClient, crypto_type: int) -> None:
    receiver = fresh("Bob", crypto_type)
    assert not await client.system.exists(receiver)
    result = await client.balances.transfer_keep_alive(SUDO, receiver, 5 * XRT)
    assert result.find("Balances", "Transfer") is not None
    info = await client.system.account(receiver)
    assert info.exists
    assert info.free == 5 * XRT


@both_key_types
async def test_account_that_does_not_exist(client: RobonomicsClient, crypto_type: int) -> None:
    ghost = fresh("Eve", crypto_type)
    with pytest.raises(InvalidTransaction) as error:
        await client.datalog.record(ghost, b"hello")
    assert error.value.kind == "Payment"
    assert "existential deposit" in error.value.explanation


# Datalog


@both_key_types
async def test_datalog_round_trip(client: RobonomicsClient, crypto_type: int) -> None:
    site = fresh("Charlie", crypto_type)
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


@both_key_types
async def test_encrypted_report_round_trip(client: RobonomicsClient, crypto_type: int) -> None:
    """A site's report, as Report Service does it: the package goes off chain (IPFS stands
    in), its address goes into the datalog, and the integrator reads and opens it."""

    site, integrator = fresh("Charlie", crypto_type), fresh("Dave", crypto_type)
    await fund(client, site)
    report = "2026-10-28 13:00:00 ERROR (MainThread) [zha] Failed to connect\n"
    meta = {"orig_file_name": "home-assistant.log"}
    off_chain = {"QmReport": encrypt_for_recipients(report, site, [integrator.address], meta)}

    await client.datalog.record(site, "QmReport")

    latest = await client.datalog.latest(site)
    assert latest is not None
    opened = decrypt_package(off_chain[latest.text], integrator, site.address)
    assert parse_decrypted(opened) == (report, meta)


# RWS


@both_key_types
async def test_rws_subscription_flow(client: RobonomicsClient, crypto_type: int) -> None:
    owner = fresh("Bob", crypto_type)
    device, stranger = fresh("Charlie", crypto_type), fresh("Dave", crypto_type)
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


@both_key_types
async def test_fresh_daily_subscription_has_no_allowance(
    client: RobonomicsClient, crypto_type: int
) -> None:
    owner, device = fresh("Bob", crypto_type), fresh("Charlie", crypto_type)
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
