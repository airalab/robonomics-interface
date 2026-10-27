// Regenerate sr25519_js.json with polkadot.js.
//
// Not run in CI. The vectors pin what polkadot.js derives, signs, agrees on and
// exports, so 3.1 can prove it reads the same accounts, JSON backups and ECIES
// messages as a wallet or a browser would produce:
//
//   mkdir jsgen && cp tests/fixtures/generate_sr25519_js.mjs jsgen/ && cd jsgen
//   npm install @polkadot/util-crypto@13.5.9 @polkadot/keyring@13.5.9
//   node generate_sr25519_js.mjs ../tests/fixtures/sr25519_old_stack.json \
//     > ../tests/fixtures/sr25519_js.json
//
// The ECIES here is built from polkadot.js primitives exactly as the SubMessage fork
// of util-crypto does it (Polkadot-DevCamp-2022/submessage-dapp, sr25519/encrypt.js,
// Unlicense): upstream @polkadot/util-crypto has no sr25519Encrypt. The messages the
// old Python stack made (the file in argv[2]) must open here, or this script fails.
//
// All mnemonics are public test phrases; never put a real account here.

import { readFileSync } from 'node:fs';

import { Keyring } from '@polkadot/keyring';
import {
  cryptoWaitReady,
  hmacSha256AsU8a,
  mnemonicToMiniSecret,
  naclDecrypt,
  naclEncrypt,
  pbkdf2Encode,
  randomAsU8a,
  sr25519Agreement,
  sr25519PairFromSeed,
  sr25519Sign
} from '@polkadot/util-crypto';
import { hexToU8a, stringToU8a, u8aConcat } from '@polkadot/util';

const MNEMONICS = [
  'bottom drive obey lake curtain smoke basket hold race lonely fit walk',
  'frozen woman pet meat entire question balcony wing echo excess adjust sleep',
  'lens exchange drum inside current bullet include stamp purity decline absurd play',
  'legal winner thank year wave sausage worth useful legal winner thank yellow'
];
const PASSWORDS = ['', 'Substrate', 'пароль'];
const SR_URIS = [
  '//Alice',
  '//Bob',
  '//Alice//stash',
  '//Alice/stash',
  '//Alice/stash//x/y',
  '//Bob//Charlie',
  '//1',
  MNEMONICS[0] + '/1',
  MNEMONICS[0] + '/soft',
  '//' + 'a'.repeat(40),
  '//Alice///secret',
  MNEMONICS[1] + '//hard/soft',
  MNEMONICS[1] + '///пароль',
  MNEMONICS[2] + '//hard///Substrate'
];
const ED_URIS = ['//Alice', '//Alice//stash', MNEMONICS[1] + '//hard///пароль'];
const MESSAGES = ['', 'report payload', 'отчёт 📦', 'x'.repeat(300), 'x'.repeat(4096)];
const JSON_PASSWORDS = ['pass', 'пароль 🔑', 'x'.repeat(64)];
const WARNING =
  'PUBLIC TEST KEYS. Every mnemonic and URI here is a published test secret ' +
  '(Substrate dev phrase, BIP39 vectors, throwaway accounts). Anyone can derive ' +
  'their keys: never fund these accounts, give them a subscription, or use them ' +
  'for a real site.';

const hex = (bytes) => Buffer.from(bytes).toString('hex');
const SS58 = 32;

// ECIES, as SubMessage's util-crypto does it.
const MAC = 32;
const ROUNDS = 2048;

function eciesKeys(secretKey, publicKey, masterPublicKey, salt) {
  const master = u8aConcat(masterPublicKey, sr25519Agreement(secretKey, publicKey));
  const { password } = pbkdf2Encode(master, salt, ROUNDS);
  return { macKey: password.slice(0, MAC), encryptionKey: password.slice(MAC, MAC + 32) };
}

function eciesEncrypt(message, receiverPublicKey) {
  const ephemeral = sr25519PairFromSeed(randomAsU8a(32));
  const salt = randomAsU8a(32);
  const { macKey, encryptionKey } = eciesKeys(
    ephemeral.secretKey, receiverPublicKey, ephemeral.publicKey, salt);
  const { encrypted, nonce } = naclEncrypt(message, encryptionKey, randomAsU8a(24));
  const mac = hmacSha256AsU8a(macKey, u8aConcat(nonce, ephemeral.publicKey, encrypted));
  return { blob: u8aConcat(nonce, salt, ephemeral.publicKey, mac, encrypted), ephemeral };
}

