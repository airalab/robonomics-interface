"""RWS: Robonomics Web Services subscriptions.

A subscription owner lists up to ``MaxDevicesAmount`` (32) device accounts;
each device can then send calls through ``RWS.call`` free of fees, paid from
the subscription's accrued free weight. A daily subscription that has expired
stays on chain but stops accruing, so calls start failing with
``FreeWeightIsNotEnough`` rather than ``NoSubscription``.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Unpack

from ..errors import EncodeError
from ..extrinsic import Call, ExtrinsicResult
from ..keys import Keypair
from ._common import SubmitOptions, as_address

if TYPE_CHECKING:
    from ..client import RobonomicsClient

__all__ = ["RWS", "Ledger", "TooManyDevices"]

_DAY_MS = 86_400_000


class TooManyDevices(EncodeError):
    """The device list would exceed the runtime's ``MaxDevicesAmount``."""


@dataclass(frozen=True, slots=True)
class Ledger:
    """A subscription, as ``RWS.Ledger`` stores it."""

    kind: str  # "Daily" or "Lifetime"
    days: int | None  # Daily only
    tps: int | None  # Lifetime only, in micro-TPS
    issue_time_ms: int
    last_update_ms: int
    free_weight: int

    @classmethod
    def from_storage(cls, value: dict[str, Any]) -> Ledger:
        kind = value["kind"]
        if "Daily" in kind:
            name, days, tps = "Daily", int(kind["Daily"]["days"]), None
        else:
            name, days, tps = "Lifetime", None, int(kind["Lifetime"]["tps"])
        return cls(
            kind=name,
            days=days,
            tps=tps,
            issue_time_ms=int(value["issue_time"]),
            last_update_ms=int(value["last_update"]),
            free_weight=int(value["free_weight"]),
        )

    @property
    def issued_at(self) -> datetime:
        return datetime.fromtimestamp(self.issue_time_ms / 1000, tz=UTC)

    @property
    def expires_at(self) -> datetime | None:
        """When a daily subscription stops accruing; ``None`` for a lifetime one."""

        if self.days is None:
            return None
        return datetime.fromtimestamp((self.issue_time_ms + self.days * _DAY_MS) / 1000, tz=UTC)

    def is_active(self, now_ms: int | None = None) -> bool:
        if self.days is None:
            return True
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        return now_ms < self.issue_time_ms + self.days * _DAY_MS

    def days_left(self, now_ms: int | None = None) -> float | None:
        """Days until expiry (0 when expired); ``None`` for a lifetime subscription."""

        if self.days is None:
            return None
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        return max(0.0, (self.issue_time_ms + self.days * _DAY_MS - now_ms) / _DAY_MS)


class RWS:
    """``client.rws``: subscriptions, their devices and free calls."""

    def __init__(self, client: RobonomicsClient) -> None:
        self._client = client

    # Reading

    async def ledger(self, owner: str | Keypair, *, at: str | None = None) -> Ledger | None:
        """The subscription of ``owner``, or ``None`` if it has none."""

        value = await self._client.query("RWS", "Ledger", as_address(owner), at=at)
        return None if value is None else Ledger.from_storage(value)

    async def devices(self, owner: str | Keypair, *, at: str | None = None) -> list[str]:
        """The devices allowed to use ``owner``'s subscription."""

        return list(await self._client.query("RWS", "Devices", as_address(owner), at=at))

    async def is_device(
        self, owner: str | Keypair, device: str | Keypair, *, at: str | None = None
    ) -> bool:
        return as_address(device) in await self.devices(owner, at=at)

    async def max_devices(self, *, at: str | None = None) -> int:
        return int(await self._client.constant("RWS", "MaxDevicesAmount", at=at))

    async def auction(self, index: int, *, at: str | None = None) -> dict[str, Any] | None:
        result: dict[str, Any] | None = await self._client.query("RWS", "Auction", index, at=at)
        return result

    async def auction_next(self, *, at: str | None = None) -> int:
        return int(await self._client.query("RWS", "AuctionNext", at=at))

    async def auction_queue(self, *, at: str | None = None) -> list[int]:
        return [int(i) for i in await self._client.query("RWS", "AuctionQueue", at=at)]

    # Writing

    async def set_devices(
        self,
        owner: Keypair,
        devices: Iterable[str | Keypair],
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        """Replace the whole device list of ``owner``'s subscription.

        Addresses are checked and normalised, duplicates dropped (order kept).
        An empty list removes every device.

        :raises TooManyDevices: more than ``MaxDevicesAmount`` devices.
        """

        unique = list(dict.fromkeys(as_address(device) for device in devices))
        limit = await self.max_devices()
        if len(unique) > limit:
            raise TooManyDevices(f"a subscription takes at most {limit} devices, got {len(unique)}")
        call = await self._client.compose_call("RWS", "set_devices", {"devices": unique})
        return await self._client.submit(call, owner, **options)

    async def add_devices(
        self,
        owner: Keypair,
        *devices: str | Keypair,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult | None:
        """Add devices to the list: read it, extend it, write it back.

        Returns ``None`` if every device is already listed. Not atomic: two
        concurrent edits of one owner's list can lose one of them.
        """

        current = await self.devices(owner)
        wanted = list(dict.fromkeys([*current, *(as_address(d) for d in devices)]))
        if wanted == current:
            return None
        return await self.set_devices(owner, wanted, **options)

    async def remove_devices(
        self,
        owner: Keypair,
        *devices: str | Keypair,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult | None:
        """Remove devices from the list; ``None`` if none of them was listed."""

        current = await self.devices(owner)
        drop = {as_address(d) for d in devices}
        wanted = [d for d in current if d not in drop]
        if wanted == current:
            return None
        return await self.set_devices(owner, wanted, **options)

    async def call(
        self,
        device: Keypair,
        owner: str | Keypair,
        call: Call,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        """Send ``call`` as ``device``, paid by ``owner``'s subscription."""

        wrapped = await self._client.compose_call(
            "RWS", "call", {"subscription_id": as_address(owner), "call": call}
        )
        return await self._client.submit(wrapped, device, **options)

    async def bid(
        self, bidder: Keypair, index: int, amount: int, **options: Unpack[SubmitOptions]
    ) -> ExtrinsicResult:
        """Bid ``amount`` (in the smallest unit, 10⁻⁹ XRT) in auction ``index``."""

        call = await self._client.compose_call("RWS", "bid", {"index": index, "amount": amount})
        return await self._client.submit(call, bidder, **options)
