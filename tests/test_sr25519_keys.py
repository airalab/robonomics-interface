"""sr25519 keys derive the same accounts and accept the same signatures as 2.x and polkadot.js."""

import pickle
from typing import Any

import pytest

from robonomicsinterface import (
    ED25519,
    SR25519,
    InvalidKey,
    Keypair,
    NoSecretKey,
    generate_mnemonic,
)

pytest.importorskip("sr25519")

MNEMONIC = "frozen woman pet meat entire question balcony wing echo excess adjust sleep"


def sr(uri: str) -> Keypair:
    return Keypair.from_uri(uri, crypto_type=SR25519)


# Accounts and URIs


def test_accounts_match_the_old_stack(sr25519_old_stack: Any) -> None:
    for vector in sr25519_old_stack["accounts"]:
        keypair = Keypair.from_mnemonic(vector["mnemonic"], vector["password"], crypto_type=SR25519)
        assert keypair.public_key.hex() == vector["public_key_hex"]
        assert keypair.address == vector["address_32"]
        mini = bytes.fromhex(vector["mini_secret_hex"])
        assert Keypair.from_seed(mini, 42, crypto_type=SR25519).address == vector["address_42"]


def test_accounts_match_polkadot_js(sr25519_js: Any) -> None:
    for vector in sr25519_js["accounts"]:
        for kind, crypto_type in (("sr25519", SR25519), ("ed25519", ED25519)):
            keypair = Keypair.from_mnemonic(
                vector["mnemonic"], vector["password"], crypto_type=crypto_type
            )
            assert keypair.public_key.hex() == vector[kind]["public_key_hex"]
            assert keypair.address == vector[kind]["address_32"]


def test_uris_match_the_old_stack(sr25519_old_stack: Any) -> None:
    for vector in sr25519_old_stack["uris"]:
        keypair = sr(vector["uri"])
        assert keypair.public_key.hex() == vector["public_key_hex"], vector["uri"]
        assert keypair.address == vector["address_32"]


def test_uris_match_polkadot_js(sr25519_js: Any) -> None:
    for vector in sr25519_js["uris"]:
        keypair = Keypair.from_uri(vector["uri"], crypto_type=vector["type"])
        assert keypair.public_key.hex() == vector["public_key_hex"], vector["uri"]
        assert keypair.address == vector["address_32"]


def test_soft_derivation_is_sr25519_only() -> None:
    assert sr("//Alice/stash") != sr("//Alice//stash")
    assert Keypair.from_uri("//Alice//stash") != sr("//Alice//stash")
    with pytest.raises(InvalidKey, match="hard derivation"):
        Keypair.from_uri("//Alice/stash")


def test_raw_seeds_and_secrets() -> None:
    seed = "0x" + "11" * 32
    by_seed = Keypair.from_seed(seed, crypto_type=SR25519)
    assert Keypair.from_secret(seed, crypto_type=SR25519) == by_seed
    assert Keypair.from_uri(seed, crypto_type=SR25519) == by_seed
    assert Keypair.from_secret(MNEMONIC, crypto_type=SR25519) == Keypair.from_mnemonic(
        MNEMONIC, crypto_type=SR25519
    )
    with pytest.raises(InvalidKey):
        Keypair.from_secret("//Alice", crypto_type=SR25519)
    with pytest.raises(InvalidKey):
        Keypair.from_seed(b"short", crypto_type=SR25519)


# Signatures


def test_signatures_from_the_old_stack_verify(sr25519_old_stack: Any) -> None:
    section = sr25519_old_stack["signatures"]
    signer = Keypair.from_mnemonic(section["signer_mnemonic"], crypto_type=SR25519)
    for vector in section["vectors"]:
        assert signer.verify(vector["message"], bytes.fromhex(vector["signature_hex"]))


