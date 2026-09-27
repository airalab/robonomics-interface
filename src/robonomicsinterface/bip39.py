"""BIP39 English mnemonics and the mini secret Substrate derives from them.

Substrate does not use the standard BIP39 seed. It derives a 32-byte "mini
secret" from the mnemonic's *entropy*, not from the mnemonic string, with
PBKDF2-HMAC-SHA512 over 2048 rounds (``substrate-bip39::seed_from_entropy``).
The standard seed would give a different address from the same words, which
is why the tests pin this against vectors from substrate-interface.
"""

import hashlib
import secrets
import unicodedata
from pathlib import Path

from .errors import InvalidMnemonic

__all__ = [
    "entropy_to_mnemonic",
    "generate_mnemonic",
    "mnemonic_to_entropy",
    "mnemonic_to_mini_secret",
    "validate_mnemonic",
]

_WORDLIST_FILE = Path(__file__).with_name("english.txt")
# The canonical BIP39 English wordlist, checked on load so that a damaged copy
# cannot silently change derived addresses.
_WORDLIST_SHA256 = "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda"
_WORDLIST_SIZE = 2048
_PBKDF2_ROUNDS = 2048
_MINI_SECRET_BYTES = 32
VALID_WORD_COUNTS = (12, 15, 18, 21, 24)


def _read_wordlist() -> tuple[str, ...]:
    data = _WORDLIST_FILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != _WORDLIST_SHA256:
        raise RuntimeError("the bundled BIP39 wordlist does not match its checksum")
    words = tuple(data.decode("utf-8").split())
    if len(words) != _WORDLIST_SIZE:
        raise RuntimeError(f"the bundled BIP39 wordlist has {len(words)} words, expected 2048")
    return words


# Read at import time: Home Assistant imports integrations off the event loop,
# while a mnemonic may be generated inside it, where file I/O is not allowed.
_WORDLIST = _read_wordlist()
_INDEX = {word: index for index, word in enumerate(_WORDLIST)}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text)


def generate_mnemonic(word_count: int = 12) -> str:
    """Generate a new random mnemonic from the system CSPRNG."""

    if word_count not in VALID_WORD_COUNTS:
        raise InvalidMnemonic(f"word count must be one of {VALID_WORD_COUNTS}")
    return entropy_to_mnemonic(secrets.token_bytes(word_count * 4 // 3))


def entropy_to_mnemonic(entropy: bytes) -> str:
    """Encode 16–32 bytes of entropy as a mnemonic with its checksum."""

    if len(entropy) * 8 not in (128, 160, 192, 224, 256):
        raise InvalidMnemonic(f"entropy must be 16, 20, 24, 28 or 32 bytes, not {len(entropy)}")
    checksum_bits = len(entropy) * 8 // 32
    checksum = hashlib.sha256(entropy).digest()[0] >> (8 - checksum_bits)
    bits = int.from_bytes(entropy, "big") << checksum_bits | checksum
    total_bits = len(entropy) * 8 + checksum_bits
    return " ".join(
        _WORDLIST[(bits >> shift) & (_WORDLIST_SIZE - 1)]
        for shift in range(total_bits - 11, -1, -11)
    )


def mnemonic_to_entropy(mnemonic: str) -> bytes:
    """Return the entropy behind a mnemonic; a bad checksum is refused."""

    words = _normalize(mnemonic).lower().split()
    if len(words) not in VALID_WORD_COUNTS:
        raise InvalidMnemonic(f"a mnemonic has 12, 15, 18, 21 or 24 words, not {len(words)}")

    bits = 0
    for position, word in enumerate(words, start=1):
        index = _INDEX.get(word)
        if index is None:
            # The position, not the word: the word is part of a secret.
            raise InvalidMnemonic(f"word #{position} is not in the BIP39 English list")
        bits = bits << 11 | index

    total_bits = len(words) * 11
    checksum_bits = total_bits // 33
    entropy = (bits >> checksum_bits).to_bytes((total_bits - checksum_bits) // 8, "big")
    expected = hashlib.sha256(entropy).digest()[0] >> (8 - checksum_bits)
    if bits & ((1 << checksum_bits) - 1) != expected:
        raise InvalidMnemonic("the mnemonic checksum does not match")
    return entropy


def validate_mnemonic(mnemonic: str) -> bool:
    """Whether the text is a valid mnemonic, words and checksum."""

    try:
        mnemonic_to_entropy(mnemonic)
    except InvalidMnemonic:
        return False
    return True


def mnemonic_to_mini_secret(mnemonic: str, password: str = "") -> bytes:
    """The 32-byte secret Substrate derives from a mnemonic and an optional password."""

    entropy = mnemonic_to_entropy(mnemonic)
    salt = ("mnemonic" + _normalize(password)).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha512", entropy, salt, _PBKDF2_ROUNDS)[:_MINI_SECRET_BYTES]
