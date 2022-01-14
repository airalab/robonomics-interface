import asyncio
import logging

import substrateinterface as substrate
import typing as tp

from threading import Thread
from scalecodec.types import GenericCall, GenericExtrinsic

from .constants import REMOTE_WS, TYPE_REGISTRY
from .exceptions import NoPrivateKey

Datalog = tp.Tuple[int, tp.Union[int, str]]
NodeTypes = tp.Dict[str, tp.Dict[str, tp.Union[str, tp.Any]]]


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
        keep_alive: bool = False,
    ) -> None:
        """
        Instance of a class is an interface with a node. Here this interface is initialized.

        @param seed: account seed in mnemonic/raw form. When not passed, no extrinsics functionality
        @param remote_ws: node url. Default node address is "wss://kusama.rpc.robonomics.network".
        Another address may be specified (e.g. "ws://127.0.0.1:9944" for local node).
        @param type_registry: types used in the chain. Defaults are the most frequently used in Robonomics
        @param keep_alive: whether send ping calls each 200 secs to keep interface opened or not
        """

        self._interface: substrate.SubstrateInterface
        self._keypair: tp.Optional[substrate.Keypair] = self._create_keypair(seed) if seed else None

        if not self._keypair:
            logging.warning("No seed specified, you won't be able to sign extrinsics, fetching chainstate only.")

        if type_registry:
            logging.warning("Using custom type registry for the node")

        logging.info("Establishing connection with Robonomics node")
        self._interface = self._establish_connection(remote_ws or REMOTE_WS, type_registry or TYPE_REGISTRY)

        if keep_alive:
            self._keep_alive_pinger()

        logging.info("Successfully established connection to Robonomics node")

    def _keep_alive_pinger(self) -> None:
        """
        It uses main thread event_loop running in another thread to add keep_alive coroutines of each interface there.
        !Be careful using asyncio, since main thread event_loop is already running (main thread is not locked though).!
        You are to add new coroutines to a main thread event_loop, not to run it. Also using this flag while creating an
        interface NOT in the main thread will throw RuntimeError.

        This was made so because of a simple way to add new interfaces' keep_alive tasks to the same event_loop (to the
        main one) without blocking main execution thread (since main thread event_loop runs in a separate thread).

        That's so with 1, 2, 3 or 18 interfaces with a keep_alive option you will still have only one dedicated thread
        for all keep_alive tasks.
        """

        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(self._keep_alive(), loop=loop)
        else:
            keep_alive_thread = Thread(target=self._keep_alive_loop_in_thread, args=(loop,))
            keep_alive_thread.start()

    async def _keep_alive(self) -> None:
        """
        Keep the connection alive by sending websocket ping each 200 seconds.
        """

        while True:
            await asyncio.sleep(25)
            self._interface.websocket.ping()

    def _keep_alive_loop_in_thread(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Run a keep_alive coroutine in the passed loop. If selected loop is already running, add a coroutine to it, else
        run a new loop with a keep_alive coroutine.

        @param loop: AbstractEventLoop passed from class __init__ function
        """

        loop.run_until_complete(self._keep_alive())

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

    @staticmethod
    def _establish_connection(url: str, types: NodeTypes) -> substrate.SubstrateInterface:
        """
        Create a substrate interface for interacting wit Robonomics node

        @param url: node endpoint
        @param types: json types used by pallets

        @return: interface of a Robonomics node connection
        """

        return substrate.SubstrateInterface(
            url=url,
            ss58_format=32,
            type_registry_preset="substrate-node-template",
            type_registry=types,
        )

    def custom_chainstate(
        self,
        module: str,
        storage_function: str,
        params: tp.Optional[tp.Union[tp.List[tp.Union[str, int]], str, int]] = None,
    ) -> tp.Any:
        """
        Create custom queries to fetch data from the Chainstate. Module names and storage functions, as well as required
        parameters are available at https://parachain.robonomics.network/#/chainstate

        @param module: chainstate module
        @param storage_function: storage function
        @param params: query parameters. None if no parameters. Include in list, if several

        @return: output of the query in any form
        """

        logging.info("Performing query")
        return self._interface.query(module, storage_function, [params] if params is not None else None)

    def define_address(self) -> str:
        """
        define ss58_address of an account, which seed was provided while initializing an interface

        @return: ss58_address of an account
        """

        if not self._keypair:
            raise NoPrivateKey("No private key was provided, unable to determine self address")
        return str(self._keypair.ss58_address)

    def fetch_datalog(self, addr: tp.Optional[str] = None, index: tp.Optional[int] = None) -> tp.Optional[Datalog]:
        """
        Fetch datalog record of a provided account. Fetch self datalog if no address provided and interface was
        initialized with a seed.

        @param addr: ss58 type 32 address of an account which datalog is to be fetched. If None, tries to fetch self
        datalog if keypair was created, else raises NoPrivateKey
        @param index: record index. case int: fetch datalog by specified index
                                    case None: fetch latest datalog

        @return: Dictionary. Datalog of the account with a timestamp, None if no records.
        """

        address: str = addr or self.define_address()

        logging.info(
            f"Fetching {'latest datalog record' if not index else 'datalog record #' + str(index)}" f" of {address}."
        )

        if index:
            record: Datalog = self.custom_chainstate("Datalog", "DatalogItem", [address, index]).value
            return record if record[0] != 0 else None
        else:
            index_latest: int = self.custom_chainstate("Datalog", "DatalogIndex", address).value["end"] - 1
            return (
                self.custom_chainstate("Datalog", "DatalogItem", [address, index_latest]).value
                if index_latest != -1
                else None
            )

    def rws_auction_queue(self) -> tp.List[tp.Optional[int]]:
        """
        Get an auction queue of Robonomics Web Services subscriptions

        @return: Auction queue of Robonomics Web Services subscriptions
        """

        logging.info("Fetching auctions queue list")
        return self.custom_chainstate("RWS", "AuctionQueue")

    def rws_auction(self, index: int) -> tp.Dict[str, tp.Union[str, int, dict]]:
        """
        Get to now information about subscription auction

        @param index: Auction index
        """

        logging.info(f"Fetching auction {index} information")
        return self.custom_chainstate("RWS", "Auction", index)

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

        logging.info(f"Creating a call {call_module}:{call_function}")
        call: GenericCall = self._interface.compose_call(
            call_module=call_module,
            call_function=call_function,
            call_params=params or None,
        )

        logging.info("Creating extrinsic")
        extrinsic: GenericExtrinsic = self._interface.create_signed_extrinsic(
            call=call, keypair=self._keypair, nonce=nonce
        )

        logging.info("Submitting extrinsic")
        receipt: substrate.ExtrinsicReceipt = self._interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        logging.info(
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

        logging.info(f"Writing datalog {data}")
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

        logging.info(f"Sending {'ON' if toggle else 'OFF'} launch command to {target_address}")
        return self.custom_extrinsic("Launch", "launch", {"robot": target_address, "param": toggle}, nonce)

    def get_account_nonce(self, account_address: tp.Optional[str] = None) -> int:
        """
        Get current account nonce

        @param account_address: account ss58_address. Self address via private key is obtained if not passed.

        @return account nonce. Due to e feature of substrate-interface lib,
        to create an extrinsic with incremented nonce, pass account's current nonce. See
        https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
        for example.
        """

        return self._interface.get_account_nonce(account_address=account_address or self.define_address())

    def rws_bid(self, index: int, amount: int) -> str:
        """
        Bid to win a subscription!


        @param index: Auction index
        @param amount: Your bid in Weiners (!)
        """

        logging.info(f"Bidding on auction {index} with {amount} Weiners (appx. {round(amount / 10 ** 9, 2)} XRT)")
        return self.custom_extrinsic("RWS", "bid", {"index": index, "amount": amount})

    def rws_set_devices(self, devices: tp.List[str]) -> str:
        """
        Set devices which are authorized to use RWS subscriptions held by the extrinsic author

        @param devices: Devices authorized to use RWS subscriptions. Include in list.

        @return: transaction hash
        """

        logging.info(f"Allowing {devices} to use {self.define_address()} subscription")
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

        logging.info("Sending transaction using subscription")
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

        return self._interface.rpc_request(method, params, result_handler)


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
