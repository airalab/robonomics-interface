"""Datalog: a per-account ring buffer of timestamped records.

Each account has ``WindowSize`` (128) slots. ``DatalogIndex`` holds ``start``
and ``end``: live records are at ``start, start+1, …, end-1`` modulo the window,
oldest first. When the buffer is full, ``start`` moves on, so at most
``WindowSize - 1`` records are live; the slot at ``end`` may still hold an
overwritten record and is not one of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Unpack

from .. import storage
from ..errors import DecodeError, EncodeError
from ..extrinsic import ExtrinsicResult
from ..keys import Keypair
from ._common import SubmitOptions, as_address, submit

if TYPE_CHECKING:
    from ..client import RobonomicsClient

__all__ = ["MAX_RECORD_BYTES", "Datalog", "DatalogIndex", "DatalogItem"]

# Record = BoundedVec<u8, MaximumMessageSize> in the runtime; the bound is not
# exported as a constant, so it is mirrored here and enforced before sending.
MAX_RECORD_BYTES = 512


@dataclass(frozen=True, slots=True)
class DatalogIndex:
    start: int
    end: int
    window_size: int

    @property
    def count(self) -> int:
        """How many records are live."""

        return (self.end - self.start) % self.window_size

    @property
    def positions(self) -> list[int]:
        """Slot numbers of the live records, oldest first."""

        return [(self.start + i) % self.window_size for i in range(self.count)]

    @property
    def latest_position(self) -> int | None:
        return (self.end - 1) % self.window_size if self.count else None


@dataclass(frozen=True, slots=True)
class DatalogItem:
    """One record: its slot, when it was written, and its bytes."""

    index: int
    timestamp_ms: int
    data: bytes

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=UTC)

    @property
    def text(self) -> str | None:
        """The record as UTF-8 text, or ``None`` if it is not valid UTF-8."""

        try:
            return self.data.decode("utf-8")
        except UnicodeDecodeError:
            return None


def _compact(data: bytes, offset: int) -> tuple[int, int]:
    mode = data[offset] & 0b11
    if mode == 0:
        return data[offset] >> 2, offset + 1
    if mode == 1:
        return int.from_bytes(data[offset : offset + 2], "little") >> 2, offset + 2
    if mode == 2:
        return int.from_bytes(data[offset : offset + 4], "little") >> 2, offset + 4
    length = (data[offset] >> 2) + 4
    return int.from_bytes(data[offset + 1 : offset + 1 + length], "little"), offset + 1 + length


def decode_item(index: int, raw: bytes) -> DatalogItem:
    """Decode a ``RingBufferItem``: ``(Compact<u64> ms, Vec<u8>)``, as bytes.

    Decoded here rather than by scalecodec, which returns a record as text or
    as hex depending on whether it happens to be printable.
    """

    try:
        timestamp, offset = _compact(raw, 0)
        length, offset = _compact(raw, offset)
    except IndexError:
        raise DecodeError("a datalog item is truncated") from None
    data = raw[offset : offset + length]
    if len(data) != length or offset + length != len(raw):
        raise DecodeError("a datalog item has an unexpected length")
    return DatalogItem(index, timestamp, bytes(data))


class Datalog:
    """``client.datalog``: read and write datalog records."""

    def __init__(self, client: RobonomicsClient) -> None:
        self._client = client

    async def window_size(self, *, at: str | None = None) -> int:
        return int(await self._client.constant("Datalog", "WindowSize", at=at))

    async def index(self, address: str | Keypair, *, at: str | None = None) -> DatalogIndex:
        """The ring buffer bounds of ``address``."""

        value = await self._client.query("Datalog", "DatalogIndex", as_address(address), at=at)
        return DatalogIndex(int(value["start"]), int(value["end"]), await self.window_size(at=at))

    async def item(
        self, address: str | Keypair, index: int, *, at: str | None = None
    ) -> DatalogItem | None:
        """The record in slot ``index`` — 0 means slot 0 — or ``None`` if the slot
        holds no live record."""

        at = at or await self._client.chain.best_hash()
        bounds = await self.index(address, at=at)
        if index not in bounds.positions:
            return None
        items = await self._fetch(address, [index], at)
        return items[0]

    async def latest(self, address: str | Keypair, *, at: str | None = None) -> DatalogItem | None:
        """The newest record, or ``None`` if there are none."""

        at = at or await self._client.chain.best_hash()
        position = (await self.index(address, at=at)).latest_position
        if position is None:
            return None
        return (await self._fetch(address, [position], at))[0]

    async def items(self, address: str | Keypair, *, at: str | None = None) -> list[DatalogItem]:
        """All live records, oldest first, read in one request."""

        at = at or await self._client.chain.best_hash()
        positions = (await self.index(address, at=at)).positions
        found = await self._fetch(address, positions, at)
        return [item for item in found if item is not None]

    async def _fetch(
        self, address: str | Keypair, positions: Sequence[int], at: str
    ) -> list[DatalogItem | None]:
        account = as_address(address)
        _, _, raw = await storage.query_raw_multi(
            self._client,
            self._client.runtimes,
            "Datalog",
            "DatalogItem",
            [[(account, position)] for position in positions],
            at=at,
        )
        return [
            decode_item(position, value) if value is not None else None
            for position, value in zip(positions, raw, strict=True)
        ]

    async def record(
        self,
        keypair: Keypair,
        data: bytes | str,
        *,
        subscription_owner: str | None = None,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        """Write a record (at most 512 bytes; ``str`` is sent as UTF-8).

        :param subscription_owner: publish through this RWS subscription
            (``RWS.call``, free of fees) instead of paying.
        """

        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if len(payload) > MAX_RECORD_BYTES:
            raise EncodeError(
                f"a datalog record is at most {MAX_RECORD_BYTES} bytes, got {len(payload)}"
            )
        call = await self._client.compose_call("Datalog", "record", {"record": payload})
        return await submit(self._client, call, keypair, subscription_owner, options)

    async def erase(
        self,
        keypair: Keypair,
        *,
        subscription_owner: str | None = None,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        """Remove all records of the signer."""

        call = await self._client.compose_call("Datalog", "erase")
        return await submit(self._client, call, keypair, subscription_owner, options)
