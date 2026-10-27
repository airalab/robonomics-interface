import pickle

import pytest

from robonomicsinterface import (
    DEV_PHRASE,
    DecryptionError,
    InvalidAddress,
    InvalidKey,
    InvalidMnemonic,
    Keypair,
    NoSecretKey,
    generate_mnemonic,
    validate_mnemonic,
)
from robonomicsinterface.bip39 import entropy_to_mnemonic, mnemonic_to_entropy

# Well-known ED25519 development accounts (polkadot-sdk, polkadot.js).
ALICE_ED25519 = "88dc3417d5058ec4b4503e0c12ea1a0a89be200fe98922423d4334014fa6b0ee"
BOB_ED25519 = "d17c2d7823ebf260fd138f2d7e27d114c0145d968b5ff5006125f2414fadae69"
MNEMONIC = "frozen woman pet meat entire question balcony wing echo excess adjust sleep"


# Mnemonics


@pytest.mark.parametrize("words", [12, 15, 18, 21, 24])
def test_generated_mnemonics_round_trip(words: int) -> None:
    mnemonic = generate_mnemonic(words)
    assert len(mnemonic.split()) == words
    assert validate_mnemonic(mnemonic)
    assert entropy_to_mnemonic(mnemonic_to_entropy(mnemonic)) == mnemonic


def test_generated_mnemonics_differ() -> None:
    assert len({generate_mnemonic() for _ in range(20)}) == 20


def test_bad_checksum_is_refused() -> None:
    words = MNEMONIC.split()
    words[-1] = "abandon"
    assert not validate_mnemonic(" ".join(words))


def test_unknown_word_error_names_the_position_not_the_word() -> None:
    words = MNEMONIC.split()
    words[3] = "notaword"
    with pytest.raises(InvalidMnemonic) as error:
        Keypair.from_mnemonic(" ".join(words))
    assert "#4" in str(error.value)
    assert "notaword" not in str(error.value)


def test_mnemonic_is_case_and_space_insensitive() -> None:
    messy = "  " + MNEMONIC.upper().replace(" ", "   ") + "\n"
    assert Keypair.from_mnemonic(messy) == Keypair.from_mnemonic(MNEMONIC)


@pytest.mark.parametrize("count", [0, 11, 13, 25])
def test_wrong_word_counts(count: int) -> None:
    with pytest.raises(InvalidMnemonic):
        generate_mnemonic(count)


# URIs and derivation


def test_dev_accounts() -> None:
    assert Keypair.from_uri("//Alice").public_key.hex() == ALICE_ED25519
    assert Keypair.from_uri("//Bob").public_key.hex() == BOB_ED25519
    assert Keypair.from_uri(DEV_PHRASE + "//Alice") == Keypair.from_uri("//Alice")


def test_uri_without_path_is_the_mnemonic() -> None:
    assert Keypair.from_uri(MNEMONIC) == Keypair.from_mnemonic(MNEMONIC)


def test_uri_password() -> None:
    assert Keypair.from_uri(MNEMONIC + "///secret") == Keypair.from_mnemonic(MNEMONIC, "secret")


def test_hard_paths_compose() -> None:
    a = Keypair.from_uri("//Alice//stash")
    assert a != Keypair.from_uri("//Alice")
    assert a == Keypair.from_uri("//Alice//stash")


def test_numeric_and_long_junctions() -> None:
    # sp_core parses a numeric junction as u64, so "00" is the same junction as "0".
    assert Keypair.from_uri("//0") == Keypair.from_uri("//00")
    keys = {
        Keypair.from_uri(uri).public_key
        for uri in ("//0", "//1", "//a", "//" + "x" * 40, "//" + "x" * 41)
    }
    assert len(keys) == 5


def test_soft_derivation_is_refused() -> None:
    with pytest.raises(InvalidKey, match="hard derivation"):
        Keypair.from_uri("//Alice/soft")


