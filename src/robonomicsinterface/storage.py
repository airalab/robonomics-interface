"""Storage keys, hashers and queries, driven by the runtime metadata.

A storage key is ``twox128(pallet) ++ twox128(item)`` followed, for a map, by
each key component hashed with the hasher the metadata names for it. The
``*Concat`` and ``Identity`` hashers keep the encoded key after the hash, so
keys found by iteration can be decoded back; the others cannot.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

import xxhash

from .errors import DecodeError, EncodeError, MetadataError
from .rpc import RpcRequester
from .runtime import Runtime, RuntimeCache, StorageEntry

__all__ = [
    "HASHERS",
    "constant",
    "decode_storage_key",
    "decode_storage_value",
    "query",
    "query_map",
    "query_raw_multi",
    "storage_key",
    "storage_prefix",
    "twox128",
]

MAX_PAGE_SIZE = 1000  # state_getKeysPaged refuses more on public nodes


def _twox(data: bytes, seeds: int) -> bytes:
    return b"".join(
        xxhash.xxh64(data, seed=seed).intdigest().to_bytes(8, "little") for seed in range(seeds)
    )


def twox128(data: bytes) -> bytes:
    return _twox(data, 2)


def _blake2(data: bytes, size: int) -> bytes:
    return hashlib.blake2b(data, digest_size=size).digest()


HASHERS: dict[str, Callable[[bytes], bytes]] = {
    "Identity": lambda data: data,
    "Twox64Concat": lambda data: _twox(data, 1) + data,
    "Twox128": twox128,
    "Twox256": lambda data: _twox(data, 4),
    "Blake2_128": lambda data: _blake2(data, 16),
    "Blake2_256": lambda data: _blake2(data, 32),
    "Blake2_128Concat": lambda data: _blake2(data, 16) + data,
}
# How many hash bytes precede the encoded key, for hashers that keep the key.
_TRANSPARENT = {"Identity": 0, "Twox64Concat": 8, "Blake2_128Concat": 16}
# Output length of hashers that do not keep the key.
_OPAQUE = {"Twox128": 16, "Twox256": 32, "Blake2_128": 16, "Blake2_256": 32}


def _hasher(name: str) -> Callable[[bytes], bytes]:
    try:
        return HASHERS[name]
    except KeyError:
        raise MetadataError(f"unknown storage hasher {name!r}") from None


def storage_prefix(pallet: str, item: str) -> bytes:
    return twox128(pallet.encode()) + twox128(item.encode())


def _normalize_keys(entry: StorageEntry, keys: Sequence[Any]) -> list[Any]:
    """Map the caller's arguments onto the entry's key components.

    A map keyed by a tuple under one hasher (``Datalog.DatalogItem`` is keyed
    by ``(AccountId, u64)``) takes the tuple's parts as separate arguments,
    or the tuple itself.
    """

    if len(entry.key_types) == 1 and len(keys) > 1:
        return [tuple(keys)]
    if len(keys) > len(entry.key_types):
        raise EncodeError(
            f"{entry.pallet}.{entry.name} takes {len(entry.key_types)} key(s), got {len(keys)}"
        )
    return list(keys)


def storage_key(runtime: Runtime, entry: StorageEntry, keys: Sequence[Any] = ()) -> bytes:
    """The key of ``entry`` for ``keys``.

    With fewer keys than the entry has, the result is the prefix shared by
    every entry starting with those keys, for iteration.
    """

    key = storage_prefix(entry.pallet, entry.name)
    for value, type_string, hasher in zip(
        _normalize_keys(entry, keys), entry.key_types, entry.hashers, strict=False
    ):
        key += _hasher(hasher)(runtime.encode(type_string, value))
    return key


def decode_storage_key(runtime: Runtime, entry: StorageEntry, key: bytes | str) -> tuple[Any, ...]:
    """The key components behind a full storage key, e.g. one found by ``query_map``.

    :raises DecodeError: a component is hashed with a hasher that does not
        keep the key, or the key does not belong to ``entry``.
    """

    raw = bytes.fromhex(key.removeprefix("0x")) if isinstance(key, str) else bytes(key)
    prefix = storage_prefix(entry.pallet, entry.name)
    if not raw.startswith(prefix):
        raise DecodeError(f"the key is not under {entry.pallet}.{entry.name}")

    rest = raw[len(prefix) :]
    values: list[Any] = []
    for type_string, hasher in zip(entry.key_types, entry.hashers, strict=True):
        if hasher in _OPAQUE:
            raise DecodeError(
                f"{entry.pallet}.{entry.name} hashes its key with {hasher}; it cannot be recovered"
            )
        offset = _TRANSPARENT.get(hasher)
        if offset is None:
            raise MetadataError(f"unknown storage hasher {hasher!r}")
        value, used = runtime.decode_prefix(type_string, rest[offset:])
        values.append(value)
        rest = rest[offset + used :]
    if rest:
        raise DecodeError(f"{len(rest)} unexpected bytes after the key")
    return tuple(values)


def decode_storage_value(runtime: Runtime, entry: StorageEntry, raw: bytes | str | None) -> Any:
    """Decode a stored value; an absent one is ``None`` or the declared default."""

    if raw is None:
        if entry.modifier == "Optional":
            return None
        raw = entry.default
    return runtime.decode(entry.value_type, raw)


# Queries


async def query(
    rpc: RpcRequester,
    runtimes: RuntimeCache,
    pallet: str,
    item: str,
    *keys: Any,
    at: str | None = None,
) -> Any:
    """Read one storage value at block ``at`` (the node's best block if ``None``).

    An absent value comes back as ``None`` for an ``Optional`` item and as the
    declared default otherwise, exactly as the runtime would see it.
    """

    runtime = await runtimes.get(rpc, at)
    entry = runtime.storage_entry(pallet, item)
    if len(_normalize_keys(entry, keys)) != len(entry.key_types):
        raise EncodeError(f"{pallet}.{item} takes {len(entry.key_types)} key(s), got {len(keys)}")
    key = "0x" + storage_key(runtime, entry, keys).hex()
    raw = await rpc.request("state_getStorage", [key, at] if at else [key])
    return decode_storage_value(runtime, entry, raw)


async def query_raw_multi(
    rpc: RpcRequester,
    runtimes: RuntimeCache,
    pallet: str,
    item: str,
    keys: Sequence[Sequence[Any]],
    *,
    at: str | None = None,
) -> tuple[Runtime, StorageEntry, list[bytes | None]]:
    """Read many entries of one item in a single request, undecoded.

    Returns the runtime and entry used, and the raw value of each key in order
    (``None`` where nothing is stored), for callers that decode themselves or
    need to tell an absent value from a default one.
    """

    block = at or str(await rpc.request("chain_getBlockHash", []))
    runtime = await runtimes.get(rpc, block)
    entry = runtime.storage_entry(pallet, item)
    hex_keys = ["0x" + storage_key(runtime, entry, list(k)).hex() for k in keys]
    if not hex_keys:
        return runtime, entry, []
    changes = await rpc.request("state_queryStorageAt", [hex_keys, block])
    values: dict[str, str | None] = {}
    for change_set in changes or ():
        values.update((k, v) for k, v in change_set["changes"])
    raw = [values.get(k) for k in hex_keys]
    return runtime, entry, [bytes.fromhex(v.removeprefix("0x")) if v else None for v in raw]


async def query_map(
    rpc: RpcRequester,
    runtimes: RuntimeCache,
    pallet: str,
    item: str,
    *keys: Any,
    at: str | None = None,
    page_size: int = 100,
) -> AsyncIterator[tuple[tuple[Any, ...], Any]]:
    """Iterate over a storage map as ``(keys, value)`` pairs.

    Pass leading keys to iterate over part of a multi-key map. All pages are
    read at one block: ``at``, or the best block when the iteration starts.
    Order is by hashed key, i.e. arbitrary but stable.
    """

    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be within 1..{MAX_PAGE_SIZE}")

    block = at or str(await rpc.request("chain_getBlockHash", []))
    runtime = await runtimes.get(rpc, block)
    entry = runtime.storage_entry(pallet, item)
    if not entry.is_map:
        raise EncodeError(f"{pallet}.{item} is a plain value, not a map")
    prefix = "0x" + storage_key(runtime, entry, keys).hex()

    start: str | None = None
    while True:
        page: list[str] = await rpc.request("state_getKeysPaged", [prefix, page_size, start, block])
        if not page:
            return
        changes = await rpc.request("state_queryStorageAt", [page, block])
        values: dict[str, str | None] = {}
        for change_set in changes or ():
            values.update((k, v) for k, v in change_set["changes"])
        for key in page:
            raw = values.get(key)
            if raw is None:  # removed between the two requests; cannot happen at a pinned block
                continue
            yield (
                decode_storage_key(runtime, entry, key),
                decode_storage_value(runtime, entry, raw),
            )
        if len(page) < page_size:
            return
        start = page[-1]


async def constant(
    rpc: RpcRequester,
    runtimes: RuntimeCache,
    pallet: str,
    name: str,
    *,
    at: str | None = None,
) -> Any:
    """A pallet constant from the runtime metadata, e.g. ``Datalog.WindowSize``."""

    runtime = await runtimes.get(rpc, at)
    return runtime.constant(pallet, name)
