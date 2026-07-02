import pytest

from robonomicsinterface.classes.digital_twin import DigitalTwin
from robonomicsinterface.utils import dt_encode_topic


def test_process_topic_hashes_plain_text():
    assert DigitalTwin._process_topic("temperature") == dt_encode_topic("temperature")


def test_process_topic_preserves_valid_hash():
    topic_hash = "0x" + "ab" * 32

    assert DigitalTwin._process_topic(topic_hash) == topic_hash


def test_process_topic_hashes_short_hex_string():
    assert DigitalTwin._process_topic("abcd") == dt_encode_topic("abcd")


@pytest.mark.parametrize(
    "topic",
    [
        "ab" * 33,
        "0x" + "zz" * 32,
    ],
)
def test_process_topic_hashes_invalid_ready_hash(topic):
    """Only valid 0x-prefixed 32-byte hex strings should bypass topic hashing."""

    assert DigitalTwin._process_topic(topic) == dt_encode_topic(topic)
