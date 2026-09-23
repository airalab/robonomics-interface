"""Accounts, balances and blocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Unpack

from ..extrinsic import ExtrinsicResult
from ..keys import Keypair
from ..runtime import RuntimeVersion
from ._common import SubmitOptions, as_address

if TYPE_CHECKING:
    from ..client import RobonomicsClient

__all__ = ["XRT", "AccountInfo", "Balances", "Chain", "System"]

# XRT has 9 decimals: amounts on chain are in units of 10⁻⁹ XRT.
XRT = 10**9


@dataclass(frozen=True, slots=True)
class AccountInfo:
    """``System.Account``: nonce, references and balance (in 10⁻⁹ XRT)."""

    nonce: int
    consumers: int
    providers: int
    sufficients: int
    free: int
    reserved: int
    frozen: int

    @classmethod
    def from_storage(cls, value: dict[str, Any]) -> AccountInfo:
        data = value["data"]
        return cls(
            nonce=int(value["nonce"]),
            consumers=int(value["consumers"]),
            providers=int(value["providers"]),
            sufficients=int(value["sufficients"]),
            free=int(data["free"]),
            reserved=int(data["reserved"]),
            frozen=int(data["frozen"]),
        )

    @property
    def exists(self) -> bool:
        """Whether the account exists on chain, i.e. can sign transactions.

        An account with nothing providing for it (no balance above the
        existential deposit) is absent: its transactions fail with
        ``InvalidTransaction::Payment``, even free RWS calls.
        """

        return self.providers > 0 or self.sufficients > 0


class System:
    """``client.system``: accounts."""

    def __init__(self, client: RobonomicsClient) -> None:
        self._client = client

    async def account(self, address: str | Keypair, *, at: str | None = None) -> AccountInfo:
        value = await self._client.query("System", "Account", as_address(address), at=at)
        return AccountInfo.from_storage(value)

    async def exists(self, address: str | Keypair, *, at: str | None = None) -> bool:
        return (await self.account(address, at=at)).exists

    async def next_nonce(self, address: str | Keypair) -> int:
        """The nonce for the account's next transaction, counting the pool."""

        return int(await self._client.request("system_accountNextIndex", [as_address(address)]))


class Balances:
    """``client.balances``: XRT transfers."""

    def __init__(self, client: RobonomicsClient) -> None:
        self._client = client

    async def existential_deposit(self, *, at: str | None = None) -> int:
        """The minimum balance for an account to exist (in 10⁻⁹ XRT)."""

        return int(await self._client.constant("Balances", "ExistentialDeposit", at=at))

    async def transfer_keep_alive(
        self,
        sender: Keypair,
        destination: str | Keypair,
        amount: int,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        """Send ``amount`` (10⁻⁹ XRT); refused if it would leave the sender below
        the existential deposit."""

        return await self._transfer("transfer_keep_alive", sender, destination, amount, options)

    async def transfer_allow_death(
        self,
        sender: Keypair,
        destination: str | Keypair,
        amount: int,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        """Send ``amount`` (10⁻⁹ XRT), even if the sender's account is then reaped."""

        return await self._transfer("transfer_allow_death", sender, destination, amount, options)

    async def _transfer(
        self,
        function: str,
        sender: Keypair,
        destination: str | Keypair,
        amount: int,
        options: SubmitOptions,
    ) -> ExtrinsicResult:
        if amount <= 0:
            raise ValueError("the amount must be positive")
        call = await self._client.compose_call(
            "Balances", function, {"dest": {"Id": as_address(destination)}, "value": amount}
        )
        return await self._client.submit(call, sender, **options)


class Chain:
    """``client.chain``: blocks and the runtime version."""

    def __init__(self, client: RobonomicsClient) -> None:
        self._client = client

    async def best_hash(self) -> str:
        return str(await self._client.request("chain_getBlockHash", []))

    async def finalized_hash(self) -> str:
        return str(await self._client.request("chain_getFinalizedHead", []))

    async def block_hash(self, number: int) -> str | None:
        result = await self._client.request("chain_getBlockHash", [number])
        return None if result is None else str(result)

    async def block_number(self, block_hash: str | None = None) -> int:
        """The number of ``block_hash``, or of the best block."""

        header = await self._client.request("chain_getHeader", [block_hash] if block_hash else [])
        return int(header["number"], 16)

    async def runtime_version(self, *, at: str | None = None) -> RuntimeVersion:
        return await self._client.runtimes.version(self._client, at)