def test_signatures_from_polkadot_js_verify(sr25519_js: Any) -> None:
    section = sr25519_js["signatures"]
    for name, crypto_type in (("sr25519", SR25519), ("ed25519", ED25519)):
        signer = Keypair.from_mnemonic(section["signer_mnemonic"], crypto_type=crypto_type)
        public_only = Keypair.from_public_key(signer.public_key, crypto_type=crypto_type)
        for vector in section["vectors"]:
            signature = bytes.fromhex(vector[f"{name}_hex"])
            assert signer.verify(vector["message"], signature)
            assert public_only.verify(vector["message"], signature)


def test_ed25519_signatures_still_match_byte_for_byte(sr25519_js: Any) -> None:
    section = sr25519_js["signatures"]
    signer = Keypair.from_mnemonic(section["signer_mnemonic"])
    for vector in section["vectors"]:
        assert signer.sign(vector["message"]).hex() == vector["ed25519_hex"]


def test_own_signatures_verify_and_are_randomized() -> None:
    signer = sr("//Alice")
    first, second = signer.sign("message"), signer.sign("message")
    assert len(first) == 64
    assert first != second
    assert signer.verify("message", first) and signer.verify("message", second)
    assert signer.verify(b"message", first)
    assert not signer.verify("another", first)
    assert not signer.verify("message", bytes([first[0] ^ 1]) + first[1:])
    assert not signer.verify("message", first[:10])
    assert not sr("//Bob").verify("message", first)


def test_a_signature_of_the_other_kind_does_not_verify() -> None:
    sr_signature = sr("//Alice").sign("message")
    ed_signature = Keypair.from_uri("//Alice").sign("message")
    assert not Keypair.from_uri("//Alice").verify("message", sr_signature)
    assert not sr("//Alice").verify("message", ed_signature)


# Public-only keypairs and the key type


def test_public_only_keypair_verifies_but_cannot_sign() -> None:
    signer = sr("//Alice")
    signature = signer.sign("message")
    for counterparty in (
        Keypair.from_public_key(signer.public_key, crypto_type=SR25519),
        Keypair.from_address(signer.address, crypto_type="sr25519"),
    ):
        assert counterparty == signer
        assert not counterparty.has_secret
        assert counterparty.verify("message", signature)
        with pytest.raises(NoSecretKey):
            counterparty.sign("message")


@pytest.mark.parametrize(
    ("given", "expected"),
    [(SR25519, SR25519), ("sr25519", SR25519), (" SR25519 ", SR25519), ("Ed25519", ED25519)],
)
def test_crypto_type_by_constant_or_name(given: int | str, expected: int) -> None:
    assert Keypair.from_seed(bytes(32), crypto_type=given).crypto_type == expected


@pytest.mark.parametrize("bad", ["ecdsa", "", 2, -1, None])
def test_unknown_crypto_type_is_refused(bad: Any) -> None:
    with pytest.raises(InvalidKey, match="key type"):
        Keypair.from_seed(bytes(32), crypto_type=bad)


def test_ed25519_stays_the_default() -> None:
    assert Keypair.from_mnemonic(MNEMONIC).crypto_type == ED25519
    assert Keypair.from_mnemonic(MNEMONIC) != Keypair.from_mnemonic(MNEMONIC, crypto_type=SR25519)


def test_a_new_mnemonic_works_for_both_kinds() -> None:
    mnemonic = generate_mnemonic()
    for crypto_type in (ED25519, SR25519):
        keypair = Keypair.from_mnemonic(mnemonic, crypto_type=crypto_type)
        assert keypair.verify("m", keypair.sign("m"))


# Secrets stay secret


def test_repr_names_the_kind_and_hides_the_secret() -> None:
    keypair = Keypair.from_mnemonic(MNEMONIC, crypto_type=SR25519)
    text = repr(keypair)
    assert text.startswith("<Keypair sr25519 ")
    assert keypair.address in text
    assert "frozen" not in text
    assert "public only" in repr(Keypair.from_public_key(keypair.public_key, crypto_type=SR25519))


def test_pickling_is_refused() -> None:
    with pytest.raises(TypeError):
        pickle.dumps(sr("//Alice"))
