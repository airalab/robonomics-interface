import pytest

from robonomicsinterface.classes.rws import RWS

NOW_MS = 1_700_000_000_000
DAY_MS = 86_400_000


def _rws_with_ledger(account, service_functions_mock, monkeypatch, ledger):
    rws = RWS(account)
    rws._service_functions = service_functions_mock
    service_functions_mock.chainstate_query.return_value = ledger
    monkeypatch.setattr(
        "robonomicsinterface.classes.rws.time.time", lambda: NOW_MS / 1000
    )
    return rws


def test_get_days_left_returns_false_without_subscription(
    account, service_functions_mock, monkeypatch
):
    rws = _rws_with_ledger(account, service_functions_mock, monkeypatch, None)

    assert rws.get_days_left() is False


def test_get_days_left_returns_minus_one_for_lifetime_subscription(
    account, service_functions_mock, monkeypatch
):
    rws = _rws_with_ledger(
        account, service_functions_mock, monkeypatch, {"kind": {"Lifetime": None}}
    )

    assert rws.get_days_left() == -1


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1.0, 1),
        (0.5, 1),
    ],
)
def test_get_days_left_rounds_positive_days_up(
    account, service_functions_mock, monkeypatch, days, expected
):
    ledger = {"issue_time": NOW_MS, "kind": {"Daily": {"days": days}}}
    rws = _rws_with_ledger(account, service_functions_mock, monkeypatch, ledger)

    assert rws.get_days_left() == expected


def test_get_days_left_returns_false_at_expiration(
    account, service_functions_mock, monkeypatch
):
    """A subscription ending now should already be considered inactive."""
    ledger = {"issue_time": NOW_MS - DAY_MS, "kind": {"Daily": {"days": 1}}}
    rws = _rws_with_ledger(account, service_functions_mock, monkeypatch, ledger)

    assert rws.get_days_left() is False


def test_get_days_left_returns_false_after_expiration(
    account, service_functions_mock, monkeypatch
):
    ledger = {"issue_time": NOW_MS - DAY_MS - 1, "kind": {"Daily": {"days": 1}}}
    rws = _rws_with_ledger(account, service_functions_mock, monkeypatch, ledger)

    assert rws.get_days_left() is False


def test_get_days_left_forwards_address_and_block_hash(
    account, service_functions_mock, monkeypatch
):
    rws = _rws_with_ledger(account, service_functions_mock, monkeypatch, None)

    rws.get_days_left(addr="target-address", block_hash="0xblock")

    service_functions_mock.chainstate_query.assert_called_once_with(
        "RWS", "Ledger", "target-address", block_hash="0xblock"
    )
