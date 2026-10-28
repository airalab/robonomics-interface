"""ED25519 and sr25519 accounts: key derivation, signatures and message encryption.

ED25519 runs on PyNaCl, sr25519 on the ``[sr25519]`` extra (:mod:`.keys_sr25519`).
Wire formats match substrate-interface byte for byte: the same mini secret
from a mnemonic, the same ed25519 → curve25519 conversion and the same NaCl
box with the nonce in front. Reports already encrypted by the 2.x stack stay
readable, and the ones produced here open with the old tools.
"""

from __future__ import annotations

import hashlib
import re
from typing import NoReturn, Self

import nacl.bindings
import nacl.exceptions
import nacl.public
import nacl.signing

from . import ecies_sr25519, keys_sr25519
from .bip39 import generate_mnemonic, mnemonic_to_mini_secret
from .errors import DecryptionError, InvalidKey, NoSecretKey
from .ss58 import ROBONOMICS_SS58_FORMAT, address_format, decode_address, encode_address

__all__ = ["DEV_PHRASE", "ED25519", "SR25519", "Keypair"]

# Substrate's MultiSignature ordering; also the signature tag in an extrinsic.
ED25519 = 0
SR25519 = 1
_KEY_TYPES = {"ed25519": ED25519, "sr25519": SR25519}
_KEY_NAMES = {value: name for name, value in _KEY_TYPES.items()}

# The well-known development phrase behind //Alice, //Bob and friends.
DEV_PHRASE = "bottom drive obey lake curtain smoke basket hold race lonely fit walk"

_SEED_BYTES = 32
_PUBLIC_KEY_BYTES = 32
_JUNCTION_BYTES = 32
_HDKD_CONTEXT = b"\x2cEd25519HDKD"  # SCALE-encoded str: compact length 11, then the bytes
_URI = re.compile(r"^(?P<phrase>[^/]*?)(?P<path>(?://?[^/]+)*)(?:///(?P<password>.*))?$")
_JUNCTION = re.compile(r"(//?)([^/]+)")


def _compact_length(length: int) -> bytes:
    if length < 1 << 6:
        return bytes([length << 2])
    if length < 1 << 14:
        return ((length << 2) | 0b01).to_bytes(2, "little")
    if length < 1 << 30:
        return ((length << 2) | 0b10).to_bytes(4, "little")
    raise InvalidKey("a derivation junction is too long")


def _chain_code(junction: str) -> bytes:
    """A junction's chain code, as ``sp_core::crypto::DeriveJunction`` builds it."""

    if junction.isdecimal() and int(junction) < 1 << 64:
        code = int(junction).to_bytes(8, "little")
    else:
        raw = junction.encode("utf-8")
        code = _compact_length(len(raw)) + raw
    if len(code) > _JUNCTION_BYTES:
        return hashlib.blake2b(code, digest_size=32).digest()
    return code.ljust(_JUNCTION_BYTES, b"\x00")


def _derive_hard(seed: bytes, junction: str) -> bytes:
    # sp_core::ed25519: ("Ed25519HDKD", seed, chain_code).using_encoded(blake2_256)
    return hashlib.blake2b(_HDKD_CONTEXT + seed + _chain_code(junction), digest_size=32).digest()


def _seed_from_hex(text: str) -> bytes:
    try:
        seed = bytes.fromhex(text.removeprefix("0x"))
    except ValueError:
        raise InvalidKey("a raw seed must be 0x-prefixed hex") from None
    if len(seed) != _SEED_BYTES:
        raise InvalidKey(f"a raw seed is {_SEED_BYTES} bytes, not {len(seed)}")
    return seed


def _as_bytes(message: bytes | str) -> bytes:
    return message.encode("utf-8") if isinstance(message, str) else bytes(message)


def _key_type(crypto_type: int | str) -> int:
    """``ED25519``/``SR25519``, or their names as a config file would hold them."""

    kind = (
        _KEY_TYPES.get(crypto_type.strip().lower()) if isinstance(crypto_type, str) else crypto_type
    )
    if kind not in _KEY_NAMES:
        raise InvalidKey("the key type must be ED25519 or SR25519 (or 'ed25519', 'sr25519')")
    return kind


