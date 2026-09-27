"""A blocking wrapper around :class:`~robonomicsinterface.client.RobonomicsClient`.

For scripts, cron jobs and command-line tools::

    with RobonomicsSync() as client:
        latest = client.datalog.latest(address)

The async client runs on an event loop in a background thread; every method
here hands its call to that loop and waits for the result. Behaviour, errors
and timeouts are exactly those of the async client.

Do not use it inside a running event loop (Home Assistant, an asyncio app): a
blocking call there would stall the loop, so it raises ``RuntimeError`` and
points to the async client instead.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine, Iterable, Iterator, Mapping, Sequence
from typing import Any, Literal, Self, TypeVar, Unpack

from .client import DEFAULT_ENDPOINT, DEFAULT_INCLUSION_TIMEOUT, RobonomicsClient
from .extrinsic import DEFAULT_ERA_PERIOD, Call, ExtrinsicResult, SignedExtrinsic
from .keys import Keypair
from .pallets import AccountInfo, DatalogIndex, DatalogItem, Ledger, SubmitOptions
from .runtime import Runtime, RuntimeVersion

__all__ = ["RobonomicsSync"]

T = TypeVar("T")


class _LoopThread:
    """An event loop running in a daemon thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self.loop.run_forever, name="robonomics-sync", daemon=True
        )
        self._thread.start()

    def run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            coroutine.close()
            raise RuntimeError(
                "RobonomicsSync blocks, and this thread runs an event loop; "
                "use RobonomicsClient with await instead"
            )
        return self.run_unchecked(coroutine)

    def run_unchecked(self, coroutine: Coroutine[Any, Any, T]) -> T:
        """Run without the running-loop check: only for calls that return at once."""

        if not self.loop.is_running():
            coroutine.close()
            raise RuntimeError("the client is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result()
        except BaseException:
            # Interrupted (Ctrl-C) or failed: never leave the call running behind.
            future.cancel()
            raise

    def stop(self) -> None:
        if not self.loop.is_running():
            return

        async def shutdown() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # Metadata is parsed in the default executor; do not leave its threads behind.
            await asyncio.get_running_loop().shutdown_default_executor()

        asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join()
        self.loop.close()


class RobonomicsSync:
    """The blocking counterpart of :class:`RobonomicsClient`; same arguments."""

    def __init__(self, endpoints: str | Sequence[str] = DEFAULT_ENDPOINT, **options: Any) -> None:
        self._thread = _LoopThread()

        async def build() -> RobonomicsClient:
            return RobonomicsClient(endpoints, **options)

        try:
            # Building the client does not block, so this is allowed anywhere.
            self._client = self._thread.run_unchecked(build())
        except BaseException:
            self._thread.stop()
            raise
        self.datalog = SyncDatalog(self)
        self.rws = SyncRWS(self)
        self.system = SyncSystem(self)
        self.balances = SyncBalances(self)
        self.chain = SyncChain(self)

    def _run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        return self._thread.run(coroutine)

    @property
    def client(self) -> RobonomicsClient:
        """The underlying async client (for use from its own loop only)."""

        return self._client

    @property
    def endpoint(self) -> str | None:
        return self._client.endpoint

    def __repr__(self) -> str:
        return f"<RobonomicsSync endpoint={self.endpoint!r}>"

    # Lifecycle

    def connect(self) -> Self:
        self._run(self._client.connect())
        return self

    def close(self) -> None:
        """Close the connection and stop the background thread."""

        if self._thread.loop.is_running():
            try:
                self._run(self._client.close())
            finally:
                self._thread.stop()

    def __enter__(self) -> Self:
        return self.connect()

    def __exit__(self, *_: object) -> None:
        self.close()

    # Requests and storage

    def request(
        self,
        method: str,
        params: list[Any] | None = None,
        *,
        timeout: float | None = None,
        retry: bool = True,
    ) -> Any:
        return self._run(self._client.request(method, params, timeout=timeout, retry=retry))

    def runtime(self, at: str | None = None) -> Runtime:
        return self._run(self._client.runtime(at))

    def query(self, pallet: str, item: str, *keys: Any, at: str | None = None) -> Any:
        return self._run(self._client.query(pallet, item, *keys, at=at))

    def query_map(
        self, pallet: str, item: str, *keys: Any, at: str | None = None, page_size: int = 100
    ) -> Iterator[tuple[tuple[Any, ...], Any]]:
        """Iterate over a storage map; pages are fetched as the iteration goes."""

        iterator = self._client.query_map(pallet, item, *keys, at=at, page_size=page_size)

        async def step() -> tuple[bool, Any]:
            try:
                return True, await anext(iterator)
            except StopAsyncIteration:
                return False, None

        try:
            while True:
                more, entry = self._run(step())
                if not more:
                    return
                yield entry
        finally:
            if self._thread.loop.is_running():
                self._run(iterator.aclose())  # type: ignore[attr-defined]

    def constant(self, pallet: str, name: str, *, at: str | None = None) -> Any:
        return self._run(self._client.constant(pallet, name, at=at))

    # Extrinsics

    def compose_call(
        self, pallet: str, function: str, args: Mapping[str, Any] | None = None
    ) -> Call:
        return self._run(self._client.compose_call(pallet, function, args))

    def sign(
        self,
        call: Call,
        keypair: Keypair,
        *,
        nonce: int | None = None,
        tip: int = 0,
        era_period: int | None = DEFAULT_ERA_PERIOD,
    ) -> SignedExtrinsic:
        return self._run(
            self._client.sign(call, keypair, nonce=nonce, tip=tip, era_period=era_period)
        )

    def validate(self, extrinsic: SignedExtrinsic) -> None:
        self._run(self._client.validate(extrinsic))

    def submit(
        self,
        call: Call,
        keypair: Keypair,
        *,
        wait_for: Literal["in_block", "finalized"] = "in_block",
        tip: int = 0,
        era_period: int | None = DEFAULT_ERA_PERIOD,
        validate: bool = True,
        timeout: float = DEFAULT_INCLUSION_TIMEOUT,
    ) -> ExtrinsicResult:
        return self._run(
            self._client.submit(
                call,
                keypair,
                wait_for=wait_for,
                tip=tip,
                era_period=era_period,
                validate=validate,
                timeout=timeout,
            )
        )

    def submit_nowait(
        self,
        call: Call,
        keypair: Keypair,
        *,
        tip: int = 0,
        era_period: int | None = DEFAULT_ERA_PERIOD,
        validate: bool = True,
    ) -> str:
        return self._run(
            self._client.submit_nowait(
                call, keypair, tip=tip, era_period=era_period, validate=validate
            )
        )


class _Section:
    def __init__(self, owner: RobonomicsSync) -> None:
        self._owner = owner
        self._client = owner.client

    def _run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        return self._owner._run(coroutine)


class SyncDatalog(_Section):
    """Blocking ``client.datalog``."""

    def window_size(self, *, at: str | None = None) -> int:
        return self._run(self._client.datalog.window_size(at=at))

    def index(self, address: str | Keypair, *, at: str | None = None) -> DatalogIndex:
        return self._run(self._client.datalog.index(address, at=at))

    def item(
        self, address: str | Keypair, index: int, *, at: str | None = None
    ) -> DatalogItem | None:
        return self._run(self._client.datalog.item(address, index, at=at))

    def latest(self, address: str | Keypair, *, at: str | None = None) -> DatalogItem | None:
        return self._run(self._client.datalog.latest(address, at=at))

    def items(self, address: str | Keypair, *, at: str | None = None) -> list[DatalogItem]:
        return self._run(self._client.datalog.items(address, at=at))

    def record(
        self,
        keypair: Keypair,
        data: bytes | str,
        *,
        subscription_owner: str | None = None,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        return self._run(
            self._client.datalog.record(
                keypair, data, subscription_owner=subscription_owner, **options
            )
        )

    def erase(
        self,
        keypair: Keypair,
        *,
        subscription_owner: str | None = None,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        return self._run(
            self._client.datalog.erase(keypair, subscription_owner=subscription_owner, **options)
        )


class SyncRWS(_Section):
    """Blocking ``client.rws``."""

    def ledger(self, owner: str | Keypair, *, at: str | None = None) -> Ledger | None:
        return self._run(self._client.rws.ledger(owner, at=at))

    def devices(self, owner: str | Keypair, *, at: str | None = None) -> list[str]:
        return self._run(self._client.rws.devices(owner, at=at))

    def is_device(
        self, owner: str | Keypair, device: str | Keypair, *, at: str | None = None
    ) -> bool:
        return self._run(self._client.rws.is_device(owner, device, at=at))

    def max_devices(self, *, at: str | None = None) -> int:
        return self._run(self._client.rws.max_devices(at=at))

    def auction(self, index: int, *, at: str | None = None) -> dict[str, Any] | None:
        return self._run(self._client.rws.auction(index, at=at))

    def auction_next(self, *, at: str | None = None) -> int:
        return self._run(self._client.rws.auction_next(at=at))

    def auction_queue(self, *, at: str | None = None) -> list[int]:
        return self._run(self._client.rws.auction_queue(at=at))

    def set_devices(
        self,
        owner: Keypair,
        devices: Iterable[str | Keypair],
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        return self._run(self._client.rws.set_devices(owner, devices, **options))

    def add_devices(
        self, owner: Keypair, *devices: str | Keypair, **options: Unpack[SubmitOptions]
    ) -> ExtrinsicResult | None:
        return self._run(self._client.rws.add_devices(owner, *devices, **options))

    def remove_devices(
        self, owner: Keypair, *devices: str | Keypair, **options: Unpack[SubmitOptions]
    ) -> ExtrinsicResult | None:
        return self._run(self._client.rws.remove_devices(owner, *devices, **options))

    def call(
        self,
        device: Keypair,
        owner: str | Keypair,
        call: Call,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        return self._run(self._client.rws.call(device, owner, call, **options))

    def bid(
        self, bidder: Keypair, index: int, amount: int, **options: Unpack[SubmitOptions]
    ) -> ExtrinsicResult:
        return self._run(self._client.rws.bid(bidder, index, amount, **options))


class SyncSystem(_Section):
    """Blocking ``client.system``."""

    def account(self, address: str | Keypair, *, at: str | None = None) -> AccountInfo:
        return self._run(self._client.system.account(address, at=at))

    def exists(self, address: str | Keypair, *, at: str | None = None) -> bool:
        return self._run(self._client.system.exists(address, at=at))

    def next_nonce(self, address: str | Keypair) -> int:
        return self._run(self._client.system.next_nonce(address))


class SyncBalances(_Section):
    """Blocking ``client.balances``."""

    def existential_deposit(self, *, at: str | None = None) -> int:
        return self._run(self._client.balances.existential_deposit(at=at))

    def transfer_keep_alive(
        self,
        sender: Keypair,
        destination: str | Keypair,
        amount: int,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        return self._run(
            self._client.balances.transfer_keep_alive(sender, destination, amount, **options)
        )

    def transfer_allow_death(
        self,
        sender: Keypair,
        destination: str | Keypair,
        amount: int,
        **options: Unpack[SubmitOptions],
    ) -> ExtrinsicResult:
        return self._run(
            self._client.balances.transfer_allow_death(sender, destination, amount, **options)
        )


class SyncChain(_Section):
    """Blocking ``client.chain``."""

    def best_hash(self) -> str:
        return self._run(self._client.chain.best_hash())

    def finalized_hash(self) -> str:
        return self._run(self._client.chain.finalized_hash())

    def block_hash(self, number: int) -> str | None:
        return self._run(self._client.chain.block_hash(number))

    def block_number(self, block_hash: str | None = None) -> int:
        return self._run(self._client.chain.block_number(block_hash))

    def runtime_version(self, *, at: str | None = None) -> RuntimeVersion:
        return self._run(self._client.chain.runtime_version(at=at))
