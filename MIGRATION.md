# Migrating to robonomics-interface 3.0

3.0 is a rewrite. It keeps the wire formats — the same address from the same
mnemonic, the same ciphertext, the same extrinsic bytes — and changes the API.
This guide is written for moving the Robonomics Report Service projects
(`rrs-connector`, `rrs-admin`, `rrs-ha-integration`) off `robonomics-interface`
2.x, `substrate-interface` and the copied `chain/` packages, but applies to any
2.x user.

Pin the exact version everywhere: `robonomics-interface==3.0.0rc1`, then `==3.0.0`.

## 1. What changed, and why

| | 2.x | 3.0 |
| --- | --- | --- |
| Dependencies | `substrate-interface` (Rust bindings, `ecdsa`, Ethereum libs, `smoldot-light`) | `pynacl`, `scalecodec`, `websockets`, `xxhash`; installs on musl/aarch64 with no compiler |
| Keys | sr25519 by default, ed25519 optional | ED25519 only (sr25519 returns as an extra in 3.1) |
| Connection | hidden, per object, synchronous, no request timeout | explicit `RobonomicsClient` (asyncio) or `RobonomicsSync`; timeout on every request; endpoints in priority order with health checks and failover |
| Types | hand-written type registry | the chain's own metadata |
| Writes | returns a hash; failure inside the block goes unnoticed | reads the block's events; a failed call raises `ExtrinsicFailed` naming the pallet error |
| Errors | whatever the transport library raised | one hierarchy under `RobonomicsError`; network failures are `TransportError` (retryable), everything else is not |

## 2. Dependencies

Remove `substrate-interface`, `websocket-client` and any copy of the `chain/`
package. Add `robonomics-interface==3.0.0rc1`. It brings `pynacl`, `scalecodec`,
`websockets` and `xxhash`; do not list them separately unless the project uses
them directly.

