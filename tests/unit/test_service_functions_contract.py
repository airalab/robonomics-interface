from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from substrateinterface.exceptions import ExtrinsicFailedException

from robonomicsinterface.classes.account import Account
from robonomicsinterface.classes.service_functions import ServiceFunctions
from robonomicsinterface.exceptions import NoPrivateKeyException


def _service(
    account,
    interface,
    wait_for_inclusion=True,
    return_block_num=False,
    rws_sub_owner=None,
):
    service = ServiceFunctions(
        account,
        wait_for_inclusion=wait_for_inclusion,
        return_block_num=return_block_num,
        rws_sub_owner=rws_sub_owner,
    )
    service.interface = interface
    return service


def _successful_receipt(
    extrinsic_hash="0xextrinsic", block_hash="0xblock", extrinsic_idx=3
):
    return SimpleNamespace(
        extrinsic_hash=extrinsic_hash,
        block_hash=block_hash,
        extrinsic_idx=extrinsic_idx,
        is_success=True,
        error_message=None,
    )


def test_chainstate_query_wraps_params_and_returns_value(
    account, substrate_interface_mock
):
    """Wrap the single storage key into substrate-interface's params list."""
    substrate_interface_mock.query.return_value = SimpleNamespace(value={"nonce": 1})
    service = _service(account, substrate_interface_mock)
    handler = Mock()

    result = service.chainstate_query(
        "System",
        "Account",
        "target-address",
        block_hash="0xblock",
        subscription_handler=handler,
    )

    assert result == {"nonce": 1}
    substrate_interface_mock.query.assert_called_once_with(
        "System",
        "Account",
        ["target-address"],
        block_hash="0xblock",
        subscription_handler=handler,
    )


def test_chainstate_query_passes_none_params(account, substrate_interface_mock):
    substrate_interface_mock.query.return_value = SimpleNamespace(value=42)
    service = _service(account, substrate_interface_mock)

    assert service.chainstate_query("RWS", "AuctionNext") == 42
    substrate_interface_mock.query.assert_called_once_with(
        "RWS",
        "AuctionNext",
        None,
        block_hash=None,
        subscription_handler=None,
    )


def test_rpc_request_delegates_to_interface(account, substrate_interface_mock):
    substrate_interface_mock.rpc_request.return_value = {"result": 7}
    service = _service(account, substrate_interface_mock)
    handler = Mock()

    assert service.rpc_request("system_accountNextIndex", ["addr"], handler) == {
        "result": 7
    }
    substrate_interface_mock.rpc_request.assert_called_once_with(
        "system_accountNextIndex", ["addr"], handler
    )


def test_subscribe_block_headers_delegates_to_interface(
    account, substrate_interface_mock
):
    substrate_interface_mock.subscribe_block_headers.return_value = {
        "subscription_id": 1
    }
    service = _service(account, substrate_interface_mock)
    handler = Mock()

    assert service.subscribe_block_headers(handler) == {"subscription_id": 1}
    substrate_interface_mock.subscribe_block_headers.assert_called_once_with(
        subscription_handler=handler
    )


def test_extrinsic_composes_signs_and_submits_without_waiting(
    account, substrate_interface_mock
):
    """Document the normal extrinsic pipeline: compose, sign, submit."""
    call = Mock(name="call")
    extrinsic = Mock(name="extrinsic")
    substrate_interface_mock.compose_call.return_value = call
    substrate_interface_mock.create_signed_extrinsic.return_value = extrinsic
    substrate_interface_mock.submit_extrinsic.return_value = _successful_receipt()
    service = _service(account, substrate_interface_mock, wait_for_inclusion=False)

    result = service.extrinsic("Datalog", "record", {"record": "hello"}, nonce=5)

    assert result == "0xextrinsic"
    substrate_interface_mock.compose_call.assert_called_once_with(
        call_module="Datalog",
        call_function="record",
        call_params={"record": "hello"},
    )
    substrate_interface_mock.create_signed_extrinsic.assert_called_once_with(
        call=call,
        keypair=account.keypair,
        nonce=5,
    )
    substrate_interface_mock.submit_extrinsic.assert_called_once_with(
        extrinsic, wait_for_inclusion=False
    )


def test_extrinsic_returns_block_event_id_when_requested(
    account, substrate_interface_mock
):
    """Keep the current return_block_num contract visible for future fixes."""
    substrate_interface_mock.compose_call.return_value = Mock(name="call")
    substrate_interface_mock.create_signed_extrinsic.return_value = Mock(
        name="extrinsic"
    )
    substrate_interface_mock.submit_extrinsic.return_value = _successful_receipt(
        extrinsic_hash="0xhash"
    )
    substrate_interface_mock.get_block_number.return_value = 100
    service = _service(
        account,
        substrate_interface_mock,
        wait_for_inclusion=True,
        return_block_num=True,
    )

    assert service.extrinsic("Launch", "launch", {"robot": "robot", "param": "ON"}) == (
        "0xhash",
        "100-3",
    )
    substrate_interface_mock.get_block_number.assert_called_once_with("0xblock")


def test_extrinsic_raises_when_receipt_failed(account, substrate_interface_mock):
    substrate_interface_mock.compose_call.return_value = Mock(name="call")
    substrate_interface_mock.create_signed_extrinsic.return_value = Mock(
        name="extrinsic"
    )
    substrate_interface_mock.submit_extrinsic.return_value = SimpleNamespace(
        extrinsic_hash="0xhash",
        is_success=False,
        error_message="BadOrigin",
    )
    service = _service(account, substrate_interface_mock)

    with pytest.raises(ExtrinsicFailedException):
        service.extrinsic("Datalog", "record", {"record": "hello"})


def test_extrinsic_requires_private_key(substrate_interface_mock):
    service = _service(Account(), substrate_interface_mock)

    with pytest.raises(NoPrivateKeyException):
        service.extrinsic("Datalog", "record", {"record": "hello"})


def test_extrinsic_wraps_call_in_legacy_rws_call(account, substrate_interface_mock):
    """Legacy RWS mode wraps the original call into RWS.call before signing."""
    call = Mock(name="rws-call")
    substrate_interface_mock.compose_call.return_value = call
    substrate_interface_mock.create_signed_extrinsic.return_value = Mock(
        name="extrinsic"
    )
    substrate_interface_mock.submit_extrinsic.return_value = _successful_receipt()
    service = _service(
        account,
        substrate_interface_mock,
        wait_for_inclusion=False,
        rws_sub_owner="sub-owner",
    )

    assert (
        service.extrinsic("Datalog", "record", {"record": "hello"}, nonce=8)
        == "0xextrinsic"
    )
    substrate_interface_mock.compose_call.assert_called_once_with(
        call_module="RWS",
        call_function="call",
        call_params={
            "subscription_id": "sub-owner",
            "call": {
                "call_module": "Datalog",
                "call_function": "record",
                "call_args": {"record": "hello"},
            },
        },
    )
    substrate_interface_mock.create_signed_extrinsic.assert_called_once_with(
        call=call,
        keypair=account.keypair,
        nonce=8,
    )
