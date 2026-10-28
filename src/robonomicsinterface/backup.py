"""Wallet backups: the JSON file polkadot.js exports for an account.

Polkadot-JS apps, the browser extension and the wallets built on its keyring all
write the same "version 3" file: the account's key pair in a PKCS8 envelope,
encrypted with a key that scrypt makes from the password and sealed in a NaCl
SecretBox. The file says which kind of key it holds, so a person need not.
"""

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from typing import Any

import nacl.exceptions
from nacl.secret import SecretBox

from .errors import InvalidAddress, InvalidKey
from .ss58 import decode_address

__all__ = ["open_backup"]

_SALT = 32
_SCRYPT_HEADER = _SALT + 3 * 4  # the salt, then N, p and r as little-endian u32
_NONCE = 24
# The scrypt settings polkadot.js itself writes and accepts as (N, p, r); anything else is
# refused before the password is stretched, so a crafted file cannot ask for gigabytes.
_SCRYPT_SETTINGS = {
    (1 << 13, 10, 8),
    (1 << 14, 5, 8),
    (1 << 15, 3, 8),
    (1 << 15, 1, 8),
    (1 << 16, 2, 8),
    (1 << 17, 1, 8),
}
_SCRYPT_MAXMEMORY = 1 << 28
_KEY_TYPES = ("ed25519", "sr25519")
_PKCS8_HEADER = bytes([48, 83, 2, 1, 1, 48, 5, 6, 3, 43, 101, 112, 4, 34, 4, 32])
_PKCS8_DIVIDER = bytes([161, 35, 3, 33, 0])
_SECRET_BYTES = 64
_PUBLIC_KEY_BYTES = 32


def open_backup(backup: str | bytes | Mapping[str, Any], password: str) -> tuple[str, bytes, bytes]:
    """Decrypt a backup into ``(key type, secret, public key)``.

    The key type is ``"ed25519"`` or ``"sr25519"``; the 64-byte secret is in the form
    polkadot.js keeps it (for ED25519 the seed and the public key, for sr25519 its own
    form, which :mod:`.keys_sr25519` converts). Scrypt takes a fraction of a second on
    a PC and a few seconds on a small board: call this off an event loop.

    :raises InvalidKey: this is not a usable backup, or the password is wrong.
    """

    try:
        document = json.loads(backup) if isinstance(backup, str | bytes) else backup
        encoded, address = document["encoded"], document["address"]
        encoding = document["encoding"]
        content, methods, version = encoding["content"], encoding["type"], encoding["version"]
        key_type = content[1]
    except (ValueError, KeyError, IndexError, TypeError):
        raise InvalidKey("this is not a polkadot.js wallet backup") from None

    if version != "3" or content[0] != "pkcs8":
        raise InvalidKey("this wallet backup format is not supported (only version 3, pkcs8)")
    if key_type not in _KEY_TYPES:
        raise InvalidKey("only ed25519 and sr25519 accounts can be restored from a backup")
    if methods == ["none"]:
        raise InvalidKey("a backup without a password is not accepted: export it with one")
    if methods != ["scrypt", "xsalsa20-poly1305"]:
        raise InvalidKey("this wallet backup is encrypted in a way that is not supported")
    if not isinstance(password, str) or not password:
        raise InvalidKey("a password is required to open a wallet backup")

    body = _decode(encoded)
    secret, public_key = _unseal(body, password)
    try:
        if decode_address(address) != public_key:
            raise InvalidKey("the backup's address does not match its key")
    except InvalidAddress:
        raise InvalidKey("the backup's address is not valid") from None
    return key_type, secret, public_key


def _decode(encoded: Any) -> bytes:
    try:
        if isinstance(encoded, str) and encoded.startswith("0x"):
            return bytes.fromhex(encoded[2:])
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, binascii.Error):
        raise InvalidKey("the wallet backup is damaged") from None


def _unseal(body: bytes, password: str) -> tuple[bytes, bytes]:
    if len(body) <= _SCRYPT_HEADER + _NONCE + 16:
        raise InvalidKey("the wallet backup is damaged")
    salt = body[:_SALT]
    n, p, r = (int.from_bytes(body[_SALT + 4 * i : _SALT + 4 * i + 4], "little") for i in range(3))
    if (n, p, r) not in _SCRYPT_SETTINGS:
        raise InvalidKey("the wallet backup asks for scrypt settings that are not accepted")
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_SCRYPT_MAXMEMORY, dklen=32
    )
    nonce = body[_SCRYPT_HEADER : _SCRYPT_HEADER + _NONCE]
    try:
        pkcs8 = SecretBox(key).decrypt(body[_SCRYPT_HEADER + _NONCE :], nonce)
    except nacl.exceptions.CryptoError:
        raise InvalidKey("wrong password, or the wallet backup is damaged") from None

    secret_end = len(_PKCS8_HEADER) + _SECRET_BYTES
    public_start = secret_end + len(_PKCS8_DIVIDER)
    if (
        len(pkcs8) != public_start + _PUBLIC_KEY_BYTES
        or pkcs8[: len(_PKCS8_HEADER)] != _PKCS8_HEADER
        or pkcs8[secret_end:public_start] != _PKCS8_DIVIDER
    ):
        raise InvalidKey("the wallet backup holds a key in a layout that is not supported")
    return bytes(pkcs8[len(_PKCS8_HEADER) : secret_end]), bytes(pkcs8[public_start:])
