from unittest.mock import create_autospec

import pytest
from substrateinterface import SubstrateInterface

from robonomicsinterface.classes.account import Account
from robonomicsinterface.classes.service_functions import ServiceFunctions


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run read-only tests against the live Robonomics Polkadot RPC endpoint",
    )
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="run write tests against an explicitly configured local Robonomics node",
    )


def pytest_collection_modifyitems(config, items):
    run_integration = config.getoption("--run-integration")
    run_e2e = config.getoption("--run-e2e")
    skip_integration = pytest.mark.skip(
        reason="use --run-integration to enable live RPC tests"
    )
    skip_e2e = pytest.mark.skip(reason="use --run-e2e to enable local-node write tests")

    for item in items:
        if "e2e" in item.keywords and not run_e2e:
            item.add_marker(skip_e2e)
        elif "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)


@pytest.fixture
def account():
    return Account(seed="//Alice")


@pytest.fixture
def readonly_account():
    return Account(remote_ws="ws://127.0.0.1:9944")


@pytest.fixture
def substrate_interface_mock():
    return create_autospec(SubstrateInterface, instance=True, spec_set=True)


@pytest.fixture
def service_functions_mock():
    return create_autospec(ServiceFunctions, instance=True, spec_set=True)
