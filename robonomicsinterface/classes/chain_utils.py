import typing as tp

from logging import getLogger
from substrateinterface import SubstrateInterface

from ..constants import REMOTE_WS, TYPE_REGISTRY
from ..decorators import check_socket_opened
from ..exceptions import InvalidExtrinsicHash
from ..types import TypeRegistryTyping

logger = getLogger(__name__)


class ChainUtils:
    """
    Various tools for obtaining information from the blockchain.

    """

    def __init__(
        self,
        remote_ws: tp.Optional[str] = None,
        type_registry: tp.Optional[TypeRegistryTyping] = None,
    ):
        """
        Initiate ChainUtils class with node address passed as an argument.

        :param remote_ws: Node url. Default node address is "wss://kusama.rpc.robonomics.network". Another address may
            be specified (e.g. "ws://127.0.0.1:9944" for local node).
        :param type_registry: Types used in the chain. Defaults are the most frequently used in Robonomics.

        """

        self.remote_ws: str = remote_ws or REMOTE_WS
        self.type_registry: TypeRegistryTyping = type_registry or TYPE_REGISTRY
        self.interface: tp.Optional[SubstrateInterface] = None

    @check_socket_opened
    def get_block_number(self, block_hash: str) -> int:
        """
        Get block number by its hash.

        :param block_hash: Block hash.

        :return: Block number.

        """

        return self.interface.get_block_number(block_hash)

    def get_block_hash(self, block_number: int) -> str:
        """
        Get block hash by its number.

        :param block_number: Block number.

        :return: Block hash.

        """

        return self.interface.get_block_hash(block_number)

    @staticmethod
    def _check_hash_valid(data_hash: str):
        """
        Check if the hash is valid.

        :param data_hash: Extrinsic hash.

        :return: Bool flag if the hash is valid.

        """

        if not data_hash.startswith("0x") or not len(data_hash) == 66:
            raise InvalidExtrinsicHash("Not a valid extrinsic has passed")

    @check_socket_opened
    def get_extrinsic_in_block(
        self, block: tp.Union[int, str], extrinsic: tp.Union[None, str, int] = None
    ) -> tp.Union[None, list, dict]:
        """
        Get all extrinsics in block or a certain extrinsic if its block ``idx`` is specified.

        :param block: Block pointer. Either block number or block hash.
        :param extrinsic: Extrinsic in this block. Either its hash or block extrinsic ``idx``.

        :return: All extrinsics in block or a certain extrinsic if its idx was passed

        """

        def _get_block_any(block_: tp.Union[int, str]) -> list:
            """
            Get all extrinsics in a block given any, block number or hash.

            :param block_: Block number or hash.

            :return: All extrinsics in a block.

            """

            return self.interface.get_block(
                block_hash=(block_ if type(block_) == str else None),
                block_number=(block_ if type(block_) == int else None),
            )["extrinsics"]

        if type(block) == str:
            self._check_hash_valid(block)

        if not extrinsic:
            logger.info(f"Getting all extrinsics of a block {block}...")
            return _get_block_any(block)
        else:
            logger.info(f"Getting extrinsic {block}-{extrinsic}...")
            if type(extrinsic) == str:
                self._check_hash_valid(extrinsic)
                found_extrinsics: list = _get_block_any(block)
                for extrinsic_ in found_extrinsics:
                    if extrinsic_.value["extrinsic_hash"] == extrinsic:
                        return extrinsic_.value

            else:
                return _get_block_any(block)[extrinsic-1].value


