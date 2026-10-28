// sr25519 ECIES from polkadot.js primitives, as the SubMessage fork of util-crypto does it
// (Polkadot-DevCamp-2022/submessage-dapp, sr25519/encrypt.js and decrypt.js, Unlicense).
// Upstream @polkadot/util-crypto has no sr25519Encrypt. Used by generate_sr25519_js.mjs and
// ecies_open_in_js.mjs, which sit next to it.

import {
  hmacSha256AsU8a,
  naclDecrypt,
  naclEncrypt,
  pbkdf2Encode,
  randomAsU8a,
  sr25519Agreement,
  sr25519PairFromSeed
} from '@polkadot/util-crypto';
import { u8aConcat } from '@polkadot/util';

const MAC = 32;
const ROUNDS = 2048;

const hex = (bytes) => Buffer.from(bytes).toString('hex');

function eciesKeys(secretKey, publicKey, masterPublicKey, salt) {
  const master = u8aConcat(masterPublicKey, sr25519Agreement(secretKey, publicKey));
  const { password } = pbkdf2Encode(master, salt, ROUNDS);
  return { macKey: password.slice(0, MAC), encryptionKey: password.slice(MAC, MAC + 32) };
}

export function eciesEncrypt(message, receiverPublicKey) {
  const ephemeral = sr25519PairFromSeed(randomAsU8a(32));
  const salt = randomAsU8a(32);
  const { macKey, encryptionKey } = eciesKeys(
    ephemeral.secretKey, receiverPublicKey, ephemeral.publicKey, salt);
  const { encrypted, nonce } = naclEncrypt(message, encryptionKey, randomAsU8a(24));
  const mac = hmacSha256AsU8a(macKey, u8aConcat(nonce, ephemeral.publicKey, encrypted));
  return u8aConcat(nonce, salt, ephemeral.publicKey, mac, encrypted);
}

export function eciesDecrypt(blob, secretKey) {
  const nonce = blob.slice(0, 24);
  const salt = blob.slice(24, 56);
  const ephemeralPublicKey = blob.slice(56, 88);
  const mac = blob.slice(88, 120);
  const sealed = blob.slice(120);
  const { macKey, encryptionKey } = eciesKeys(secretKey, ephemeralPublicKey, ephemeralPublicKey, salt);
  const expected = hmacSha256AsU8a(macKey, u8aConcat(nonce, ephemeralPublicKey, sealed));
  if (hex(expected) !== hex(mac)) throw new Error("Mac values don't match");
  return naclDecrypt(sealed, nonce, encryptionKey);
}
