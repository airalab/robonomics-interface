import pytest

from robonomicsinterface.classes.chain_utils import ChainUtils
from robonomicsinterface.classes.liability import Liability
from robonomicsinterface.exceptions import InvalidExtrinsicHash
from robonomicsinterface.utils import (
    ipfs_32_bytes_to_qm_hash,
    ipfs_qm_hash_to_32_bytes,
)

PAYLOAD_HASH = "0x" + "ab" * 32


def test_hash_validation_accepts_32_byte_hex_hash():
    ChainUtils._check_hash_valid("0x" + "aB" * 32)


@pytest.mark.parametrize(
    "value",
    [
        "ab" * 32,
        "0x" + "ab" * 31,
        "0x" + "ab" * 33,
        None,
    ],
)
def test_hash_validation_rejects_wrong_hash_shape(value):
    with pytest.raises(InvalidExtrinsicHash):
        ChainUtils._check_hash_valid(value)


def test_hash_validation_rejects_non_hex_hash():
    """A 66-character string is not enough; the payload must be hex."""
    with pytest.raises(InvalidExtrinsicHash):
        ChainUtils._check_hash_valid("0x" + "zz" * 32)


def test_ipfs_32_bytes_to_qm_hash_rejects_wrong_digest_length():
    """A digest with 31 bytes must not be accepted as a valid content hash."""
    with pytest.raises(ValueError):
        ipfs_32_bytes_to_qm_hash("0x" + "ab" * 31)


def test_ipfs_qm_hash_to_32_bytes_rejects_invalid_cid():
    """A short Qm-like string is not a valid sha2-256 IPFS CID."""
    with pytest.raises(ValueError):
        ipfs_qm_hash_to_32_bytes("Qm")


def test_liability_create_rejects_unknown_crypto_type(account):
    """Unknown crypto type integers should not surface as IndexError."""
    liability = Liability(account)

    with pytest.raises(ValueError):
        liability.create(
            PAYLOAD_HASH,
            1000,
            "promisee-address",
            "promisor-address",
            "promisee-signature",
            "promisor-signature",
            promisee_signature_crypto_type=99,
        )
