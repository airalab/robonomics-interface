import pytest

from robonomicsinterface import (
    InvalidAddress,
    address_format,
    decode_address,
    encode_address,
    is_valid_address,
)

PUBLIC_KEY = bytes.fromhex("88dc3417d5058ec4b4503e0c12ea1a0a89be200fe98922423d4334014fa6b0ee")
GENERIC = "5FA9nQDVg267DEd8m1ZypXLBnvN7SFxYwV7ndqSYGiN9TTpu"


def test_robonomics_is_the_default_format() -> None:
    address = encode_address(PUBLIC_KEY)
    assert address.startswith("4")
    assert address_format(address) == 32
    assert decode_address(address) == PUBLIC_KEY


def test_known_generic_address() -> None:
    assert encode_address(PUBLIC_KEY, 42) == GENERIC
    assert decode_address(GENERIC) == PUBLIC_KEY


@pytest.mark.parametrize("ss58_format", [0, 2, 32, 42, 63, 64, 255, 2254, 16383])
def test_every_format_round_trips(ss58_format: int) -> None:
    address = encode_address(PUBLIC_KEY, ss58_format)
    assert address_format(address) == ss58_format
    assert decode_address(address, ss58_format) == PUBLIC_KEY


def test_format_check() -> None:
    assert is_valid_address(encode_address(PUBLIC_KEY))
    assert not is_valid_address(GENERIC)
    assert is_valid_address(GENERIC, ss58_format=None)
    with pytest.raises(InvalidAddress, match="format 42"):
        decode_address(GENERIC, 32)


@pytest.mark.parametrize(
    "address",
    ["", "0OIl", GENERIC[:-1], GENERIC[:-1] + "v", GENERIC + "1", "1" * 48],
)
def test_invalid_addresses(address: str) -> None:
    assert not is_valid_address(address, ss58_format=None)
    with pytest.raises(InvalidAddress):
        decode_address(address)


def test_invalid_inputs() -> None:
    with pytest.raises(InvalidAddress):
        encode_address(b"\x00" * 31)
    with pytest.raises(InvalidAddress):
        encode_address(PUBLIC_KEY, 16384)
    assert not is_valid_address(None)  # type: ignore[arg-type]
