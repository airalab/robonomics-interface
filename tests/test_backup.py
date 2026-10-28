"""Wallet backups made by polkadot.js open here, for both key types."""

import base64
import copy
import json
import time
from typing import Any

import pytest

from robonomicsinterface import ED25519, SR25519, InvalidKey, Keypair, decode_address

pytest.importorskip("sr25519")

TYPES = {"sr25519": SR25519, "ed25519": ED25519}


@pytest.fixture(scope="module")
def backups(sr25519_js: Any) -> list[dict[str, Any]]:
    return list(sr25519_js["backups"])


@pytest.fixture(scope="module")
def sr_backup(backups: list[dict[str, Any]]) -> dict[str, Any]:
    return next(b for b in backups if b["type"] == "sr25519")


def tampered(backup: dict[str, Any], **changes: Any) -> dict[str, Any]:
    document = copy.deepcopy(backup["json"])
    for path, value in changes.items():
        target = document
        *parents, last = path.split("__")
        for parent in parents:
            target = target[parent]
        target[last] = value
    return document


def with_body(backup: dict[str, Any], change: Any) -> dict[str, Any]:
    document = copy.deepcopy(backup["json"])
    body = bytearray(base64.b64decode(document["encoded"]))
    change(body)
    document["encoded"] = base64.b64encode(bytes(body)).decode()
    return document


# Opening


def test_every_backup_opens(backups: list[dict[str, Any]]) -> None:
    assert {(b["type"], b["password"]) for b in backups} >= {
        ("sr25519", "пароль 🔑"),
        ("ed25519", "пароль 🔑"),
    }
    for backup in backups:
        keypair = Keypair.from_json(backup["json"], backup["password"])
        assert keypair.crypto_type == TYPES[backup["type"]]
        assert keypair.public_key.hex() == backup["public_key_hex"]
        assert keypair.address == backup["address_32"]
        assert keypair.has_secret


def test_the_key_is_the_one_the_mnemonic_gives(backups: list[dict[str, Any]]) -> None:
    for backup in backups:
        crypto_type = TYPES[backup["type"]]
        from_mnemonic = Keypair.from_mnemonic(backup["mnemonic"], crypto_type=crypto_type)
        restored = Keypair.from_json(backup["json"], backup["password"])
        assert restored == from_mnemonic
        # Each can use what the other made: the restored secret is the real one.
        assert from_mnemonic.verify("report", restored.sign("report"))
        assert restored.verify("report", from_mnemonic.sign("report"))
        box = Keypair.from_uri("//Alice", crypto_type=crypto_type)
        message = box.encrypt_message("secret", restored.public_key)
        assert restored.decrypt_message(message, box.public_key) == b"secret"


def test_polkadot_js_messages_open_with_the_restored_sr25519_key(
    sr_backup: dict[str, Any], sr25519_js: Any
) -> None:
    restored = Keypair.from_json(sr_backup["json"], sr_backup["password"])
    section = sr25519_js["ecies"]
    assert section["recipient_mnemonic"] == sr_backup["mnemonic"]
    for vector in section["vectors"]:
        opened = restored.decrypt_message(bytes.fromhex(vector["blob_hex"]), b"")
        assert opened == vector["plaintext"].encode()


def test_json_text_and_parsed_json_are_both_accepted(sr_backup: dict[str, Any]) -> None:
    from_text = Keypair.from_json(json.dumps(sr_backup["json"]), sr_backup["password"])
    from_bytes = Keypair.from_json(json.dumps(sr_backup["json"]).encode(), sr_backup["password"])
    from_dict = Keypair.from_json(sr_backup["json"], sr_backup["password"])
    assert from_text == from_bytes == from_dict


def test_the_address_format_is_the_callers(sr_backup: dict[str, Any]) -> None:
    restored = Keypair.from_json(sr_backup["json"], sr_backup["password"], ss58_format=42)
    assert restored.address.startswith("5")
    assert decode_address(restored.address) == bytes.fromhex(sr_backup["public_key_hex"])


def test_a_wallets_own_address_format_does_not_matter(sr_backup: dict[str, Any]) -> None:
    generic = Keypair.from_public_key(bytes.fromhex(sr_backup["public_key_hex"]), 42).address
    document = tampered(sr_backup, address=generic)
    assert Keypair.from_json(document, sr_backup["password"]).address == sr_backup["address_32"]


