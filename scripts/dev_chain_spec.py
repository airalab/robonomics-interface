"""Patch a Robonomics development chain spec for this library's integration tests.

The runtime's ``development`` preset endows and makes sudo only sr25519 dev
accounts, which this library cannot sign with (sr25519 is planned for 3.1).
This adds ED25519 dev accounts derived with the library itself, and makes the
ED25519 ``//Alice`` the sudo key:

    chain-spec-builder -c spec.json create -t development \\
        -r robonomics_runtime.compact.compressed.wasm \\
        --relay-chain rococo-local --para-id 2048 named-preset development
    python scripts/dev_chain_spec.py spec.json
    polkadot-omni-node --chain spec.json --dev

Accounts endowed: //Alice (sudo), //Bob, //Charlie, //Dave. //Eve is left
without funds on purpose, to test what an account that does not exist sees.
"""

import json
import sys
from pathlib import Path

from robonomicsinterface import Keypair

ENDOWED = ["//Alice", "//Bob", "//Charlie", "//Dave"]
SUDO = "//Alice"
ENDOWMENT = 10**18  # 10^9 XRT
GENERIC_SS58 = 42  # the format genesis JSON is written in


def ed25519_address(uri: str) -> str:
    return Keypair.from_uri(uri, ss58_format=GENERIC_SS58).address


def patch(spec: dict) -> dict:
    runtime_genesis = spec["genesis"]["runtimeGenesis"]
    config = runtime_genesis.get("patch") or runtime_genesis["config"]
    balances = config.setdefault("balances", {}).setdefault("balances", [])
    known = {address for address, _ in balances}
    for uri in ENDOWED:
        address = ed25519_address(uri)
        if address not in known:
            balances.append([address, ENDOWMENT])
    config.setdefault("sudo", {})["key"] = ed25519_address(SUDO)
    return spec


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    spec = patch(json.loads(path.read_text()))
    path.write_text(json.dumps(spec, indent=2))
    print(f"patched {path}: sudo and funds for ED25519 {', '.join(ENDOWED)}")


if __name__ == "__main__":
    main()
