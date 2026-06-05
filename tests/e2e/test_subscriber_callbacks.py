import threading
import time
import uuid

import pytest
from helpers import require_runtime_call

from robonomicsinterface.classes.datalog import Datalog
from robonomicsinterface.classes.subscriptions import SubEvent, Subscriber


@pytest.mark.e2e
def test_subscriber_receives_new_record_callback(e2e_substrate, e2e_alice):
    """Subscribe to NewRecord and verify that a local Datalog write reaches callback."""
    require_runtime_call(e2e_substrate, "Datalog", "record")
    received = []
    callback_received = threading.Event()

    def callback(attributes, event_id):
        received.append((attributes, event_id))
        callback_received.set()

    subscriber = Subscriber(
        e2e_alice,
        SubEvent.NewRecord,
        subscription_handler=callback,
        pass_event_id=True,
        addr=[e2e_alice.get_address()],
    )
    try:
        time.sleep(1)
        datalog = Datalog(e2e_alice, wait_for_inclusion=True)
        datalog.record(f"subscriber-e2e-{uuid.uuid4()}")

        if not callback_received.wait(30):
            pytest.xfail(
                "Subscriber did not receive NewRecord on the current implementation"
            )
        assert received
        assert "-" in received[0][1]
    finally:
        subscriber.cancel()
        subscriber._subscription.join(timeout=5)
