import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).with_name("fixtures")


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def compat_vectors() -> Any:
    """Produced by substrate-interface 1.7 (see fixtures/generate_compat_vectors.py)."""

    return load_fixture("compat_vectors.json")


@pytest.fixture(scope="session")
def report_service_vectors() -> Any:
    """The contract rrs-ha-integration was built against, copied with a warning header."""

    return load_fixture("substrate_vectors.json")
