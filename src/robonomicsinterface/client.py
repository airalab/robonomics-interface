"""The async client: endpoints in priority order, health checks, retries.

::

    async with RobonomicsClient(["ws://192.168.1.10:9944", DEFAULT_ENDPOINT]) as client:
        number = await client.query("System", "Number")

Endpoints are tried in the order given, so a node on the local network can come
first and a public node serve as the fallback. A node is used only if it is on
the expected chain (by genesis hash) and not syncing; while the client runs on a
fallback it periodically tries to return to a preferred endpoint.

Reads are retried on another endpoint after a network failure. Anything that
must not run twice — submitting an extrinsic — is sent with ``retry=False``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl as ssl_module
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal, Self

from . import storage
from .errors import (
    AllEndpointsFailed,
    ConnectionFailed,
    ConnectionLost,
    ExtrinsicDropped,
    ExtrinsicFailed,
    ExtrinsicOutcomeUnknown,
    InvalidTransaction,
    MetadataError,
    RequestTimeout,
    RpcError,
    TransportError,
)
from .extrinsic import (
    DEFAULT_ERA_PERIOD,
    Call,
    Era,
    ExtrinsicResult,
    SignedExtrinsic,
    SigningContext,
    compose_call,
    decode_events,
    dispatch_error_message,
    explain_invalid_transaction,
    sign_extrinsic,
)
from .keys import Keypair

if TYPE_CHECKING:
    from .pallets import RWS, Balances, Chain, Datalog, System
from .runtime import Runtime, RuntimeCache, RuntimeVersion
from .ss58 import ROBONOMICS_SS58_FORMAT
from .transport import DEFAULT_MAX_MESSAGE_BYTES, Connection, Subscription

__all__ = ["DEFAULT_ENDPOINT", "ROBONOMICS_GENESIS_HASH", "RobonomicsClient"]

LOGGER = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "wss://polkadot.rpc.robonomics.network/"
# Robonomics on Polkadot. A node on any other chain is refused: an extrinsic
# signed for another genesis would fail with an unhelpful "bad signature".
ROBONOMICS_GENESIS_HASH = "0x29f4371dcc41045f5041489dfcd51389bf8ccd2161332e0de1ca803bcc3ee872"

_RETIRE_GRACE_SECONDS = 30.0
DEFAULT_INCLUSION_TIMEOUT = 120.0

# Error codes of author_submit* (sc_rpc_api::author::error).
_POOL_INVALID = 1010
_POOL_UNKNOWN = 1011
_POOL_REJECTIONS = {
    "pay": "Payment",
    "bad signature": "BadProof",
    "outdated": "Stale",
    "future": "Future",
    "ancient": "AncientBirthBlock",
    "exhaust": "ExhaustsResources",
}


def _user_agent() -> str:
    from . import __version__

    return f"robonomics-interface/{__version__}"


class RobonomicsClient:
    """A connection to Robonomics that survives node failures.

    :param endpoints: one URL or several, in order of preference. ``ws://`` is
        fine on a local network; use ``wss://`` across the internet.
    :param timeout: seconds to wait for each answer.
    :param connect_timeout: seconds to wait for a connection to open.
    :param retries: how many more times a read is tried after a network failure.
    :param genesis_hash: the chain every node must be on; ``None`` accepts any
        chain (a development node, for instance).
    :param require_healthy: refuse nodes that are syncing or have no peers.
    :param ssl: a TLS context for ``wss://`` endpoints with a private CA.
    :param failback_interval: seconds between attempts to return to a preferred
        endpoint, and how long a failed endpoint is skipped.
    """

    def __init__(
        self,
        endpoints: str | Sequence[str] = DEFAULT_ENDPOINT,
        *,
        timeout: float = 30.0,
        connect_timeout: float = 10.0,
        retries: int = 2,
        genesis_hash: str | None = ROBONOMICS_GENESIS_HASH,
        require_healthy: bool = True,
        ssl: ssl_module.SSLContext | None = None,
        failback_interval: float = 300.0,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
    ) -> None:
        self.endpoints: tuple[str, ...] = (
            (endpoints,) if isinstance(endpoints, str) else tuple(endpoints)
        )
        if not self.endpoints:
            raise ValueError("at least one endpoint is required")
        if retries < 0:
            raise ValueError("retries cannot be negative")
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.retries = retries
        self.genesis_hash = genesis_hash
        self.require_healthy = require_healthy
        self.failback_interval = failback_interval
        self.runtimes = RuntimeCache(ss58_format=ss58_format)
        self._ssl = ssl
        self._max_message_bytes = max_message_bytes
        self._connection: Connection | None = None
        self._active_index: int | None = None
        self._failed_at: dict[int, float] = {}
        self._connect_lock = asyncio.Lock()
        self._watcher: asyncio.Task[None] | None = None
        self._failback: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[None]] = set()
        self._nonce_locks: dict[str, asyncio.Lock] = {}
        self._closed = False

    def __repr__(self) -> str:
        return f"<RobonomicsClient endpoint={self.endpoint!r}>"

    @property
    def endpoint(self) -> str | None:
        """The endpoint in use now, or ``None`` when not connected."""

        connection = self._connection
        return connection.endpoint if connection is not None and not connection.closed else None

    # Pallets

    @cached_property
    def datalog(self) -> Datalog:
        from .pallets import Datalog

        return Datalog(self)

    @cached_property
    def rws(self) -> RWS:
        from .pallets import RWS

        return RWS(self)

    @cached_property
    def system(self) -> System:
        from .pallets import System

        return System(self)

    @cached_property
    def balances(self) -> Balances:
        from .pallets import Balances

        return Balances(self)

    @cached_property
    def chain(self) -> Chain:
        from .pallets import Chain

        return Chain(self)

    # Lifecycle

    async def connect(self) -> Self:
        """Connect to the first usable endpoint; ``AllEndpointsFailed`` if none is."""

        self._closed = False
        await self._ensure_connection()
        if len(self.endpoints) > 1 and self._failback is None:
            self._failback = asyncio.create_task(self._failback_loop(), name="robonomics-failback")
        return self

    async def close(self) -> None:
        self._closed = True
        tasks = [t for t in (self._watcher, self._failback, *self._background) if t is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._watcher = self._failback = None
        self._background.clear()
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
        self.runtimes.set_current(None)

    async def __aenter__(self) -> Self:
        return await self.connect()

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # Requests

    async def request(
        self,
        method: str,
        params: list[Any] | None = None,
        *,
        timeout: float | None = None,
        retry: bool = True,
    ) -> Any:
        """Send a JSON-RPC request, retrying on another endpoint if the network fails.

        :param retry: ``False`` for requests with side effects: a network
            failure is raised as is, since the request may have been executed.
        """

        retries_left = self.retries if retry else 0
        while True:
            connection = await self._ensure_connection()
            try:
                return await connection.request(method, params, timeout)
            except (ConnectionLost, RequestTimeout) as e:
                LOGGER.warning("request to %s failed: %s", connection.endpoint, e)
                await self._drop(connection)
                if retries_left == 0:
                    raise
                retries_left -= 1

    async def subscribe(
        self, method: str, params: list[Any] | None, unsubscribe: str
    ) -> Subscription:
        """Start a subscription on the current connection. It is not moved if the
        connection drops: iteration raises ``ConnectionLost`` and the caller decides."""

        connection = await self._ensure_connection()
        return await connection.subscribe(method, params, unsubscribe)

    # Storage

    async def runtime(self, at: str | None = None) -> Runtime:
        """The runtime metadata of block ``at`` (the best block if ``None``)."""

        return await self.runtimes.get(self, at)

    async def query(self, pallet: str, item: str, *keys: Any, at: str | None = None) -> Any:
        """Read a storage value; see :func:`robonomicsinterface.storage.query`."""

        return await storage.query(self, self.runtimes, pallet, item, *keys, at=at)

    def query_map(
        self, pallet: str, item: str, *keys: Any, at: str | None = None, page_size: int = 100
    ) -> AsyncIterator[tuple[tuple[Any, ...], Any]]:
        """Iterate over a storage map; see :func:`robonomicsinterface.storage.query_map`."""

        return storage.query_map(
            self, self.runtimes, pallet, item, *keys, at=at, page_size=page_size
        )

    async def constant(self, pallet: str, name: str, *, at: str | None = None) -> Any:
        """A pallet constant, e.g. ``await client.constant("Datalog", "WindowSize")``."""

        return await storage.constant(self, self.runtimes, pallet, name, at=at)

    # Extrinsics

    async def compose_call(
        self, pallet: str, function: str, args: Mapping[str, Any] | None = None
    ) -> Call:
        """Encode a call for the current runtime; see :func:`~.extrinsic.compose_call`."""

        return compose_call(await self.runtime(), pallet, function, args)

    async def sign(
        self,
        call: Call,
        keypair: Keypair,
        *,
        nonce: int | None = None,
        tip: int = 0,
        era_period: int | None = DEFAULT_ERA_PERIOD,
    ) -> SignedExtrinsic:
        """Sign a call: the nonce from the node, a mortal era from the finalized head.

        :param era_period: blocks the extrinsic stays valid; ``None`` for immortal.
        """

        runtime = await self.runtime()
        if call.spec_version != runtime.version.spec_version:
            raise MetadataError(
                f"the call was composed for runtime {call.spec_version}, the chain now runs "
                f"{runtime.version.spec_version}; compose it again"
            )
        genesis = await self.runtimes.genesis_hash(self)
        if era_period is None:
            era, birth_hash = Era.immortal(), genesis
        else:
            head = str(await self.request("chain_getFinalizedHead"))
            number = int((await self.request("chain_getHeader", [head]))["number"], 16)
            era = Era.mortal(era_period, number)
            birth = era.birth(number)
            birth_hash = (
                head if birth == number else str(await self.request("chain_getBlockHash", [birth]))
            )
        if nonce is None:
            nonce = int(await self.request("system_accountNextIndex", [keypair.address]))
        context = SigningContext(
            nonce=nonce,
            era=era,
            birth_hash=birth_hash,
            genesis_hash=genesis,
            spec_version=runtime.version.spec_version,
            transaction_version=runtime.version.transaction_version,
            tip=tip,
        )
        return sign_extrinsic(runtime, call, keypair, context)

    async def validate(self, extrinsic: SignedExtrinsic) -> None:
        """Ask the runtime whether it would accept the extrinsic, without sending it.

        This is the transaction pool's own check, reached through ``state_call``
        (allowed on public nodes). It turns an opaque "Invalid Transaction" into
        a reason. ``Future`` is not an error: the pool queues such transactions.

        :raises InvalidTransaction: with the reason and what it usually means.
        """

        best = str(await self.request("chain_getBlockHash", []))
        data = "0x02" + extrinsic.data.hex() + best.removeprefix("0x")
        answer = await self.request(
            "state_call", ["TaggedTransactionQueue_validate_transaction", data, best]
        )
        invalid = explain_invalid_transaction(bytes.fromhex(str(answer).removeprefix("0x")))
        if invalid is not None and invalid[0] != "Future":
            raise InvalidTransaction(*invalid)

    async def submit(
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
        """Sign, check, send and follow an extrinsic until it is in a block.

        Inclusion is not success: the block's events are read, and a failed
        call raises :class:`~robonomicsinterface.errors.ExtrinsicFailed` naming
        the pallet error (``RWS.NotLinkedDevice`` and the like).

        :raises InvalidTransaction: refused before sending (see :meth:`validate`).
        :raises ExtrinsicFailed: included, but the call failed.
        :raises ExtrinsicDropped: the node dropped it.
        :raises ExtrinsicOutcomeUnknown: sent, but the connection or the wait ran
            out; it may still land, so look it up before sending it again.
        """

        async with self._nonce_lock(keypair.address):
            extrinsic = await self.sign(call, keypair, tip=tip, era_period=era_period)
            if validate:
                await self.validate(extrinsic)
            try:
                subscription = await self.subscribe(
                    "author_submitAndWatchExtrinsic", [extrinsic.hex], "author_unwatchExtrinsic"
                )
            except RpcError as e:
                raise _pool_rejection(e) from e
            except TransportError as e:
                raise ExtrinsicOutcomeUnknown(extrinsic.hash, str(e)) from e
        async with subscription:
            return await self._follow(extrinsic, subscription, wait_for, timeout)

    async def submit_nowait(
        self,
        call: Call,
        keypair: Keypair,
        *,
        tip: int = 0,
        era_period: int | None = DEFAULT_ERA_PERIOD,
        validate: bool = True,
    ) -> str:
        """Sign and send without waiting for a block; returns the extrinsic hash."""

        async with self._nonce_lock(keypair.address):
            extrinsic = await self.sign(call, keypair, tip=tip, era_period=era_period)
            if validate:
                await self.validate(extrinsic)
            try:
                await self.request("author_submitExtrinsic", [extrinsic.hex], retry=False)
            except RpcError as e:
                raise _pool_rejection(e) from e
            except TransportError as e:
                raise ExtrinsicOutcomeUnknown(extrinsic.hash, str(e)) from e
        return extrinsic.hash

    def _nonce_lock(self, address: str) -> asyncio.Lock:
        """One submission per account at a time, so two never take the same nonce."""

        return self._nonce_locks.setdefault(address, asyncio.Lock())

    async def _follow(
        self,
        extrinsic: SignedExtrinsic,
        subscription: Subscription,
        wait_for: str,
        timeout: float,
    ) -> ExtrinsicResult:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            try:
                status = await subscription.next(timeout=max(remaining, 0.001))
            except RequestTimeout:
                raise ExtrinsicOutcomeUnknown(
                    extrinsic.hash, f"not {wait_for.replace('_', ' ')} within {timeout}s"
                ) from None
            except ConnectionLost as e:
                raise ExtrinsicOutcomeUnknown(extrinsic.hash, str(e)) from e

            if isinstance(status, str):
                if status in ("dropped", "invalid"):
                    raise ExtrinsicDropped(extrinsic.hash, status)
                continue  # "future", "ready"
            if not isinstance(status, dict):
                continue
            if "usurped" in status:
                raise ExtrinsicDropped(extrinsic.hash, "usurped")
            if "dropped" in status or "invalid" in status:
                raise ExtrinsicDropped(extrinsic.hash, next(iter(status)))
            if "finalityTimeout" in status:
                raise ExtrinsicOutcomeUnknown(extrinsic.hash, "finality timed out")
            if "inBlock" in status and wait_for == "in_block":
                return await self._result(extrinsic, str(status["inBlock"]), finalized=False)
            if "finalized" in status:
                return await self._result(extrinsic, str(status["finalized"]), finalized=True)

    async def _result(
        self, extrinsic: SignedExtrinsic, block_hash: str, *, finalized: bool
    ) -> ExtrinsicResult:
        block = await self.request("chain_getBlock", [block_hash])
        try:
            extrinsics = [str(x).lower() for x in block["block"]["extrinsics"]]
            number = int(block["block"]["header"]["number"], 16)
        except (TypeError, KeyError, ValueError) as e:
            raise ExtrinsicOutcomeUnknown(
                extrinsic.hash, "the node returned an unreadable block"
            ) from e
        try:
            index = extrinsics.index(extrinsic.hex.lower())
        except ValueError:
            raise ExtrinsicOutcomeUnknown(
                extrinsic.hash, f"block {block_hash} does not contain it"
            ) from None

        runtime = await self.runtime(block_hash)
        records = await self.query("System", "Events", at=block_hash)
        events = tuple(e for e in decode_events(records) if e.extrinsic_index == index)
        result = ExtrinsicResult(extrinsic.hash, block_hash, number, index, events, finalized)

        failed = result.find("System", "ExtrinsicFailed")
        if failed is not None:
            dispatch_error = (failed.attributes or {}).get("dispatch_error")
            pallet, error, docs, message = dispatch_error_message(runtime, dispatch_error)
            raise ExtrinsicFailed(message, pallet=pallet, error=error, docs=docs, result=result)
        if result.find("System", "ExtrinsicSuccess") is None:
            raise ExtrinsicOutcomeUnknown(extrinsic.hash, "the block records no outcome for it")
        return result

    # Connections

    async def _ensure_connection(self) -> Connection:
        connection = self._connection
        if connection is not None and not connection.closed:
            return connection
        async with self._connect_lock:
            connection = self._connection
            if connection is not None and not connection.closed:
                return connection
            if self._closed:
                raise ConnectionLost("the client is closed")
            return await self._connect_any()

    def _candidates(self) -> list[int]:
        """Endpoint indices to try: healthy ones by priority, recently failed last."""

        now = time.monotonic()

        def recently_failed(index: int) -> bool:
            failed = self._failed_at.get(index)
            return failed is not None and now - failed < self.failback_interval

        order = range(len(self.endpoints))
        fresh = [i for i in order if not recently_failed(i)]
        return fresh + [i for i in order if recently_failed(i)]

    async def _connect_any(self) -> Connection:
        failures: list[ConnectionFailed] = []
        for index in self._candidates():
            try:
                connection = await self._open(self.endpoints[index])
            except ConnectionFailed as e:
                LOGGER.warning("skipping %s", e)
                self._failed_at[index] = time.monotonic()
                failures.append(e)
                continue
            self._failed_at.pop(index, None)
            self._activate(connection, index)
            return connection
        raise AllEndpointsFailed(failures)

    async def _open(self, endpoint: str) -> Connection:
        """Open and vet one endpoint; any problem is a ``ConnectionFailed``."""

        connection = await Connection.open(
            endpoint,
            timeout=self.timeout,
            connect_timeout=self.connect_timeout,
            max_message_bytes=self._max_message_bytes,
            ssl=self._ssl,
            user_agent=_user_agent(),
        )
        try:
            await self._vet(connection)
        except BaseException:
            await connection.close()
            raise
        return connection

    async def _vet(self, connection: Connection) -> None:
        endpoint = connection.endpoint
        try:
            genesis = await connection.request("chain_getBlockHash", [0], self.connect_timeout)
            health = await connection.request("system_health", [], self.connect_timeout)
        except (TransportError, RpcError) as e:
            raise ConnectionFailed(endpoint, f"does not answer as a Substrate node ({e})") from e

        if self.genesis_hash is not None and genesis != self.genesis_hash:
            raise ConnectionFailed(endpoint, f"wrong chain: genesis {genesis}")
        if self.require_healthy and isinstance(health, dict):
            if health.get("isSyncing"):
                raise ConnectionFailed(endpoint, "the node is still syncing")
            if health.get("shouldHavePeers", True) and not health.get("peers"):
                raise ConnectionFailed(endpoint, "the node has no peers")
        self.runtimes.set_genesis_hash(str(genesis))

    def _activate(self, connection: Connection, index: int) -> None:
        previous = self._connection
        self._connection = connection
        self._active_index = index
        LOGGER.info("using %s", connection.endpoint)
        self._restart_watcher(connection)
        if previous is not None and previous is not connection and not previous.closed:
            self._spawn(self._retire(previous))

    async def _drop(self, connection: Connection) -> None:
        """Give up on a connection after a failure and remember the endpoint failed."""

        if self._connection is connection:
            if self._active_index is not None:
                self._failed_at[self._active_index] = time.monotonic()
            self._connection = None
            self._active_index = None
            self.runtimes.set_current(None)
        await connection.close()

    async def _retire(self, connection: Connection) -> None:
        """Close a replaced connection once its in-flight work is done."""

        deadline = time.monotonic() + _RETIRE_GRACE_SECONDS
        while connection.busy and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
        await connection.close()

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # Runtime version tracking

    def _restart_watcher(self, connection: Connection) -> None:
        if self._watcher is not None:
            self._watcher.cancel()
        self.runtimes.set_current(None)
        self._watcher = asyncio.create_task(
            self._watch_runtime_version(connection), name="robonomics-runtime-version"
        )

    async def _watch_runtime_version(self, connection: Connection) -> None:
        """Keep the runtime cache told about upgrades, so best-block queries need
        no version request. Without the subscription, the cache simply asks."""

        try:
            subscription = await connection.subscribe(
                "state_subscribeRuntimeVersion", [], "state_unsubscribeRuntimeVersion"
            )
        except (TransportError, RpcError) as e:
            LOGGER.debug("runtime version subscription unavailable: %s", e)
            return
        try:
            async for version in subscription:
                self.runtimes.set_current(RuntimeVersion.from_rpc(version))
        except TransportError:
            pass
        finally:
            if self._connection is connection:
                self.runtimes.set_current(None)
            await subscription.close()

    # Failback

    async def _failback_loop(self) -> None:
        while True:
            await asyncio.sleep(self.failback_interval)
            with contextlib.suppress(Exception):
                await self._try_failback()

    async def _try_failback(self) -> None:
        """If a more preferred endpoint is usable again, move to it."""

        active = self._active_index
        if active is None or active == 0:
            return
        for index in range(active):
            try:
                connection = await self._open(self.endpoints[index])
            except ConnectionFailed as e:
                LOGGER.debug("failback to %s not possible: %s", self.endpoints[index], e)
                self._failed_at[index] = time.monotonic()
                continue
            async with self._connect_lock:
                self._failed_at.pop(index, None)
                self._activate(connection, index)
            return


def _pool_rejection(error: RpcError) -> InvalidTransaction | RpcError:
    """Turn the pool's "Invalid Transaction" answer into an explained error."""

    if error.code not in (_POOL_INVALID, _POOL_UNKNOWN):
        return error
    detail = str(error.data or error.message)
    lowered = detail.lower()
    kind = next((k for needle, k in _POOL_REJECTIONS.items() if needle in lowered), "Rejected")
    from .extrinsic import INVALID_EXPLANATIONS

    return InvalidTransaction(kind, INVALID_EXPLANATIONS.get(kind, detail))