function eciesDecrypt(blob, secretKey) {
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

function account(pair, extra) {
  return {
    ...extra,
    public_key_hex: hex(pair.publicKey),
    address_32: pair.address
  };
}

async function main() {
  await cryptoWaitReady();
  const oldStack = JSON.parse(readFileSync(process.argv[2], 'utf8'));
  const sr = new Keyring({ type: 'sr25519', ss58Format: SS58 });
  const ed = new Keyring({ type: 'ed25519', ss58Format: SS58 });

  const accounts = [];
  for (const mnemonic of MNEMONICS) {
    for (const password of PASSWORDS) {
      const suri = password ? `${mnemonic}///${password}` : mnemonic;
      const mini = mnemonicToMiniSecret(mnemonic, password);
      const srPair = sr.createFromUri(suri);
      const edPair = ed.createFromUri(suri);
      accounts.push({
        mnemonic, password, mini_secret_hex: hex(mini),
        sr25519: account(srPair, { secret_key_hex: hex(sr25519PairFromSeed(mini).secretKey) }),
        ed25519: account(edPair, {})
      });
    }
  }

  const uris = [
    ...SR_URIS.map((uri) => ({ type: 'sr25519', uri, ...account(sr.createFromUri(uri), {}) })),
    ...ED_URIS.map((uri) => ({ type: 'ed25519', uri, ...account(ed.createFromUri(uri), {}) }))
  ];

  const receiverPair = sr25519PairFromSeed(mnemonicToMiniSecret(MNEMONICS[2]));
  const senderPair = sr25519PairFromSeed(mnemonicToMiniSecret(MNEMONICS[1]));
  const edSender = ed.createFromUri(MNEMONICS[1]);

  const signatures = MESSAGES.map((message) => ({
    message,
    sr25519_hex: hex(sr25519Sign(stringToU8a(message), senderPair)),
    ed25519_hex: hex(edSender.sign(stringToU8a(message)))
  }));

  // polkadot.js and the Python bindings keep the 64-byte secret in different forms;
  // what matters for ECIES is that both give the same agreement.
  const agreement = {
    secret_mnemonic: MNEMONICS[1],
    public_mnemonic: MNEMONICS[2],
    secret_key_js_hex: hex(senderPair.secretKey),
    public_key_hex: hex(receiverPair.publicKey),
    agreement_hex: hex(sr25519Agreement(senderPair.secretKey, receiverPair.publicKey))
  };
  if (hex(sr25519Agreement(receiverPair.secretKey, senderPair.publicKey)) !== agreement.agreement_hex) {
    throw new Error('sr25519 agreement is not symmetric');
  }

  const ecies = [];
  for (const message of MESSAGES) {
    const { blob } = eciesEncrypt(stringToU8a(message), receiverPair.publicKey);
    if (Buffer.from(eciesDecrypt(blob, receiverPair.secretKey)).toString('utf8') !== message) {
      throw new Error('ECIES round trip failed');
    }
    ecies.push({ plaintext: message, blob_hex: hex(blob) });
  }

  // What the Python stack produced must open here (and the reverse is checked when
  // 3.1's own encryption is tested against these files).
  for (const vector of oldStack.ecies.vectors) {
    const opened = eciesDecrypt(hexToU8a('0x' + vector.blob_hex), receiverPair.secretKey);
    if (hex(opened) !== vector.plaintext_hex) throw new Error('old-stack ECIES does not open here');
  }

  // Wallet backups: keyring JSON v3, scrypt + xsalsa20-poly1305.
  const backups = [];
  for (const [type, keyring] of [['sr25519', sr], ['ed25519', ed]]) {
    for (const password of JSON_PASSWORDS) {
      const pair = keyring.addFromMnemonic(MNEMONICS[2], { name: 'vector' }, type);
      backups.push({
        type, mnemonic: MNEMONICS[2], password,
        public_key_hex: hex(pair.publicKey), address_32: pair.address,
        json: pair.toJson(password)
      });
    }
  }
  const unencrypted = sr.addFromMnemonic(MNEMONICS[2], { name: 'vector' }, 'sr25519').toJson();

  console.log(JSON.stringify({
    warning: WARNING,
    generator: '@polkadot/util-crypto 13.5.9, @polkadot/keyring 13.5.9',
    accounts, uris, signatures: { signer_mnemonic: MNEMONICS[1], vectors: signatures },
    agreement,
    ecies: { recipient_mnemonic: MNEMONICS[2], vectors: ecies },
    backups, unencrypted_backup: unencrypted
  }, null, 2));
}

main().catch((error) => { console.error(error); process.exit(1); });
