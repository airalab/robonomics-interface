from robonomicsinterface.classes.datalog import Datalog

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def _datalog(account, service_functions_mock):
    datalog = Datalog(account)
    datalog._service_functions = service_functions_mock
    return datalog


def test_get_item_index_zero_does_not_read_latest_index(
    account, service_functions_mock
):
    """index=0 is a real Datalog item index, not a false-y latest marker."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = (123, "first")

    assert datalog.get_item(index=0) == (123, "first")
    service_functions_mock.chainstate_query.assert_called_once_with(
        "Datalog",
        "DatalogItem",
        [ALICE_ADDRESS, 0],
        block_hash=None,
    )


def test_get_item_latest_returns_none_when_end_is_zero(account, service_functions_mock):
    """An empty Datalog index must not query DatalogItem."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = {"start": 0, "end": 0}

    assert datalog.get_item() is None
    service_functions_mock.chainstate_query.assert_called_once_with(
        "Datalog",
        "DatalogIndex",
        ALICE_ADDRESS,
        block_hash=None,
    )
    service_functions_mock.get_constant.assert_not_called()


def test_get_item_latest_wraps_when_end_is_zero_after_ring_turn(
    account, service_functions_mock
):
    """A non-empty ring buffer with end=0 has latest item at WindowSize - 1."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.side_effect = [
        {"start": 1, "end": 0},
        (123, "wrapped"),
    ]
    service_functions_mock.get_constant.return_value = 128

    assert datalog.get_item() == (123, "wrapped")

    service_functions_mock.get_constant.assert_called_once_with(
        "Datalog",
        "WindowSize",
        block_hash=None,
    )
    service_functions_mock.chainstate_query.assert_any_call(
        "Datalog",
        "DatalogItem",
        [ALICE_ADDRESS, 127],
        block_hash=None,
    )


def test_get_item_latest_uses_historical_block_for_index(
    account, service_functions_mock
):
    """Index and item must be selected from the same historical chain state."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.side_effect = [
        {"start": 0, "end": 2},
        (123, "payload"),
    ]
    service_functions_mock.get_constant.return_value = 128

    datalog.get_item(block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_any_call(
        "Datalog",
        "DatalogIndex",
        ALICE_ADDRESS,
        block_hash="0xblock",
    )
    service_functions_mock.get_constant.assert_called_once_with(
        "Datalog",
        "WindowSize",
        block_hash="0xblock",
    )
