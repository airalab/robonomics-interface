from types import SimpleNamespace

import pytest

from robonomicsinterface.classes.service_functions import ServiceFunctions


def _successful_receipt():
    return SimpleNamespace(
        extrinsic_hash="0xextrinsic",
        block_hash="0xblock",
        extrinsic_idx=0,
        is_success=True,
        error_message=None,
    )


@pytest.mark.xfail(
    reason="Extrinsic submission must not be retried after a socket error"
)
def test_extrinsic_socket_error_does_not_resubmit(
    account, substrate_interface_mock, monkeypatch
):
    """A retry after submit_extrinsic may submit the same signed call twice."""
    call = object()
    extrinsic = object()
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

    with pytest.raises(BrokenPipeError):
        service.extrinsic("Datalog", "record", {"record": "hello"})

    substrate_interface_mock.submit_extrinsic.assert_called_once_with(
        extrinsic, wait_for_inclusion=False
    )