def test_seed_uri_with_path() -> None:
    seed = "0x" + "11" * 32
    assert Keypair.from_uri(seed + "//a") != Keypair.from_seed(seed)
    with pytest.raises(InvalidKey):
        Keypair.from_uri(seed + "///password")


def test_from_secret_refuses_paths() -> None:
    with pytest.raises(InvalidKey):
        Keypair.from_secret("//Alice")
    with pytest.raises(InvalidKey):
        Keypair.from_secret(MNEMONIC + "//hard")
    assert Keypair.from_secret(f"  {MNEMONIC}  ") == Keypair.from_mnemonic(MNEMONIC)


@pytest.mark.parametrize("seed", ["0x1234", "0x" + "zz" * 32, b"\x00" * 31])
def test_bad_seeds(seed: str | bytes) -> None:
    with pytest.raises(InvalidKey):
        Keypair.from_seed(seed)


# Public-only keypairs


def test_from_address_and_public_key() -> None:
    alice = Keypair.from_uri("//Alice")
    by_address = Keypair.from_address(alice.address)
    by_key = Keypair.from_public_key("0x" + ALICE_ED25519)

    assert by_address == alice == by_key
    assert not by_address.has_secret
    assert by_address.address == alice.address


def test_from_address_keeps_or_checks_the_format() -> None:
    generic = Keypair.from_uri("//Alice", ss58_format=42).address
    assert Keypair.from_address(generic).ss58_format == 42
    with pytest.raises(InvalidAddress):
        Keypair.from_address(generic, ss58_format=32)


def test_public_only_cannot_sign_or_decrypt() -> None:
    alice = Keypair.from_uri("//Alice")
    public = Keypair.from_address(alice.address)
    with pytest.raises(NoSecretKey):
        public.sign(b"x")
    with pytest.raises(NoSecretKey):
        public.decrypt_message(b"\x00" * 64, alice.public_key)
    assert public.verify(b"x", alice.sign(b"x"))


def test_direct_construction_is_refused() -> None:
    with pytest.raises(TypeError):
        Keypair()


# Signatures and encryption


def test_signature_checks() -> None:
    alice, bob = Keypair.from_uri("//Alice"), Keypair.from_uri("//Bob")
    signature = alice.sign("message")
    assert alice.verify(b"message", signature)
    assert not alice.verify("other", signature)
    assert not bob.verify("message", signature)
    assert not alice.verify("message", b"short")


def test_encryption_round_trip_and_random_nonce() -> None:
    alice, bob = Keypair.from_uri("//Alice"), Keypair.from_uri("//Bob")
    first = alice.encrypt_message("hello", bob.public_key)
    second = alice.encrypt_message("hello", bob.public_key)
    assert first != second
    assert bob.decrypt_message(first, alice.public_key) == b"hello"
    assert alice.decrypt_message(first, bob.public_key) == b"hello"


def test_wrong_keys_raise_decryption_error() -> None:
    alice, bob = Keypair.from_uri("//Alice"), Keypair.from_uri("//Bob")
    charlie = Keypair.from_uri("//Charlie")
    box = alice.encrypt_message("hello", bob.public_key)
    with pytest.raises(DecryptionError):
        charlie.decrypt_message(box, alice.public_key)
    with pytest.raises(DecryptionError):
        bob.decrypt_message(box[:-1] + bytes([box[-1] ^ 1]), alice.public_key)


# Secrets never leak


def test_repr_and_errors_hide_secrets() -> None:
    keypair = Keypair.from_mnemonic(MNEMONIC)
    text = repr(keypair)
    assert keypair.address in text
    assert MNEMONIC.split()[0] not in text
    for attribute in ("mnemonic", "seed", "private_key", "__dict__"):
        assert not hasattr(keypair, attribute)

    with pytest.raises(InvalidKey) as error:
        Keypair.from_seed("0x" + "ab" * 31)
    assert "ab" * 31 not in str(error.value)


def test_keypair_cannot_be_pickled() -> None:
    with pytest.raises(TypeError):
        pickle.dumps(Keypair.from_uri("//Alice"))
