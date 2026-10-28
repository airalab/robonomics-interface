# robonomics-interface

Python client for the [Robonomics](https://robonomics.network/) parachain on Polkadot:
ED25519 and sr25519 accounts, the multi-recipient report envelope, storage queries, Datalog and
RWS subscriptions.

> [!IMPORTANT]
> **3.0 is a rewrite and is not compatible with 2.x.** It no longer depends on
> `substrate-interface`: the core is pure Python plus packages with wheels for every
> platform, including Home Assistant on Raspberry Pi and HA Green (musl, aarch64).
> 2.x stays available on PyPI as `robonomics-interface<3`. Moving from 2.x or
> `substrate-interface`: see [MIGRATION.md](MIGRATION.md).

## Status

| Part | State |
| --- | --- |
| Keys, SS58, BIP39, message encryption, envelope | ready |
| Metadata and storage queries | ready |
| Async client, local node with public fallback | ready |
| Extrinsics with events and readable errors | ready |
| Datalog, RWS, System, Balances helpers | ready |
| Synchronous wrapper | ready |
| sr25519 keys, encryption and wallet-backup import (`[sr25519]` extra) | ready |

## Installation

```bash
pip install robonomics-interface
```

Python 3.12 or newer. Core dependencies: `pynacl`, `scalecodec`, `websockets`, `xxhash`.

sr25519 accounts (the default of Polkadot wallets) need an extra, which also installs
from wheels without a compiler on musl and aarch64:

```bash
pip install 'robonomics-interface[sr25519]'
```

Without it the core works as before, and asking for an sr25519 key raises an
`ImportError` that says what to install.

## Keys

ED25519 is the default: the same mnemonic gives the same address as polkadot.js and
substrate-interface, and existing code keeps its addresses. sr25519 is chosen
explicitly, with `crypto_type=SR25519` or `"sr25519"` (a string fits a config file).

```python
from robonomicsinterface import Keypair, generate_mnemonic

mnemonic = generate_mnemonic()
site = Keypair.from_mnemonic(mnemonic)
print(site.address)  # 4..., SS58 format 32

Keypair.from_secret("0x<32-byte hex seed>")  # what a person pastes: mnemonic or seed
Keypair.from_uri("//Alice")  # development keys and hard paths
integrator = Keypair.from_address("4F...")  # public only: verify and encrypt to
```

```python
from robonomicsinterface import SR25519, Keypair

site = Keypair.from_mnemonic(mnemonic, crypto_type=SR25519)  # also from_seed, from_uri, from_secret
site.crypto_type  # 1; ED25519 is 0

# A backup exported by a polkadot.js wallet: the file says which type the account is.
site = Keypair.from_json(backup_json, password)
```

`Keypair.from_json` takes the keyring JSON (version 3) as a string, bytes or dict.
Decrypting it uses scrypt with 128 MiB: about 0.2 s on a laptop and seconds on a
Raspberry Pi, so call it off the event loop (`await asyncio.to_thread(...)`). ECDSA and
Ethereum backups, a backup without a password and a wrong password are refused.

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

### sr25519 in the Report Service

- **One key type per package.** The sender and every recipient of a package have the
  same type, sr25519 to sr25519 or ED25519 to ED25519; the type of a package is the
  type of the sender's key. A mixed list raises `RecipientError`.
- **The type is a setting of the object, not a guess.** An address does not say what
  type of key it belongs to, so the Home Assistant config (and the connector's list of
  integrators) carries it. Opening a package with a key of the wrong type raises
  `PayloadError` that names the mismatch; sometimes a wrong-type address is refused
  already when encrypting, but not always.
- **sr25519 encryption does not authenticate the sender.** It is the ECIES scheme of
  [py-sr25519-encryption](https://github.com/Fingerling42/py-sr25519-encryption) by
  Ivan Berman and of SubMessage (the same bytes, so a browser can decrypt with
  polkadot.js), and the sender's key does not enter it. In the Report Service the
  chain provides authenticity: the connector reads datalog records only from the
  addresses in its senders registry. ED25519 packages are unchanged.

## Connecting

```python
from robonomicsinterface import DEFAULT_ENDPOINT, RobonomicsClient

async with RobonomicsClient(["ws://192.168.1.10:9944", DEFAULT_ENDPOINT]) as client:
    window = await client.constant("Datalog", "WindowSize")
    ledger = await client.query("RWS", "Ledger", owner_address)
    async for (owner,), devices in client.query_map("RWS", "Devices"):
        ...
```

Endpoints are used in the order given. A node is accepted only if it is on
Robonomics Polkadot (checked by genesis hash) and is neither syncing nor without
peers; otherwise the next endpoint is tried. While on a fallback, the client
periodically tries to return to a preferred endpoint. `client.endpoint` tells which
node is in use.

Every request has a timeout. Reads are retried on another endpoint after a network
failure; network failures raise `TransportError` subclasses (worth retrying), while
`RpcError`, `DecodeError` and the like mean retrying will not help.

## Datalog, RWS and accounts

```python
async with RobonomicsClient() as client:
    # Datalog: slot numbers mean what they say — item(address, 0) is slot 0
    latest = await client.datalog.latest(site_address)
    for item in await client.datalog.items(site_address):  # oldest first, one request
        print(item.index, item.timestamp, item.data)  # bytes; item.text for UTF-8
    await client.datalog.record(site, b"QmReport...", subscription_owner=integrator_address)

    # RWS subscriptions
    ledger = await client.rws.ledger(integrator_address)  # None without a subscription
    if ledger and not ledger.is_active():
        print("expired on", ledger.expires_at)
    await client.rws.add_devices(integrator, site_address)  # read, extend, write back
    await client.rws.set_devices(integrator, [a, b, c])  # a plain list, max 32

    # Accounts
    if not await client.system.exists(site_address):
        print("send it the existential deposit first")
```

Everything else is reachable through `client.query`, `client.query_map`,
`client.constant`, `client.compose_call` and `client.submit`.

## Without asyncio

`RobonomicsSync` is the same client for scripts, cron jobs and tools: every method
blocks until the result is there. It runs the async client on an event loop in a
background thread, so behaviour, errors and timeouts are identical.

```python
from robonomicsinterface import RobonomicsSync

with RobonomicsSync() as client:
    for item in client.datalog.items(site_address):
        ...
    client.rws.set_devices(integrator, devices)
```

Inside an event loop (Home Assistant, any asyncio application) use `RobonomicsClient`:
a blocking call there would stall the loop, so `RobonomicsSync` raises `RuntimeError`
instead.

## Sending extrinsics

```python
from robonomicsinterface import ExtrinsicFailed, InvalidTransaction

record = await client.compose_call("Datalog", "record", {"record": b"QmReport..."})
call = await client.compose_call("RWS", "call", {"subscription_id": owner, "call": record})
try:
    result = await client.submit(call, site)  # waits until the block
except InvalidTransaction as e:  # refused before sending
    print(e.kind, e.explanation)  # "Payment: ... send it the existential deposit"
except ExtrinsicFailed as e:  # in a block, but the call failed
    print(e.pallet, e.error)  # "RWS", "NotLinkedDevice"
else:
    print(result.block_number, result.find("Datalog", "NewRecord"))
```

Arguments take natural Python values: `bytes` are sent as bytes (a `str` starting with
`0x` would be read as hex), a `Keypair` stands for its account, a `Call` nests, and a
`BoundedVec` takes a plain list (`{"devices": [a, b]}`).

`submit` signs with a nonce from the node and a mortal era (64 blocks from the
finalized head), asks the runtime to validate the extrinsic first, sends it once and
reads the block's events: inclusion alone is not success. Signed extensions are taken
from the runtime metadata. A lost connection after sending raises
`ExtrinsicOutcomeUnknown` with the extrinsic hash, never a silent resend.

### Your own node on the local network

A fully synced node at home makes a good first endpoint for Home Assistant. Expose its
RPC to the LAN only with safe methods, e.g.
`--rpc-external --rpc-methods=safe --rpc-cors=all`, and keep it off the internet. The
library uses safe methods only. Prefer a separate RPC node to opening a collator's RPC:
a collator's unsafe methods (`author_rotateKeys`, `author_insertKey`) must stay closed.
Plain `ws://` is fine inside the LAN; for `wss://` with a private CA pass
`ssl=ssl.create_default_context(cafile=...)`.

## Development

```bash
uv sync
uv run pytest                                  # offline: recorded mainnet data, local fake nodes
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Integration tests run against a development node with the newest Robonomics runtime
that ships its wasm in a GitHub release (v52; mainnet runs 53). `scripts/devchain.sh`
downloads pinned, checksum-verified `polkadot-omni-node` and `chain-spec-builder` (Parity)
and that runtime, builds the development chain spec (funded sr25519 dev accounts, `//Alice`
among them), seeds RWS auctions into its genesis (the runtime has no Sudo), and starts the
node. The RWS tests tell one user story: a new account is funded by transfer, wins an
auction, sets its devices and writes through the subscription. A won auction is spent, so a
node serves four runs of the suite; restart it for more:

```bash
scripts/devchain.sh &                          # ws://127.0.0.1:9944
ROBONOMICS_DEV_URL=ws://127.0.0.1:9944 uv run pytest -m integration
ROBONOMICS_MAINNET_SMOKE=1 uv run pytest -m mainnet   # read-only, sends nothing
```

`tests/fixtures/compat_vectors.json` pins what the 2.x stack produced (addresses,
ciphertexts, signatures); `tests/fixtures/generate_compat_vectors.py` regenerates it.
`scripts/fetch_chain_fixtures.py` re-records mainnet metadata and storage samples after
a runtime upgrade. CI also installs the wheel in `python:3.13-alpine` on aarch64 and
x86_64 without a compiler, with and without the `[sr25519]` extra, and runs the tests
on a core install that has no sr25519 packages.

`tests/fixtures/generate_sr25519_old_stack.py` and `generate_sr25519_js.mjs` regenerate
the sr25519 vectors from the 2.x stack and polkadot.js; the tests check against them
and do not compare signature bytes, which sr25519 randomizes. To also check our blobs
in polkadot.js, point `ROBONOMICS_JS_DIR` at a directory with the script and its
`node_modules`.

### Documentation

The API reference is built from the docstrings with Sphinx and published to
<https://airalab.github.io/robonomics-interface/> when `main` or a `v*` tag is pushed:

```bash
uv run --group docs sphinx-build -W -b html docs/source docs/build   # warnings fail the build
```

### Releasing

1. `ROBONOMICS_MAINNET_SMOKE=1 uv run pytest -m mainnet` against the live runtime.
2. Set `version` in `pyproject.toml`, date the section in `CHANGELOG.md`.
3. Tag `vX.Y.Z` and push the tag: CI builds the package and uploads it with the
   maintainer's token in the `PYPI_API_TOKEN` repository secret (after approval, if
   the `pypi` environment has required reviewers).

## License

Apache-2.0.
