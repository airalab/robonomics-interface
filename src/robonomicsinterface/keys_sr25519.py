"""sr25519 (Schnorrkel) primitives on py-sr25519-bindings, from the ``[sr25519]`` extra.

The secret is the bindings' own 64 bytes: a 32-byte scalar and a 32-byte nonce.
polkadot.js keeps the same pair in a different byte form; the two are told apart
where a JSON backup is read, not here.
"""

from ._extras import require

__all__ = ["derive", "pair_from_seed", "sign", "verify"]


def pair_from_seed(seed: bytes) -> tuple[bytes, bytes]:
    """The public key and the secret of a 32-byte mini secret."""

    public, secret = require("sr25519").pair_from_seed(seed)
    return bytes(public), bytes(secret)


def derive(public: bytes, secret: bytes, chain_code: bytes, *, hard: bool) -> tuple[bytes, bytes]:
    """The child for one junction. A soft child's nonce is random, as in the bindings."""

    sr25519 = require("sr25519")
    child = sr25519.hard_derive_keypair if hard else sr25519.derive_keypair
    _, child_public, child_secret = child((chain_code, public, secret), b"")
    return bytes(child_public), bytes(child_secret)


def sign(public: bytes, secret: bytes, message: bytes) -> bytes:
    return bytes(require("sr25519").sign((public, secret), message))


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    try:
        return bool(require("sr25519").verify(signature, message, public))
    except ValueError:  # a signature or key of the wrong length
        return False
