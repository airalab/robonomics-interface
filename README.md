# robonomics-interface

Python client for the [Robonomics](https://robonomics.network/) parachain on Polkadot:
ED25519 accounts, the multi-recipient report envelope, and (in progress) storage
queries, Datalog and RWS subscriptions.

> [!IMPORTANT]
> **3.0 is a rewrite and is not compatible with 2.x.** It no longer depends on
> `substrate-interface`: the core is pure Python plus packages with wheels for every
> platform, including Home Assistant on Raspberry Pi and HA Green (musl, aarch64).
> 2.x stays available on PyPI as `robonomics-interface<3`.

## Status

| Part | State |
| --- | --- |
| Keys, SS58, BIP39, message encryption, envelope | ready |
| Metadata and storage queries | planned |
| Async transport, local node with public fallback | planned |
| Extrinsics with events and readable errors | planned |
| Datalog, RWS, System helpers; sync wrapper | planned |
| sr25519 (`[sr25519]` extra) | next release |

## Installation

```bash
pip install --pre robonomics-interface
```

Python 3.12 or newer. Core dependencies: `pynacl`, `scalecodec`, `websockets`, `xxhash`.

## Keys

Only ED25519 accounts are supported in 3.0. The same mnemonic gives the same address
as polkadot.js and substrate-interface.

```python
from robonomicsinterface import Keypair, generate_mnemonic

mnemonic = generate_mnemonic()
site = Keypair.from_mnemonic(mnemonic)
print(site.address)  # 4..., SS58 format 32

Keypair.from_secret("0x<32-byte hex seed>")  # what a person pastes: mnemonic or seed
Keypair.from_uri("//Alice")  # development keys and hard paths
integrator = Keypair.from_address("4F...")  # public only: verify and encrypt to
```

A keypair never exposes its secret: `repr()` shows the address only, exceptions
never contain the input, and pickling is refused.

## Report envelope

One symmetric key encrypts the payload; that key is wrapped for every recipient.
The format is the one Robonomics Report Service already publishes.

```python
from robonomicsinterface import decrypt_package, encrypt_for_recipients, parse_decrypted

package = encrypt_for_recipients(log_text, site, [integrator_address], {"orig_file_name": "ha.log"})
payload, meta = parse_decrypted(decrypt_package(package, integrator_keypair, site.address))
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

`tests/fixtures/compat_vectors.json` pins what the 2.x stack produced (addresses,
ciphertexts, signatures); `tests/fixtures/generate_compat_vectors.py` regenerates it.
CI also installs the wheel in `python:3.13-alpine` on aarch64 without a compiler.

## License

Apache-2.0.
