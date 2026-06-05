import pytest

from robonomicsinterface.classes.rws import RWS

ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def _rws(account, service_functions_mock):
    rws = RWS(account)
    rws._service_functions = service_functions_mock
    return rws


def test_get_auction_queries_auction(account, service_functions_mock):
    rws = _rws(account, service_functions_mock)

    rws.get_auction(3, block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS", "Auction", 3, block_hash="0xblock"
    )


def test_get_auction_next_queries_auction_next(account, service_functions_mock):
    rws = _rws(account, service_functions_mock)

    rws.get_auction_next(block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS", "AuctionNext", block_hash="0xblock"
    )


def test_get_auction_queue_queries_auction_queue(account, service_functions_mock):
    rws = _rws(account, service_functions_mock)

    rws.get_auction_queue(block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS", "AuctionQueue", block_hash="0xblock"
    )


def test_get_devices_queries_devices_for_default_account(
    account, service_functions_mock
):
    rws = _rws(account, service_functions_mock)

    rws.get_devices(block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS",
        "Devices",
        ALICE_ADDRESS,
        block_hash="0xblock",
    )


def test_get_ledger_queries_ledger(account, service_functions_mock):
    rws = _rws(account, service_functions_mock)

    rws.get_ledger(addr="owner-address", block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS",
        "Ledger",
        "owner-address",
        block_hash="0xblock",
    )


def test_is_in_sub_checks_devices(account, service_functions_mock):
    rws = _rws(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = [ALICE_ADDRESS]

    assert rws.is_in_sub("owner-address", block_hash="0xblock") is True
    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS",
        "Devices",
        "owner-address",
        block_hash="0xblock",
    )


@pytest.mark.xfail(
    reason="RWS.is_in_sub should treat missing Devices storage as an empty list"
)
def test_is_in_sub_returns_false_when_devices_missing(account, service_functions_mock):
    """Missing Devices storage should behave like an empty device list."""
    rws = _rws(account, service_functions_mock)
    service_functions_mock.chainstate_query.return_value = None

    assert rws.is_in_sub("owner-address") is False


def test_bid_submits_rws_bid(account, service_functions_mock):
    rws = _rws(account, service_functions_mock)

    rws.bid(2, 1000)

    service_functions_mock.extrinsic.assert_called_once_with(
        "RWS", "bid", {"index": 2, "amount": 1000}
    )


def test_set_devices_submits_plain_devices_list(account, service_functions_mock):
    """The wrapper passes devices as params; substrate-interface encodes SCALE."""
    rws = _rws(account, service_functions_mock)
    devices = ["device-one", "device-two"]

    rws.set_devices(devices)

    service_functions_mock.extrinsic.assert_called_once_with(
        "RWS", "set_devices", {"devices": devices}
    )
