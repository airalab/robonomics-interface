"""Submitting extrinsics through the client, against a local fake node."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from fake_node import recorded_runtime
from fake_server import BLOCKS, FakeServer, Fault, install_chain
from robonomicsinterface import (
    ExtrinsicDropped,
    ExtrinsicFailed,
    ExtrinsicOutcomeUnknown,
    InvalidTransaction,
    Keypair,
    RobonomicsClient,
)

SIGNER = Keypair.from_uri("//Alice")
OWNER = "4H13HaTutSqePohv26FB9sXwQvWbrXBEHaZYE8mYo2744qjU"


@pytest.fixture
async def server() -> AsyncIterator[FakeServer]:
    server = await FakeServer().start()
    install_chain(server)
    yield server
    await server.stop()


@pytest.fixture
async def client(server: FakeServer) -> AsyncIterator[RobonomicsClient]:
    client = RobonomicsClient(server.url, timeout=2, connect_timeout=2)
    client.runtimes.add(recorded_runtime())
    async with client:
        yield client


async def record_call(client: RobonomicsClient) -> Any:
    record = await client.compose_call("Datalog", "record", {"record": b"report"})
    return await client.compose_call("RWS", "call", {"subscription_id": OWNER, "call": record})


def in_block(name: str) -> dict[str, str]:
    return {"inBlock": BLOCKS[name]["hash"]}


async def test_success(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = ["ready", {"broadcast": ["peer"]}, in_block("successful_rws_call")]
    result = await client.submit(await record_call(client), SIGNER)

    assert result.block_hash == BLOCKS["successful_rws_call"]["hash"]
    assert result.block_number == BLOCKS["successful_rws_call"]["number"]
    assert result.index == 2
    assert not result.finalized
    assert result.find("Datalog", "NewRecord") is not None
    assert result.find("RWS", "NewCall") is not None
    assert all(event.extrinsic_index == 2 for event in result.events)


async def test_failure_names_the_pallet_error(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = [in_block("failed_rws_call")]
    with pytest.raises(ExtrinsicFailed) as error:
        await client.submit(await record_call(client), SIGNER)
    assert (error.value.pallet, error.value.error) == ("RWS", "FreeWeightIsNotEnough")
    assert "allowance" in str(error.value)
    assert error.value.result.block_number == BLOCKS["failed_rws_call"]["number"]  # type: ignore[attr-defined]


async def test_wait_for_finalized(server: FakeServer, client: RobonomicsClient) -> None:
    hash_ = BLOCKS["successful_rws_call"]["hash"]
    server.watch_script = [{"inBlock": hash_}, {"finalized": hash_}]
    result = await client.submit(await record_call(client), SIGNER, wait_for="finalized")
    assert result.finalized


async def test_invalid_is_refused_before_sending(
    server: FakeServer, client: RobonomicsClient
) -> None:
    server.overrides["state_call"] = lambda params: "0x010001"
    with pytest.raises(InvalidTransaction) as error:
        await client.submit(await record_call(client), SIGNER)
    assert error.value.kind == "Payment"
    assert "existential deposit" in str(error.value)
    assert not server.submitted


async def test_future_is_not_an_error(server: FakeServer, client: RobonomicsClient) -> None:
    server.overrides["state_call"] = lambda params: "0x010002"
    server.watch_script = [in_block("successful_rws_call")]
    await client.submit(await record_call(client), SIGNER)
    assert len(server.submitted) == 1


async def test_pool_rejection_is_explained(server: FakeServer, client: RobonomicsClient) -> None:
    def reject(params: list[Any]) -> None:
        raise Fault(1010, "Invalid Transaction")

    server.overrides["author_submitAndWatchExtrinsic"] = reject
    with pytest.raises(InvalidTransaction):
        await client.submit(await record_call(client), SIGNER, validate=False)


async def test_dropped(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = ["ready", "dropped"]
    with pytest.raises(ExtrinsicDropped):
        await client.submit(await record_call(client), SIGNER)


async def test_lost_connection_is_an_unknown_outcome_and_not_resent(
    server: FakeServer, client: RobonomicsClient
) -> None:
    server.watch_script = ["ready", "DROP"]
    with pytest.raises(ExtrinsicOutcomeUnknown) as error:
        await client.submit(await record_call(client), SIGNER)
    assert error.value.extrinsic_hash.startswith("0x")
    assert len(server.submitted) == 1


async def test_inclusion_timeout(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = ["ready"]
    with pytest.raises(ExtrinsicOutcomeUnknown, match="within"):
        await client.submit(await record_call(client), SIGNER, timeout=0.3)


async def test_block_without_our_extrinsic(server: FakeServer, client: RobonomicsClient) -> None:
    server.watch_script = [in_block("successful_rws_call")]
    original = server.overrides["chain_getBlock"]

    def block_without_ours(params: list[Any]) -> dict[str, Any]:
        block = original(params)
        block["block"]["extrinsics"][2] = "0x00"
        return block

    server.overrides["chain_getBlock"] = block_without_ours
    with pytest.raises(ExtrinsicOutcomeUnknown, match="does not contain"):
        await client.submit(await record_call(client), SIGNER)


async def test_concurrent_submissions_take_distinct_nonces(
    server: FakeServer, client: RobonomicsClient
) -> None:
    server.watch_script = [in_block("successful_rws_call")]
    call = await record_call(client)
    signed: list[int] = []
    original = client.sign

    async def spy(*args: Any, **kwargs: Any) -> Any:
        extrinsic = await original(*args, **kwargs)
        signed.append(extrinsic.nonce)
        return extrinsic

    client.sign = spy  # type: ignore[method-assign]
    results = await asyncio.gather(
        client.submit(call, SIGNER), client.submit(call, SIGNER), return_exceptions=True
    )
    assert sorted(signed) == [0, 1]
    assert len(results) == 2


async def test_mortal_era_by_default(server: FakeServer, client: RobonomicsClient) -> None:
    extrinsic = await client.sign(await record_call(client), SIGNER)
    assert extrinsic.era.period == 64
    assert extrinsic.era.birth(1000) == 1000
    immortal = await client.sign(await record_call(client), SIGNER, era_period=None)
    assert immortal.era.is_immortal


async def test_submit_nowait(server: FakeServer, client: RobonomicsClient) -> None:
    server.overrides["author_submitExtrinsic"] = lambda params: "0x" + "33" * 32
    extrinsic_hash = await client.submit_nowait(await record_call(client), SIGNER)
    assert extrinsic_hash.startswith("0x")
