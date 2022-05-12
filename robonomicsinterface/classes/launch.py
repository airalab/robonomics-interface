import typing as tp

from logging import getLogger

from .base import BaseClass
from ..utils import ipfs_qm_hash_to_32_bytes

logger = getLogger(__name__)


class Launch(BaseClass):
    """
    Class for sending launch transactions.
    """

    def launch(self, target_address: str, parameter: str, nonce: tp.Optional[int] = None) -> str:
        """
        Send Launch command to device.

        :param target_address: Device to be triggered with launch.
        :param parameter: Launch command accompanying parameter. Should be a 32 bytes data. Also, IPFS ``Qm...`` hash is
            supported. It will be transformed into a 32 bytes string without heading ``0x`` bytes.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with
            incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the launch transaction.

        """

        logger.info(f"Sending launch command to {target_address}")

        if parameter.startswith("Qm"):
            parameter = ipfs_qm_hash_to_32_bytes(parameter)

        return self._service_functions.extrinsic(
            "Launch", "launch", {"robot": target_address, "param": parameter}, nonce
        )
