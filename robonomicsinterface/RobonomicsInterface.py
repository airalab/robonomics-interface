import logging

import substrateinterface as substrate
import typing as tp

from enum import Enum
from scalecodec.types import GenericCall, GenericExtrinsic

from .constants import REMOTE_WS, TYPE_REGISTRY
from .exceptions import NoPrivateKey
from .decorators import connect_close_substrate_node

Datalog = tp.Tuple[int, tp.Union[int, str]]
NodeTypes = tp.Dict[str, tp.Dict[str, tp.Union[str, tp.Any]]]

logger = logging.getLogger(__name__)


class RobonomicsInterface:
    """
    A class for establishing connection to the Robonomics nodes and interacting with them.
    Fetch chainstate, submit extrinsics, custom calls.
    """

    def __init__(
        self,
        seed: tp.Optional[str] = None,
        remote_ws: tp.Optional[str] = None,
        type_registry: tp.Optional[NodeTypes] = None,
    ) -> None:
        """
        Instance of a class is an interface with a node. Here this interface is initialized.

        @param seed: account seed in mnemonic/raw form. When not passed, no extrinsics functionality
        @param remote_ws: node url. Default node address is "wss://kusama.rpc.robonomics.network".
        Another address may be specified (e.g. "ws://127.0.0.1:9944" for local node).
        @param type_registry: types used in the chain. Defaults are the most frequently used in Robonomics
        """

        self._keypair: tp.Optional[substrate.Keypair] = self._create_keypair(seed) if seed else None
        self.remote_ws = remote_ws or REMOTE_WS
        self.type_registry = type_registry or TYPE_REGISTRY
        self.interface: tp.Optional[substrate.SubstrateInterface] = None
        # This is a dummy since interface is opened-closed every time it's needed

    @staticmethod
    def _create_keypair(seed: str) -> substrate.Keypair:
        """
        Create a keypair for further use

        @param seed: user seed as a key to sign transactions

        @return: a Keypair instance used by substrate to sign transactions
        """

        if seed.startswith("0x"):
            return substrate.Keypair.create_from_seed(seed_hex=hex(int(seed, 16)), ss58_format=32)
        else:
            return substrate.Keypair.create_from_mnemonic(seed, ss58_format=32)

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
        parameters are available at https://parachain.robonomics.network/#/chainstate

        @param module: chainstate module
        @param storage_function: storage function
        @param params: query parameters. None if no parameters. Include in list, if several
        @param block_hash: Retrieves data as of passed block hash
        @param subscription_handler: Callback function that processes the updates of the storage query subscription.
        The workflow is the same as in substrateinterface lib. Calling method with this parameter blocks current thread!
                Example of subscription handler:
        ```
        def subscription_handler(obj, update_nr, subscription_id):
            if update_nr == 0:
                print('Initial data:', obj.value)
            if update_nr > 0:
                # Do something with the update.
                print('data changed:', obj.value)
            # The execution will block until an arbitrary value is returned, which will be the result of the `query`
            if update_nr > 1:
                return obj
        ```
        @return: output of the query in any form
        """

        logger.info("Performing query")
        return self.interface.query(
            module,
            storage_function,
            [params] if params is not None else None,
            block_hash=block_hash,
            subscription_handler=subscription_handler,
        )

    def define_address(self) -> str:
        """
        define ss58_address of an account, which seed was provided while initializing an interface

        @return: ss58_address of an account
        """

        if not self._keypair:
            raise NoPrivateKey("No private key was provided, unable to determine self address")
        return str(self._keypair.ss58_address)

    def fetch_datalog(
        self, addr: tp.Optional[str] = None, index: tp.Optional[int] = None, block_hash: tp.Optional[str] = None
    ) -> tp.Optional[Datalog]:
        """
        Fetch datalog record of a provided account. Fetch self datalog if no address provided and interface was
        initialized with a seed.

        @param addr: ss58 type 32 address of an account which datalog is to be fetched. If None, tries to fetch self
        datalog if keypair was created, else raises NoPrivateKey
        @param index: record index. case int: fetch datalog by specified index
                                    case None: fetch latest datalog
        @param block_hash: Retrieves data as of passed block hash

        @return: Tuple. Datalog of the account with a timestamp, None if no records.
        """

        address: str = addr or self.define_address()

        logger.info(
            f"Fetching {'latest datalog record' if not index else 'datalog record #' + str(index)}" f" of {address}."
        )

        if index:
            record: Datalog = self.custom_chainstate(
                "Datalog", "DatalogItem", [address, index], block_hash=block_hash
            ).value
            return record if record[0] != 0 else None
        else:
            index_latest: int = self.custom_chainstate("Datalog", "DatalogIndex", address, block_hash=block_hash).value[
                "end"
            ] - 1
            return (
                self.custom_chainstate("Datalog", "DatalogItem", [address, index_latest], block_hash=block_hash).value
                if index_latest != -1
                else None
            )

    def rws_auction_queue(self, block_hash: tp.Optional[str] = None) -> tp.List[tp.Optional[int]]:
        """
        Get an auction queue of Robonomics Web Services subscriptions

        @param block_hash: Retrieves data as of passed block hash

        @return: Auction queue of Robonomics Web Services subscriptions
        """

        logger.info("Fetching auctions queue list")
        return self.custom_chainstate("RWS", "AuctionQueue", block_hash=block_hash)

    def rws_auction(self, index: int, block_hash: tp.Optional[str] = None) -> tp.Dict[str, tp.Union[str, int, dict]]:
        """
        Get to now information about subscription auction

        @param index: Auction index
        @param block_hash: Retrieves data as of passed block hash

        @return: Auction info
        """

        logger.info(f"Fetching auction {index} information")
        return self.custom_chainstate("RWS", "Auction", index, block_hash=block_hash)

    def rws_list_devices(self, addr: str, block_hash: tp.Optional[str] = None) -> tp.List[tp.Optional[str]]:
        """
        Fetch list of RWS added devices

        @param addr: Subscription owner
        @param block_hash: Retrieves data as of passed block hash

        @return: List of added devices. Empty if none
        """

        logging.info(f"Fetching list of RWS devices set by owner {addr}")

        return self.custom_chainstate("RWS", "Devices", addr, block_hash=block_hash)

    @connect_close_substrate_node
    def custom_extrinsic(
        self,
        call_module: str,
        call_function: str,
        params: tp.Optional[tp.Dict[str, tp.Any]] = None,
        nonce: tp.Optional[int] = None,
    ) -> str:
        """
        Create an extrinsic, sign&submit it. Module names and functions, as well as required parameters are available
        at https://parachain.robonomics.network/#/extrinsics

        @param call_module: Call module from extrinsic tab on portal
        @param call_function: Call function from extrinsic tab on portal
        @param params: Call parameters as a dictionary. None for no parameters
        @param nonce: transaction nonce, defined automatically if None. Due to e feature of substrate-interface lib,
        to create an extrinsic with incremented nonce, pass account's current nonce. See
        https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
        for example.

        @return: Extrinsic hash or None if failed
        """

        if not self._keypair:
            raise NoPrivateKey("No seed was provided, unable to use extrinsics.")

        logger.info(f"Creating a call {call_module}:{call_function}")
        call: GenericCall = self.interface.compose_call(
            call_module=call_module, call_function=call_function, call_params=params or None
        )

        logger.info("Creating extrinsic")
        extrinsic: GenericExtrinsic = self.interface.create_signed_extrinsic(
            call=call, keypair=self._keypair, nonce=nonce
        )

        logger.info("Submitting extrinsic")
        receipt: substrate.ExtrinsicReceipt = self.interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        logger.info(
            f"Extrinsic {receipt.extrinsic_hash} for RPC {call_module}:{call_function} submitted and "
            f"included in block {receipt.block_hash}"
        )

        return str(receipt.extrinsic_hash)

    def record_datalog(self, data: str, nonce: tp.Optional[int] = None) -> str:
        """
        Write any string to datalog

        @param data: string to be stored in datalog
        @param nonce: nonce of the transaction. Due to e feature of substrate-interface lib,
        to create an extrinsic with incremented nonce, pass account's current nonce. See
        https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
        for example.

        @return: Hash of the datalog transaction
        """

        logger.info(f"Writing datalog {data}")
        return self.custom_extrinsic("Datalog", "record", {"record": data}, nonce)

    def send_launch(self, target_address: str, toggle: bool, nonce: tp.Optional[int] = None) -> str:
        """
        Send Launch command to device

        @param target_address: device to be triggered with launch
        @param toggle: whether send ON or OFF command. ON == True, OFF == False
        @param nonce: account nonce. Due to e feature of substrate-interface lib,
        to create an extrinsic with incremented nonce, pass account's current nonce. See
        https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
        for example.

        @return: Hash of the launch transaction
        """

        logger.info(f"Sending {'ON' if toggle else 'OFF'} launch command to {target_address}")
        return self.custom_extrinsic("Launch", "launch", {"robot": target_address, "param": toggle}, nonce)

    @connect_close_substrate_node
    def get_account_nonce(self, account_address: tp.Optional[str] = None) -> int:
        """
        Get current account nonce

        @param account_address: account ss58_address. Self address via private key is obtained if not passed.

        @return account nonce. Due to e feature of substrate-interface lib,
        to create an extrinsic with incremented nonce, pass account's current nonce. See
        https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
        for example.
        """

        return self.interface.get_account_nonce(account_address=account_address or self.define_address())

    def rws_bid(self, index: int, amount: int) -> str:
        """
        Bid to win a subscription!


        @param index: Auction index
        @param amount: Your bid in Weiners (!)
        """

        logger.info(f"Bidding on auction {index} with {amount} Weiners (appx. {round(amount / 10 ** 9, 2)} XRT)")
        return self.custom_extrinsic("RWS", "bid", {"index": index, "amount": amount})

    def rws_set_devices(self, devices: tp.List[str]) -> str:
        """
        Set devices which are authorized to use RWS subscriptions held by the extrinsic author

        @param devices: Devices authorized to use RWS subscriptions. Include in list.

        @return: transaction hash
        """

        logger.info(f"Allowing {devices} to use {self.define_address()} subscription")
        return self.custom_extrinsic("RWS", "set_devices", {"devices": devices})

    def rws_custom_call(
        self,
        subscription_owner_addr: str,
        call_module: str,
        call_function: str,
        params: tp.Optional[tp.Dict[str, tp.Any]] = None,
    ) -> str:
        """
        Send transaction from a device given a RWS subscription

        @param subscription_owner_addr: Subscription owner, the one who granted this device ability to send transactions
        @param call_module: Call module from extrinsic tab on portal
        @param call_function: Call function from extrinsic tab on portal
        @param params: Call parameters as a dictionary. None for no parameters

        @return: Transaction hash
        """

        logger.info("Sending transaction using subscription")
        return self.custom_extrinsic(
            "RWS",
            "call",
            {
                "subscription_id": subscription_owner_addr,
                "call": {"call_module": call_module, "call_function": call_function, "call_args": params},
            },
        )

    def rws_record_datalog(self, subscription_owner_addr: str, data: str) -> str:
        """
        Write any string to datalog from a device which was granted a subscription.

        @param subscription_owner_addr: Subscription owner, the one who granted this device ability to send transactions
        @param data: string to be stored in datalog

        @return: Hash of the datalog transaction
        """

        return self.rws_custom_call(subscription_owner_addr, "Datalog", "record", {"record": data})

    def rws_send_launch(self, subscription_owner_addr: str, target_address: str, toggle: bool) -> str:
        """
        Send Launch command to device from another device which was granted a subscription.

        @param subscription_owner_addr: Subscription owner, the one who granted this device ability to send transactions
        @param target_address: device to be triggered with launch
        @param toggle: whether send ON or OFF command. ON == True, OFF == False

        @return: Hash of the launch transaction
        """

        return self.rws_custom_call(
            subscription_owner_addr, "Launch", "launch", {"robot": target_address, "param": toggle}
        )

    @connect_close_substrate_node
    def custom_rpc_request(
        self, method: str, params: tp.Optional[tp.List[str]], result_handler: tp.Optional[tp.Callable]
    ) -> dict:
        """
        Method that handles the actual RPC request to the Substrate node. The other implemented functions eventually
        use this method to perform the request.

        @param method: method of the JSONRPC request
        @param params: a list containing the parameters of the JSONRPC request
        @param result_handler: Callback function that processes the result received from the node

        @return: result of the request
        """

        return self.interface.rpc_request(method, params, result_handler)

    @connect_close_substrate_node
    def subscribe_block_headers(self, callback: callable) -> dict:
        """
        Get chain head block headers

        @return: Chain head block headers
        """

        return self.interface.subscribe_block_headers(subscription_handler=callback)


class PubSub:
    """
    Class for handling Robonomics pubsub rpc requests

    WARNING: THIS MODULE IS UNDER CONSTRUCTION, USE AT YOUR OWN RISK! TO BE UPDATED SOON
    """

    def __init__(self, interface: RobonomicsInterface) -> None:
        """
        Initiate an instance for further use.

        @param interface: RobonomicsInterface instance
        """

        self._pubsub_interface = interface

    def connect(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Connect to peer and add it into swarm.

        @param address: Multiaddr address of the peer to connect to
        @param result_handler: Callback function that processes the result received from the node

        @return: success flag in JSON message
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_connect", [address], result_handler)

    def listen(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Listen address for incoming connections.

        @param address: Multiaddr address of the peer to connect to
        @param result_handler: Callback function that processes the result received from the node

        @return: success flag in JSON message
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_listen", [address], result_handler)

    def listeners(
        self, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, tp.List[str], int]]:
        """
        Returns a list of node addresses.

        @param result_handler: Callback function that processes the result received from the node

        @return: list of node addresses in JSON message
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_listeners", None, result_handler)

    def peer(self, result_handler: tp.Optional[tp.Callable] = None) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Returns local peer ID.

        @return: local peer ID in JSON message
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_peer", None, result_handler)

    def publish(self, topic_name: str, message: str, result_handler: tp.Optional[tp.Callable] = None) -> tp.Any:
        """
        Publish message into the topic by name.

        @param topic_name: topic name
        @param message: message to be published
        @param result_handler: Callback function that processes the result received from the node

        @return: TODO
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_publish", [topic_name, message], result_handler)

    def subscribe(
        self, topic_name: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Listen address for incoming connections.

        @param topic_name: topic name to subscribe to
        @param result_handler: Callback function that processes the result received from the node

        @return: subscription ID in JSON message
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_subscribe", [topic_name], result_handler)

    def unsubscribe(
        self, subscription_id: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Unsubscribe for incoming messages from topic.

        @param subscription_id: subscription ID obtained when subscribed
        @param result_handler: Callback function that processes the result received from the node

        @return: success flag in JSON message
        """

        return self._pubsub_interface.custom_rpc_request("pubsub_unsubscribe", [subscription_id], result_handler)


