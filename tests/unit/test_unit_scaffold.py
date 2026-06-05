from unittest.mock import NonCallableMagicMock


def test_account_fixture_is_local_development_account(account):
    assert account.get_address() == "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def test_readonly_account_fixture_does_not_create_keypair(readonly_account):
    assert readonly_account.keypair is None
    assert readonly_account.remote_ws == "ws://127.0.0.1:9944"


def test_substrate_interface_mock_uses_interface_spec(substrate_interface_mock):
    assert isinstance(substrate_interface_mock, NonCallableMagicMock)
    substrate_interface_mock.query("System", "Events")


def test_service_functions_mock_uses_wrapper_spec(service_functions_mock):
    assert isinstance(service_functions_mock, NonCallableMagicMock)
    service_functions_mock.chainstate_query("System", "Events")
