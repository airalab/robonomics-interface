"""3.0 must derive the same accounts and read the same ciphertexts as the 2.x stack."""

from typing import Any

import pytest

from robonomicsinterface import Keypair
from robonomicsinterface.bip39 import mnemonic_to_mini_secret


def test_mini_secrets_and_addresses_match(compat_vectors: Any) -> None:
    for vector in compat_vectors["accounts"]:
        mini = mnemonic_to_mini_secret(vector["mnemonic"], vector["password"])
        assert mini.hex() == vector["mini_secret_hex"]

        keypair = Keypair.from_mnemonic(vector["mnemonic"], vector["password"])
        assert keypair.public_key.hex() == vector["public_key_hex"]
        assert keypair.address == vector["address_32"]
        assert Keypair.from_seed(mini, ss58_format=42).address == vector["address_42"]


def test_raw_seeds_match(compat_vectors: Any) -> None:
    for vector in compat_vectors["seeds"]:
        keypair = Keypair.from_seed(vector["seed_hex"])
        assert keypair.public_key.hex() == vector["public_key_hex"]
        assert keypair.address == vector["address_32"]
        assert Keypair.from_secret(vector["seed_hex"]).address == vector["address_32"]


def test_boxes_are_byte_identical_both_ways(compat_vectors: Any) -> None:
    section = compat_vectors["encryption"]
    sender = Keypair.from_mnemonic(section["sender_mnemonic"])
    recipient = Keypair.from_mnemonic(section["recipient_mnemonic"])

    for vector in section["vectors"]:
        nonce = bytes.fromhex(vector["nonce_hex"])
        box = sender.encrypt_message(vector["plaintext"], recipient.public_key, nonce)
        assert box.hex() == vector["box_hex"]
        opened = recipient.decrypt_message(bytes.fromhex(vector["box_hex"]), sender.public_key)
        assert opened == vector["plaintext"].encode("utf-8")


def test_signatures_are_byte_identical(compat_vectors: Any) -> None:
    section = compat_vectors["signatures"]
    signer = Keypair.from_mnemonic(section["signer_mnemonic"])

    for vector in section["vectors"]:
        signature = signer.sign(vector["message"])
        assert signature.hex() == vector["signature_hex"]
        assert signer.verify(vector["message"], signature)


# The contract rrs-ha-integration already holds


@pytest.fixture
def accounts(report_service_vectors: Any) -> dict[str, Any]:
    return {entry["name"]: entry for entry in report_service_vectors["accounts"]}


def test_report_service_accounts(accounts: dict[str, Any]) -> None:
    for entry in accounts.values():
        keypair = Keypair.from_mnemonic(entry["mnemonic"])
        assert mnemonic_to_mini_secret(entry["mnemonic"]).hex() == entry["mini_secret_hex"]
        assert keypair.public_key.hex() == entry["public_key_hex"]
        assert keypair.address == entry["account_address"]
        generic = Keypair.from_mnemonic(entry["mnemonic"], ss58_format=42)
        assert generic.address == entry["ss58_address"]


def test_report_service_encryption(accounts: dict[str, Any], report_service_vectors: Any) -> None:
    sender = Keypair.from_mnemonic(accounts["sender"]["mnemonic"])
    recipient = Keypair.from_mnemonic(accounts["recipient"]["mnemonic"])
    vector = report_service_vectors["encryption"]

    opened = recipient.decrypt_message(bytes.fromhex(vector["encrypted_hex"]), sender.public_key)
    assert opened.decode("utf-8") == vector["decrypts_back"]


def test_report_service_signature(accounts: dict[str, Any], report_service_vectors: Any) -> None:
    sender = Keypair.from_mnemonic(accounts["sender"]["mnemonic"])
    vector = report_service_vectors["signature"]

    assert sender.sign(vector["message_utf8"]).hex() == vector["signature_hex"]
    assert sender.verify(vector["message_utf8"], bytes.fromhex(vector["signature_hex"]))
