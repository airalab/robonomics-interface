"""Python client for the Robonomics parachain."""

from importlib.metadata import PackageNotFoundError, version

from .bip39 import generate_mnemonic, validate_mnemonic
from .client import DEFAULT_ENDPOINT, ROBONOMICS_GENESIS_HASH, RobonomicsClient
from .envelope import decrypt_package, encrypt_for_recipients, parse_decrypted
from .errors import (
    AllEndpointsFailed,
    ConnectionFailed,
    ConnectionLost,
    DecodeError,
    DecryptionError,
    EncodeError,
    EnvelopeError,
    InvalidAddress,
    InvalidKey,
    InvalidMnemonic,
    MetadataError,
    NoSecretKey,
    NoSuchConstant,
    NoSuchPallet,
    NoSuchStorage,
    PackageError,
    PayloadError,
    RecipientError,
    RequestTimeout,
    RobonomicsError,
    RpcError,
    TransportError,
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
    "DEFAULT_ENDPOINT",
    "DEV_PHRASE",
    "ED25519",
    "ROBONOMICS_GENESIS_HASH",
    "ROBONOMICS_SS58_FORMAT",
    "AllEndpointsFailed",
    "ConnectionFailed",
    "ConnectionLost",
    "DecodeError",
    "DecryptionError",
    "EncodeError",
    "EnvelopeError",
    "InvalidAddress",
    "InvalidKey",
    "InvalidMnemonic",
    "Keypair",
    "MetadataError",
    "NoSecretKey",
    "NoSuchConstant",
    "NoSuchPallet",
    "NoSuchStorage",
    "PackageError",
    "PayloadError",
    "RecipientError",
    "RequestTimeout",
    "RobonomicsClient",
    "RobonomicsError",
    "RpcError",
    "TransportError",
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
