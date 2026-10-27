"""Record runtime metadata and a few real storage values for the offline tests.

Not run in CI. Rerun after a runtime upgrade and commit the result:

    uv run python scripts/fetch_chain_fixtures.py [wss://endpoint]

Writes tests/fixtures/metadata.hex.gz and tests/fixtures/chain_samples.json.
Everything recorded is public chain state at one pinned block.
"""

import asyncio
import gzip
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import xxhash
from websockets.asyncio.client import connect

ENDPOINT = "wss://polkadot.rpc.robonomics.network/"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SAMPLES_PER_ITEM = 3

# (pallet, item) pairs whose raw keys and values the tests decode.
MAPS = [
    ("System", "Account"),
    ("Datalog", "DatalogIndex"),
    ("Datalog", "DatalogItem"),
    ("RWS", "Ledger"),
    ("RWS", "Devices"),
    ("RWS", "Auction"),
]
VALUES = [
    ("System", "Number"),
    ("Timestamp", "Now"),
    ("RWS", "AuctionNext"),
    ("RWS", "AuctionQueue"),
]


def twox128(data: bytes) -> bytes:
    return b"".join(xxhash.xxh64(data, seed=seed).digest()[::-1] for seed in (0, 1))


def prefix(pallet: str, item: str) -> str:
    return "0x" + (twox128(pallet.encode()) + twox128(item.encode())).hex()


class Rpc:
    def __init__(self, socket: Any) -> None:
        self.socket = socket
        self.ids = itertools.count(1)

    async def __call__(self, method: str, params: list[Any]) -> Any:
        request_id = next(self.ids)
        await self.socket.send(
            json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        )
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]


async def main(endpoint: str) -> None:
    async with connect(endpoint, max_size=64 * 1024 * 1024) as socket:
        rpc = Rpc(socket)
        block = await rpc("chain_getFinalizedHead", [])
        header = await rpc("chain_getHeader", [block])
        version = await rpc("state_getRuntimeVersion", [block])
        metadata = await rpc("state_getMetadata", [block])
        genesis = await rpc("chain_getBlockHash", [0])

        maps = []
        for pallet, item in MAPS:
            keys = await rpc(
                "state_getKeysPaged", [prefix(pallet, item), SAMPLES_PER_ITEM, None, block]
            )
            changes = await rpc("state_queryStorageAt", [keys, block]) if keys else []
            entries = [[k, v] for k, v in (changes[0]["changes"] if changes else [])]
            maps.append({"pallet": pallet, "item": item, "entries": sorted(entries)})

        values = []
        for pallet, item in VALUES:
            raw = await rpc("state_getStorage", [prefix(pallet, item), block])
            values.append({"pallet": pallet, "item": item, "raw": raw})

    samples = {
        "note": "Public chain state recorded by scripts/fetch_chain_fixtures.py.",
        "endpoint": endpoint,
        "block_hash": block,
        "block_number": int(header["number"], 16),
        "genesis_hash": genesis,
        "spec_name": version["specName"],
        "spec_version": version["specVersion"],
        "transaction_version": version["transactionVersion"],
        "maps": maps,
        "values": values,
    }
    (FIXTURES / "metadata.hex.gz").write_bytes(gzip.compress(metadata.encode(), mtime=0))
    (FIXTURES / "chain_samples.json").write_text(json.dumps(samples, indent=2) + "\n")
    print(f"spec {version['specVersion']} at block {samples['block_number']}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ENDPOINT))
