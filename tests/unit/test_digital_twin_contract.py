import pytest

from robonomicsinterface.classes.digital_twin import DigitalTwin
from robonomicsinterface.exceptions import DigitalTwinMapException
from robonomicsinterface.utils import dt_encode_topic

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def _digital_twin(account, service_functions_mock):
    digital_twin = DigitalTwin(account)
    digital_twin._service_functions = service_functions_mock
    return digital_twin


def test_get_info_queries_digital_twin_storage(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)

    digital_twin.get_info(7, block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "DigitalTwin",
        "DigitalTwin",
        7,
        block_hash="0xblock",
    )


def test_get_owner_queries_owner_storage(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)

    digital_twin.get_owner(7, block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "DigitalTwin",
        "Owner",
        7,
        block_hash="0xblock",
    )


def test_get_total_queries_total_storage(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)

    digital_twin.get_total(block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "DigitalTwin",
        "Total",
        block_hash="0xblock",
    )


def test_get_source_returns_matching_source(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)
    topic_hash = dt_encode_topic("temperature")
    service_functions_mock.chainstate_query.return_value = [
        (topic_hash, "source-address")
    ]

    assert (
        digital_twin.get_source(7, "temperature", block_hash="0xblock")
        == "source-address"
    )
    service_functions_mock.chainstate_query.assert_called_once_with(
        "DigitalTwin",
        "DigitalTwin",
        7,
        block_hash="0xblock",
    )


def test_get_source_raises_when_map_is_empty(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = None

    with pytest.raises(DigitalTwinMapException):
        digital_twin.get_source(7, "temperature")


def test_get_source_raises_when_topic_is_missing(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = [
        (dt_encode_topic("humidity"), "source-address")
    ]

    with pytest.raises(DigitalTwinMapException):
        digital_twin.get_source(7, "temperature")


def test_create_submits_create_and_scans_owner(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)
    service_functions_mock.extrinsic.return_value = "0xhash"
    service_functions_mock.chainstate_query.side_effect = [
        3,
        "other-owner",
        ALICE_ADDRESS,
    ]

    assert digital_twin.create(nonce=5) == (1, "0xhash")
    service_functions_mock.extrinsic.assert_called_once_with(
        "DigitalTwin", "create", nonce=5
    )
    assert service_functions_mock.chainstate_query.call_args_list[0].args == (
        "DigitalTwin",
        "Total",
    )
    assert service_functions_mock.chainstate_query.call_args_list[1].args == (
        "DigitalTwin",
        "Owner",
        2,
    )
    assert service_functions_mock.chainstate_query.call_args_list[2].args == (
        "DigitalTwin",
        "Owner",
        1,
    )


def test_set_source_submits_hashed_topic(account, service_functions_mock):
    digital_twin = _digital_twin(account, service_functions_mock)
    service_functions_mock.extrinsic.return_value = "0xhash"
    topic_hash = dt_encode_topic("temperature")

    assert digital_twin.set_source(7, "temperature", "source-address", nonce=5) == (
        topic_hash,
        "0xhash",
    )
    service_functions_mock.extrinsic.assert_called_once_with(
        "DigitalTwin",
        "set_source",
        {"id": 7, "topic": topic_hash, "source": "source-address"},
        nonce=5,
    )
