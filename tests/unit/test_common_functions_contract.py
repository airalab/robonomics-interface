import pytest

from robonomicsinterface.classes.common_functions import CommonFunctions

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def _common(account, service_functions_mock):
    common = CommonFunctions(account)
    common._service_functions = service_functions_mock
    return common


def test_get_account_info_queries_system_account(account, service_functions_mock):
    common = _common(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = {"nonce": 1}

    assert common.get_account_info(block_hash="0xblock") == {"nonce": 1}
    service_functions_mock.chainstate_query.assert_called_once_with(
        "System",
        "Account",
        ALICE_ADDRESS,
        block_hash="0xblock",
    )


def test_get_account_nonce_uses_system_account_next_index(
    account, service_functions_mock
):
    common = _common(account, service_functions_mock)
    service_functions_mock.rpc_request.return_value = {"result": 9}

    assert common.get_account_nonce("target-address") == 9
    service_functions_mock.rpc_request.assert_called_once_with(
        "system_accountNextIndex",
        ["target-address"],
        result_handler=None,
    )


@pytest.mark.xfail(
    reason="Current runtime exposes Balances.transfer_allow_death, not Balances.transfer"
)
def test_transfer_tokens_uses_current_runtime_transfer_call(
    account, service_functions_mock
):
    """Mark the transfer call name expected by the current Polkadot runtime."""
    common = _common(account, service_functions_mock)

    common.transfer_tokens("target-address", 123, nonce=4)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Balances",
        "transfer_allow_death",
        {"dest": {"Id": "target-address"}, "value": 123},
        4,
    )
