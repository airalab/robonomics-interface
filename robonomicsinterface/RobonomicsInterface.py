import hashlib
import logging

import substrateinterface as substrate
import typing as tp

from base58 import b58decode, b58encode
from enum import Enum
from scalecodec.types import GenericCall, GenericExtrinsic
from scalecodec.base import RuntimeConfiguration, ScaleBytes, ScaleType
from substrateinterface.exceptions import ExtrinsicFailedException
from websocket import WebSocketConnectionClosedException

from .constants import REMOTE_WS, TYPE_REGISTRY
from .decorators import connect_close_substrate_node
from .exceptions import NoPrivateKey, DigitalTwinMapError

DatalogTyping = tp.Tuple[int, tp.Union[int, str]]
LiabilityTyping = tp.Dict[str, tp.Union[tp.Dict[str, tp.Union[str, int]], str]]
ReportTyping = tp.Dict[str, tp.Union[int, str, tp.Dict[str, str]]]
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

        :param seed: Account seed in mnemonic/raw form. When not passed, no extrinsics functionality.
        :param remote_ws: Node url. Default node address is "wss://kusama.rpc.robonomics.network".
        Another address may be specified (e.g. "ws://127.0.0.1:9944" for local node).
        :param type_registry: Types used in the chain. Defaults are the most frequently used in Robonomics.

        """

        self.keypair: tp.Optional[substrate.Keypair] = self._create_keypair(seed) if seed else None
        self.remote_ws = remote_ws or REMOTE_WS
        self.type_registry = type_registry or TYPE_REGISTRY
        self.interface: tp.Optional[substrate.SubstrateInterface] = None
        # This is a dummy since interface is opened-closed every time it's needed

    @staticmethod
    def _create_keypair(seed: str) -> substrate.Keypair:
        """
        Create a keypair for further use.

        :param seed: Account seed as a key to sign transactions.

        :return: A Keypair instance used by substrate to sign transactions.

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

    def account_info(
        self, addr: tp.Optional[str] = None, block_hash: tp.Optional[str] = None
    ) -> tp.Dict[str, tp.Union[int, tp.Dict[str, int]]]:
        """
        Get account information.

        :param addr: Explored account ss_58 address.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Account information dictionary.

        """
        account_address: str = addr or self.define_address()

        logger.info(f"Getting account {account_address} data")

        return self.custom_chainstate("System", "Account", account_address, block_hash=block_hash)

    def define_address(self) -> str:
        """
        Define ss58_address of an account, which seed was provided while initializing an interface.

        :return: ss58_address of an account.

        """

        if not self.keypair:
            raise NoPrivateKey("No private key was provided, unable to determine self address")
        return str(self.keypair.ss58_address)

    def fetch_datalog(
        self, addr: tp.Optional[str] = None, index: tp.Optional[int] = None, block_hash: tp.Optional[str] = None
    ) -> tp.Optional[DatalogTyping]:
        """
        Fetch datalog record of a provided account. Fetch self datalog if no address provided and interface was
        initialized with a seed.

        :param addr: ss58 type 32 address of an account which datalog is to be fetched. If None, tries to fetch self
            datalog if keypair was created, else raises NoPrivateKey.
        :param index: record index. case int: fetch datalog by specified index case None: fetch latest datalog.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Tuple. Datalog of the account with a timestamp, None if no records.

        """

        address: str = addr or self.define_address()

        logger.info(
            f"Fetching {'latest datalog record' if not index else 'datalog record #' + str(index)}" f" of {address}."
        )

        if index:
            record: DatalogTyping = self.custom_chainstate(
                "Datalog", "DatalogItem", [address, index], block_hash=block_hash
            )
            return record if record[0] != 0 else None
        else:
            index_latest: int = (
                self.custom_chainstate("Datalog", "DatalogIndex", address, block_hash=block_hash)["end"] - 1
            )
            return (
                self.custom_chainstate("Datalog", "DatalogItem", [address, index_latest], block_hash=block_hash)
                if index_latest != -1
                else None
            )

    def rws_auction_queue(self, block_hash: tp.Optional[str] = None) -> tp.List[tp.Optional[int]]:
        """
        Get an auction queue of Robonomics Web Services subscriptions.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Auction queue of Robonomics Web Services subscriptions.

        """

        logger.info("Fetching auctions queue list")
        return self.custom_chainstate("RWS", "AuctionQueue", block_hash=block_hash)

    def rws_auction(self, index: int, block_hash: tp.Optional[str] = None) -> tp.Dict[str, tp.Union[str, int, dict]]:
        """
        Get to now information about subscription auction.

        :param index: Auction index.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Auction info.

        """

        logger.info(f"Fetching auction {index} information")
        return self.custom_chainstate("RWS", "Auction", index, block_hash=block_hash)

    def rws_list_devices(self, addr: str, block_hash: tp.Optional[str] = None) -> tp.List[tp.Optional[str]]:
        """
        Fetch list of RWS added devices.

        :param addr: Subscription owner.
        :param block_hash: Retrieves data as of passed block hash.

        :return: List of added devices. Empty if none.

        """

        logger.info(f"Fetching list of RWS devices set by owner {addr}")

        return self.custom_chainstate("RWS", "Devices", addr, block_hash=block_hash)

    def dt_info(self, dt_id: int, block_hash: tp.Optional[str] = None) -> tp.Optional[tp.List[tp.Tuple[str, str]]]:
        """
        Fetch information about existing digital twin.

        :param dt_id: Digital Twin object ID.
        :param block_hash: Retrieves data as of passed block hash.

        :return: List of DigitalTwin associated mapping. None if no Digital Twin with such id.

        """
        logger.info(f"Fetching info about Digital Twin with ID {dt_id}")

        return self.custom_chainstate("DigitalTwin", "DigitalTwin", dt_id, block_hash=block_hash)

    def dt_owner(self, dt_id: int, block_hash: tp.Optional[str] = None) -> tp.Optional[str]:
        """
        Fetch existing Digital Twin owner address.

        :param dt_id: Digital Twin object ID.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Owner address. None if no Digital Twin with such id.

        """
        logger.info(f"Fetching owner of Digital Twin with ID {dt_id}")

        return self.custom_chainstate("DigitalTwin", "Owner", dt_id, block_hash=block_hash)

    def dt_total(self, block_hash: tp.Optional[str] = None) -> tp.Optional[int]:
        """
        Fetch total number of Digital Twins.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Total number of Digital Twins. None no Digital Twins.

        """
        logger.info("Fetching Total number of Digital Twins")

        return self.custom_chainstate("DigitalTwin", "Total", block_hash=block_hash)

    def dt_get_source(self, dt_id: int, topic: str) -> str:
        """
        Find a source for a passed Digital Twin topic.

        :param dt_id: Digital Twin id.
        :param topic: Searched topic. Normal string.

        :return: If found, topic source ss58 address.

        """

        topic_hashed: str = self.dt_encode_topic(topic)
        dt_map: tp.Optional[tp.List[tp.Tuple[str, str]]] = self.dt_info(dt_id)
        if not dt_map:
            raise DigitalTwinMapError("No Digital Twin was created or Digital Twin map is empty.")
        for source in dt_map:
            if source[0] == topic_hashed:
                return source[1]
        raise DigitalTwinMapError(f"No topic {topic} was found in Digital Twin with id {dt_id}")

    def liability_info(self, liability_index: int, block_hash: tp.Optional[str] = None) -> tp.Optional[LiabilityTyping]:
        """
        Fetch information about existing liabilities.

        :param liability_index: Liability item index.
        :param block_hash: block_hash: Retrieves data as of passed block hash.

        :return: Liability information: technics, economics, promisee, promisor, signatures. None if no such liability.

        """
        logger.info(f"Fetching information about liability with index {liability_index}")

        return self.custom_chainstate("Liability", "AgreementOf", liability_index, block_hash=block_hash)

    def liability_total(self, block_hash: tp.Optional[str] = None) -> tp.Optional[int]:
        """
        Fetch total number of liabilities in chain.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Total number of liabilities in chain. None no liabilities.

        """

        logger.info("Fetching total number of liabilities in chain.")

        return self.custom_chainstate("Liability", "LatestIndex", block_hash=block_hash)

    def liability_report(self, report_index: int, block_hash: tp.Optional[str] = None) -> ReportTyping:
        """
        Fetch information about existing liability reports.

        :param report_index: Reported liability item index.
        :param block_hash: block_hash: Retrieves data as of passed block hash.

        :return: Liability report information: index, promisor, report, signature. None if no such liability report.

        """

        logger.info(f"Fetching information about reported liability with index {report_index}")

        return self.custom_chainstate("Liability", "ReportOf", report_index, block_hash=block_hash)

    @connect_close_substrate_node
    def get_account_nonce(self, account_address: tp.Optional[str] = None) -> int:
        """
        Get current account nonce.

        :param account_address: Account ss58_address. Self address via private key is obtained if not passed.

        :return Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with incremented
            nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        """

        logger.info(f"Fetching nonce of account {account_address or self.define_address()}")
        return self.interface.get_account_nonce(account_address=account_address or self.define_address())

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
        at https://parachain.robonomics.network/#/extrinsics.

        :param call_module: Call module from extrinsic tab on portal.
        :param call_function: Call function from extrinsic tab on portal.
        :param params: Call parameters as a dictionary. None for no parameters.
        :param nonce: Transaction nonce, defined automatically if None. Due to the feature of substrate-interface lib,
            to create an extrinsic with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Extrinsic hash.

        """

        if not self.keypair:
            raise NoPrivateKey("No seed was provided, unable to use extrinsics.")

        logger.info(f"Creating a call {call_module}:{call_function}")
        call: GenericCall = self.interface.compose_call(
            call_module=call_module, call_function=call_function, call_params=params or None
        )

        logger.info("Creating extrinsic")
        extrinsic: GenericExtrinsic = self.interface.create_signed_extrinsic(
            call=call, keypair=self.keypair, nonce=nonce
        )

        logger.info("Submitting extrinsic")
        receipt: substrate.ExtrinsicReceipt = self.interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        if not receipt.is_success:
            raise ExtrinsicFailedException()
        logger.info(
            f"Extrinsic {receipt.extrinsic_hash} for RPC {call_module}:{call_function} submitted and "
            f"included in block {receipt.block_hash}"
        )

        return str(receipt.extrinsic_hash)

    def send_tokens(self, target_address: str, tokens: int, nonce: tp.Optional[int] = None) -> str:
        """
        Send tokens to target address.

        :param target_address: Account that will receive tokens.
        :param tokens: Number of tokens to be sent, in Wei, so if you want to send 1 XRT, you should send
            "1 000 000 000" units.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib,
            to create an extrinsic with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the transfer transaction.

        """

        logger.info(f"Sending tokens to {target_address}")

        return self.custom_extrinsic("Balances", "transfer", {"dest": {"Id": target_address}, "value": tokens}, nonce)

    def record_datalog(self, data: str, nonce: tp.Optional[int] = None) -> str:
        """
        Write any string to datalog.

        :param data: String to be stored in datalog.
        :param nonce: Nonce of the transaction. Due to the feature of substrate-interface lib,
            to create an extrinsic with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the datalog transaction.

        """

        logger.info(f"Writing datalog {data}")
        return self.custom_extrinsic("Datalog", "record", {"record": data}, nonce)

    def send_launch(self, target_address: str, parameter: str, nonce: tp.Optional[int] = None) -> str:
        """
        Send Launch command to device.

        :param target_address: Device to be triggered with launch.
        :param parameter: Launch command accompanying parameter. Should be a 32 bytes data. Also, IPFS Qm... hash is
            supported.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib,
            to create an extrinsic with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the launch transaction.

        """

        logger.info(f"Sending launch command to {target_address}")

        if parameter.startswith("Qm"):
            parameter = self.ipfs_qm_hash_to_32_bytes(parameter)

        return self.custom_extrinsic("Launch", "launch", {"robot": target_address, "param": parameter}, nonce)

    def dt_create(self) -> tp.Tuple[int, str]:
        """
        Create a new digital twin.

        :return: Tuple of newly created Digital Twin ID and hash of the creation transaction.

        """

        tr_hash: str = self.custom_extrinsic("DigitalTwin", "create")
        dt_total: int = self.dt_total()
        dt_id: int = dt_total
        for ids in reversed(range(dt_total)):
            if self.dt_owner(ids) == self.define_address():
                dt_id: int = ids
                break

        return dt_id, tr_hash

    @staticmethod
    def dt_encode_topic(topic: str) -> str:
        """
        Encode any string to be accepted by Digital Twin setSource. Use byte encoding and sha256-hashing.

        :param topic: Topic name to be encoded.

        :return: Hashed-encoded topic name

        """

        return f"0x{hashlib.sha256(topic.encode('utf-8')).hexdigest()}"

    def dt_set_source(self, dt_id: int, topic: str, source: str) -> tp.Tuple[str, str]:
        """
        Set DT topics and their sources. Since topic_name is byte encoded and then sha256-hashed, it's considered as
        good practice saving the map of digital twin in human-readable format in the very first DT topic. Still there is
        a dt_get_source function which transforms given string to the format as saved in the chain for comparing.

        :param dt_id: Digital Twin ID, which should have been created by this function calling account.
        :param topic: Topic to add. The string is sha256 hashed and stored in blockchain.
        :param source: Source address in ss58 format.

        :return: Tuple of hashed topic and transaction hash.

        """

        topic_hashed = self.dt_encode_topic(topic)
        return (
            topic_hashed,
            self.custom_extrinsic("DigitalTwin", "set_source", {"id": dt_id, "topic": topic_hashed, "source": source}),
        )

    @staticmethod
    def ipfs_32_bytes_to_qm_hash(string_32_bytes: str) -> str:
        """
        Transform 32 bytes sting (without 2 heading bytes) to an IPFS base58 Qm... hash.

        :param string_32_bytes: 32 bytes sting (without 2 heading bytes).

        :return: IPFS base58 Qm... hash.

        """

        if string_32_bytes.startswith("0x"):
            string_32_bytes = string_32_bytes[2:]
        return b58encode(b"\x12 " + bytes.fromhex(string_32_bytes)).decode("utf-8")

    @staticmethod
    def ipfs_qm_hash_to_32_bytes(ipfs_qm: str) -> str:
        """
        Transform IPFS base58 Qm... hash to a 32 bytes sting (without 2 heading bytes).

        :param ipfs_qm: IPFS base58 Qm... hash.

        :return: 32 bytes sting (without 2 heading bytes).

        """

        return f"0x{b58decode(ipfs_qm).hex()[4:]}"

    def create_liability(
        self,
        technics_hash: str,
        economics: int,
        promisee: str,
        promisor: str,
        promisee_params_signature: str,
        promisor_params_signature: str,
    ) -> tp.Tuple[int, str]:
        """
        Create a liability to ensure economical relationships between robots! This is a contract to be assigned to a
        promisor by promisee. As soon as the job is done and reported, the promisor gets his reward.
        This extrinsic may be submitted by another address, but there should be promisee and promisor signatures.

        :param technics_hash: Details of the liability, where the promisee order is described. Accepts any 32-bytes data
            or a base58 (Qm...) IPFS hash.
        :param economics: Promisor reward in Weiners.
        :param promisee: Promisee (customer) ss58_address
        :param promisor: Promisor (worker) ss58_address
        :param promisee_params_signature: An agreement proof. This is a private key signed message containing technics
            and economics. Both sides need to do this. Signed by promisee.
        :param promisor_params_signature: An agreement proof. This is a private key signed message containing the same
            technics and economics. Both sides need to do this. Signed by promisor.

        :return: New liability index and hash of the liability creation transaction.

        """

        logger.info(
            f"Creating new liability with promisee {promisee}, promisor {promisor}, technics {technics_hash} and"
            f"economics {economics}."
        )

        if technics_hash.startswith("Qm"):
            technics_hash = self.ipfs_qm_hash_to_32_bytes(technics_hash)

        liability_creation_transaction_hash: str = self.custom_extrinsic(
            "Liability",
            "create",
            {
                "agreement": {
                    "technics": {"hash": technics_hash},
                    "economics": {"price": economics},
                    "promisee": promisee,
                    "promisor": promisor,
                    "promisee_signature": {"Sr25519": promisee_params_signature},
                    "promisor_signature": {"Sr25519": promisor_params_signature},
                }
            },
        )

        liability_total: int = self.liability_total()
        index: int = liability_total - 1
        for liabilities in reversed(range(liability_total)):
            if self.liability_info(liabilities)["promisee_signature"]["Sr25519"] == promisee_params_signature:
                index = liabilities
                break

        return index, liability_creation_transaction_hash

    def sign_create_liability(self, technics_hash: str, economics: int) -> str:
        """
        Sign liability params approve message with a private key. This function is meant to sign technics and economics
        details message to state the agreement of promisee and promisor. Both sides need to do this.

        :param technics_hash: Details of the liability, where the promisee order is described. Accepts any 32-bytes data
            or a base58 (Qm...) IPFS hash.
        :param economics: Promisor reward in Weiners.

        :return: Signed message 64-byte hash in sting form.

        """

        if not self.keypair:
            raise NoPrivateKey("No private key, unable to sign a message")

        if technics_hash.startswith("Qm"):
            technics_hash = self.ipfs_qm_hash_to_32_bytes(technics_hash)

        logger.info(f"Signing proof with technics {technics_hash} and economics {economics}.")

        h256_scale_obj: ScaleType = RuntimeConfiguration().create_scale_object("H256")
        technics_scale: ScaleBytes = h256_scale_obj.encode(technics_hash)

        compact_scale_obj: ScaleType = RuntimeConfiguration().create_scale_object("Compact<Balance>")
        economics_scale: ScaleBytes = compact_scale_obj.encode(economics)

        return f"0x{self.keypair.sign(technics_scale + economics_scale).hex()}"

    def finalize_liability(
        self,
        index: int,
        report_hash: str,
        promisor: tp.Optional[str] = None,
        promisor_finalize_signature: tp.Optional[str] = None,
    ) -> str:
        """
        Report on a completed job to receive a deserved award. This may be done by another address, but there should be
        a liability promisor signature.

        :param index: Liability item index.
        :param report_hash: IPFS hash of a report data (videos, text, etc). Accepts any 32-bytes data or a base58
            (Qm...) IPFS hash.
        :param promisor: Promisor (worker) ss58_address. If not passed, replaced with transaction author address.
        :param promisor_finalize_signature: 'Job done' proof. A message containing liability index and report data
            signed by promisor. If not passed, this message is signed by a transaction author which should be a promisor
            so.

        :return: Liability finalization transaction hash

        """

        logger.info(f"Finalizing liability {index} by promisor {promisor or self.define_address()}.")

        if report_hash.startswith("Qm"):
            report_hash = self.ipfs_qm_hash_to_32_bytes(report_hash)

        return self.custom_extrinsic(
            "Liability",
            "finalize",
            {
                "report": {
                    "index": index,
                    "sender": promisor or self.define_address(),
                    "payload": {"hash": report_hash},
                    "signature": {
                        "Sr25519": promisor_finalize_signature or self.sign_liability_finalize(index, report_hash)
                    },
                }
            },
        )

    def sign_liability_finalize(self, index: int, report_hash: str) -> str:
        """
        Sing liability finalization parameters proof message with a private key. This is meant to state that the job is
        done by promisor.

        :param index: Liability item index.
        :param report_hash: IPFS hash of a report data (videos, text, etc). Accepts any 32-bytes data or a base58
            (Qm...) IPFS hash.

        :return: Signed message 64-byte hash in sting form.

        """

        if not self.keypair:
            raise NoPrivateKey("No private key, unable to sign a message")

        if report_hash.startswith("Qm"):
            report_hash = self.ipfs_qm_hash_to_32_bytes(report_hash)

        logger.info(f"Signing report for liability {index} with report_hash {report_hash}.")

        u64_scale_obj: ScaleType = RuntimeConfiguration().create_scale_object("U32")
        index_scale: ScaleBytes = u64_scale_obj.encode(index)

        h256_scale_obj: ScaleType = RuntimeConfiguration().create_scale_object("H256")
        technics_scale: ScaleBytes = h256_scale_obj.encode(report_hash)

        return f"0x{self.keypair.sign(index_scale + technics_scale).hex()}"

    def rws_bid(self, index: int, amount: int) -> str:
        """
        Bid to win a subscription!

        :param index: Auction index.
        :param amount: Your bid in Weiners.

        :return: Transaction hash.

        """

        logger.info(f"Bidding on auction {index} with {amount} Weiners (appx. {round(amount / 10 ** 9, 2)} XRT)")
        return self.custom_extrinsic("RWS", "bid", {"index": index, "amount": amount})

    def rws_set_devices(self, devices: tp.List[str]) -> str:
        """
        Set devices which are authorized to use RWS subscriptions held by the extrinsic author.

        :param devices: Devices authorized to use RWS subscriptions. Include in list.

        :return: Transaction hash.

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
        Send transaction from a device given a RWS subscription.

        :param subscription_owner_addr: Subscription owner, the one who granted this device ability to send
            transactions.
        :param call_module: Call module from extrinsic tab on portal.
        :param call_function: Call function from extrinsic tab on portal.
        :param params: Call parameters as a dictionary. None for no parameters.

        :return: Transaction hash.

        """

        logger.info(
            f"Sending {call_module}.{call_function} transaction using subscription of {subscription_owner_addr}"
        )
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

        :param subscription_owner_addr: Subscription owner, the one who granted this device ability to send
            transactions.
        :param data: String to be stored in datalog.

        :return: Hash of the datalog transaction.

        """

        return self.rws_custom_call(subscription_owner_addr, "Datalog", "record", {"record": data})

    def rws_send_launch(self, subscription_owner_addr: str, target_address: str, parameter: str) -> str:
        """
        Send Launch command to device from another device which was granted a subscription.

        :param subscription_owner_addr: Subscription owner, the one who granted this device ability to send
            transactions.
        :param target_address: device to be triggered with launch.
        :param parameter: Launch command accompanying parameter. Should be a 32 bytes data. Also, IPFS Qm... hash is
            supported.

        :return: Hash of the launch transaction.

        """

        if parameter.startswith("Qm"):
            parameter = self.ipfs_qm_hash_to_32_bytes(parameter)

        return self.rws_custom_call(
            subscription_owner_addr, "Launch", "launch", {"robot": target_address, "param": parameter}
        )

    def rws_dt_create(self, subscription_owner_addr: str) -> tp.Tuple[int, str]:
        """
        Create a Digital Twin from a device which was granted a subscription.

        :param subscription_owner_addr: Subscription owner, the one who granted this device ability to send
            transactions.

        :return: Tuple of newly created Digital Twin ID and hash of the creation transaction.

        """

        tr_hash: str = self.rws_custom_call(subscription_owner_addr, "DigitalTwin", "create")
        dt_total: int = self.dt_total()
        dt_id: int = dt_total
        for ids in reversed(range(dt_total)):
            if self.dt_owner(ids) == self.define_address():
                dt_id: int = ids
                break

        return dt_id, tr_hash

    def rws_dt_set_source(
        self, subscription_owner_addr: str, dt_id: int, topic: str, source: str
    ) -> tp.Tuple[str, str]:
        """
        Set DT topics and their sources from a device which was granted a subscription. Since topic_name is byte encoded
        and then sha256-hashed, it's considered as good practice saving the map of digital twin in human-readable
        format in the very first DT topic. Still there is a dt_get_source function which transforms given string
        to the format as saved in the chain for comparing.

        :param subscription_owner_addr: Subscription owner, the one who granted this device ability to send
            transactions.
        :param dt_id: Digital Twin ID, which should have been created by this function calling account.
        :param topic: Topic to add. The passed string is sha256 hashed and stored in blockchain.
        :param source: Source address in ss58 format.

        :return: Tuple of hashed topic and transaction hash.

        """

        topic_hashed = self.dt_encode_topic(topic)
        return (
            topic_hashed,
            self.rws_custom_call(
                subscription_owner_addr,
                "DigitalTwin",
                "set_source",
                {"id": dt_id, "topic": topic_hashed, "source": source},
            ),
        )

    @connect_close_substrate_node
    def custom_rpc_request(
        self, method: str, params: tp.Optional[tp.List[str]], result_handler: tp.Optional[tp.Callable]
    ) -> dict:
        """
        Method that handles the actual RPC request to the Substrate node. The other implemented functions eventually
        use this method to perform the request.

        :param method: Method of the JSONRPC request.
        :param params: A list containing the parameters of the JSONRPC request.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Result of the request.

        """

        return self.interface.rpc_request(method, params, result_handler)

    @connect_close_substrate_node
    def subscribe_block_headers(self, callback: callable) -> dict:
        """
        Get chain head block headers.

        :return: Chain head block headers.

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

        :param interface: RobonomicsInterface instance.

        """

        self._pubsub_interface = interface

    def connect(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Connect to peer and add it into swarm.

        :param address: Multiaddr address of the peer to connect to.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_connect", [address], result_handler)

    def listen(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Listen address for incoming connections.

        :param address: Multiaddr address of the peer to connect to.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_listen", [address], result_handler)

    def listeners(
        self, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, tp.List[str], int]]:
        """
        Returns a list of node addresses.

        :param result_handler: Callback function that processes the result received from the node.

        :return: List of node addresses in JSON message.

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_listeners", None, result_handler)

    def peer(self, result_handler: tp.Optional[tp.Callable] = None) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Returns local peer ID.

        :return: Local peer ID in JSON message.

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_peer", None, result_handler)

    def publish(self, topic_name: str, message: str, result_handler: tp.Optional[tp.Callable] = None) -> tp.Any:
        """
        Publish message into the topic by name.

        :param topic_name: Topic name.
        :param message: Message to be published.
        :param result_handler: Callback function that processes the result received from the node.

        :return: TODO

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_publish", [topic_name, message], result_handler)

    def subscribe(
        self, topic_name: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Listen address for incoming connections.

        :param topic_name: Topic name to subscribe to.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Subscription ID in JSON message.

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_subscribe", [topic_name], result_handler)

    def unsubscribe(
        self, subscription_id: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Unsubscribe for incoming messages from topic.

        :param subscription_id: Subscription ID obtained when subscribed.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._pubsub_interface.custom_rpc_request("pubsub_unsubscribe", [subscription_id], result_handler)


class SubEvent(Enum):
    NewRecord = "NewRecord"
    NewLaunch = "NewLaunch"
    Transfer = "Transfer"
    TopicChanged = "TopicChanged"
    NewDevices = "NewDevices"


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
        Initiates an instance for further use and starts a subscription for a selected action.

        :param interface: RobonomicsInterface instance
        :param subscribed_event: Event in substrate chain to be awaited. Choose from [NewRecord, NewLaunch, Transfer].
            This parameter should be a SubEvent class attribute. This also requires importing this class.
        :param subscription_handler: Callback function that processes the updates of the storage.
            THIS FUNCTION IS MEANT TO ACCEPT ONLY ONE ARGUMENT (THE NEW EVENT DESCRIPTION TUPLE).
        :param addr: ss58 type 32 address(-es) of an account(-s) which is(are) meant to be event target. If None, will
            subscribe to all such events never-mind target address(-es).

        """

        self._subscriber_interface: substrate.SubstrateInterface = substrate.SubstrateInterface(
            url=interface.remote_ws,
            ss58_format=32,
            type_registry_preset="substrate-node-template",
            type_registry=interface.type_registry,
        )

        self._event: SubEvent = subscribed_event
        self._callback: callable = subscription_handler
        self._target_address: tp.Optional[tp.Union[tp.List[str], str]] = addr

        self._subscribe_event()

    def _subscribe_event(self) -> None:
        """
        Subscribe to events targeted to a certain account (launch, transfer). Call subscription_handler when updated.
        """

        logger.info(f"Subscribing to event {self._event.value} for target addresses {self._target_address}")
        try:
            self._subscriber_interface.subscribe_block_headers(self._event_callback)
        except WebSocketConnectionClosedException:
            self._subscribe_event()

    def _event_callback(self, index_obj: tp.Any, update_nr: int, subscription_id: int) -> None:
        """
        Function, processing updates in event list storage. On update filters events to a desired account
        and passes the event description to the user-provided callback method.

        :param index_obj: Updated event list.
        :param update_nr: Update counter. Increments every new update added. Starts with 0.
        :param subscription_id: Subscription ID.

        """

        if update_nr != 0:
            chain_events: list = self._subscriber_interface.query("System", "Events").value
            for events in chain_events:
                if events["event_id"] == self._event.value:
                    if self._target_address is None:
                        self._callback(events["event"]["attributes"])  # All events
                    elif (
                        events["event"]["attributes"][0 if self._event == SubEvent.NewRecord else 1]
                        in self._target_address
                    ):
                        self._callback(events["event"]["attributes"])  # address-targeted


class ReqRes:
    """
    Class for handling Robonomics reqres rpc requests
    """

    def __init__(self, interface: RobonomicsInterface) -> None:
        """
        Initiate an instance for further use.

        :param interface: RobonomicsInterface instance.

        """
        self._reqres_interface = interface

    def p2p_get(self, address: str, message: str, result_handler: tp.Optional[tp.Callable] = None):
        """
        Returns for p2p rpc get response.

        :param address: Multiaddr address of the peer to connect to. For example:
            "/ip4/127.0.0.1/tcp/61240/<Peer ID of server>."
            This ID may be obtained on node/server initialization.
        :param message: Request message. "GET" for example.
        :param result_handler: Callback function that processes the result received from the node. This function accepts
            one argument - response.

        """

        return self._reqres_interface.custom_rpc_request("p2p_get", [address, message], result_handler)

    def p2p_ping(self, address: str, result_handler: tp.Optional[tp.Callable] = None):

        """
        Returns for reqres p2p rpc ping to server response

        :param address: Multiaddr address of the peer to connect to. For example:
            "/ip4/127.0.0.1/tcp/61240/<Peer ID of server>."
            This ID may be obtained on node/server initialization.
        :param result_handler: Callback function that processes the result received from the node. This function accepts
            one argument - response.

        """

        return self._reqres_interface.custom_rpc_request("p2p_ping", [address], result_handler)
