import pytest
from helpers import HASH_A, events_from_result, has_event, require_runtime_call

from robonomicsinterface.classes.launch import Launch


@pytest.mark.e2e
def test_launch_extrinsic_emits_new_launch(e2e_substrate, e2e_alice, e2e_bob):
    """Submit Launch.launch and verify that the runtime emitted NewLaunch."""
    require_runtime_call(e2e_substrate, "Launch", "launch")
    launch = Launch(e2e_alice, wait_for_inclusion=True, return_block_num=True)

    result = launch.launch(e2e_bob.get_address(), HASH_A)
    events = events_from_result(e2e_substrate, result)

    assert has_event(events, "Launch", "NewLaunch")
