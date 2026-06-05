import pytest
from helpers import events_from_result, has_event, require_runtime_call

from robonomicsinterface.classes.digital_twin import DigitalTwin
from robonomicsinterface.exceptions import DigitalTwinMapException


@pytest.mark.e2e
def test_digital_twin_create_and_set_source(e2e_substrate, e2e_alice, e2e_bob):
    """Create a Digital Twin and attach a source address to one topic."""
    require_runtime_call(e2e_substrate, "DigitalTwin", "create")
    require_runtime_call(e2e_substrate, "DigitalTwin", "set_source")
    digital_twin = DigitalTwin(
        e2e_alice,
        wait_for_inclusion=True,
        return_block_num=True,
    )

    digital_twin_id, create_result = digital_twin.create()
    assert has_event(
        events_from_result(e2e_substrate, create_result),
        "DigitalTwin",
        "NewDigitalTwin",
    )

    topic_hash, set_source_result = digital_twin.set_source(
        digital_twin_id,
        "temperature",
        e2e_bob.get_address(),
    )
    assert has_event(
        events_from_result(e2e_substrate, set_source_result),
        "DigitalTwin",
        "TopicChanged",
    )

    assert digital_twin.get_owner(digital_twin_id) == e2e_alice.get_address()
    assert digital_twin.get_source(digital_twin_id, topic_hash) == e2e_bob.get_address()


@pytest.mark.e2e
def test_digital_twin_remove_source(e2e_substrate, e2e_alice, e2e_bob):
    """Document the future remove_source e2e scenario until the wrapper exists."""
    require_runtime_call(e2e_substrate, "DigitalTwin", "remove_source")
    digital_twin = DigitalTwin(
        e2e_alice,
        wait_for_inclusion=True,
        return_block_num=True,
    )
    if not hasattr(digital_twin, "remove_source"):
        pytest.xfail("DigitalTwin.remove_source wrapper is not implemented yet")

    digital_twin_id, _ = digital_twin.create()
    topic_hash, _ = digital_twin.set_source(
        digital_twin_id,
        "temperature",
        e2e_bob.get_address(),
    )

    remove_result = digital_twin.remove_source(
        digital_twin_id,
        topic_hash,
        e2e_bob.get_address(),
    )
    assert has_event(
        events_from_result(e2e_substrate, remove_result),
        "DigitalTwin",
        "TopicChanged",
    )

    with pytest.raises(DigitalTwinMapException):
        digital_twin.get_source(digital_twin_id, topic_hash)