Home Assistant: the manifest `requirements` becomes `["robonomics-interface==3.0.0rc1", ...]`
(plus the project's own, e.g. `pinatapy-vourhey`). HA already constrains
`websockets>=15`, which 3.0 accepts. No `aiohttp` session is needed: the library
has its own WebSocket client.

## 3. The client

### Async (Home Assistant, any asyncio code)

```python
from robonomicsinterface import RobonomicsClient

client = RobonomicsClient(endpoints)        # str or list, in order of preference
await client.connect()                      # or: async with RobonomicsClient(...) as client:
...
await client.close()
```

Create one client and keep it: it holds one multiplexed connection and the
parsed runtime metadata (parsing takes seconds on a Raspberry Pi; the library
does it off the event loop). In an integration, create it per config entry and
close it on unload (`entry.async_on_unload(client.close)`).

### Blocking (scripts, cron jobs, CLIs)

```python
from robonomicsinterface import RobonomicsSync

with RobonomicsSync(endpoints) as client:
    client.datalog.latest(address)
```

Same methods and arguments without `await`; `query_map` is a plain iterator.
It must not be called from a thread running an event loop — it raises
`RuntimeError` there, because blocking would stall that loop.

### Options that replace 2.x workarounds

| Need | 3.0 |
| --- | --- |
| Per-request timeout (was: `interface.websocket.settimeout(...)`) | `RobonomicsClient(..., timeout=30.0, connect_timeout=10.0)` |
| Several nodes, move on when one fails (was: hand-written `_reconnect` / `change_current_wss`) | pass them all: `RobonomicsClient([local, public])`; reads are retried on the next endpoint (`retries=2`), the client returns to a preferred endpoint on its own (`failback_interval=300`) |
| Know which node is in use | `client.endpoint` |
| Kusama | `RobonomicsClient("wss://kusama.rpc.robonomics.network/", genesis_hash=ROBONOMICS_KUSAMA_GENESIS)` with `ROBONOMICS_KUSAMA_GENESIS = "0x631ccc82a078481584041656af292834e1ae6daab61d2875b4dd0c14bb9b17bc"` defined by the project. The default genesis check accepts Robonomics Polkadot only. Checked on 2026-09-23: reads and signatures work on Kusama (spec 42). |
| A node on the local network | put it first: `["ws://192.168.1.10:9944", DEFAULT_ENDPOINT]`; a node that is syncing or has no peers is skipped |

## 4. Errors

```
RobonomicsError
├── TransportError            .retryable = True: the node was not reached or stopped answering
│   ├── ConnectionFailed      (.endpoint, .reason)
│   ├── ConnectionLost
│   ├── RequestTimeout        (also a TimeoutError)
│   └── AllEndpointsFailed    (.failures: one ConnectionFailed per endpoint)
├── RpcError                  the node answered with an error (.code, .message, .data)
├── TransactionError          an extrinsic did not do what was asked
│   ├── InvalidTransaction    refused before sending (.kind, .explanation)
│   ├── ExtrinsicFailed       in a block, call failed (.pallet, .error, .docs, .result)
│   ├── ExtrinsicDropped      dropped by the node
│   └── ExtrinsicOutcomeUnknown  sent, outcome unknown (.extrinsic_hash) — do not resend blindly
├── MetadataError / NoSuchPallet / NoSuchStorage / NoSuchCall / NoSuchConstant / UnsupportedExtension
├── EncodeError / DecodeError (ValueError)      e.g. TooManyDevices is an EncodeError
├── InvalidAddress / InvalidKey / InvalidMnemonic (ValueError)
├── NoSecretKey, DecryptionError
└── EnvelopeError: RecipientError, PackageError (ValueError), PayloadError
```

Replace `TRANSIENT_ERRORS = (OSError, TimeoutError, WebSocketException)` and
`RETRYABLE_ERRORS = (RpcError, ChainError, TimeoutError, OSError)` with
`TransportError`. The client already retries reads across endpoints, so an
outer retry loop only needs to cover a whole run, if at all. `RpcError` is not a
network failure and repeating the request will not help.

## 5. API mapping

### Keys and addresses

| 2.x / substrate-interface / `chain/` | 3.0 |
| --- | --- |
| `Keypair.create_from_mnemonic(m, crypto_type=KeypairType.ED25519, ss58_format=32)` | `Keypair.from_mnemonic(m)` |
| `chain.Keypair.create_from_secret(s)` (mnemonic or `0x` seed) | `Keypair.from_secret(s)` |
| `Account(seed, crypto_type=KeypairType.ED25519)` | `Keypair.from_secret(seed)` |
| `account.get_address()`, `keypair.ss58_address` | `keypair.address` |
| `account.keypair` | the `Keypair` itself |
| `Keypair(ss58_address=a, crypto_type=KeypairType.ED25519)`, `chain.Keypair.create_from_address(a)` | `Keypair.from_address(a)` (public only) |
| `chain.Keypair.create_from_public_key(pk)` | `Keypair.from_public_key(pk)` |
| `Keypair.generate_mnemonic()` | `generate_mnemonic()` or `Keypair.generate_mnemonic()` |
| `is_valid_ss58_address(a)` | `is_valid_address(a, ss58_format=None)` — see pitfall 4 |
| `chain.ss58_decode(a)` / `SS58Error` | `decode_address(a)` / `InvalidAddress` (a `ValueError`) |
| `chain.ss58_encode(pk, 32)` | `encode_address(pk)` |
| `"//Alice"` for tests | `Keypair.from_uri("//Alice")` (ED25519, as polkadot-sdk derives it) |

### Encryption

| Before | 3.0 |
| --- | --- |
| `keypair.encrypt_message(msg, recipient_pk)` / `decrypt_message(box, sender_pk)` | same names, same bytes; failures raise `DecryptionError` |
| `chain.envelope.encrypt_for_recipients(data, sender, addresses, meta)` | `encrypt_for_recipients(...)`, same arguments and output |
| `chain.envelope.decrypt_package(package, recipient, sender_address)`, connector's `multi_envelope_decrypt_data(...)` | `decrypt_package(package, recipient_keypair, sender_address)` |
| `parse_decrypted(text)` | `parse_decrypted(text)` |
| `chain.envelope` errors | `RecipientError`, `PackageError`, `PayloadError` (all `EnvelopeError`) |

### Reading the chain

| Before | 3.0 (async; `RobonomicsSync` is the same without `await`) |
| --- | --- |
| `Datalog(Account(remote_ws=url)).get_index(a)` → `{"start", "end"}` | `await client.datalog.index(a)` → `DatalogIndex(start, end, window_size)` with `.count`, `.positions` (oldest first), `.latest_position` |
| `interface.get_constant("Datalog", "WindowSize").value` | `await client.datalog.window_size()` or `await client.constant("Datalog", "WindowSize")` |
| `chainstate_query("Datalog", "DatalogItem", [a, i])` → `(ts, content)` | `await client.datalog.item(a, i)` → `DatalogItem(index, timestamp_ms, data)` or `None` |
| walking `ring_buffer_indices(...)` and calling `get_item` per slot | `await client.datalog.items(a)` — every live record, oldest first, in one request; `await client.datalog.latest(a)` |
| `Datalog.get_item(a)` (latest) | `await client.datalog.latest(a)` |
| `substrate.query("RWS", "Devices", [pool]).value or []` | `await client.rws.devices(pool)` → `list[str]` |
| `substrate.query("RWS", "Ledger", [pool]).value` | `await client.rws.ledger(pool)` → `Ledger` or `None`: `.kind` (`"Daily"`/`"Lifetime"`), `.days`, `.tps`, `.issued_at`, `.expires_at`, `.is_active()`, `.days_left()`, `.free_weight` |
| `substrate.query("System", "Account", [a]).value` | `await client.system.account(a)` → `AccountInfo`: `.free`, `.reserved`, `.frozen`, `.nonce`, `.exists` |
| anything else: `substrate.query(pallet, item, [keys])` | `await client.query(pallet, item, *keys)`; maps: `client.query_map(pallet, item)`; constants: `client.constant(pallet, name)` |
| `RWS.MaxDevicesAmount` | `await client.rws.max_devices()` |

### Writing

| Before | 3.0 |
| --- | --- |
| `chain.RobonomicsClient.record_datalog(kp, data, owner)` | `await client.datalog.record(kp, data, subscription_owner=owner)` |
| `Datalog(Account(seed), rws_sub_owner=owner).record(data)` | same as above |
| `compose_call("RWS", "set_devices", {"devices": [devices]})` + sign + `submit_extrinsic(wait_for_inclusion=True)` + `receipt.is_success` | `await client.rws.set_devices(owner_kp, devices)` — a **flat** list |
| read devices, edit, `set_devices` | `await client.rws.add_devices(owner_kp, *new)` / `remove_devices(owner_kp, *old)` (`None` when nothing changes) |
| `CommonFunctions.transfer_tokens(to, amount)` | `await client.balances.transfer_keep_alive(kp, to, amount)` |
| any other call | `call = await client.compose_call(pallet, function, args)`; `await client.submit(call, kp)` |

Every write returns an `ExtrinsicResult` (`.block_hash`, `.block_number`,
`.index`, `.events`, `.find(pallet, name)`) or raises. Options for all writes:
`wait_for="in_block"|"finalized"`, `tip`, `era_period` (64; `None` for immortal),
`validate` (ask the runtime first; on by default), `timeout` (120 s).

## 6. Pitfalls — behaviour that changed silently in meaning

1. **`item(a, 0)` is slot 0.** In 2.x `get_item(index=0)` meant "latest". The
   connector worked around it through `_service_functions`; that code goes.
2. **Only live slots are returned.** The ring buffer keeps at most
   `WindowSize - 1` (127) records; the slot at `end` may still hold an
   overwritten record in storage. `item()` returns `None` for it, where a raw
   storage read returned the stale record.
3. **Records are `bytes`.** scalecodec returned a record as text when it was
   printable and as `0x…` hex otherwise, so `str(content)` could silently turn a
   CID into hex. Use `item.text` (UTF-8 or `None`) or `item.data`. When writing,
   a `str` is sent as UTF-8 — `"0x12"` stays the four characters it is.
4. **`is_valid_address(a)` checks for Robonomics (format 32) by default.**
   `is_valid_ss58_address(a)` accepted any network. Pass `ss58_format=None` to
   keep the old behaviour, or keep the default to reject `5…` addresses.
   `Keypair.from_address` and `decode_address` accept any format unless given one.
5. **`set_devices` takes a flat list and replaces the whole list.** The
   `[[a, b]]` wrapping and the decode-back guard in `rrs-admin` go. Addresses of
   any SS58 format are accepted, normalised to format 32 and de-duplicated; more
   than `MaxDevicesAmount` (32) raises `TooManyDevices` before anything is sent.
   `add_devices`/`remove_devices` read, edit and write — two concurrent edits of
   one owner can lose one.
6. **A failed call raises.** Inclusion in a block is not success. Catch
   `ExtrinsicFailed` and look at `.pallet`/`.error`:
   - `RWS.NotLinkedDevice` — the signer is not in the owner's device list;
   - `RWS.FreeWeightIsNotEnough` — no allowance left: an **expired daily
     subscription stays on chain** and fails this way (not with
     `NoSubscription`), and so does a fresh one before it has accrued;
   - `RWS.NoSubscription` — the owner has none.
7. **`InvalidTransaction` with `.kind == "Payment"`** means the signer does not
   exist on chain (balance below the existential deposit, 0.000001 XRT), even for
   free RWS calls. `client.system.exists(a)` tells beforehand. It is true when the
   account has providers or sufficients — not the `free or nonce` test `rrs-admin`
   used, which misses reserved-only accounts.
8. **`ExtrinsicOutcomeUnknown` is not a failure.** The extrinsic was sent and
   may still land; look it up by `.extrinsic_hash` before sending again.
9. **Mortal era by default.** Extrinsics are valid for ~64 blocks, so a stuck
   one cannot land an hour later, nor be replayed if the account is ever reaped.
10. **`Keypair.from_secret` refuses derivation paths** (`//Alice`); use
    `Keypair.from_uri` in tests. `Keypair.sign(str)` signs UTF-8; the 2.x stack
    decoded a `str` starting with `0x` as hex first.
11. **Keypairs keep secrets to themselves:** `repr()` shows the address, errors
    never include the input, pickling raises `TypeError`.
12. **One key type.** Accounts must be ED25519 — which report encryption
    already required. A mnemonic that was used with sr25519 gives a different
    address here.

## 7. Per project

### rrs-connector

- `pyproject.toml`: drop `substrate-interface` and `websocket-client`; replace
  `robonomics-interface>=2.0.0` with `==3.0.0rc1`.
- `robonomics/datalog_reader.py`: rebuild on `RobonomicsSync`, keeping
  `DatalogRecord`, `DatalogIndexRange`, `DatalogScan` and the cursor logic
  (`list_new_records`, `list_last_records`) as they are:

  ```python
  class DatalogReader:
      def __init__(self, wss_endpoints, request_timeout_seconds, max_attempts=1, backoff_seconds=0):
          if not wss_endpoints:
              raise ValueError("At least one WSS endpoint is required")
          self.client = RobonomicsSync(
              list(wss_endpoints),
              timeout=request_timeout_seconds,
              retries=max(max_attempts - 1, 0),
          ).connect()

      def get_window_size(self) -> int:
          return self.client.datalog.window_size()

      def get_index_range(self, sender_address):
          index = self.client.datalog.index(sender_address)
          return DatalogIndexRange(index.start, index.end)

      def get_item(self, sender_address, datalog_index):
          item = self.client.datalog.item(sender_address, datalog_index)
          if item is None or item.text is None:
              return None
          return DatalogRecord(sender_address, item.index, item.timestamp_ms, payload=item.text)
  ```

  `_interface`, `_reconnect`, the socket timeout and the direct
  `chainstate_query` all go. `ring_buffer_indices` can stay (it matches
  `DatalogIndex.positions`) or be replaced; `client.datalog.items(a)` reads all
  records in one request, which is cheaper than one `get_item` per slot. Add a
  `close()` and call it at the end of a run.
- `robonomics/retry.py`: `TRANSIENT_ERRORS = (TransportError,)`; with the
  client retrying across endpoints, `before_retry=_reconnect` is no longer needed.
- `keygen.py`: `mnemonic = generate_mnemonic()`, `Keypair.from_mnemonic(...)`,
  `.address`. The read-back check stays.
- `config.py`: `is_valid_address(address, ss58_format=None)` to keep accepting
  any format — or the default, to require Robonomics addresses (pitfall 4).
- `proton_pass.py`: `load_integrator_account` returns
  `Keypair.from_secret(seed)` and compares `.address`.
- `pipeline.py`, `reports/recipients.py`: the `Account` type becomes `Keypair`
  (`AccountLoader = Callable[[str], Keypair]`).
- `reports/decryptor.py`: `multi_envelope_decrypt_data` becomes a thin wrapper
  over `decrypt_package(package, recipient_keypair, sender_address)` that maps
  `PackageError`/`PayloadError` to `ReportDecryptionError`; `decrypt_msg` and
  the `substrateinterface` imports go. `parse_decrypted` can come from the library.
- Tests: `tests/test_decryptor.py`, `test_keygen.py`, `test_retry.py`,
  `conftest.py` import `substrateinterface`; switch them to the library. Keep
  any fixture ciphertext produced by the old stack: it is the compatibility check.

### rrs-admin

- `pyproject.toml`: drop `substrate-interface`; add `robonomics-interface==3.0.0rc1`.
- Delete `src/rrs_admin/chain/` (the third copy of the integration's key code);
  import from `robonomicsinterface`: `Keypair.create_from_mnemonic` →
  `Keypair.from_mnemonic`, `create_from_secret` → `from_secret`, `.ss58_address`
  → `.address`, `ss58_decode` → `decode_address`, `SS58Error` → `InvalidAddress`,
  `validate_mnemonic` unchanged, `MnemonicError` → `InvalidMnemonic`.
  Files: `pools.py`, `sites.py`.
- `rws.py`:

  ```python
  def read_subscription(url, pool) -> Subscription:
      with RobonomicsSync(url) as client:
          devices = client.rws.devices(pool)
          ledger = client.rws.ledger(pool)
          account = client.system.account(pool)
      ...  # Subscription(kind=ledger.kind, issued=ledger.issued_at,
           #   expires=ledger.expires_at, free_weight=ledger.free_weight,
           #   balance=account.free / XRT)

  def account_exists(url, address) -> bool:
      with RobonomicsSync(url) as client:
          return client.system.exists(address)

  def set_devices(url, pool_seed, devices) -> str:
      REDACT.add(pool_seed)
      pool = Keypair.from_mnemonic(pool_seed)
      planned = list(dict.fromkeys(encode_address(decode_address(d)) for d in devices))
      with RobonomicsSync(url) as client:
          try:
              result = client.rws.set_devices(pool, planned)
          except TransactionError as e:
              raise ChainError(REDACT(f"set_devices failed: {e}")) from e
          if client.rws.devices(pool) != planned:
              raise ChainError("the chain holds a different device list than planned")
          return result.block_hash
  ```

  `_addresses_in` and the `[devices]` wrapping go (pitfall 5). Reading the list
  back after inclusion is a stronger check than decoding the call before signing.
  `Subscription.kind` changes from `"Daily 30 days"` formatting done by hand to
  `ledger.kind`/`ledger.days`.

### rrs-ha-integration

- `manifest.json` `requirements`: `["robonomics-interface==3.0.0rc1", "pinatapy-vourhey==0.1.9"]`.
- Delete `custom_components/robonomics_report_service/chain/` and its tests
  (`tests/test_chain.py`, `tests/test_chain_client.py`): the library carries
  them, byte-for-byte vectors included. Keep `tests/fixtures/substrate_vectors.json`
  in a test that runs the library against it, as the project's own contract.
- `robonomics.py`:
  - one `RobonomicsClient(NETWORK_WSS[network], genesis_hash=GENESIS[network])`
    per config entry, created in `async_setup_entry`, closed on unload; remove
    `_clients`, `current_wss`, `change_current_wss` and the endpoint loop in
    `_send_datalog`;
  - publishing: `await client.datalog.record(self.sender_keypair, data, subscription_owner=self._owner_address or self.sender_address)`;
  - errors: `ExtrinsicFailed` and `InvalidTransaction` → the integration's
    `RobonomicsError` with the library's message (it already explains
    `Payment`, `NotLinkedDevice` and `FreeWeightIsNotEnough`); `TransportError` →
    retry later; `ExtrinsicOutcomeUnknown` → do not unpin the files from Pinata
    yet, the record may have landed.
  - `const.py`: add the Kusama genesis hash from section 3; Polkadot's is
    `ROBONOMICS_GENESIS_HASH` in the library.
- `config_flow.py`: `Keypair.from_secret`, `generate_mnemonic()`,
  `decode_address` (raises `InvalidAddress`, a `ValueError`, so the existing
  `except ValueError` still works).
- `utils/encrypt_tools.py`, `utils/file_handler.py`: import `Keypair`,
  `encrypt_for_recipients`, `decrypt_package`, `parse_decrypted` and the
  envelope errors from `robonomicsinterface`; `encrypt_message`/`decrypt_message`
  wrappers become `keypair.encrypt_message(...)` + hex.
- Nothing may block the event loop: use `RobonomicsClient` only, never
  `RobonomicsSync` (which refuses to run there anyway).

## 8. Checklist

- [ ] No `substrateinterface`, `websocket`, `robonomicsinterface.Account` or
      `chain.` import left (`grep -rn "substrateinterface\|from websocket\|Account\b\|\.chain" src`).
- [ ] The same mnemonic gives the same address as before (the project's
      fixtures, or `substrate_vectors.json`).
- [ ] A report encrypted by the old stack still decrypts, and a new one opens
      with the connector.
- [ ] Datalog slot 0 reads as slot 0; a wrapped buffer reads 127 records, oldest first.
- [ ] `set_devices` with a flat list, read back from the chain.
- [ ] A missing account raises `InvalidTransaction` with `kind == "Payment"`; a
      device outside the list raises `ExtrinsicFailed` `RWS.NotLinkedDevice`.
- [ ] Home Assistant: the integration installs in `python:3.13-alpine` on aarch64
      and HA logs no "Detected blocking call".
- [ ] Integration tests against a development node, if the project has any:
      `scripts/devchain.sh` in this repository starts one with funded ED25519
      accounts.
