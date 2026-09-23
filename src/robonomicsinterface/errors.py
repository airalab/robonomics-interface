"""Exceptions raised by the library.

Everything derives from :class:`RobonomicsError`, so a caller can catch the
library as a whole. Input errors also derive from :class:`ValueError`: they
describe bad data, and retrying them is pointless.

Messages never contain secrets: no mnemonic, seed or private key is ever
formatted into an exception, including the input that failed to parse.
"""


class RobonomicsError(Exception):
    """Base class for every error raised by robonomics-interface."""


class InvalidMnemonic(RobonomicsError, ValueError):
    """The text is not a valid BIP39 English mnemonic."""


class InvalidAddress(RobonomicsError, ValueError):
    """The text is not a valid SS58 address, or it has an unexpected format."""


class InvalidKey(RobonomicsError, ValueError):
    """A seed, public key or derivation path cannot be used."""


class NoSecretKey(RobonomicsError):
    """The keypair holds a public key only, so it cannot sign or decrypt."""


class DecryptionError(RobonomicsError):
    """A box does not open: wrong keys, or the ciphertext was damaged."""


class EnvelopeError(RobonomicsError):
    """Base class for multi-recipient envelope errors."""


class RecipientError(EnvelopeError, ValueError):
    """A recipient address cannot be used to wrap the key."""


class PackageError(EnvelopeError, ValueError):
    """The package is malformed, or not addressed to this recipient."""


class PayloadError(EnvelopeError):
    """The package is well formed but could not be decrypted."""
