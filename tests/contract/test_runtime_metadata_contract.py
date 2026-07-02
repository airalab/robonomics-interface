import pytest
from metadata_fixture import (
    SUPPORTED_CALLS,
    call_names,
    constant_names,
    event_names,
    fixture_paths,
    load_fixture,
    pallets,
    signed_extensions,
    spec_version,
    storage_names,
)


@pytest.fixture(params=fixture_paths())
def metadata_fixture(request):
    return load_fixture(request.param)


def test_fixture_filename_matches_runtime_spec_version(metadata_fixture):
    """Fixture filenames should make runtime spec-version updates explicit."""
    fixture_path = metadata_fixture["_fixture_path"]

    assert f"spec_{spec_version(metadata_fixture)}.json" in fixture_path


@pytest.mark.parametrize(
    "pallet_name",
    [
        "System",
        "Balances",
        "Datalog",
        "Launch",
        "DigitalTwin",
        "RWS",
        "Liability",
    ],
)
def test_supported_pallets_exist(metadata_fixture, pallet_name):
    """Every pallet used by robonomics-interface should exist in metadata."""
    assert pallet_name in pallets(metadata_fixture)


@pytest.mark.parametrize(
    ("pallet_name", "expected_storage"),
    [
        ("System", {"Account", "Events"}),
        ("Datalog", {"DatalogIndex", "DatalogItem"}),
        ("DigitalTwin", {"DigitalTwin", "Owner", "Total"}),
        ("RWS", {"Auction", "AuctionNext", "AuctionQueue", "Devices", "Ledger"}),
        ("Liability", {"AgreementOf", "NextIndex", "ReportOf"}),
    ],
)
def test_supported_storage_items_exist(metadata_fixture, pallet_name, expected_storage):
    """Wrapper chainstate queries should target storage items still in runtime."""
    assert expected_storage <= storage_names(metadata_fixture, pallet_name)


@pytest.mark.parametrize(
    ("pallet_name", "expected_constants"),
    [
        ("System", {"SS58Prefix"}),
        ("Balances", {"ExistentialDeposit"}),
        ("Datalog", {"WindowSize"}),
    ],
)
def test_supported_constants_exist(metadata_fixture, pallet_name, expected_constants):
    """Constants consumed by wrappers and smoke checks should remain exported."""
    assert expected_constants <= constant_names(metadata_fixture, pallet_name)


@pytest.mark.parametrize(
    ("pallet_name", "expected_events"),
    [
        ("System", {"ExtrinsicSuccess", "ExtrinsicFailed"}),
        ("Balances", {"Transfer"}),
        ("Datalog", {"NewRecord"}),
        ("Launch", {"NewLaunch"}),
        ("DigitalTwin", {"TopicChanged"}),
        ("RWS", {"NewDevices"}),
        ("Liability", {"NewLiability", "NewReport"}),
    ],
)
def test_supported_events_exist(metadata_fixture, pallet_name, expected_events):
    """Events consumed by Subscriber and e2e assertions should remain exported."""
    assert expected_events <= event_names(metadata_fixture, pallet_name)


def _event(metadata_fixture, pallet_name, event_name):
    events = metadata_fixture["metadata"]["pallets"][pallet_name]["events"]
    for event in events:
        if event.get("event_name") == event_name or event.get("event_id") == event_name:
            return event
    pytest.fail(f"Missing {pallet_name}.{event_name} event")


def _event_args(metadata_fixture, pallet_name, event_name):
    return _event(metadata_fixture, pallet_name, event_name).get("event_args", [])


def test_liability_event_shapes_match_subscriber_extractors(metadata_fixture):
    """Subscriber address filters depend on current Liability event arg positions."""
    new_liability_args = _event_args(metadata_fixture, "Liability", "NewLiability")
    new_report_args = _event_args(metadata_fixture, "Liability", "NewReport")

    assert len(new_liability_args) == 5
    assert new_liability_args[3]["typeName"] == "T::AccountId"
    assert new_liability_args[4]["typeName"] == "T::AccountId"
    assert len(new_report_args) == 2
    assert new_report_args[1]["typeName"] == "ReportFor<T>"


def test_datalog_window_size_constant_is_exported(metadata_fixture):
    """Datalog.WindowSize should be present and carry a concrete value."""
    constants = metadata_fixture["metadata"]["pallets"]["Datalog"]["constants"]
    window_size = [
        constant
        for constant in constants
        if constant.get("constant_name") == "WindowSize"
        or constant.get("name") == "WindowSize"
    ]

    assert window_size
    assert window_size[0].get("constant_value") is not None


def test_balances_transfer_calls_exist(metadata_fixture):
    """Both safe default and explicit allow-death transfer calls should exist."""
    assert "transfer_keep_alive" in call_names(metadata_fixture, "Balances")
    assert "transfer_allow_death" in call_names(metadata_fixture, "Balances")


def test_supported_calls_are_present(metadata_fixture):
    """Every supported wrapper extrinsic should be present in runtime metadata."""
    missing = {
        (pallet_name, call_name)
        for pallet_name, call_name in SUPPORTED_CALLS
        if call_name not in call_names(metadata_fixture, pallet_name)
    }

    assert missing == set()


def test_check_metadata_hash_signed_extension_exists(metadata_fixture):
    """Signed payload checks should track the CheckMetadataHash extension."""
    assert "CheckMetadataHash" in signed_extensions(metadata_fixture)


def test_removed_runtime_surfaces_are_absent(metadata_fixture):
    """Removed pubsub/p2p/Subscription/CPS surfaces should stay absent."""
    assert "Subscription" not in pallets(metadata_fixture)
    assert "CPS" not in pallets(metadata_fixture)

    rpc_methods = set(metadata_fixture.get("rpc_methods", []))
    forbidden_rpc_methods = {
        "pubsub_connect",
        "pubsub_listen",
        "pubsub_listeners",
        "pubsub_peer",
        "pubsub_publish",
        "pubsub_subscribe",
        "pubsub_unsubscribe",
        "p2p_get",
        "p2p_ping",
    }
    assert forbidden_rpc_methods.isdisjoint(rpc_methods)
