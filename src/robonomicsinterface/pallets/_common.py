"""Helpers shared by the pallet wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

from ..extrinsic import Call, ExtrinsicResult
from ..keys import Keypair
from ..ss58 import ROBONOMICS_SS58_FORMAT, decode_address, encode_address

if TYPE_CHECKING:
    from ..client import RobonomicsClient


class SubmitOptions(TypedDict, total=False):
    """Options passed through to :meth:`RobonomicsClient.submit`."""

    wait_for: Literal["in_block", "finalized"]
    tip: int
    era_period: int | None
    validate: bool
    timeout: float


def as_address(value: str | Keypair) -> str:
    """A Robonomics (format 32) address from a keypair or any valid SS58 address.

    :raises InvalidAddress: the text is not a valid address.
    """

    if isinstance(value, Keypair):
        return encode_address(value.public_key, ROBONOMICS_SS58_FORMAT)
    return encode_address(decode_address(value), ROBONOMICS_SS58_FORMAT)


async def submit(
    client: RobonomicsClient,
    call: Call,
    keypair: Keypair,
    subscription_owner: str | Keypair | None,
    options: SubmitOptions,
) -> ExtrinsicResult:
    """Submit ``call``, wrapped in ``RWS.call`` when a subscription pays for it."""

    if subscription_owner is not None:
        call = await client.compose_call(
            "RWS", "call", {"subscription_id": as_address(subscription_owner), "call": call}
        )
    return await client.submit(call, keypair, **options)
