"""Read-only smoke test against Robonomics mainnet. Sends nothing.

    ROBONOMICS_MAINNET_SMOKE=1 uv run pytest -m mainnet

Run before a release: it checks that the library still understands the live
runtime — metadata, storage layouts, signed extensions — without funds.
"""

import os

import pytest

from robonomicsinterface import (
    ROBONOMICS_GENESIS_HASH,
    InvalidTransaction,
    Keypair,
    RobonomicsClient,
)

pytestmark = [
    pytest.mark.mainnet,
    pytest.mark.skipif(
        not os.environ.get("ROBONOMICS_MAINNET_SMOKE"), reason="ROBONOMICS_MAINNET_SMOKE is not set"
    ),
]


async def test_mainnet_reads_and_signature_check() -> None:
    async with RobonomicsClient() as client:
        assert await client.request("chain_getBlockHash", [0]) == ROBONOMICS_GENESIS_HASH
        version = await client.chain.runtime_version()
        assert version.spec_name == "robonomics"
        assert await client.constant("Datalog", "WindowSize") == 128
        assert await client.rws.max_devices() == 32

        owners = 0
        async for _entry in client.query_map("RWS", "Ledger", page_size=50):
            owners += 1
            if owners >= 5:
                break
        assert owners > 0

        async for (address,), _ in client.query_map("Datalog", "DatalogIndex", page_size=5):
            items = await client.datalog.items(address)
            assert all(item.timestamp_ms > 0 for item in items)
            break

        # Sign for real and let the runtime check it, without sending: an account
        # that does not exist gets Payment, which proves the signature and every
        # signed extension were accepted (a bad one would be BadProof).
        ghost = Keypair.from_uri("//Alice")
        call = await client.compose_call("Datalog", "record", {"record": b"smoke"})
        with pytest.raises(InvalidTransaction) as error:
            await client.validate(await client.sign(call, ghost))
        assert error.value.kind == "Payment"
