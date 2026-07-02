from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from robonomicsinterface.classes.service_functions import ServiceFunctions
from robonomicsinterface.exceptions import AmbiguousExtrinsicSubmissionException


def _successful_receipt():
    return SimpleNamespace(
        extrinsic_hash="0xextrinsic",
        block_hash="0xblock",
        extrinsic_idx=0,
        is_success=True,
        error_message=None,
    )


def test_extrinsic_socket_error_does_not_resubmit(
    account, substrate_interface_mock, monkeypatch
):
    """A retry after submit_extrinsic may submit the same signed call twice."""
    call = object()
    extrinsic = Mock()
    extrinsic.extrinsic_hash = "0xsigned"
    substrate_interface_mock.compose_call.return_value = call
    substrate_interface_mock.create_signed_extrinsic.return_value = extrinsic
    substrate_interface_mock.submit_extrinsic.side_effect = [
        BrokenPipeError("socket closed after submission"),
        _successful_receipt(),
    ]

    def keep_mock_interface(service):
        service.interface = substrate_interface_mock

    monkeypatch.setattr(
        "robonomicsinterface.decorators.open_interface", keep_mock_interface
    )
    service = ServiceFunctions(account, wait_for_inclusion=False)
    service.interface = substrate_interface_mock

    with pytest.raises(AmbiguousExtrinsicSubmissionException) as exc_info:
        service.extrinsic("Datalog", "record", {"record": "hello"})

    assert exc_info.value.extrinsic_hash == "0xsigned"
    substrate_interface_mock.submit_extrinsic.assert_called_once_with(
        extrinsic, wait_for_inclusion=False
    )


def test_chainstate_query_socket_error_retries_once(
    account, substrate_interface_mock, monkeypatch
):
    """Read-only calls may reconnect once and retry after a socket error."""
    substrate_interface_mock.query.side_effect = [
        BrokenPipeError("socket closed before query response"),
        SimpleNamespace(value=42),
    ]
    sleep = Mock()

    def keep_mock_interface(service):
        service.interface = substrate_interface_mock

    monkeypatch.setattr(
        "robonomicsinterface.decorators.open_interface", keep_mock_interface
    )
    monkeypatch.setattr("robonomicsinterface.decorators.sleep", sleep)
    service = ServiceFunctions(account)
    service.interface = substrate_interface_mock

    assert service.chainstate_query("RWS", "AuctionNext") == 42

    sleep.assert_called_once_with(0.2)
    assert substrate_interface_mock.query.call_count == 2
