import json
import os
from pathlib import Path

import pytest

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "metadata"
FIXTURE_DIR = Path(
    os.environ.get("ROBONOMICS_METADATA_FIXTURE_DIR", DEFAULT_FIXTURE_DIR)
)
FIXTURE_PATTERN = "robonomics_spec_*.json"

SUPPORTED_CALLS = {
    ("Balances", "transfer_allow_death"),
    ("Balances", "transfer_keep_alive"),
    ("Datalog", "record"),
    ("Datalog", "erase"),
    ("Launch", "launch"),
    ("DigitalTwin", "create"),
    ("DigitalTwin", "set_source"),
    ("RWS", "bid"),
    ("RWS", "set_devices"),
    ("RWS", "call"),
    ("Liability", "create"),
    ("Liability", "finalize"),
}


def fixture_paths():
    paths = sorted(FIXTURE_DIR.glob(FIXTURE_PATTERN))
    if not paths:
        return [
            pytest.param(
                None,
                marks=pytest.mark.skip(
                    reason=(
                        "Runtime metadata fixtures are missing: "
                        f"{FIXTURE_DIR / FIXTURE_PATTERN}"
                    )
                ),
                id="missing_metadata_fixture",
            )
        ]
    return [pytest.param(path, id=fixture_id(path)) for path in paths]


def fixture_id(path):
    if path is None:
        return "missing_metadata_fixture"
    return path.stem.replace("robonomics_", "")


def load_fixture(path):
    if path is None:
        pytest.skip(
            f"Runtime metadata fixtures are missing: {FIXTURE_DIR / FIXTURE_PATTERN}"
        )

    with path.open(encoding="utf-8") as fp:
        fixture = json.load(fp)
    fixture["_fixture_path"] = str(path)
    return fixture


def runtime_version(fixture):
    return fixture.get("runtime_version", {})


def spec_version(fixture):
    return runtime_version(fixture).get("specVersion")


def metadata_version(fixture):
    exported_version = fixture.get("metadata", {}).get("version")
    if exported_version is not None:
        return exported_version

    raw_metadata = fixture.get("metadata", {}).get("raw", "")
    if not raw_metadata.startswith("0x6d657461"):
        pytest.fail("Unexpected runtime metadata prefix in fixture")
    return int(raw_metadata[10:12], 16)


def pallets(fixture):
    return fixture.get("metadata", {}).get("pallets", {})


def pallet(fixture, pallet_name):
    try:
        return pallets(fixture)[pallet_name]
    except KeyError:
        pytest.fail(f"Missing pallet in metadata fixture: {pallet_name}")


def names(entries, keys):
    result = set()
    for entry in entries or []:
        if isinstance(entry, str):
            result.add(entry)
            continue
        for key in keys:
            if key in entry:
                result.add(entry[key])
                break
    return result


def storage_names(fixture, pallet_name):
    return names(pallet(fixture, pallet_name).get("storage"), ["storage_name", "name"])


def call_names(fixture, pallet_name):
    return names(pallet(fixture, pallet_name).get("calls"), ["call_name", "name"])


def constant_names(fixture, pallet_name):
    return names(
        pallet(fixture, pallet_name).get("constants"),
        ["constant_name", "name"],
    )


def event_names(fixture, pallet_name):
    return names(
        pallet(fixture, pallet_name).get("events"), ["event_name", "event_id", "name"]
    )


def signed_extensions(fixture):
    value = fixture.get("metadata", {}).get("signed_extensions", {})
    if isinstance(value, dict):
        return set(value)
    return set(value or [])
