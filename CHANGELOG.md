# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased] — 3.0.0

A rewrite for the current Robonomics runtime. Not compatible with 2.x; a
migration guide will ship with the release.

### Added
- `Keypair` (ED25519) from a mnemonic (with optional password), a raw seed, a
  Substrate secret URI with hard derivation (`//Alice`, `<phrase>//a//b///password`),
  a public key or an address. `from_secret()` accepts only what a person should
  paste: a mnemonic or a seed, never a derivation path.
- Message encryption (`encrypt_message` / `decrypt_message`) byte-compatible with
  substrate-interface.
- Multi-recipient envelope: `encrypt_for_recipients`, `decrypt_package`,
  `parse_decrypted`, in the format Robonomics Report Service publishes.
- SS58 helpers: `encode_address`, `decode_address`, `address_format`,
  `is_valid_address` (format 32 by default).
- BIP39 English: `generate_mnemonic`, `validate_mnemonic`.
- A typed exception hierarchy rooted at `RobonomicsError`; input errors are also
  `ValueError`. No exception message contains secret material.
- Runtime metadata (V14) decoded from the chain itself: `Runtime` describes one
  runtime version (pallets, storage entries, constants, SCALE encode/decode);
  `RuntimeCache` fetches metadata per `(genesis_hash, spec_version)`, parses it off
  the event loop and reloads it after a runtime upgrade.
- Storage: every hasher (`Identity`, `Twox64Concat`, `Twox128`, `Twox256`,
  `Blake2_128`, `Blake2_256`, `Blake2_128Concat`), multi-key maps and maps keyed by
  a tuple; `query`, `query_map` (paged, pinned to one block, keys decoded back) and
  `constant`. An absent value is `None` for an `Optional` item and the declared
  default otherwise.
- New errors: `MetadataError`, `NoSuchPallet`, `NoSuchStorage`, `NoSuchConstant`,
  `EncodeError`, `DecodeError`.
- `RobonomicsClient`, an asyncio client over one multiplexed WebSocket: endpoints in
  priority order (e.g. a LAN node first, the public node as fallback), a node is
  used only if its genesis hash matches Robonomics Polkadot and it is neither
  syncing nor without peers, failback to a preferred endpoint, a timeout on every
  request, automatic retry of reads on another endpoint (`retry=False` for requests
  with side effects), subscriptions, and runtime-upgrade tracking through
  `state_subscribeRuntimeVersion`. `query`, `query_map` and `constant` on the client.
- Transport errors, all `TransportError` (retryable): `ConnectionFailed`,
  `ConnectionLost`, `RequestTimeout`, `AllEndpointsFailed` (with the reason for each
  endpoint). `RpcError` for errors returned by the node.
- `py.typed`.

### Changed
- Python 3.12+; built with hatchling.
- Core dependencies are `pynacl`, `scalecodec`, `websockets` and `xxhash` only;
  every one installs from a wheel or as pure Python on musl/aarch64.
- ED25519 is the only key type. sr25519 returns as an optional extra in a later
  release.
- `Keypair.sign()` signs a `str` as its UTF-8 bytes. substrate-interface decoded a
  `str` starting with `0x` as hex first; pass `bytes.fromhex(...)` for that.

### Removed
- The dependency on `substrate-interface` and, with it, `ecdsa`, the Ethereum
  libraries, `smoldot-light` and the Rust bindings.
- The 2.x API: `Account`, `ServiceFunctions`, `BaseClass`, `ChainUtils`,
  `CommonFunctions`, the per-pallet classes, `Subscriber`/`SubEvent`,
  `TYPE_REGISTRY`, and the `robonomics_interface` CLI.
- `PubSub` and `ReqRes`: the node RPCs behind them are gone since collators moved
  to `polkadot-omni-node`.
- IPFS helpers (`web_3_auth`, `ipfs_32_bytes_to_qm_hash`, `ipfs_qm_hash_to_32_bytes`).
