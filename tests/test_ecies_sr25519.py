"""sr25519 messages open across this library, py-sr25519-encryption and polkadot.js."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from nacl.secret import SecretBox

from conftest import FIXTURES
from robonomicsinterface import (
    SR25519,
    DecryptionError,
    InvalidKey,
    Keypair,
    NoSecretKey,
)

pytest.importorskip("sr25519")

HEADER = 24 + 32 + 32 + 32  # nonce, salt, one-time public key, mac
OVERHEAD = HEADER + 16  # and SecretBox's authenticator


def sr(uri: str) -> Keypair:
    return Keypair.from_uri(uri, crypto_type=SR25519)


@pytest.fixture(scope="module")
def alice() -> Keypair:
    return sr("//Alice")


@pytest.fixture(scope="module")
def bob() -> Keypair:
    return sr("//Bob")


# Messages made by the other implementations


def test_py_sr25519_encryption_messages_open(sr25519_old_stack: Any) -> None:
    section = sr25519_old_stack["ecies"]
    recipient = Keypair.from_mnemonic(section["recipient_mnemonic"], crypto_type=SR25519)
    kinds = set()
    for vector in section["vectors"]:
        opened = recipient.decrypt_message(bytes.fromhex(vector["blob_hex"]), b"")
        assert opened.hex() == vector["plaintext_hex"]
        kinds.add(vector["kind"])
    assert kinds == {"ephemeral", "sender_key"}


def test_polkadot_js_messages_open(sr25519_js: Any) -> None:
    section = sr25519_js["ecies"]
    recipient = Keypair.from_mnemonic(section["recipient_mnemonic"], crypto_type=SR25519)
    for vector in section["vectors"]:
        opened = recipient.decrypt_message(bytes.fromhex(vector["blob_hex"]), b"")
        assert opened == vector["plaintext"].encode()


# Round trip


@pytest.mark.parametrize("message", [b"", b"x", "отчёт 📦", b"\x00" * 32, b"x" * 100_000])
def test_round_trip(alice: Keypair, bob: Keypair, message: bytes | str) -> None:
    encrypted = alice.encrypt_message(message, bob.public_key)
    expected = message.encode() if isinstance(message, str) else message
    assert len(encrypted) == OVERHEAD + len(expected)
    assert bob.decrypt_message(encrypted, alice.public_key) == expected


def test_every_message_has_its_own_one_time_key_salt_and_nonce(
    alice: Keypair, bob: Keypair
) -> None:
    first = alice.encrypt_message("same", bob.public_key)
    second = alice.encrypt_message("same", bob.public_key)
    assert first != second
    assert first[:24] != second[:24]  # nonce
    assert first[24:56] != second[24:56]  # salt
    assert first[56:88] != second[56:88]  # one-time public key


def test_the_sender_plays_no_part(alice: Keypair, bob: Keypair) -> None:
    encrypted = alice.encrypt_message("hello", bob.public_key)
    # Not the sender's key, and no key at all: the message carries what it needs.
    assert bob.decrypt_message(encrypted, sr("//Charlie").public_key) == b"hello"
    assert bob.decrypt_message(encrypted, b"") == b"hello"
    # A keypair without a secret can encrypt, too.
    public_only = Keypair.from_public_key(alice.public_key, crypto_type=SR25519)
    assert bob.decrypt_message(public_only.encrypt_message("hi", bob.public_key), b"") == b"hi"


def test_the_message_is_for_the_recipient_only(alice: Keypair, bob: Keypair) -> None:
    encrypted = alice.encrypt_message("secret", bob.public_key)
    with pytest.raises(DecryptionError):
        sr("//Charlie").decrypt_message(encrypted, alice.public_key)
    with pytest.raises(DecryptionError):
        alice.decrypt_message(encrypted, alice.public_key)


# Damaged and hostile input: every failure is a DecryptionError


def _flip(data: bytes, index: int) -> bytes:
    return data[:index] + bytes([data[index] ^ 1]) + data[index + 1 :]


@pytest.mark.parametrize(
    "index",
    [0, 23, 24, 55, 56, 87, 88, 119, 120, 135, 136, -1],
    ids=lambda i: f"byte{i}",
)
def test_a_damaged_byte_is_refused(alice: Keypair, bob: Keypair, index: int) -> None:
    encrypted = alice.encrypt_message("secret payload", bob.public_key)
    with pytest.raises(DecryptionError):
        bob.decrypt_message(_flip(encrypted, index), alice.public_key)


@pytest.mark.parametrize("length", [0, 1, 24, 56, 119, 120, 121, 135, 136])
def test_a_truncated_message_is_refused(alice: Keypair, bob: Keypair, length: int) -> None:
    encrypted = alice.encrypt_message("secret payload", bob.public_key)
    with pytest.raises(DecryptionError):
        bob.decrypt_message(encrypted[:length], alice.public_key)


def test_an_appended_byte_is_refused(alice: Keypair, bob: Keypair) -> None:
    encrypted = alice.encrypt_message("secret payload", bob.public_key)
    with pytest.raises(DecryptionError):
        bob.decrypt_message(encrypted + b"\x00", alice.public_key)


@pytest.mark.parametrize("point", [bytes(32), b"\xff" * 32, bytes([1]) + bytes(31)])
def test_a_one_time_key_that_is_not_a_valid_point_is_refused(
    alice: Keypair, bob: Keypair, point: bytes
) -> None:
    encrypted = alice.encrypt_message("secret payload", bob.public_key)
    with pytest.raises(DecryptionError):
        bob.decrypt_message(encrypted[:56] + point + encrypted[88:], alice.public_key)


def test_the_mac_is_checked_before_the_payload_is_opened(
    alice: Keypair, bob: Keypair, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = []
    real = SecretBox.decrypt
    monkeypatch.setattr(SecretBox, "decrypt", lambda *a, **k: opened.append(1) or real(*a, **k))
    encrypted = alice.encrypt_message("secret payload", bob.public_key)
    with pytest.raises(DecryptionError):
        bob.decrypt_message(_flip(encrypted, 120), alice.public_key)
    assert not opened


def test_python_optimization_cannot_remove_the_checks() -> None:
    """The original guarded the MAC with ``assert``; there is none in this module."""

    import ast
    import inspect

    from robonomicsinterface import ecies_sr25519

    tree = ast.parse(inspect.getsource(ecies_sr25519))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]


# Bad recipients and the API around it


@pytest.mark.parametrize("public_key", [bytes(32), b"\xff" * 32, bytes(31), b"", b"\x01" * 32])
def test_a_recipient_that_is_not_a_valid_key_is_refused(alice: Keypair, public_key: bytes) -> None:
    with pytest.raises(InvalidKey, match="sr25519 public key"):
        alice.encrypt_message("x", public_key)


def test_nobody_can_decrypt_without_a_secret(alice: Keypair, bob: Keypair) -> None:
    encrypted = alice.encrypt_message("x", bob.public_key)
    public_only = Keypair.from_public_key(bob.public_key, crypto_type=SR25519)
    with pytest.raises(NoSecretKey):
        public_only.decrypt_message(encrypted, alice.public_key)


def test_a_nonce_is_for_ed25519_only(alice: Keypair, bob: Keypair) -> None:
    with pytest.raises(TypeError, match="ED25519"):
        alice.encrypt_message("x", bob.public_key, bytes(24))


def test_the_two_kinds_do_not_open_each_other() -> None:
    ed_alice, ed_bob = Keypair.from_uri("//Alice"), Keypair.from_uri("//Bob")
    box = ed_alice.encrypt_message("x", ed_bob.public_key)
    ecies = sr("//Alice").encrypt_message("x", sr("//Bob").public_key)
    with pytest.raises(DecryptionError):
        sr("//Bob").decrypt_message(box, ed_alice.public_key)
    with pytest.raises(DecryptionError):
        ed_bob.decrypt_message(ecies, ed_alice.public_key)


def test_ed25519_boxes_are_unchanged() -> None:
    alice, bob = Keypair.from_uri("//Alice"), Keypair.from_uri("//Bob")
    box = alice.encrypt_message("x", bob.public_key, bytes(24))
    assert box == alice.encrypt_message("x", bob.public_key, bytes(24))
    assert bob.decrypt_message(box, alice.public_key) == b"x"


# Our messages in polkadot.js (needs node; set ROBONOMICS_JS_DIR to the directory prepared
# for generate_sr25519_js.mjs, with its node_modules)


@pytest.mark.skipif(
    not os.environ.get("ROBONOMICS_JS_DIR") or not shutil.which("node"),
    reason="ROBONOMICS_JS_DIR is not set, or there is no node",
)
def test_our_messages_open_in_polkadot_js(tmp_path: Path, alice: Keypair) -> None:
    mnemonic = "frozen woman pet meat entire question balcony wing echo excess adjust sleep"
    recipient = Keypair.from_mnemonic(mnemonic, crypto_type=SR25519)
    messages = [b"", b"report payload", "отчёт 📦".encode(), bytes(range(32)), b"x" * 4096]
    blobs = [alice.encrypt_message(m, recipient.public_key).hex() for m in messages]

    (tmp_path / "node_modules").symlink_to(Path(os.environ["ROBONOMICS_JS_DIR"]) / "node_modules")
    for name in ("ecies_sr25519.mjs", "ecies_open_in_js.mjs"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    done = subprocess.run(  # noqa: S603 - our own script, node found on PATH
        [str(shutil.which("node")), "ecies_open_in_js.mjs"],
        input=json.dumps({"mnemonic": mnemonic, "blobs": blobs}),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(done.stdout) == [m.hex() for m in messages]
