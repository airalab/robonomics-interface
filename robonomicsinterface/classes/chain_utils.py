import typing as tp

from logging import getLogger
from substrateinterface import SubstrateInterface

from ..constants import REMOTE_WS, TYPE_REGISTRY
from ..decorators import check_socket_opened
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
