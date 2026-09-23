"""Runtime metadata: what one runtime version says about its pallets and types.

Everything is decoded from the chain's own V14 metadata and portable type
registry — there is no hand-written type registry to keep in step with runtime
upgrades. A :class:`Runtime` is built for one ``spec_version`` and is
immutable; :class:`RuntimeCache` fetches and keeps the ones in use.

Parsing metadata is CPU-bound and takes seconds on a Raspberry Pi, so the
cache does it in a worker thread, never on the event loop.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from scalecodec.base import RuntimeConfigurationObject, ScaleBytes
from scalecodec.type_registry import load_type_registry_preset

from .errors import (
    DecodeError,
    EncodeError,
    MetadataError,
    NoSuchConstant,
    NoSuchPallet,
    NoSuchStorage,
)
from .rpc import RpcRequester
from .ss58 import ROBONOMICS_SS58_FORMAT

__all__ = ["Runtime", "RuntimeCache", "RuntimeVersion", "StorageEntry"]

_METADATA_MAGIC = b"meta"
_SUPPORTED_METADATA = 14


def _to_bytes(data: bytes | str) -> bytes:
    if isinstance(data, str):
        try:
            return bytes.fromhex(data.removeprefix("0x"))
        except ValueError:
            raise DecodeError("expected 0x-prefixed hex from the node") from None
    return bytes(data)


def _raw_field(struct: Any, field: str) -> bytes:
    # scalecodec turns a Bytes field into str when it happens to be printable
    # ("\n\x00\x00\x00" for 10u32); the raw bytearray is on value_object.
    return bytes(struct.value_object[field].value_object)


@dataclass(frozen=True, slots=True)
class RuntimeVersion:
    """The identity of a runtime, as ``state_getRuntimeVersion`` reports it."""

    spec_name: str
    spec_version: int
    transaction_version: int

    @classmethod
    def from_rpc(cls, result: dict[str, Any]) -> RuntimeVersion:
        try:
            return cls(
                spec_name=str(result["specName"]),
                spec_version=int(result["specVersion"]),
                transaction_version=int(result["transactionVersion"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise DecodeError("the node returned an unreadable runtime version") from e


@dataclass(frozen=True, slots=True)
class StorageEntry:
    """How one storage item is keyed and what it holds.

    ``hashers`` and ``key_types`` have one element per key a caller passes;
    a plain value has none. A map keyed by a tuple under a single hasher
    (``Datalog.DatalogItem``) has one key of tuple type.
    """

    pallet: str
    name: str
    modifier: Literal["Optional", "Default"]
    hashers: tuple[str, ...]
    key_types: tuple[str, ...]
    value_type: str
    default: bytes
    docs: str

    @property
    def is_map(self) -> bool:
        return bool(self.hashers)


class Runtime:
    """The metadata of one runtime version, able to encode and decode its types."""

    def __init__(
        self,
        metadata: bytes | str,
        version: RuntimeVersion,
        genesis_hash: str,
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
    ) -> None:
        raw = _to_bytes(metadata)
        if raw[:4] != _METADATA_MAGIC:
            raise MetadataError("the node's answer is not runtime metadata")

        self.version = version
        self.genesis_hash = genesis_hash
        self.ss58_format = ss58_format

        config = RuntimeConfigurationObject(ss58_format=ss58_format, implements_scale_info=True)
        config.update_type_registry(load_type_registry_preset(name="core"))
        try:
            metadata_object = config.create_scale_object(
                "MetadataVersioned", data=ScaleBytes(bytearray(raw))
            )
            metadata_object.decode()
        except Exception as e:
            raise MetadataError("the runtime metadata does not decode") from e

        metadata_version = metadata_object[1].index
        if metadata_version != _SUPPORTED_METADATA:
            raise MetadataError(
                f"metadata V{metadata_version} is not supported; V{_SUPPORTED_METADATA} is"
            )
        config.add_portable_registry(metadata_object)
        config.set_active_spec_version_id(version.spec_version)

        self._config = config
        self._metadata = metadata_object
        self._pallets = {pallet.value["name"]: pallet for pallet in metadata_object.pallets}
        self._storage: dict[tuple[str, str], StorageEntry] = {}

    def __repr__(self) -> str:
        return f"<Runtime {self.version.spec_name}/{self.version.spec_version}>"

    # Pallets and storage

    @property
    def pallet_names(self) -> tuple[str, ...]:
        return tuple(self._pallets)

    def _pallet(self, name: str) -> Any:
        try:
            return self._pallets[name]
        except KeyError:
            raise NoSuchPallet(
                f"runtime {self.version.spec_version} has no pallet {name!r}"
            ) from None

    def pallet_index(self, name: str) -> int:
        return int(self._pallet(name).value["index"])

    def storage_entry(self, pallet: str, name: str) -> StorageEntry:
        """Describe ``pallet.name``; the result is cached per runtime."""

        cached = self._storage.get((pallet, name))
        if cached is not None:
            return cached

        function = self._pallet(pallet).get_storage_function(name)
        if function is None:
            raise NoSuchStorage(f"{pallet} has no storage item {name!r}")
        value = function.value
        hashers: tuple[str, ...] = ()
        key_types: tuple[str, ...] = ()
        if "Map" in value["type"]:
            hashers = tuple(function.get_param_hashers())
            key_types = tuple(function.get_params_type_string())
            if len(hashers) != len(key_types):
                raise MetadataError(f"{pallet}.{name} has mismatched hashers and keys")

        entry = StorageEntry(
            pallet=pallet,
            name=name,
            modifier=value["modifier"],
            hashers=hashers,
            key_types=key_types,
            value_type=function.get_value_type_string(),
            default=_raw_field(function, "default"),
            docs="\n".join(value.get("documentation") or ()).strip(),
        )
        self._storage[(pallet, name)] = entry
        return entry

    def constant(self, pallet: str, name: str) -> Any:
        """A pallet constant, decoded (e.g. ``Datalog.WindowSize`` → 128)."""

        for constant in self._pallet(pallet).constants or ():
            if constant.value["name"] == name:
                type_string = f"scale_info::{constant.value['type']}"
                return self.decode(type_string, _raw_field(constant, "value"))
        raise NoSuchConstant(f"{pallet} has no constant {name!r}")

    # Types

    def _scale_object(self, type_string: str, data: bytes | None = None) -> Any:
        scale_bytes = ScaleBytes(bytearray(data)) if data is not None else None
        return self._config.create_scale_object(
            type_string, data=scale_bytes, metadata=self._metadata
        )

    def decode(self, type_string: str, data: bytes | str) -> Any:
        """Decode bytes (or 0x hex) as ``type_string``; every byte must be used."""

        raw = _to_bytes(data)
        try:
            return self._scale_object(type_string, raw).decode(check_remaining=True)
        except Exception as e:
            raise DecodeError(f"{len(raw)} bytes do not decode as {type_string}") from e

    def decode_prefix(self, type_string: str, data: bytes) -> tuple[Any, int]:
        """Decode a value from the start of ``data``; return it and the bytes used."""

        try:
            scale_object = self._scale_object(type_string, data)
            value = scale_object.decode(check_remaining=False)
        except Exception as e:
            raise DecodeError(f"bytes do not start with a {type_string}") from e
        return value, scale_object.data.offset

    def encode(self, type_string: str, value: Any) -> bytes:
        """SCALE-encode ``value`` as ``type_string``."""

        try:
            return bytes(self._scale_object(type_string).encode(value).data)
        except Exception as e:
            raise EncodeError(f"the value does not encode as {type_string}") from e

    @property
    def scale_metadata(self) -> Any:
        """The underlying scalecodec metadata object (internal use)."""

        return self._metadata

    @property
    def scale_config(self) -> Any:
        """The underlying scalecodec runtime configuration (internal use)."""

        return self._config


class RuntimeCache:
    """Fetches runtime metadata on demand and keeps the few versions in use.

    Keyed by ``(genesis_hash, spec_version)``: a runtime upgrade gets new
    metadata, and a query at an old block gets the runtime of that block.
    """

    def __init__(self, ss58_format: int = ROBONOMICS_SS58_FORMAT, max_runtimes: int = 2) -> None:
        self.ss58_format = ss58_format
        self.max_runtimes = max_runtimes
        self._genesis_hash: str | None = None
        self._current: RuntimeVersion | None = None
        self._runtimes: OrderedDict[tuple[str, int], Runtime] = OrderedDict()
        self._lock = asyncio.Lock()

    async def genesis_hash(self, rpc: RpcRequester) -> str:
        if self._genesis_hash is None:
            self._genesis_hash = str(await rpc.request("chain_getBlockHash", [0]))
        return self._genesis_hash

    def set_genesis_hash(self, genesis_hash: str) -> None:
        """Record the genesis hash a connection has already verified."""

        self._genesis_hash = genesis_hash

    def set_current(self, version: RuntimeVersion | None) -> None:
        """Track the best block's runtime from ``state_subscribeRuntimeVersion``.

        While set, queries at the best block skip asking for the version. The
        client clears it whenever the subscription is not running, so a
        runtime upgrade is never missed.
        """

        self._current = version

    async def version(self, rpc: RpcRequester, at: str | None = None) -> RuntimeVersion:
        if at is None and self._current is not None:
            return self._current
        return RuntimeVersion.from_rpc(
            await rpc.request("state_getRuntimeVersion", [at] if at else [])
        )

    async def get(self, rpc: RpcRequester, at: str | None = None) -> Runtime:
        """The runtime of block ``at`` (the node's best block if ``None``)."""

        version = await self.version(rpc, at)
        genesis = await self.genesis_hash(rpc)
        cached = self._lookup(genesis, version.spec_version)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._lookup(genesis, version.spec_version)
            if cached is not None:
                return cached
            # Pin one block, so the version and the metadata cannot straddle
            # a runtime upgrade that lands between the two requests.
            block = at or str(await rpc.request("chain_getBlockHash", []))
            version = await self.version(rpc, block)
            metadata = await rpc.request("state_getMetadata", [block])
            runtime = await asyncio.to_thread(Runtime, metadata, version, genesis, self.ss58_format)
            self._store(genesis, runtime)
            return runtime

    def _lookup(self, genesis: str, spec_version: int) -> Runtime | None:
        runtime = self._runtimes.get((genesis, spec_version))
        if runtime is not None:
            self._runtimes.move_to_end((genesis, spec_version))
        return runtime

    def _store(self, genesis: str, runtime: Runtime) -> None:
        self._runtimes[(genesis, runtime.version.spec_version)] = runtime
        while len(self._runtimes) > self.max_runtimes:
            self._runtimes.popitem(last=False)

    def add(self, runtime: Runtime) -> None:
        """Seed the cache, e.g. with metadata recorded earlier."""

        if self._genesis_hash is None:
            self._genesis_hash = runtime.genesis_hash
        self._store(runtime.genesis_hash, runtime)
