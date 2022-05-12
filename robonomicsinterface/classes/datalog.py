import typing as tp

from logging import getLogger

from .base import BaseClass
from ..types import DatalogTyping

logger = getLogger(__name__)


class Datalog(BaseClass):
    """
    Class for datalog chainstate queries and extrinsic executions.
    """

    def get_index(self, addr: tp.Optional[str] = None, block_hash: tp.Optional[str] = None) -> tp.Dict[str, int]:
        """
        Get account datalog index dictionary.

        :param addr: ss58 type ``32`` address of an account which datalog index is to be obtained. If ``None``, tries to
            get Account datalog index if keypair was created, else raises ``NoPrivateKey``.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Tuple of form {'start': <int>, 'end': <int>}

        """

        address: str = addr or self.account.get_address()

        logger.info(f"Fetching datalog index of {address}")

        return self._service_functions.chainstate_query("Datalog", "DatalogIndex", address, block_hash=block_hash)

    def get_item(
        self, addr: tp.Optional[str] = None, index: tp.Optional[int] = None, block_hash: tp.Optional[str] = None
    ) -> tp.Optional[DatalogTyping]:
        """
        Fetch datalog record of a provided account. Fetch self datalog if no address provided and interface was
        initialized with a seed.

        :param addr: ss58 type ``32`` address of an account which datalog is to be fetched. If ``None``, tries to fetch
            self datalog if keypair was created, else raises ``NoPrivateKey``.
        :param index: record index. case ``int``: fetch datalog by specified index case ``None``: fetch latest datalog.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Tuple. Datalog of the account with a timestamp, ``None`` if no records.

        """

        address: str = addr or self.account.get_address()

        logger.info(
            f"Fetching {'latest datalog record' if not index else 'datalog record #' + str(index)}" f" of {address}."
        )

        if index:
            record: DatalogTyping = self._service_functions.chainstate_query(
                "Datalog", "DatalogItem", [address, index], block_hash=block_hash
            )
            return record if record[0] != 0 else None
        else:
            index_latest: int = self.get_index(address)["end"] - 1
            return (
                self._service_functions.chainstate_query(
                    "Datalog", "DatalogItem", [address, index_latest], block_hash=block_hash
                )
                if index_latest != -1
                else None
            )

    def record(self, data: str, nonce: tp.Optional[int] = None) -> str:
        """
        Write any string to datalog. It has 512 bytes length limit.

        :param data: String to be stored in datalog. It has 512 bytes length limit.
        :param nonce: Nonce of the transaction. Due to the feature of substrate-interface lib, to create an extrinsic
            with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the datalog record transaction.

        """

        logger.info(f"Writing datalog {data}")
        return self._service_functions.extrinsic("Datalog", "record", {"record": data}, nonce)

    def erase(self, nonce: tp.Optional[int] = None) -> str:
        """
        Erase ALL datalog records of Account.

        :param nonce: Nonce of the transaction. Due to the feature of substrate-interface lib, to create an extrinsic
            with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the datalog erase transaction.

        """

        logger.info(f"Erasing all datalogs of Account")
        return self._service_functions.extrinsic("Datalog", "erase", nonce)
