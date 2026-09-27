"""The envelope must stay readable by everything that reads the published reports."""

import json
import secrets
from typing import Any

import pytest
from nacl.secret import SecretBox

from robonomicsinterface import (
    EnvelopeError,
    Keypair,
    PackageError,
    PayloadError,
    RecipientError,
    decrypt_package,
    encrypt_for_recipients,
    parse_decrypted,
)

PAYLOAD = "2026-09-16 13:00:00 ERROR (MainThread) [zha] Failed to connect\n"
META = {"orig_file_name": "home-assistant.log"}


@pytest.fixture
def sender(compat_vectors: Any) -> Keypair:
    return Keypair.from_mnemonic(compat_vectors["encryption"]["sender_mnemonic"])


@pytest.fixture
def recipient(compat_vectors: Any) -> Keypair:
    return Keypair.from_mnemonic(compat_vectors["encryption"]["recipient_mnemonic"])


def test_recipient_and_sender_read_the_payload(sender: Keypair, recipient: Keypair) -> None:
    package = encrypt_for_recipients(PAYLOAD, sender, [recipient.address])
    assert decrypt_package(package, recipient, sender.address) == PAYLOAD
    assert decrypt_package(package, sender, sender.address) == PAYLOAD


def test_metadata_travels_inside(sender: Keypair, recipient: Keypair) -> None:
    package = encrypt_for_recipients(PAYLOAD, sender, [recipient.address], META)
    assert parse_decrypted(decrypt_package(package, recipient, sender.address)) == (PAYLOAD, META)


def test_package_shape(sender: Keypair, recipient: Keypair) -> None:
    package = json.loads(encrypt_for_recipients(PAYLOAD, sender, [recipient.address]))
    assert set(package) == {"data", "keys"}
    assert package["data"].startswith("0x")
    assert set(package["keys"]) == {sender.address, recipient.address}
    assert all(key.startswith("0x") for key in package["keys"].values())


def test_each_package_uses_a_new_key(sender: Keypair, recipient: Keypair) -> None:
    first = json.loads(encrypt_for_recipients(PAYLOAD, sender, [recipient.address]))
    second = json.loads(encrypt_for_recipients(PAYLOAD, sender, [recipient.address]))
    assert first["data"] != second["data"]
    assert first["keys"] != second["keys"]


def test_stranger_is_not_addressed(sender: Keypair, recipient: Keypair) -> None:
    stranger = Keypair.from_uri("//Stranger")
    package = encrypt_for_recipients(PAYLOAD, sender, [recipient.address])
    with pytest.raises(PackageError, match="not addressed"):
        decrypt_package(package, stranger, sender.address)


def test_wrong_sender_cannot_unwrap(sender: Keypair, recipient: Keypair) -> None:
    package = encrypt_for_recipients(PAYLOAD, sender, [recipient.address])
    with pytest.raises(PayloadError, match="unwrap"):
        decrypt_package(package, recipient, Keypair.from_uri("//Other").address)


def test_invalid_recipient(sender: Keypair) -> None:
    with pytest.raises(RecipientError, match="invalid address"):
        encrypt_for_recipients(PAYLOAD, sender, ["not-an-address"])


@pytest.mark.parametrize(
    "package",
    [
        "not json",
        "[]",
        "null",
        json.dumps({"data": "0x00"}),
        json.dumps({"keys": {}}),
        json.dumps({"data": 1, "keys": {}}),
        b"\xff\xfe",
    ],
)
def test_malformed_packages(package: str, sender: Keypair, recipient: Keypair) -> None:
    with pytest.raises(PackageError):
        decrypt_package(package, recipient, sender.address)


def test_damaged_payload(sender: Keypair, recipient: Keypair) -> None:
    package = json.loads(encrypt_for_recipients(PAYLOAD, sender, [recipient.address]))
    package["data"] = package["data"][:-2] + ("00" if package["data"][-2:] != "00" else "01")
    with pytest.raises(PayloadError, match="payload"):
        decrypt_package(json.dumps(package), recipient, sender.address)


def test_errors_share_a_base() -> None:
    assert issubclass(PackageError, EnvelopeError)
    assert issubclass(PayloadError, EnvelopeError)


# Compatibility with packages built on substrate-interface keys: the 2.x stack
# wraps the key with Keypair.encrypt_message, which test_compat pins byte for
# byte, so a package assembled from those boxes is what old senders produced.


def test_package_built_like_the_old_stack_opens(
    compat_vectors: Any, sender: Keypair, recipient: Keypair
) -> None:
    secret_key = secrets.token_bytes(32)
    nonce = bytes.fromhex(compat_vectors["encryption"]["vectors"][0]["nonce_hex"])
    prepared = json.dumps({"payload": PAYLOAD, "meta": META}, ensure_ascii=False)
    package = json.dumps(
        {
            "data": "0x" + bytes(SecretBox(secret_key).encrypt(prepared.encode())).hex(),
            "keys": {
                recipient.address: "0x"
                + sender.encrypt_message(secret_key, recipient.public_key, nonce).hex(),
            },
        }
    )
    assert parse_decrypted(decrypt_package(package, recipient, sender.address)) == (PAYLOAD, META)
