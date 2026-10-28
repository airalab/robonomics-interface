// Open sr25519 ECIES messages with polkadot.js: the half of the interop check that
// needs node. Reads {"mnemonic": ..., "blobs": ["<hex>", ...]} on stdin and writes
// the plaintexts as a JSON list of hex strings. Run by tests/test_ecies_sr25519.py
// when ROBONOMICS_JS_DIR points at the directory prepared for generate_sr25519_js.mjs.

import { readFileSync } from 'node:fs';

import { cryptoWaitReady, mnemonicToMiniSecret, sr25519PairFromSeed } from '@polkadot/util-crypto';
import { hexToU8a } from '@polkadot/util';

import { eciesDecrypt } from './ecies_sr25519.mjs';

await cryptoWaitReady();
const { mnemonic, blobs } = JSON.parse(readFileSync(0, 'utf8'));
const { secretKey } = sr25519PairFromSeed(mnemonicToMiniSecret(mnemonic));
console.log(JSON.stringify(
  blobs.map((blob) => Buffer.from(eciesDecrypt(hexToU8a('0x' + blob), secretKey)).toString('hex'))));
