from unittest.mock import Mock

import pytest

from robonomicsinterface.classes.common_functions import CommonFunctions


def _common(account, service_functions):
    common = CommonFunctions(account)
    common._service_functions = service_functions
    return common


@pytest.mark.xfail(
    reason="Current runtime exposes Balances.transfer_allow_death, not Balances.transfer"
)
def test_transfer_tokens_uses_transfer_allow_death(account, service_functions_mock):
    """Regression guard for the Polkadot Balances transfer call name."""
    common = _common(account, service_functions_mock)

    common.transfer_tokens("target-address", 123, nonce=4)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Balances",
        "transfer_allow_death",
        {"dest": {"Id": "target-address"}, "value": 123},
        4,
    )


@pytest.mark.xfail(
    reason="Nonce lookup should delegate to substrate-interface nonce handling"
)
def test_get_account_nonce_uses_service_nonce_helper(account):
    """substrate-interface can use AccountNonceApi instead of a raw legacy RPC."""
    service_functions = Mock()
    service_functions.get_account_nonce.return_value = 9
    common = _common(account, service_functions)

    assert common.get_account_nonce("target-address") == 9
    service_functions.get_account_nonce.assert_called_once_with("target-address")
    service_functions.rpc_request.assert_not_called()
