"""A node that answers from the recorded mainnet fixtures."""

import gzip
from collections import Counter
from functools import cache
from typing import Any

from conftest import FIXTURES, load_fixture
from robonomicsinterface.runtime import Runtime, RuntimeVersion


@cache
def recorded_metadata() -> str:
    return gzip.decompress((FIXTURES / "metadata.hex.gz").read_bytes()).decode()


@cache
def recorded_runtime() -> Runtime:
    """Parsed once per test session; tests must not mutate it."""

    samples = load_fixture("chain_samples.json")
    version = RuntimeVersion(
        samples["spec_name"], samples["spec_version"], samples["transaction_version"]
    )
    return Runtime(recorded_metadata(), version, samples["genesis_hash"])


class FakeNode:
    """Implements RpcRequester over chain_samples.json, counting every call."""

    def __init__(self) -> None:
        self.samples = load_fixture("chain_samples.json")
        self.metadata = recorded_metadata()
        self.calls: Counter[str] = Counter()
        self.spec_version = self.samples["spec_version"]
        self.storage: dict[str, str] = {}
        for item in self.samples["maps"]:
            self.storage.update(dict(item["entries"]))

    def add_value(self, key: str, raw: str) -> None:
        self.storage[key] = raw

    async def request(self, method: str, params: list[Any] | None = None) -> Any:
        params = params or []
        self.calls[method] += 1
        handler = getattr(self, "_" + method)
        return handler(*params)

    def _system_health(self) -> dict[str, Any]:
        return {"peers": 12, "isSyncing": False, "shouldHavePeers": True}

    def _chain_getBlockHash(self, number: int | None = None) -> str:
        return self.samples["genesis_hash"] if number == 0 else self.samples["block_hash"]

    def _state_getRuntimeVersion(self, at: str | None = None) -> dict[str, Any]:
        return {
            "specName": self.samples["spec_name"],
            "specVersion": self.spec_version,
            "transactionVersion": self.samples["transaction_version"],
        }

    def _state_getMetadata(self, at: str | None = None) -> str:
        return self.metadata

    def _state_getStorage(self, key: str, at: str | None = None) -> str | None:
        return self.storage.get(key)

    def _state_getKeysPaged(
        self, prefix: str, count: int, start: str | None, at: str | None = None
    ) -> list[str]:
        keys = sorted(
            k for k in self.storage if k.startswith(prefix) and (start is None or k > start)
        )
        return keys[:count]

    def _state_queryStorageAt(self, keys: list[str], at: str | None = None) -> list[dict[str, Any]]:
        return [{"block": at, "changes": [[k, self.storage.get(k)] for k in keys]}]
