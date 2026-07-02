from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from robonomicsinterface.classes.chain_utils import ChainUtils
from robonomicsinterface.exceptions import InvalidExtrinsicIndex


def _extrinsic(extrinsic_hash):
    return SimpleNamespace(value={"extrinsic_hash": extrinsic_hash})


def _chain_utils_with_extrinsics():
    chain_utils = ChainUtils()
    chain_utils.interface = Mock()
    chain_utils.interface.get_block.return_value = {
        "extrinsics": [_extrinsic("0xfirst"), _extrinsic("0xsecond")]
    }
    return chain_utils


def test_get_extrinsic_in_block_without_index_returns_all_extrinsics():
    """None means all extrinsics; zero is a real index."""
    chain_utils = _chain_utils_with_extrinsics()

    assert chain_utils.get_extrinsic_in_block(100) == [
        _extrinsic("0xfirst"),
        _extrinsic("0xsecond"),
    ]
    chain_utils.interface.get_block.assert_called_once_with(
        block_hash=None,
        block_number=100,
    )


def test_get_extrinsic_in_block_accepts_zero_based_index():
    """Block extrinsic indexes are zero-based, so index 0 means first item."""
    chain_utils = _chain_utils_with_extrinsics()

    assert chain_utils.get_extrinsic_in_block(100, 0) == {"extrinsic_hash": "0xfirst"}
    chain_utils.interface.get_block.assert_called_once_with(
        block_hash=None,
        block_number=100,
    )


def test_get_extrinsic_in_block_accepts_last_zero_based_index():
    """Index 1 in a two-extrinsic block means the second item, not the first."""
    chain_utils = _chain_utils_with_extrinsics()

    assert chain_utils.get_extrinsic_in_block(100, 1) == {"extrinsic_hash": "0xsecond"}


def test_get_extrinsic_in_block_raises_for_out_of_bounds_index():
    """Out-of-range numeric indexes should fail with a domain exception."""
    chain_utils = _chain_utils_with_extrinsics()

    with pytest.raises(InvalidExtrinsicIndex):
        chain_utils.get_extrinsic_in_block(100, 2)


def test_get_extrinsic_in_block_raises_for_negative_index():
    """Negative indexes are not valid block extrinsic IDs."""
    chain_utils = _chain_utils_with_extrinsics()

    with pytest.raises(InvalidExtrinsicIndex):
        chain_utils.get_extrinsic_in_block(100, -1)


def test_get_extrinsic_in_block_raises_for_invalid_index_type():
    """Only None, hash strings, and integer indexes are valid selectors."""
    chain_utils = _chain_utils_with_extrinsics()

    with pytest.raises(InvalidExtrinsicIndex):
        chain_utils.get_extrinsic_in_block(100, 1.5)
