import pytest
from base58 import b58encode

from robonomicsinterface.utils import (
    create_keypair,
    dt_encode_topic,
    ipfs_32_bytes_to_qm_hash,
    ipfs_qm_hash_to_32_bytes,
    str_to_scalebytes,
    web_3_auth,
)

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def test_dt_encode_topic_returns_sha256_hash():
    assert (
        dt_encode_topic("temperature")
        == "0xb314ae60cb741e69f1cc9105ad33b19e34f608c1d2658995d648f385d7b07ac5"
    )


@pytest.mark.parametrize("digest", ["ab" * 32, "0x" + "ab" * 32])
def test_ipfs_hash_round_trip(digest):
    cid = ipfs_32_bytes_to_qm_hash(digest)

    assert cid == "QmZtnFaddFtzGNT8BxdHVbQrhSFdq1pWxud5z4fA4kxfDt"
    assert ipfs_qm_hash_to_32_bytes(cid) == "0x" + "ab" * 32


@pytest.mark.parametrize(
    "digest",
    [
        "ab" * 31,
        "0x" + "ab" * 33,
    ],
)
def test_ipfs_32_bytes_to_qm_hash_rejects_wrong_digest_length(digest):
    with pytest.raises(ValueError, match="32 bytes"):
        ipfs_32_bytes_to_qm_hash(digest)


def test_ipfs_32_bytes_to_qm_hash_rejects_non_hex_digest():
    with pytest.raises(ValueError):
        ipfs_32_bytes_to_qm_hash("zz" * 32)


@pytest.mark.parametrize(
    "cid",
    [
        "Qm",
        b58encode(b"\x13\x20" + b"\xab" * 32).decode("utf-8"),
    ],
)
def test_ipfs_qm_hash_to_32_bytes_rejects_invalid_cid(cid):
    with pytest.raises(ValueError):
        ipfs_qm_hash_to_32_bytes(cid)


@pytest.mark.parametrize(
    ("value", "type_str", "expected"),
    [
        (7, "U32", "0x07000000"),
        (42, "Compact<Balance>", "0xa8"),
        ("0x" + "ab" * 32, "H256", "0x" + "ab" * 32),
    ],
)
def test_str_to_scalebytes_encodes_supported_values(value, type_str, expected):
    assert str(str_to_scalebytes(value, type_str)) == expected


def test_web_3_auth_returns_verifiable_signature():
    """web_3_auth signs the account address and returns the sub-* login."""
    login, signature = web_3_auth("//Alice")
    keypair = create_keypair("//Alice")

    assert login == f"sub-{ALICE_ADDRESS}"
    assert signature.startswith("0x")
    assert keypair.verify(ALICE_ADDRESS, signature)
