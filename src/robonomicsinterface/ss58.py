"""SS58 addresses: a network prefix, a 32-byte public key and a blake2b checksum."""

import hashlib

from .errors import InvalidAddress

__all__ = [
    "ROBONOMICS_SS58_FORMAT",
    "address_format",
    "decode_address",
    "encode_address",
    "is_valid_address",
]

# Robonomics addresses start with "4".
ROBONOMICS_SS58_FORMAT = 32

_CHECKSUM_PREFIX = b"SS58PRE"
_CHECKSUM_BYTES = 2
_PUBLIC_KEY_BYTES = 32
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ALPHABET_INDEX = {char: index for index, char in enumerate(_ALPHABET)}


def _b58encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _ALPHABET[remainder] + encoded
    leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    return _ALPHABET[0] * leading_zeros + encoded


def _b58decode(text: str) -> bytes:
    number = 0
    for char in text:
        index = _ALPHABET_INDEX.get(char)
        if index is None:
            raise InvalidAddress("the address contains a character outside base58")
        number = number * 58 + index
    leading_zeros = len(text) - len(text.lstrip(_ALPHABET[0]))
    return b"\x00" * leading_zeros + number.to_bytes((number.bit_length() + 7) // 8, "big")


def _prefix(ss58_format: int) -> bytes:
    if 0 <= ss58_format <= 63:
        return bytes([ss58_format])
    if 64 <= ss58_format <= 16383:
        # The two-byte form defined by the SS58 registry.
        first = ((ss58_format & 0b1111_1100) >> 2) | 0b0100_0000
        second = (ss58_format >> 8) | ((ss58_format & 0b11) << 6)
        return bytes([first, second])
    raise InvalidAddress(f"SS58 format {ss58_format} is outside 0..16383")


def _checksum(payload: bytes) -> bytes:
    return hashlib.blake2b(_CHECKSUM_PREFIX + payload, digest_size=64).digest()[:_CHECKSUM_BYTES]


def _split(address: str) -> tuple[int, bytes]:
    if not isinstance(address, str) or not address:
        raise InvalidAddress("an address must be a non-empty string")
    decoded = _b58decode(address)
    if not decoded:
        raise InvalidAddress("the address is empty")
    if decoded[0] < 64:
        ss58_format, prefix_length = decoded[0], 1
    elif decoded[0] < 128 and len(decoded) >= 2:
        low = ((decoded[0] & 0b0011_1111) << 2) | (decoded[1] >> 6)
        ss58_format, prefix_length = low | ((decoded[1] & 0b0011_1111) << 8), 2
    else:
        raise InvalidAddress("the address has a reserved SS58 prefix")
    if len(decoded) != prefix_length + _PUBLIC_KEY_BYTES + _CHECKSUM_BYTES:
        raise InvalidAddress("the address does not hold a 32-byte account id")
    payload, given = decoded[:-_CHECKSUM_BYTES], decoded[-_CHECKSUM_BYTES:]
    if _checksum(payload) != given:
        raise InvalidAddress("the address checksum does not match")
    return ss58_format, payload[prefix_length:]


def encode_address(public_key: bytes, ss58_format: int = ROBONOMICS_SS58_FORMAT) -> str:
    """Encode a 32-byte public key (account id) as an SS58 address."""

    if len(public_key) != _PUBLIC_KEY_BYTES:
        raise InvalidAddress(f"a public key is {_PUBLIC_KEY_BYTES} bytes, not {len(public_key)}")
    payload = _prefix(ss58_format) + bytes(public_key)
    return _b58encode(payload + _checksum(payload))


def decode_address(address: str, ss58_format: int | None = None) -> bytes:
    """Return the 32-byte public key behind an address.

    :param ss58_format: when given, an address of any other network is refused.
    """

    actual, public_key = _split(address)
    if ss58_format is not None and actual != ss58_format:
        raise InvalidAddress(f"the address has SS58 format {actual}, expected {ss58_format}")
    return public_key


def address_format(address: str) -> int:
    """The SS58 network format an address is encoded with."""

    return _split(address)[0]


def is_valid_address(address: str, ss58_format: int | None = ROBONOMICS_SS58_FORMAT) -> bool:
    """Whether the text is a valid address of the given format (any format if ``None``)."""

    try:
        decode_address(address, ss58_format)
    except InvalidAddress:
        return False
    return True
