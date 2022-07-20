import typing as tp

from logging import getLogger
from scalecodec.types import GenericCall, GenericExtrinsic
from substrateinterface import Keypair, SubstrateInterface, ExtrinsicReceipt
from substrateinterface.exceptions import ExtrinsicFailedException

from .account import Account
from ..decorators import check_socket_opened
from ..exceptions import NoPrivateKeyException
from ..types import QueryParams, TypeRegistryTyping, RWSParamsTyping

logger = getLogger(__name__)


class ServiceFunctions:
    """
    Class for custom queries, extrinsics and RPC calls to Robonomics parachain network.
    """

    def __init__(
        self,
        account: Account,
        wait_for_inclusion: bool = True,
        return_block_num: bool = False,
        rws_sub_owner: tp.Optional[str] = None,
    ):
        """
        Assign Account dataclass parameters and create an empty interface attribute for a decorator.

        :param account: Account dataclass with ``seed``, ``remote_ws`` and node ``type_registry``.
        :param wait_for_inclusion: Whether wait for a transaction to included in block. You will get the hash anyway.
        :param return_block_num: If set to True, any executed extrinsic function will return a tuple of form
            ``(<extrinsic_hash>, <block_number-idx>)``. ONLY WORKS WHEN ``wait_for_inclusion`` IS SET TO TRUE.
        :param rws_sub_owner: Subscription owner address. If passed, all extrinsics will be executed via RWS
            subscriptions.

        """
        self.remote_ws: str = account.remote_ws
        self.type_registry: TypeRegistryTyping = account.type_registry
        self.keypair: Keypair = account.keypair
        self.interface: tp.Optional[SubstrateInterface] = None
        self.wait_for_inclusion: bool = wait_for_inclusion
        self.return_block_num: bool = return_block_num
        self.rws_sub_owner: tp.Optional[str] = rws_sub_owner

    @check_socket_opened
    def chainstate_query(
        self,
        module: str,
        storage_function: str,
        params: QueryParams = None,
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

    @check_socket_opened
    def extrinsic(
        self,
        call_module: str,
        call_function: str,
        params: tp.Optional[tp.Dict[str, tp.Any]] = None,
        nonce: tp.Optional[int] = None,
    ) -> tp.Union[str, tp.Tuple[str, str]]:
        """
        Create an extrinsic, sign&submit it. Module names and functions, as well as required parameters are available
        at https://parachain.robonomics.network/#/extrinsics.

        :param call_module: Call module from extrinsic tab on portal.
        :param call_function: Call function from extrinsic tab on portal.
        :param params: Call parameters as a dictionary. ``None`` for no parameters.
        :param nonce: Transaction nonce, defined automatically if None. Due to the feature of substrate-interface lib,
            to create an extrinsic with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: A tuple of form ``(<extrinsic_hash>, <block_number-idx>)`` if ``return_block_num`` and
            ``wait_for_inclusion`` in ``__init__`` were set to ``True``. String ``<extrinsic_hash>`` otherwise.
        """

        if not self.keypair:
            raise NoPrivateKeyException("No seed was provided, unable to use extrinsics.")

        if not self.rws_sub_owner:
            logger.info(f"Creating a call {call_module}:{call_function}")
            call: GenericCall = self.interface.compose_call(
                call_module=call_module,
                call_function=call_function,
                call_params=params or None,
            )
        else:
            logger.info(f"Creating an RWS call {call_module}:{call_function}")

            rws_params: RWSParamsTyping = {
                "subscription_id": self.rws_sub_owner,
                "call": {
                    "call_module": call_module,
                    "call_function": call_function,
                    "call_args": params,
                },
            }

            call: GenericCall = self.interface.compose_call(
                call_module="RWS", call_function="call", call_params=rws_params
            )

        logger.info("Creating extrinsic")
        extrinsic: GenericExtrinsic = self.interface.create_signed_extrinsic(
            call=call, keypair=self.keypair, nonce=nonce
        )

        logger.info("Submitting extrinsic")
        receipt: ExtrinsicReceipt = self.interface.submit_extrinsic(
            extrinsic, wait_for_inclusion=self.wait_for_inclusion
        )

        logger.info(f"Extrinsic {receipt.extrinsic_hash} for RPC {call_module}:{call_function} submitted.")

        if self.wait_for_inclusion:

            if not receipt.is_success:
                raise ExtrinsicFailedException()

            block_num: int = self.interface.get_block_number(receipt.block_hash)
            logger.info(f"Extrinsic included in block {block_num}")

            if self.return_block_num:
                return receipt.extrinsic_hash, f"{block_num}-{receipt.extrinsic_idx}"

            else:
                return receipt.extrinsic_hash

        else:
            return receipt.extrinsic_hash

    @check_socket_opened
    def rpc_request(
        self,
        method: str,
        params: tp.Optional[tp.List[str]],
        result_handler: tp.Optional[tp.Callable],
    ) -> tp.Dict[str, tp.Any]:
        """
        Method that handles the actual RPC request to the Substrate node. The other implemented functions eventually
        use this method to perform the request.

        :param method: Method of the ``JSONRPC`` request.
        :param params: A list containing the parameters of the ``JSONRPC`` request.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Result of the request.

        """

        return self.interface.rpc_request(method, params, result_handler)

    @check_socket_opened
    def subscribe_block_headers(self, callback: callable) -> dict:
        """
        Get chain head block headers.

        :return: Chain head block headers.

        """

        return self.interface.subscribe_block_headers(subscription_handler=callback)
