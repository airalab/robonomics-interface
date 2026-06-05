import pytest

from robonomicsinterface.classes.account import Account
from robonomicsinterface.classes.liability import Liability
from robonomicsinterface.exceptions import NoPrivateKeyException
from robonomicsinterface.utils import ipfs_32_bytes_to_qm_hash, str_to_scalebytes

PAYLOAD_HASH = "0x" + "ab" * 32


def test_sign_liability_returns_verifiable_signature(account):
    """sign_liability signs the SCALE payload hash and compact price."""
    liability = Liability(account)
    encoded_payload = str_to_scalebytes(PAYLOAD_HASH, "H256") + str_to_scalebytes(
        42, "Compact<Balance>"
    )

    signature = liability.sign_liability(PAYLOAD_HASH, 42)

    assert signature.startswith("0x")
    assert account.keypair.verify(encoded_payload, signature)


def test_sign_liability_accepts_ipfs_hash(account):
    liability = Liability(account)
    encoded_payload = str_to_scalebytes(PAYLOAD_HASH, "H256") + str_to_scalebytes(
        42, "Compact<Balance>"
    )

    signature = liability.sign_liability(ipfs_32_bytes_to_qm_hash(PAYLOAD_HASH), 42)

    assert account.keypair.verify(encoded_payload, signature)


def test_sign_liability_requires_private_key():
    liability = Liability(Account())

    with pytest.raises(NoPrivateKeyException):
        liability.sign_liability(PAYLOAD_HASH, 42)


def test_sign_report_returns_verifiable_signature(account):
    """sign_report signs the SCALE liability index and payload hash."""
    liability = Liability(account)
    encoded_payload = str_to_scalebytes(7, "U32") + str_to_scalebytes(
        PAYLOAD_HASH, "H256"
    )

    signature = liability.sign_report(7, PAYLOAD_HASH)

    assert signature.startswith("0x")
    assert account.keypair.verify(encoded_payload, signature)


def test_sign_report_accepts_ipfs_hash(account):
    liability = Liability(account)
    encoded_payload = str_to_scalebytes(7, "U32") + str_to_scalebytes(
        PAYLOAD_HASH, "H256"
    )

    signature = liability.sign_report(7, ipfs_32_bytes_to_qm_hash(PAYLOAD_HASH))

    assert account.keypair.verify(encoded_payload, signature)


def test_sign_report_requires_private_key():
    liability = Liability(Account())

    with pytest.raises(NoPrivateKeyException):
        liability.sign_report(7, PAYLOAD_HASH)
