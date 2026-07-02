import pytest

from robonomicsinterface.classes.common_functions import CommonFunctions
from robonomicsinterface.exceptions import RPCRequestException

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


def test_get_account_nonce_raises_on_rpc_error(account, service_functions_mock):
    """RPC errors must not be masked as nonce=0."""
    common = _common(account, service_functions_mock)
    error = {"code": -32603, "message": "Internal error"}
    service_functions_mock.rpc_request.return_value = {"error": error}

    with pytest.raises(RPCRequestException) as exc_info:
        common.get_account_nonce("target-address")

    assert exc_info.value.error == error


def test_get_account_nonce_raises_on_missing_result(account, service_functions_mock):
    """A malformed RPC response is not a valid zero nonce."""
    common = _common(account, service_functions_mock)
    service_functions_mock.rpc_request.return_value = {}

    with pytest.raises(RPCRequestException):
        common.get_account_nonce("target-address")


def test_transfer_tokens_uses_keep_alive_transfer_call(
    account, service_functions_mock
):
    """The default transfer wrapper should keep the sender account alive."""
    common = _common(account, service_functions_mock)

    common.transfer_tokens("target-address", 123, nonce=4)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Balances",
        "transfer_keep_alive",
        {"dest": {"Id": "target-address"}, "value": 123},
        4,
    )


def test_transfer_tokens_allow_death_uses_explicit_allow_death_call(
    account, service_functions_mock
):
    """Allow-death transfers should require an explicit wrapper method."""
    common = _common(account, service_functions_mock)

    common.transfer_tokens_allow_death("target-address", 123, nonce=4)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Balances",
        "transfer_allow_death",
        {"dest": {"Id": "target-address"}, "value": 123},
        4,
    )
