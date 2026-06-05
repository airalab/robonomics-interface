import pytest
from helpers import has_runtime_call, is_local_dev_chain

EXPECTED_RUNTIME_CALLS = (
    ("Datalog", "record"),
    ("Datalog", "erase"),
    ("Launch", "launch"),
    ("DigitalTwin", "create"),
    ("DigitalTwin", "set_source"),
    ("Liability", "create"),
    ("Liability", "finalize"),
)


@pytest.mark.e2e
def test_local_dev_node_preflight(e2e_substrate):
    """Guard e2e writes so they run only against a reachable local dev chain."""
    assert is_local_dev_chain(e2e_substrate.chain)
    assert isinstance(e2e_substrate.runtime_version, int)
    assert e2e_substrate.get_chain_head().startswith("0x")


@pytest.mark.e2e
def test_local_dev_node_exposes_supported_write_calls(e2e_substrate):
    """The dev node must expose every runtime call covered by stable e2e tests."""
    missing_calls = [
        f"{module}.{call}"
        for module, call in EXPECTED_RUNTIME_CALLS
        if not has_runtime_call(e2e_substrate, module, call)
    ]

    assert missing_calls == []
