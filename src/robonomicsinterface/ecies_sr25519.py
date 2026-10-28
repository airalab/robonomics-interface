"""ECIES for sr25519 accounts: encrypt to a public key, open with the secret.

The scheme is the one of py-sr25519-encryption by Ivan Berman
(https://github.com/Fingerling42/py-sr25519-encryption, Apache-2.0), which follows
the JS implementation of the SubMessage dapp (Polkadot DevCamp 2022, Unlicense).
Wire format, unchanged, so messages open across all three::

    nonce(24) | salt(32) | ephemeral public key(32) | mac(32) | secretbox

A one-time key pair is made for every message and its secret is thrown away; the
shared secret is the ristretto255 product of that one-time secret and the
recipient's public key, stretched with PBKDF2-SHA512 into a MAC key and a
SecretBox key. Nothing of the sender's own key takes part, so the message does
not tell who sent it; in Report Service that is the Datalog record's signer.

Differences from the original: the MAC is compared in constant time, every
failure is a :class:`DecryptionError` (not an ``assert``, which ``python -O``
removes), and the length is checked before anything is parsed.
"""

import hashlib
import hmac
import os

import nacl.exceptions
from nacl.secret import SecretBox

from . import keys_sr25519
from ._extras import require
from .errors import DecryptionError, InvalidKey

__all__ = ["decrypt", "encrypt"]

_NONCE = 24
_SALT = 32
_PUBLIC_KEY = 32
_MAC = 32
_BOX_OVERHEAD = 16  # SecretBox's authenticator
_HEADER = _NONCE + _SALT + _PUBLIC_KEY + _MAC
_PBKDF2_ROUNDS = 2048
_CANNOT_DECRYPT = "the message cannot be decrypted with these keys"


def _agree(secret: bytes, public_key: bytes) -> bytes:
    """The ristretto255 product of the secret's scalar and a public key."""

    return bytes(require("rbcl").crypto_scalarmult_ristretto255(secret[:32], public_key))


def _keys(
    secret: bytes, public_key: bytes, ephemeral_public_key: bytes, salt: bytes
) -> tuple[bytes, bytes]:
    """The MAC key and the SecretBox key."""

    master = ephemeral_public_key + _agree(secret, public_key)
    derived = hashlib.pbkdf2_hmac("sha512", master, salt, _PBKDF2_ROUNDS, dklen=64)
    return derived[:32], derived[32:]


def _mac(mac_key: bytes, nonce: bytes, ephemeral_public_key: bytes, sealed: bytes) -> bytes:
    return hmac.new(mac_key, nonce + ephemeral_public_key + sealed, hashlib.sha256).digest()


def encrypt(message: bytes, recipient_public_key: bytes) -> bytes:
    """Encrypt ``message`` for the owner of an sr25519 public key."""

    ephemeral_public_key, ephemeral_secret = keys_sr25519.pair_from_seed(os.urandom(32))
    salt, nonce = os.urandom(_SALT), os.urandom(_NONCE)
    try:
        mac_key, box_key = _keys(
            ephemeral_secret, bytes(recipient_public_key), ephemeral_public_key, salt
        )
    except (RuntimeError, ValueError):
        raise InvalidKey("the recipient public key is not a valid sr25519 public key") from None
    sealed = SecretBox(box_key).encrypt(message, nonce).ciphertext
    mac = _mac(mac_key, nonce, ephemeral_public_key, sealed)
    return nonce + salt + ephemeral_public_key + mac + sealed


def decrypt(encrypted: bytes, secret: bytes) -> bytes:
    """Open a message made by :func:`encrypt` (or by py-sr25519-encryption, or SubMessage)."""

    if len(encrypted) < _HEADER + _BOX_OVERHEAD:
        raise DecryptionError(_CANNOT_DECRYPT)
    nonce = encrypted[:_NONCE]
    salt = encrypted[_NONCE : _NONCE + _SALT]
    ephemeral_public_key = encrypted[_NONCE + _SALT : _NONCE + _SALT + _PUBLIC_KEY]
    mac = encrypted[_NONCE + _SALT + _PUBLIC_KEY : _HEADER]
    sealed = encrypted[_HEADER:]
    try:
        mac_key, box_key = _keys(secret, ephemeral_public_key, ephemeral_public_key, salt)
    except (RuntimeError, ValueError):  # not a ristretto255 point
        raise DecryptionError(_CANNOT_DECRYPT) from None
    if not hmac.compare_digest(mac, _mac(mac_key, nonce, ephemeral_public_key, sealed)):
        raise DecryptionError(_CANNOT_DECRYPT)
    try:
        return bytes(SecretBox(box_key).decrypt(sealed, nonce))
    except nacl.exceptions.CryptoError:
        raise DecryptionError(_CANNOT_DECRYPT) from None
