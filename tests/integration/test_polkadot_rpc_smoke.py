import json
import os
from pathlib import Path

import pytest
from substrateinterface import SubstrateInterface

from robonomicsinterface.classes.account import Account
from robonomicsinterface.constants import REMOTE_WS, TYPE_REGISTRY

METADATA_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "metadata"
ALICE_ADDRESS = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


@pytest.fixture(scope="module")
def substrate():
    rpc_url = os.environ.get("ROBONOMICS_RPC_URL") or REMOTE_WS
    interface = SubstrateInterface(
        url=rpc_url,
        ss58_format=32,
        type_registry_preset="substrate-node-template",
        type_registry=TYPE_REGISTRY,
    )
    interface.init_runtime()
    yield interface
    interface.close()


def _metadata_version(raw_metadata):
    if not raw_metadata.startswith("0x6d657461"):
        pytest.fail("Unexpected runtime metadata prefix")
    return int(raw_metadata[10:12], 16)


def _fixture_metadata_version(fixture):
    exported_version = fixture.get("metadata", {}).get("version")
    if exported_version is not None:
        return exported_version
    return _metadata_version(fixture.get("metadata", {}).get("raw", ""))


def _metadata_fixtures_by_spec_version():
    fixtures = {}
    for path in METADATA_FIXTURE_DIR.glob("robonomics_spec_*.json"):
        with path.open(encoding="utf-8") as fp:
            fixture = json.load(fp)
        fixtures[fixture["runtime_version"]["specVersion"]] = fixture
    return fixtures


@pytest.mark.integration
@pytest.mark.smoke
def test_live_runtime_version_is_covered_by_metadata_fixture(substrate):
    """The live runtime specVersion should have an offline metadata fixture."""
    runtime_version = substrate.get_block_runtime_version(substrate.block_hash)

    assert runtime_version["specVersion"] == substrate.runtime_version
    assert runtime_version["transactionVersion"] == substrate.transaction_version
    assert substrate.runtime_version in _metadata_fixtures_by_spec_version()


@pytest.mark.integration
@pytest.mark.smoke
def test_live_runtime_metadata_version_matches_fixture(substrate):
    """The live metadata format version should match the covered fixture."""
    fixtures = _metadata_fixtures_by_spec_version()
    raw_metadata = substrate.get_block_metadata(substrate.block_hash, decode=False)[
        "result"
    ]

    assert _metadata_version(raw_metadata) == _fixture_metadata_version(
        fixtures[substrate.runtime_version]
    )


@pytest.mark.integration
@pytest.mark.smoke
def test_live_rpc_methods_include_read_only_smoke_surface(substrate):
    """The RPC should expose read-only methods needed by smoke checks."""
    rpc_methods = set(
        substrate.rpc_request("rpc_methods", []).get("result", {}).get("methods", [])
    )

    assert {
        "rpc_methods",
        "state_getMetadata",
        "state_getRuntimeVersion",
        "state_getStorageAt",
        "payment_queryInfo",
    } <= rpc_methods
    assert (
        not {
            "pubsub_connect",
            "pubsub_publish",
            "pubsub_subscribe",
            "p2p_get",
            "p2p_ping",
        }
        & rpc_methods
    )


@pytest.mark.integration
@pytest.mark.smoke
def test_live_safe_storage_queries(substrate):
    """Safe live storage reads should still have the expected shape."""
    ss58_prefix = substrate.get_constant("System", "SS58Prefix")
    datalog_window_size = substrate.get_constant("Datalog", "WindowSize")
    account = substrate.query("System", "Account", [ALICE_ADDRESS])
    datalog_index = substrate.query("Datalog", "DatalogIndex", [ALICE_ADDRESS])
    auction_next = substrate.query("RWS", "AuctionNext")

    assert ss58_prefix.value == 32
    assert datalog_window_size.value > 0
    assert "nonce" in account.value
    assert {"start", "end"} <= set(datalog_index.value)
    assert isinstance(auction_next.value, int)


@pytest.mark.integration
@pytest.mark.smoke
def test_live_payment_query_info_for_unsigned_submission_candidate(substrate):
    """payment_queryInfo should work for a signed but unsubmitted call."""
    call = substrate.compose_call(
        "Datalog",
        "record",
        {"record": "robonomics-interface smoke test"},
    )

    payment_info = substrate.get_payment_info(call, Account(seed="//Alice").keypair)

    assert int(payment_info["partialFee"]) > 0
    assert payment_info["class"].lower() in {"normal", "operational", "mandatory"}
    assert payment_info["weight"]
