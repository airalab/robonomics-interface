"""A package takes the sender's key type: sr25519 senders wrap for sr25519 recipients."""

import json
from typing import Any

import pytest
from nacl.secret import SecretBox

from robonomicsinterface import (
    ED25519,
    SR25519,
    Keypair,
    PackageError,
    PayloadError,
    RecipientError,
    decrypt_package,
    encrypt_for_recipients,
    parse_decrypted,
)

pytest.importorskip("sr25519")

PAYLOAD = "2026-09-16 13:00:00 ERROR (MainThread) [zha] Failed to connect\n"
META = {"orig_file_name": "home-assistant.log"}
BOX_BYTES = 24 + 32 + 16
ECIES_BYTES = 120 + 32 + 16


def sr(uri: str) -> Keypair:
    return Keypair.from_uri(uri, crypto_type=SR25519)


def ed(uri: str) -> Keypair:
    return Keypair.from_uri(uri, crypto_type=ED25519)


@pytest.fixture
def site() -> Keypair:
    return sr("//Site")


@pytest.fixture
def integrator() -> Keypair:
    return sr("//Integrator")


def wrapped_lengths(package: str) -> set[int]:
    return {len(bytes.fromhex(key[2:])) for key in json.loads(package)["keys"].values()}


# sr25519 → sr25519


def test_recipients_and_sender_read_the_payload(site: Keypair, integrator: Keypair) -> None:
    admin = sr("//Admin")
    package = encrypt_for_recipients(PAYLOAD, site, [integrator.address, admin.address], META)
    for reader in (integrator, admin, site):
        opened = decrypt_package(package, reader, site.address)
        assert parse_decrypted(opened) == (PAYLOAD, META)


def test_the_keys_are_ecies_messages_in_the_published_shape(
    site: Keypair, integrator: Keypair
) -> None:
    package = json.loads(encrypt_for_recipients(PAYLOAD, site, [integrator.address]))
    assert set(package) == {"data", "keys"}
    assert package["data"].startswith("0x")
    assert set(package["keys"]) == {site.address, integrator.address}
    assert all(key.startswith("0x") for key in package["keys"].values())
    assert wrapped_lengths(json.dumps(package)) == {ECIES_BYTES}


def test_ed25519_packages_keep_their_boxes() -> None:
    sender, recipient = ed("//Site"), ed("//Integrator")
    package = encrypt_for_recipients(PAYLOAD, sender, [recipient.address])
    assert wrapped_lengths(package) == {BOX_BYTES}
    assert decrypt_package(package, recipient, sender.address) == PAYLOAD


def test_the_sender_address_is_not_needed_to_open_an_sr25519_package(
    site: Keypair, integrator: Keypair
) -> None:
    package = encrypt_for_recipients(PAYLOAD, site, [integrator.address])
    assert decrypt_package(package, integrator, "not an address") == PAYLOAD
    assert decrypt_package(package, integrator, sr("//Other").address) == PAYLOAD


def test_each_package_uses_a_new_key(site: Keypair, integrator: Keypair) -> None:
    first = json.loads(encrypt_for_recipients(PAYLOAD, site, [integrator.address]))
    second = json.loads(encrypt_for_recipients(PAYLOAD, site, [integrator.address]))
    assert first["data"] != second["data"]
    assert first["keys"] != second["keys"]


def test_a_stranger_is_not_addressed(site: Keypair, integrator: Keypair) -> None:
    package = encrypt_for_recipients(PAYLOAD, site, [integrator.address])
    with pytest.raises(PackageError, match="not addressed"):
        decrypt_package(package, sr("//Stranger"), site.address)


def test_a_key_in_the_other_recipients_slot_does_not_open(
    site: Keypair, integrator: Keypair
) -> None:
    other = sr("//Other")
    package = json.loads(encrypt_for_recipients(PAYLOAD, site, [integrator.address, other.address]))
    package["keys"][integrator.address] = package["keys"][other.address]
    with pytest.raises(PayloadError, match="unwrap"):
        decrypt_package(json.dumps(package), integrator, site.address)


# What the old tools made


def test_a_package_with_a_key_wrapped_by_py_sr25519_encryption_opens(
    sr25519_old_stack: Any,
) -> None:
    section = sr25519_old_stack["ecies"]
    recipient = Keypair.from_mnemonic(section["recipient_mnemonic"], crypto_type=SR25519)
    payload_key = bytes(range(32))
    wrapped = next(
        v["blob_hex"]
        for v in section["vectors"]
        if v["kind"] == "ephemeral" and v["plaintext_hex"] == payload_key.hex()
    )
    package = json.dumps(
        {
            "data": "0x" + bytes(SecretBox(payload_key).encrypt(PAYLOAD.encode())).hex(),
            "keys": {recipient.address: "0x" + wrapped},
        }
    )
    assert decrypt_package(package, recipient, "anyone") == PAYLOAD


# One key type per package


def test_an_address_that_is_not_a_valid_key_of_the_senders_type_is_refused() -> None:
    site = sr("//Site")
    refused = []
    for seed in range(1, 40):  # most, not all, ED25519 keys are no ristretto points
        stranger = Keypair.from_seed(bytes([seed]) * 32)
        try:
            encrypt_for_recipients(PAYLOAD, site, [stranger.address])
        except RecipientError as error:
            assert stranger.address in str(error)
            assert "sr25519" in str(error)
            refused.append(seed)
    assert refused


def test_an_ed25519_sender_refuses_addresses_that_are_not_ed25519_points() -> None:
    site = ed("//Site")
    refused = 0
    for seed in range(1, 40):
        stranger = Keypair.from_seed(bytes([seed]) * 32, crypto_type=SR25519)
        try:
            encrypt_for_recipients(PAYLOAD, site, [stranger.address])
        except RecipientError as error:
            assert "ED25519" in str(error)
            refused += 1
    assert refused


def test_opening_with_the_wrong_key_type_says_so(site: Keypair, integrator: Keypair) -> None:
    sr_package = encrypt_for_recipients(PAYLOAD, site, [integrator.address])
    ed_reader = Keypair.from_seed(bytes(32))  # an ED25519 account
    wrong = json.loads(sr_package)
    wrong["keys"][ed_reader.address] = wrong["keys"][integrator.address]
    with pytest.raises(PayloadError, match=r"wrapped for an sr25519 account.* is ED25519"):
        decrypt_package(json.dumps(wrong), ed_reader, site.address)

    ed_sender, ed_recipient = ed("//Site"), ed("//Integrator")
    ed_package = json.loads(encrypt_for_recipients(PAYLOAD, ed_sender, [ed_recipient.address]))
    ed_package["keys"][integrator.address] = ed_package["keys"][ed_recipient.address]
    with pytest.raises(PayloadError, match=r"wrapped for an ED25519 account.* is sr25519"):
        decrypt_package(json.dumps(ed_package), integrator, ed_sender.address)


def test_a_damaged_key_is_not_blamed_on_the_key_type(site: Keypair, integrator: Keypair) -> None:
    package = json.loads(encrypt_for_recipients(PAYLOAD, site, [integrator.address]))
    key = package["keys"][integrator.address]
    package["keys"][integrator.address] = key[:-2] + ("00" if key[-2:] != "00" else "01")
    with pytest.raises(PayloadError) as error:
        decrypt_package(json.dumps(package), integrator, site.address)
    assert "wrapped for" not in str(error.value)
