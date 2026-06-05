import uuid

import pytest
from helpers import (
    events_from_result,
    has_event,
    record_payload_to_text,
    require_runtime_call,
)

from robonomicsinterface.classes.datalog import Datalog


@pytest.mark.e2e
def test_datalog_record_and_erase(e2e_substrate, e2e_alice):
    """Record a payload, read it back, then erase the local account datalog."""
    require_runtime_call(e2e_substrate, "Datalog", "record")
    require_runtime_call(e2e_substrate, "Datalog", "erase")
    datalog = Datalog(e2e_alice, wait_for_inclusion=True, return_block_num=True)
    payload = f"robonomics-interface-e2e-{uuid.uuid4()}"

    record_result = datalog.record(payload)
    assert has_event(
        events_from_result(e2e_substrate, record_result),
        "Datalog",
        "NewRecord",
    )

    latest = datalog.get_item()
    assert latest is not None
    assert record_payload_to_text(latest[1]) == payload

    erase_result = datalog.erase()
    assert has_event(
        events_from_result(e2e_substrate, erase_result),
        "Datalog",
        "Erased",
    )

    assert datalog.get_item() is None
