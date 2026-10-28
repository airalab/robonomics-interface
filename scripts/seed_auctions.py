"""Put RWS auctions into a raw chain spec, so a dev chain without Sudo has some to bid on.

Starting an auction is a Root call and the production runtime has no Sudo, so the
spec carries the auctions as genesis storage, as if a referendum had started them:

    uv run python scripts/seed_auctions.py raw-spec.json

Run by scripts/devchain.sh. An auction nobody bids on stays in the queue; a won one
leaves it at the next rotation (every `AuctionDuration` blocks) and becomes a
subscription, so each test takes a free auction and a node serves a few runs.
"""

import json
import sys
from pathlib import Path

import xxhash

LIFETIME = 8  # auctions of each kind
DAILY = 8
TPS = 10**9  # Lifetime: free weight accrues at this rate per second
DAYS = 30


def twox(data: bytes, rounds: int) -> bytes:
    return b"".join(xxhash.xxh64_digest(data, seed=i)[::-1] for i in range(rounds))


def compact(n: int) -> bytes:
    """SCALE compact integer (single-byte and four-byte modes are all that is needed)."""

    if n < 1 << 6:
        return bytes([n << 2])
    if n < 1 << 30:
        return ((n << 2) | 0b10).to_bytes(4, "little")
    raise ValueError(n)


def u32(n: int) -> bytes:
    return n.to_bytes(4, "little")


def key(item: str, *map_key: bytes) -> str:
    """Storage key of RWS.item; a map key is hashed with Twox64Concat."""

    suffix = b"".join(twox(k, 1) + k for k in map_key)
    return "0x" + (twox(b"RWS", 2) + twox(item.encode(), 2) + suffix).hex()


def auction(kind: int, size: int) -> bytes:
    """AuctionLedger: no winner, best price 0, and the subscription on offer."""

    return b"\x00" + compact(0) + bytes([kind]) + compact(size)


def seed(top: dict[str, str]) -> None:
    kinds = [(0, TPS)] * LIFETIME + [(1, DAYS)] * DAILY  # Subscription::{Lifetime, Daily}
    top[key("AuctionNext")] = "0x" + u32(len(kinds)).hex()
    top[key("AuctionQueue")] = (
        "0x" + (compact(len(kinds)) + b"".join(u32(i) for i in range(len(kinds)))).hex()
    )
    for index, (kind, size) in enumerate(kinds):
        top[key("Auction", u32(index))] = "0x" + auction(kind, size).hex()


if __name__ == "__main__":
    path = Path(sys.argv[1])
    spec = json.loads(path.read_text())
    seed(spec["genesis"]["raw"]["top"])
    path.write_text(json.dumps(spec))
