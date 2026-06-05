from unittest.mock import Mock

import pytest
from websocket import WebSocketConnectionClosedException

from robonomicsinterface.classes.subscriptions import SubEvent, Subscriber


def _subscriber(
    subscribed_event=SubEvent.NewRecord,
    handler=None,
    addr=None,
    pass_event_id=False,
):
    subscriber = object.__new__(Subscriber)
    subscriber._subscribed_event = [subscribed_event.value]
    subscriber._subscription_handler = handler or Mock()
    subscriber._pass_event_id = pass_event_id
    subscriber._addr = addr
    subscriber._custom_functions = Mock()
    subscriber._cancel_flag = False
    return subscriber


@pytest.mark.xfail(reason="Subscriber should read System.Events from the event block")
def test_event_callback_queries_events_at_header_block_hash():
    """The callback must not mix a header update with latest System.Events."""
    subscriber = _subscriber()
    subscriber._custom_functions.chainstate_query.return_value = []

    subscriber._event_callback(
        {"header": {"number": 42, "hash": "0xblock"}},
        update_nr=1,
        subscription_id=1,
    )

    subscriber._custom_functions.chainstate_query.assert_called_once_with(
        "System",
        "Events",
        block_hash="0xblock",
    )


@pytest.mark.xfail(
    reason="Subscriber event IDs should use event indexes, not extrinsic indexes"
)
def test_event_callback_passes_unique_event_ids_for_same_extrinsic():
    """Several events in one extrinsic need distinct callback event IDs."""
    handler = Mock()
    subscriber = _subscriber(handler=handler, pass_event_id=True)
    subscriber._custom_functions.chainstate_query.return_value = [
        {
            "event_id": "NewRecord",
            "attributes": ["robot-address", "first"],
            "extrinsic_idx": 7,
            "event_idx": 0,
        },
        {
            "event_id": "NewRecord",
            "attributes": ["robot-address", "second"],
            "extrinsic_idx": 7,
            "event_idx": 1,
        },
    ]

    subscriber._event_callback(
        {"header": {"number": 42, "hash": "0xblock"}},
        update_nr=1,
        subscription_id=1,
    )

    assert [call.args[1] for call in handler.call_args_list] == ["42-0", "42-1"]


@pytest.mark.xfail(
    reason="Liability events should be filterable by promisee or promisor address"
)
def test_liability_event_matches_nested_party_address():
    """NewLiability attributes are nested, not a flat transfer-like tuple."""
    handler = Mock()
    subscriber = _subscriber(
        subscribed_event=SubEvent.NewLiability,
        handler=handler,
        addr="promisee-address",
    )
    subscriber._custom_functions.chainstate_query.return_value = [
        {
            "event_id": "NewLiability",
            "attributes": {
                "index": 7,
                "agreement": {
                    "promisee": "promisee-address",
                    "promisor": "promisor-address",
                },
            },
            "extrinsic_idx": 3,
            "event_idx": 0,
        }
    ]

    subscriber._event_callback(
        {"header": {"number": 42, "hash": "0xblock"}},
        update_nr=1,
        subscription_id=1,
    )

    handler.assert_called_once()


@pytest.mark.xfail(reason="Subscriber address filtering should use exact matches")
def test_target_address_filter_does_not_use_substring_matching():
    """Address filtering must not match short strings inside another address."""
    subscriber = _subscriber(addr="robot-address")

    assert (
        subscriber._target_address_in_event(
            {"event_id": "NewRecord", "attributes": ["bot", "payload"]}
        )
        is False
    )


@pytest.mark.xfail(reason="Cancelled subscribers should not reconnect recursively")
def test_subscribe_event_does_not_reconnect_after_cancel():
    """A closed socket after cancel should stop instead of starting a new loop."""
    subscriber = _subscriber()
    subscriber._cancel_flag = True
    subscriber._custom_functions.subscribe_block_headers.side_effect = [
        WebSocketConnectionClosedException("closed"),
        None,
    ]

    subscriber._subscribe_event()

    subscriber._custom_functions.subscribe_block_headers.assert_called_once_with(
        subscriber._event_callback
    )
