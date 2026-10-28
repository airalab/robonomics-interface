"""The multi-recipient envelope: one symmetric key, wrapped for every recipient.

The payload is encrypted once with a random key for NaCl's SecretBox, and that
key is encrypted separately, with :meth:`Keypair.encrypt_message`, for each
address that may open it. The serialized form is the one already published by
Robonomics Report Service::

    {"data": "0x<secretbox>", "keys": {"<address>": "0x<box of the key>", ...}}

Optional metadata travels inside the encrypted payload as
``{"payload": <data>, "meta": {...}}``; :func:`parse_decrypted` splits it.

A package has one key type, the sender's: ED25519 senders wrap the key in NaCl
boxes for ED25519 recipients, sr25519 senders in ECIES messages for sr25519
recipients. An address does not say which kind it is, so every recipient is
taken to be of the sender's kind; the recipient's own key says how to open it.
"""

import json
import secrets
from collections.abc import Iterable
from typing import Any

import nacl.exceptions
from nacl.secret import SecretBox

from .errors import (
    DecryptionError,
    InvalidAddress,
    InvalidKey,
    PackageError,
    PayloadError,
    RecipientError,
)
from .keys import ED25519, SR25519, Keypair

__all__ = ["decrypt_package", "encrypt_for_recipients", "parse_decrypted"]

_SECRET_KEY_BYTES = 32
_KEY_TYPE_NAMES = {ED25519: "ED25519", SR25519: "sr25519"}
# What a wrapped payload key measures: a NaCl box (nonce, authenticator) or an ECIES message
# (nonce, salt, one-time key, mac, authenticator) around the 32 bytes.
_WRAPPED_LENGTH = {24 + _SECRET_KEY_BYTES + 16: ED25519, 120 + _SECRET_KEY_BYTES + 16: SR25519}


def _hex(data: bytes) -> str:
    return "0x" + data.hex()


def _unhex(text: str) -> bytes:
    return bytes.fromhex(text.removeprefix("0x"))


def encrypt_for_recipients(
    data: str,
    sender: Keypair,
    recipients: Iterable[str],
    metadata: dict[str, Any] | None = None,
) -> str:
    """Encrypt ``data`` once and wrap its key for each recipient address.

    The sender is always added as a recipient, so it can read back what it
    sent. Every recipient is taken to have the sender's key type. Returns the
    JSON package.
    """

    if metadata is not None:
        data = json.dumps({"payload": data, "meta": metadata}, ensure_ascii=False)

    secret_key = secrets.token_bytes(_SECRET_KEY_BYTES)
    encrypted_data = SecretBox(secret_key).encrypt(data.encode("utf-8"))

    keys: dict[str, str] = {}
    for address in sorted(set(recipients) | {sender.address}):
        try:
            recipient = Keypair.from_address(address, crypto_type=sender.crypto_type)
        except InvalidAddress as e:
            raise RecipientError(f"{address}: invalid address") from e
        try:
            keys[address] = _hex(sender.encrypt_message(secret_key, recipient.public_key))
        except InvalidKey as e:
            kind = _KEY_TYPE_NAMES[sender.crypto_type]
            raise RecipientError(
                f"{address}: not a valid {kind} public key (a package takes the sender's key type)"
            ) from e

    return json.dumps({"data": _hex(bytes(encrypted_data)), "keys": keys})


def decrypt_package(package: str | bytes, recipient: Keypair, sender_address: str) -> str:
    """Unwrap the key addressed to ``recipient``, then decrypt the payload.

    ``sender_address`` opens an ED25519 box; an sr25519 message carries its own
    one-time key, so it is not used for an sr25519 recipient.

    :raises PackageError: the package is malformed or has no key for this recipient.
    :raises PayloadError: the key or the payload does not decrypt.
    """

    try:
        parsed = json.loads(package)
        encrypted_keys = parsed["keys"]
        encrypted_data = parsed["data"]
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError) as e:
        raise PackageError("not an encryption package") from e
    if not isinstance(encrypted_keys, dict) or not isinstance(encrypted_data, str):
        raise PackageError("the encryption package has an unexpected structure")

    wrapped_key = encrypted_keys.get(recipient.address)
    if not isinstance(wrapped_key, str) or not wrapped_key:
        raise PackageError(f"the package is not addressed to {recipient.address}")

    try:
        sender_key = b""
        if recipient.crypto_type == ED25519:
            sender_key = Keypair.from_address(sender_address).public_key
        secret_key = recipient.decrypt_message(_unhex(wrapped_key), sender_key)
    except (InvalidAddress, InvalidKey, DecryptionError, ValueError) as e:
        raise PayloadError(
            f"cannot unwrap the secret key{_wrong_kind(wrapped_key, recipient)}"
        ) from e

    try:
        return SecretBox(secret_key).decrypt(_unhex(encrypted_data)).decode("utf-8")
    except (nacl.exceptions.CryptoError, ValueError, TypeError) as e:
        raise PayloadError("cannot decrypt the payload") from e


def _wrong_kind(wrapped_key: str, recipient: Keypair) -> str:
    """A hint when the key was wrapped for the other key type: usually a misconfigured type."""

    try:
        wrapped_for = _WRAPPED_LENGTH.get(len(_unhex(wrapped_key)))
    except ValueError:
        return ""
    if wrapped_for is None or wrapped_for == recipient.crypto_type:
        return ""
    return (
        f": it is wrapped for an {_KEY_TYPE_NAMES[wrapped_for]} account, "
        f"and {recipient.address} is {_KEY_TYPE_NAMES[recipient.crypto_type]}"
    )


def parse_decrypted(text: str) -> tuple[str, dict[str, Any] | None]:
    """Split ``{"payload": ..., "meta": ...}``; plain data comes back without meta."""

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    if isinstance(parsed, dict) and "payload" in parsed:
        meta = parsed.get("meta")
        return parsed["payload"], meta if isinstance(meta, dict) else None
    return text, None