class SubEvent(Enum):
    NewRecord = "NewRecord"
    NewLaunch = "NewLaunch"
    Transfer = "Transfer"


class Subscriber:
    """
    Class intended for use in cases when needed to subscribe on chainstate updates/events. Blocks current thread!
    """

    def __init__(
        self,
        interface: RobonomicsInterface,
        subscribed_event: SubEvent,
        subscription_handler: callable,
        addr: tp.Optional[tp.Union[tp.List[str], str]] = None,
    ) -> None:
        """
        Initiates an instance for further use and starts a subscription for a selected action

        @param interface: RobonomicsInterface instance
        @param subscribed_event: Event in substrate chain to be awaited. Choose from [NewRecord, NewLaunch, Transfer]
        This parameter should be a SubEvent class attribute. This also requires importing this class.
        @param subscription_handler: Callback function that processes the updates of the storage.
        THIS FUNCTION IS MEANT TO ACCEPT ONLY ONE ARGUMENT (THE NEW EVENT DESCRIPTION TUPLE).
        @param addr: ss58 type 32 address(-es) of an account(-s) which is(are) meant to be event target. If None, will
        subscribe to all such events never-mind target address(-es).
        """

        self._subscriber_interface: RobonomicsInterface = interface

        self._event: SubEvent = subscribed_event
        self._callback: callable = subscription_handler
        self._target_address: tp.Optional[tp.Union[tp.List[str], str]] = addr

        self._subscribe_event()

    def _subscribe_event(self) -> None:
        """
        Subscribe to events targeted to a certain account (launch, transfer). Call subscription_handler when updated
        """

        self._subscriber_interface.subscribe_block_headers(self._event_callback)

    def _event_callback(self, index_obj: tp.Any, update_nr: int, subscription_id: int) -> None:
        """
        Function, processing updates in event list storage. When update, filters events to a desired account
        and passes the event description to the user-provided callback method.

        @param index_obj: updated event list
        @param update_nr: update counter. Increments every new update added. Starts with 0
        @param subscription_id: subscription ID
        """

        if update_nr != 0:
            chain_events = self._subscriber_interface.custom_chainstate("System", "Events")
            for events in chain_events:
                if events.value["event_id"] == self._event.value:
                    if self._target_address is None:
                        self._callback(events.value["event"]["attributes"])  # All events
                    elif (
                        events.value["event"]["attributes"][0 if self._event == SubEvent.NewRecord else 1]
                        in self._target_address
                    ):
                        self._callback(events.value["event"]["attributes"])  # address-targeted
