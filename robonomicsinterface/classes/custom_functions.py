import logging
import substrateinterface as substrate
import sys
import typing as tp

from account import Account

sys.path.append("../")

from robonomicsinterface.decorators import connect_close_substrate_node
from robonomicsinterface.types import TypeRegistryTyping

logger = logging.getLogger(__name__)


class CustomFunctions:
    """
    Class for custom queries, extrinsics and RPC calls to Robonomics parachain network.
    """

    def __init__(self, account: Account):
        """
        Assign Account dataclass parameters and create an empty interface attribute for a decorator.

        :param account: Account dataclass with seed, ws address and node type_registry

        """
        self.remote_ws: str = account.remote_ws
        self.type_registry: TypeRegistryTyping = account.type_registry
        self.keypair: substrate.Keypair = account.keypair
        self.interface: tp.Optional[substrate.SubstrateInterface] = None

    @connect_close_substrate_node
    def custom_chainstate(
            self,
            module: str,
            storage_function: str,
            params: tp.Optional[tp.Union[tp.List[tp.Union[str, int]], str, int]] = None,
            block_hash: tp.Optional[str] = None,
            subscription_handler: tp.Optional[callable] = None,
    ) -> tp.Any:
        """
        Create custom queries to fetch data from the Chainstate. Module names and storage functions, as well as required
        parameters are available at https://parachain.robonomics.network/#/chainstate.

        :param module: Chainstate module.
        :param storage_function: Storage function.
        :param params: Query parameters. None if no parameters. Include in list, if several.
        :param block_hash: Retrieves data as of passed block hash.
        :param subscription_handler: Callback function that processes the updates of the storage query subscription.
            The workflow is the same as in substrateinterface lib. Calling method with this parameter blocks current
            thread! Example of subscription handler:
            https://github.com/polkascan/py-substrate-interface#storage-subscriptions

        :return: Output of the query in any form.

        """

        logger.info(f"Performing query {module}.{storage_function}")
        return self.interface.query(
            module,
            storage_function,
            [params] if params is not None else None,
            block_hash=block_hash,
            subscription_handler=subscription_handler,
        ).value
