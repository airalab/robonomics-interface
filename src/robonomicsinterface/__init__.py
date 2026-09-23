"""Python client for the Robonomics parachain."""

from importlib.metadata import PackageNotFoundError, version

from .bip39 import generate_mnemonic, validate_mnemonic
from .envelope import decrypt_package, encrypt_for_recipients, parse_decrypted
from .errors import (
    DecryptionError,
    EnvelopeError,
    InvalidAddress,
    InvalidKey,
    InvalidMnemonic,
    NoSecretKey,
    PackageError,
    PayloadError,
    RecipientError,
    RobonomicsError,
)
from .keys import DEV_PHRASE, ED25519, Keypair
from .ss58 import (
    ROBONOMICS_SS58_FORMAT,
    address_format,
    decode_address,
    encode_address,
    is_valid_address,
)

try:
    __version__ = version("robonomics-interface")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0+unknown"

__all__ = [
    "DEV_PHRASE",
    "ED25519",
    "ROBONOMICS_SS58_FORMAT",
    "DecryptionError",
    "EnvelopeError",
    "InvalidAddress",
    "InvalidKey",
    "InvalidMnemonic",
    "Keypair",
    "NoSecretKey",
    "PackageError",
    "PayloadError",
    "RecipientError",
    "RobonomicsError",
    "__version__",
    "address_format",
    "decode_address",
    "decrypt_package",
    "encode_address",
    "encrypt_for_recipients",
    "generate_mnemonic",
    "is_valid_address",
    "parse_decrypted",
    "validate_mnemonic",
]
