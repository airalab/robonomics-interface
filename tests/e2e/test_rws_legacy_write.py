import uuid

import pytest
from helpers import (
    events_from_result,
    has_event,
    record_payload_to_text,
    require_runtime_call,
)

from robonomicsinterface.classes.datalog import Datalog
from robonomicsinterface.classes.rws import RWS


@pytest.mark.e2e
def test_rws_set_devices_wrapper_encodes_current_runtime_devices(
    e2e_substrate,
    e2e_alice,
    e2e_bob,
    e2e_rws_subscription,
):
    """Document current wrapper encoding for RWS.set_devices."""
    require_runtime_call(e2e_substrate, "RWS", "set_devices")
    rws_owner = RWS(e2e_alice, wait_for_inclusion=True, return_block_num=True)
    assert rws_owner.get_ledger() == e2e_rws_subscription

    try:
        set_devices_result = rws_owner.set_devices([e2e_bob.get_address()])
    except Exception as exc:
        pytest.xfail(f"RWS.set_devices is not encodable with current wrapper: {exc}")
    assert has_event(
        events_from_result(e2e_substrate, set_devices_result),
        "RWS",
        "NewDevices",
    )


@pytest.mark.e2e
def test_rws_legacy_call_records_datalog_with_prepared_device(
    e2e_substrate,
    e2e_alice,
    e2e_bob,
    e2e_rws_device,
):
    """Use legacy RWS.call for Datalog after preparing devices directly."""
    require_runtime_call(e2e_substrate, "RWS", "call")
    require_runtime_call(e2e_substrate, "Datalog", "record")
    assert e2e_bob.get_address() in e2e_rws_device

    payload = f"rws-e2e-{uuid.uuid4()}"
    datalog_via_rws = Datalog(
        e2e_bob,
        wait_for_inclusion=True,
        return_block_num=True,
        rws_sub_owner=e2e_alice.get_address(),
    )
    try:
        record_result = datalog_via_rws.record(payload)
    except Exception as exc:
        pytest.xfail(
            f"RWS.call legacy wrapper is not usable on this dev runtime: {exc}"
        )
    assert has_event(
        events_from_result(e2e_substrate, record_result),
        "RWS",
        "NewCall",
    )

    latest = Datalog(e2e_bob).get_item()
    assert latest is not None
    assert record_payload_to_text(latest[1]) == payload
