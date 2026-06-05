from substrateinterface import KeypairType

from robonomicsinterface.classes.liability import Liability
from robonomicsinterface.utils import ipfs_32_bytes_to_qm_hash

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"
PAYLOAD_HASH = "0x" + "ab" * 32


def _liability(account, service_functions_mock):
    liability = Liability(account)
    liability._service_functions = service_functions_mock
    return liability


def test_get_agreement_queries_agreement_of(account, service_functions_mock):
    liability = _liability(account, service_functions_mock)

    liability.get_agreement(7, block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "Liability",
        "AgreementOf",
        7,
        block_hash="0xblock",
    )


def test_get_latest_index_queries_next_index(account, service_functions_mock):
    liability = _liability(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = 8

    assert liability.get_latest_index(block_hash="0xblock") == 7
    service_functions_mock.chainstate_query.assert_called_once_with(
        "Liability",
        "NextIndex",
        block_hash="0xblock",
    )


def test_get_latest_index_returns_none_when_no_liabilities(
    account, service_functions_mock
):
    liability = _liability(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = 0

    assert liability.get_latest_index() is None


def test_get_report_queries_report_of(account, service_functions_mock):
    liability = _liability(account, service_functions_mock)

    liability.get_report(7, block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "Liability",
        "ReportOf",
        7,
        block_hash="0xblock",
    )


def test_create_submits_liability_create_params_and_returns_matched_index(
    account, service_functions_mock
):
    """create returns the index whose stored agreement matches the signature."""
    liability = _liability(account, service_functions_mock)
    service_functions_mock.extrinsic.return_value = "0xhash"
    service_functions_mock.chainstate_query.side_effect = [
        3,
        {"promisee_signature": {"Sr25519": "other-signature"}},
        {"promisee_signature": {"Sr25519": "promisee-signature"}},
    ]

    assert liability.create(
        PAYLOAD_HASH,
        1000,
        "promisee-address",
        "promisor-address",
        "promisee-signature",
        "promisor-signature",
        nonce=5,
    ) == (1, "0xhash")
    service_functions_mock.extrinsic.assert_called_once_with(
        "Liability",
        "create",
        {
            "agreement": {
                "technics": {"hash": PAYLOAD_HASH},
                "economics": {"price": 1000},
                "promisee": "promisee-address",
                "promisor": "promisor-address",
                "promisee_signature": {"Sr25519": "promisee-signature"},
                "promisor_signature": {"Sr25519": "promisor-signature"},
            }
        },
        nonce=5,
    )


def test_create_converts_ipfs_hash_and_crypto_variants(account, service_functions_mock):
    liability = _liability(account, service_functions_mock)
    service_functions_mock.extrinsic.return_value = "0xhash"
    service_functions_mock.chainstate_query.return_value = 0

    liability.create(
        ipfs_32_bytes_to_qm_hash(PAYLOAD_HASH),
        1000,
        "promisee-address",
        "promisor-address",
        "promisee-signature",
        "promisor-signature",
        promisee_signature_crypto_type=KeypairType.ED25519,
        promisor_signature_crypto_type=KeypairType.ECDSA,
    )

    params = service_functions_mock.extrinsic.call_args.args[2]
    assert params["agreement"]["technics"] == {"hash": PAYLOAD_HASH}
    assert params["agreement"]["promisee_signature"] == {
        "Ed25519": "promisee-signature"
    }
    assert params["agreement"]["promisor_signature"] == {"Ecdsa": "promisor-signature"}


def test_finalize_submits_report_params_with_provided_signature(
    account, service_functions_mock
):
    liability = _liability(account, service_functions_mock)

    liability.finalize(
        7,
        PAYLOAD_HASH,
        promisor="promisor-address",
        promisor_signature_crypto_type=KeypairType.ECDSA,
        promisor_finalize_signature="report-signature",
        nonce=5,
    )

    service_functions_mock.extrinsic.assert_called_once_with(
        "Liability",
        "finalize",
        {
            "report": {
                "index": 7,
                "sender": "promisor-address",
                "payload": {"hash": PAYLOAD_HASH},
                "signature": {"Ecdsa": "report-signature"},
            }
        },
        nonce=5,
    )


def test_finalize_uses_account_address_and_generated_signature(
    account, service_functions_mock
):
    """finalize defaults to the account address and generates a report signature."""
    liability = _liability(account, service_functions_mock)

    liability.finalize(7, PAYLOAD_HASH)

    params = service_functions_mock.extrinsic.call_args.args[2]
    assert service_functions_mock.extrinsic.call_args.args[:2] == (
        "Liability",
        "finalize",
    )
    assert params["report"]["index"] == 7
    assert params["report"]["sender"] == ALICE_ADDRESS
    assert params["report"]["payload"] == {"hash": PAYLOAD_HASH}
    assert params["report"]["signature"]["Sr25519"].startswith("0x")