# Refusals


def test_a_wrong_password_is_refused_without_a_hint(sr_backup: dict[str, Any]) -> None:
    with pytest.raises(InvalidKey, match="wrong password"):
        Keypair.from_json(sr_backup["json"], "not " + sr_backup["password"])


@pytest.mark.parametrize("password", ["", None, 123])
def test_a_password_is_required(sr_backup: dict[str, Any], password: Any) -> None:
    with pytest.raises(InvalidKey, match="password is required"):
        Keypair.from_json(sr_backup["json"], password)


def test_a_backup_without_a_password_is_not_accepted(sr25519_js: Any) -> None:
    with pytest.raises(InvalidKey, match="without a password"):
        Keypair.from_json(sr25519_js["unencrypted_backup"], "anything")


def test_a_backup_whose_address_is_another_account_is_refused(
    backups: list[dict[str, Any]], sr_backup: dict[str, Any]
) -> None:
    other = Keypair.from_uri("//Alice", crypto_type=SR25519).address
    with pytest.raises(InvalidKey, match="address does not match"):
        Keypair.from_json(tampered(sr_backup, address=other), sr_backup["password"])
    with pytest.raises(InvalidKey, match="address is not valid"):
        Keypair.from_json(tampered(sr_backup, address="not an address"), sr_backup["password"])


@pytest.mark.parametrize("index", [0, 31, 40, 44, 60, 70, -1])
def test_a_damaged_body_is_refused(sr_backup: dict[str, Any], index: int) -> None:
    def flip(body: bytearray) -> None:
        body[index] ^= 1

    with pytest.raises(InvalidKey):
        Keypair.from_json(with_body(sr_backup, flip), sr_backup["password"])


@pytest.mark.parametrize("length", [0, 43, 44, 67, 83])
def test_a_truncated_body_is_refused(sr_backup: dict[str, Any], length: int) -> None:
    with pytest.raises(InvalidKey, match="damaged"):
        Keypair.from_json(
            with_body(sr_backup, lambda body: body.__delitem__(slice(length, None))), "x"
        )


def test_scrypt_settings_outside_the_known_ones_are_refused_before_any_work(
    sr_backup: dict[str, Any],
) -> None:
    def greedy(body: bytearray) -> None:
        body[32:36] = (1 << 20).to_bytes(4, "little")  # N: gigabytes of memory

    started = time.monotonic()
    with pytest.raises(InvalidKey, match="scrypt settings"):
        Keypair.from_json(with_body(sr_backup, greedy), sr_backup["password"])
    assert time.monotonic() - started < 0.5


@pytest.mark.parametrize(
    "changes",
    [
        {"encoding__version": "2"},
        {"encoding__content": ["pkcs8", "ecdsa"]},
        {"encoding__content": ["pkcs8", "ethereum"]},
        {"encoding__content": ["pkcs1", "sr25519"]},
        {"encoding__type": ["scrypt"]},
        {"encoding__type": ["xsalsa20-poly1305"]},
        {"encoded": "not base64!"},
        {"encoded": ""},
    ],
    ids=lambda changes: next(iter(changes)),
)
def test_formats_that_are_not_supported_are_refused(
    sr_backup: dict[str, Any], changes: dict[str, Any]
) -> None:
    with pytest.raises(InvalidKey):
        Keypair.from_json(tampered(sr_backup, **changes), sr_backup["password"])


@pytest.mark.parametrize(
    "document", ["", "{}", "[]", "null", "not json", '{"encoded": 1}', [], None, 7]
)
def test_something_that_is_not_a_backup_is_refused(document: Any) -> None:
    with pytest.raises(InvalidKey, match=r"not a polkadot\.js wallet backup"):
        Keypair.from_json(document, "password")


def test_errors_never_carry_the_password_or_the_secret(sr_backup: dict[str, Any]) -> None:
    password = "correct horse battery staple"
    for document in (sr_backup["json"], tampered(sr_backup, address="5nope")):
        with pytest.raises(InvalidKey) as error:
            Keypair.from_json(document, password)
        text = str(error.value) + repr(error.value)
        assert password not in text
        assert sr_backup["json"]["encoded"] not in text
