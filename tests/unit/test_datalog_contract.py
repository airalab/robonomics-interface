import pytest

from robonomicsinterface.classes.datalog import Datalog

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def _datalog(account, service_functions_mock):
    datalog = Datalog(account)
    datalog._service_functions = service_functions_mock
    return datalog


def test_get_index_queries_datalog_index(account, service_functions_mock):
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = {"start": 0, "end": 1}

    assert datalog.get_index(block_hash="0xblock") == {"start": 0, "end": 1}
    service_functions_mock.chainstate_query.assert_called_once_with(
        "Datalog",
        "DatalogIndex",
        ALICE_ADDRESS,
        block_hash="0xblock",
    )


def test_get_item_with_explicit_zero_index_queries_datalog_item(
    account, service_functions_mock
):
    """Guard against treating index=0 as a request for the latest item."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = (123, "payload")

    assert datalog.get_item(index=0, block_hash="0xblock") == (123, "payload")
    service_functions_mock.chainstate_query.assert_called_once_with(
        "Datalog",
        "DatalogItem",
        [ALICE_ADDRESS, 0],
        block_hash="0xblock",
    )


def test_get_item_returns_none_for_empty_record(account, service_functions_mock):
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = (0, "")

    assert datalog.get_item(index=7) is None


def test_get_item_latest_uses_end_minus_one(account, service_functions_mock):
    """For ordinary indexes, latest is still the previous end slot."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.side_effect = [
        {"start": 0, "end": 3},
        (123, "payload"),
    ]
    service_functions_mock.get_constant.return_value = 128

    assert datalog.get_item() == (123, "payload")
    service_functions_mock.get_constant.assert_called_once_with(
        "Datalog",
        "WindowSize",
        block_hash=None,
    )
    assert service_functions_mock.chainstate_query.call_args_list[0].args == (
        "Datalog",
        "DatalogIndex",
        ALICE_ADDRESS,
    )
    assert service_functions_mock.chainstate_query.call_args_list[1].args == (
        "Datalog",
        "DatalogItem",
        [ALICE_ADDRESS, 2],
    )


def test_get_item_latest_forwards_block_hash_to_index_query(
    account, service_functions_mock
):
    """Historical latest lookup must read index and item from the same block."""
    datalog = _datalog(account, service_functions_mock)
    service_functions_mock.chainstate_query.side_effect = [
        {"start": 0, "end": 3},
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


def test_record_submits_datalog_record(account, service_functions_mock):
    datalog = _datalog(account, service_functions_mock)

    datalog.record("hello", nonce=5)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Datalog", "record", {"record": "hello"}, 5
    )


def test_erase_submits_datalog_erase_without_nonce(account, service_functions_mock):
    datalog = _datalog(account, service_functions_mock)

    datalog.erase()

    service_functions_mock.extrinsic.assert_called_once_with("Datalog", "erase", None)


@pytest.mark.xfail(
    reason="Datalog.erase passes nonce as params instead of the nonce argument"
)
def test_erase_submits_datalog_erase_with_nonce(account, service_functions_mock):
    """Nonce belongs to the extrinsic kwargs, not to Datalog.erase params."""
    datalog = _datalog(account, service_functions_mock)

    datalog.erase(nonce=5)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Datalog", "erase", nonce=5
    )
