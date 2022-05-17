import typing as tp

from logging import getLogger

from .base import BaseClass
from ..exceptions import DigitalTwinMapException
from ..types import DigitalTwinTyping
from ..utils import dt_encode_topic

logger = getLogger(__name__)


class DigitalTwin(BaseClass):
    """
    Class for interacting with `Digital Twins <https://wiki.robonomics.network/docs/en/digital-twins/>`_..
    """

    def get_info(self, dt_id: int, block_hash: tp.Optional[str] = None) -> tp.Optional[DigitalTwinTyping]:
        """
        Fetch information about existing digital twin.

        :param dt_id: Digital Twin object ID.
        :param block_hash: Retrieves data as of passed block hash.

        :return: List of DigitalTwin associated mapping. ``None`` if no Digital Twin with such id.

        """
        logger.info(f"Fetching info about Digital Twin with ID {dt_id}")

        return self._service_functions.chainstate_query("DigitalTwin", "DigitalTwin", dt_id, block_hash=block_hash)

    def get_owner(self, dt_id: int, block_hash: tp.Optional[str] = None) -> tp.Optional[str]:
        """
        Fetch existing Digital Twin owner address.

        :param dt_id: Digital Twin object ID.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Owner address. ``None`` if no Digital Twin with such id.

        """

        logger.info(f"Fetching owner of Digital Twin with ID {dt_id}")

        return self._service_functions.chainstate_query("DigitalTwin", "Owner", dt_id, block_hash=block_hash)

    def get_total(self, block_hash: tp.Optional[str] = None) -> tp.Optional[int]:
        """
        Fetch total number of Digital Twins.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Total number of Digital Twins. ``None`` if no Digital Twins.

        """
        logger.info("Fetching Total number of Digital Twins")

        return self._service_functions.chainstate_query("DigitalTwin", "Total", block_hash=block_hash)

    def get_source(self, dt_id: int, topic: str, block_hash: tp.Optional[str] = None) -> str:
        """
        Find a source for a passed Digital Twin topic.

        :param dt_id: Digital Twin id.
        :param topic: Searched topic. Normal string.
        :param block_hash: Retrieves data as of passed block hash.

        :return: If found, topic source ss58 address.

        """

        dt_map: tp.Optional[DigitalTwinTyping] = self.get_info(dt_id, block_hash=block_hash)
        if not dt_map:
            raise DigitalTwinMapException("No Digital Twin was created or Digital Twin map is empty.")
        topic_hashed: str = dt_encode_topic(topic)
        for source in dt_map:
            if source[0] == topic_hashed:
                return source[1]
        raise DigitalTwinMapException(f"No topic {topic} was found in Digital Twin with id {dt_id}")

    def create(self, nonce: tp.Optional[int] = None) -> tp.Tuple[int, str]:
        """
        Create a new digital twin.

        :param nonce: Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with
            incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Tuple of newly created Digital Twin ID and hash of the creation transaction.

        """

        tr_hash: str = self._service_functions.extrinsic("DigitalTwin", "create", nonce=nonce)
        dt_total: int = self.get_total()
        dt_id: int = dt_total
        for ids in reversed(range(dt_total)):
            if self.get_owner(ids) == self.account.get_address():
                dt_id: int = ids
                break

        return dt_id, tr_hash

    def set_source(self, dt_id: int, topic: str, source: str, nonce: tp.Optional[int] = None) -> tp.Tuple[str, str]:
        """
        Set DT topics and their sources. Since ``topic_name`` is byte encoded and then sha256-hashed, it's considered as
        good practice saving the map of digital twin in human-readable format in the very first DT topic. Still there is
        a ``get_source`` function which transforms given string to the format as saved in the chain for comparing.

        :param dt_id: Digital Twin ID, which should have been created by account, calling this function.
        :param topic: Topic to add. Any string you want. It will be sha256 hashed and stored in blockchain.
        :param source: Source address in ss58 format.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with
            incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Tuple of hashed topic and transaction hash.

        """

        topic_hashed = dt_encode_topic(topic)
        return (
            topic_hashed,
            self._service_functions.extrinsic(
                "DigitalTwin", "set_source", {"id": dt_id, "topic": topic_hashed, "source": source}, nonce=nonce
            ),
        )
