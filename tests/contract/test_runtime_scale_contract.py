import pytest
from metadata_fixture import (
    SUPPORTED_CALLS,
    fixture_paths,
    load_fixture,
    signed_extensions,
)


@pytest.fixture(params=fixture_paths())
def metadata_fixture(request):
    return load_fixture(request.param)


def test_fixture_contains_composed_and_decoded_supported_calls(metadata_fixture):
    """Each supported wrapper extrinsic should have an offline call sample."""
    samples = metadata_fixture.get("scale", {}).get("calls", [])
    by_name = {(sample["module"], sample["function"]): sample for sample in samples}

    assert SUPPORTED_CALLS <= set(by_name)

    for call_id in SUPPORTED_CALLS:
        sample = by_name[call_id]
        assert sample["encoded"].startswith("0x")
        assert sample["decoded"]["call_module"] == call_id[0]
        assert sample["decoded"]["call_function"] == call_id[1]


def test_signed_payload_fixture_includes_check_metadata_hash(metadata_fixture):
    """The exported payload should document CheckMetadataHash payload fields."""
    payload = metadata_fixture.get("scale", {}).get("signed_payload", {})

    assert "CheckMetadataHash" in signed_extensions(metadata_fixture)
    assert payload.get("hex", "").startswith("0x")
    assert "mode" in payload.get("fields", [])
    assert "metadata_hash" in payload.get("fields", [])