class Keypair:
    """An ED25519 or sr25519 account, with or without its secret key.

    Build one with a ``from_*`` class method; ``crypto_type`` picks the kind
    (``ED25519`` by default, so an existing mnemonic keeps its address). A
    keypair built from a public key or an address can verify signatures and be
    encrypted to, but not sign or decrypt. The secret is held only inside the
    signing key: the mnemonic or URI it came from is not kept, and neither
    :func:`repr` nor exceptions ever show it.
    """

    __slots__ = ("_public_key", "_signing_key", "_sr25519_secret", "crypto_type", "ss58_format")

    _public_key: bytes
    _signing_key: nacl.signing.SigningKey | None
    _sr25519_secret: bytes | None
    crypto_type: int
    ss58_format: int

    def __init__(self) -> None:
        raise TypeError("use Keypair.from_mnemonic(), from_seed(), from_uri() or from_address()")

    @classmethod
    def _build(
        cls,
        crypto_type: int,
        signing_key: nacl.signing.SigningKey | None,
        sr25519_secret: bytes | None,
        public_key: bytes,
        ss58_format: int,
    ) -> Self:
        keypair = object.__new__(cls)
        keypair.crypto_type = crypto_type
        keypair._signing_key = signing_key
        keypair._sr25519_secret = sr25519_secret
        keypair._public_key = public_key
        keypair.ss58_format = ss58_format
        return keypair

    # Construction

    @classmethod
    def from_seed(
        cls,
        seed: bytes | str,
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
        *,
        crypto_type: int | str = ED25519,
    ) -> Self:
        """From a 32-byte seed (the Substrate "mini secret"), raw or as 0x hex."""

        kind = _key_type(crypto_type)
        if isinstance(seed, str):
            seed = _seed_from_hex(seed)
        if len(seed) != _SEED_BYTES:
            raise InvalidKey(f"a seed is {_SEED_BYTES} bytes, not {len(seed)}")
        if kind == SR25519:
            public_key, secret = keys_sr25519.pair_from_seed(bytes(seed))
            return cls._build(kind, None, secret, public_key, ss58_format)
        signing_key = nacl.signing.SigningKey(bytes(seed))
        return cls._build(kind, signing_key, None, bytes(signing_key.verify_key), ss58_format)

    @classmethod
    def from_mnemonic(
        cls,
        mnemonic: str,
        password: str = "",
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
        *,
        crypto_type: int | str = ED25519,
    ) -> Self:
        """From a BIP39 English mnemonic, as polkadot.js and substrate-interface derive it."""

        return cls.from_seed(
            mnemonic_to_mini_secret(mnemonic, password), ss58_format, crypto_type=crypto_type
        )

    @classmethod
    def from_uri(
        cls,
        uri: str,
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
        *,
        crypto_type: int | str = ED25519,
    ) -> Self:
        """From a Substrate secret URI: ``<phrase or 0x seed>//hard/soft///password``.

        An empty phrase means the development phrase, so ``//Alice`` gives the
        well-known development account. ED25519 has hard derivation only; a
        soft junction (``/path``) is refused. Use this for development and
        tests; for keys that people paste, use :meth:`from_secret`.
        """

        kind = _key_type(crypto_type)
        match = _URI.match(uri.strip())
        if match is None:
            raise InvalidKey("the secret URI is malformed")
        phrase = match["phrase"].strip() or DEV_PHRASE
        password = match["password"] or ""

        if phrase.startswith("0x"):
            if password:
                raise InvalidKey("a password applies to a mnemonic, not to a raw seed")
            seed = _seed_from_hex(phrase)
        else:
            seed = mnemonic_to_mini_secret(phrase, password)

        junctions = _JUNCTION.findall(match["path"])
        if kind == SR25519:
            public_key, secret = keys_sr25519.pair_from_seed(seed)
            for separator, junction in junctions:
                public_key, secret = keys_sr25519.derive(
                    public_key, secret, _chain_code(junction), hard=separator == "//"
                )
            return cls._build(kind, None, secret, public_key, ss58_format)

        for separator, junction in junctions:
            if separator == "/":
                raise InvalidKey("ED25519 supports hard derivation (//path) only")
            seed = _derive_hard(seed, junction)

        return cls.from_seed(seed, ss58_format)

    @classmethod
    def from_secret(
        cls,
        secret: str,
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
        *,
        crypto_type: int | str = ED25519,
    ) -> Self:
        """From what a person may paste: a mnemonic or a raw 0x seed.

        Derivation paths, and development keys such as ``//Alice`` with them,
        are refused on purpose: those secrets are public.
        """

        secret = secret.strip()
        if "/" in secret:
            raise InvalidKey("derivation paths are not accepted here; use Keypair.from_uri()")
        if secret.startswith("0x"):
            return cls.from_seed(secret, ss58_format, crypto_type=crypto_type)
        return cls.from_mnemonic(secret, ss58_format=ss58_format, crypto_type=crypto_type)

    @classmethod
    def from_public_key(
        cls,
        public_key: bytes | str,
        ss58_format: int = ROBONOMICS_SS58_FORMAT,
        *,
        crypto_type: int | str = ED25519,
    ) -> Self:
        """A counterparty known by its public key: can verify and be encrypted to."""

        kind = _key_type(crypto_type)
        if isinstance(public_key, str):
            try:
                public_key = bytes.fromhex(public_key.removeprefix("0x"))
            except ValueError:
                raise InvalidKey("a public key must be 0x-prefixed hex") from None
        if len(public_key) != _PUBLIC_KEY_BYTES:
            raise InvalidKey(f"a public key is {_PUBLIC_KEY_BYTES} bytes, not {len(public_key)}")
        return cls._build(kind, None, None, bytes(public_key), ss58_format)

    @classmethod
    def from_address(
        cls,
        address: str,
        ss58_format: int | None = None,
        *,
        crypto_type: int | str = ED25519,
    ) -> Self:
        """A counterparty known by its SS58 address.

        :param ss58_format: when given, an address of another network is
            refused; otherwise the address's own format is kept.

        An address carries no key type: say which it is with ``crypto_type``.
        A wrong one only shows later, when a signature does not verify or a
        message does not decrypt.
        """

        kind = _key_type(crypto_type)
        public_key = decode_address(address, ss58_format)
        return cls._build(kind, None, None, public_key, address_format(address))

    @staticmethod
    def generate_mnemonic(word_count: int = 12) -> str:
        """A new random mnemonic; build the keypair with :meth:`from_mnemonic`."""

        return generate_mnemonic(word_count)

    # Identity

    @property
    def public_key(self) -> bytes:
        return self._public_key

    @property
    def address(self) -> str:
        """The SS58 address in this keypair's format (32, Robonomics, by default)."""

        return encode_address(self._public_key, self.ss58_format)

    @property
    def has_secret(self) -> bool:
        return self._signing_key is not None or self._sr25519_secret is not None

    def __repr__(self) -> str:
        public_only = "" if self.has_secret else ", public only"
        return f"<Keypair {_KEY_NAMES[self.crypto_type]} {self.address}{public_only}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Keypair):
            return NotImplemented
        return (self.crypto_type, self._public_key) == (other.crypto_type, other._public_key)

    def __hash__(self) -> int:
        return hash((self.crypto_type, self._public_key))

    def __reduce__(self) -> NoReturn:
        # Pickling would write the secret key out; refuse rather than leak.
        raise TypeError("Keypair cannot be pickled")

    # Signatures

    def _secret(self) -> nacl.signing.SigningKey:
        if self._signing_key is None:
            raise NoSecretKey(f"{self.address} is a public key only")
        return self._signing_key

    def sign(self, message: bytes | str) -> bytes:
        """A 64-byte signature. A ``str`` is signed as its UTF-8 bytes.

        An sr25519 signature is randomized: signing twice gives different
        bytes, and both verify.
        """

        if self.crypto_type == SR25519:
            if self._sr25519_secret is None:
                raise NoSecretKey(f"{self.address} is a public key only")
            return keys_sr25519.sign(self._public_key, self._sr25519_secret, _as_bytes(message))
        return bytes(self._secret().sign(_as_bytes(message)).signature)

    def verify(self, message: bytes | str, signature: bytes) -> bool:
        if self.crypto_type == SR25519:
            return keys_sr25519.verify(self._public_key, _as_bytes(message), bytes(signature))
        try:
            nacl.signing.VerifyKey(self._public_key).verify(_as_bytes(message), bytes(signature))
        except (nacl.exceptions.BadSignatureError, nacl.exceptions.ValueError, TypeError):
            return False
        return True

    # Encryption

    def _box(self, counterparty_public_key: bytes) -> nacl.public.Box:
        signing_key = self._secret()
        own = nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(
            bytes(signing_key) + self._public_key
        )
        try:
            other = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(
                bytes(counterparty_public_key)
            )
        except (nacl.exceptions.RuntimeError, nacl.exceptions.ValueError, TypeError):
            raise InvalidKey("the counterparty public key is not a valid ED25519 point") from None
        return nacl.public.Box(nacl.public.PrivateKey(own), nacl.public.PublicKey(other))

    def encrypt_message(
        self, message: bytes | str, recipient_public_key: bytes, nonce: bytes | None = None
    ) -> bytes:
        """Encrypt for one recipient.

        An ED25519 keypair makes a NaCl box with the 24-byte nonce in front; the
        recipient needs this keypair's public key to open it. An sr25519 keypair
        makes an ECIES message (:mod:`.ecies_sr25519`) from a one-time key, so
        its own key plays no part: nothing in the message names the sender, and
        a public-only keypair can encrypt too.

        :param nonce: for ED25519 test vectors only; a random nonce is used otherwise.
        """

        if self.crypto_type == SR25519:
            if nonce is not None:
                raise TypeError("a nonce can be given for ED25519 only")
            return ecies_sr25519.encrypt(_as_bytes(message), bytes(recipient_public_key))
        box = self._box(recipient_public_key)
        return bytes(box.encrypt(_as_bytes(message), nonce))

    def decrypt_message(self, encrypted_message: bytes, sender_public_key: bytes) -> bytes:
        """Open what :meth:`encrypt_message` made (an ED25519 box may be from substrate-interface).

        ``sender_public_key`` opens an ED25519 box; an sr25519 message carries
        its own one-time key, so the argument is not used.
        """

        if self.crypto_type == SR25519:
            if self._sr25519_secret is None:
                raise NoSecretKey(f"{self.address} is a public key only")
            return ecies_sr25519.decrypt(bytes(encrypted_message), self._sr25519_secret)
        box = self._box(sender_public_key)
        try:
            return bytes(box.decrypt(bytes(encrypted_message)))
        except (nacl.exceptions.CryptoError, nacl.exceptions.ValueError, TypeError):
            raise DecryptionError("the message cannot be decrypted with these keys") from None
