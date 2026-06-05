from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from robonomicsinterface.classes.chain_utils import ChainUtils


def _extrinsic(extrinsic_hash):
    return SimpleNamespace(value={"extrinsic_hash": extrinsic_hash})


@pytest.mark.xfail(reason="ChainUtils currently treats extrinsic index 0 as no index")
def test_get_extrinsic_in_block_accepts_zero_based_index():
    """Block extrinsic indexes are zero-based, so index 0 means first item."""
    chain_utils = ChainUtils()
    chain_utils.interface = Mock()
    chain_utils.interface.get_block.return_value = {
        "extrinsics": [_extrinsic("0xfirst"), _extrinsic("0xsecond")]
    }

    assert chain_utils.get_extrinsic_in_block(100, 0) == {"extrinsic_hash": "0xfirst"}
    chain_utils.interface.get_block.assert_called_once_with(
        block_hash=None,
        block_number=100,
    )
