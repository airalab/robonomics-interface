from robonomicsinterface.classes.launch import Launch
from robonomicsinterface.utils import ipfs_32_bytes_to_qm_hash


def _launch(account, service_functions_mock):
    launch = Launch(account)
    launch._service_functions = service_functions_mock
    return launch


def test_launch_submits_raw_parameter(account, service_functions_mock):
    launch = _launch(account, service_functions_mock)

    launch.launch("robot-address", "ON", nonce=2)

    service_functions_mock.extrinsic.assert_called_once_with(
        "Launch",
        "launch",
        {"robot": "robot-address", "param": "ON"},
        2,
    )


def test_launch_converts_ipfs_parameter(account, service_functions_mock):
    """Launch accepts a CID and passes the runtime the underlying H256 digest."""
    launch = _launch(account, service_functions_mock)
    digest = "0x" + "ab" * 32

    launch.launch("robot-address", ipfs_32_bytes_to_qm_hash(digest))

    service_functions_mock.extrinsic.assert_called_once_with(
        "Launch",
        "launch",
        {"robot": "robot-address", "param": digest},
        None,
    )
