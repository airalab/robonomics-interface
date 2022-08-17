import typing as tp

from logging import getLogger

from .base import BaseClass
from ..types import ListenersResponse

logger = getLogger(__name__)


class PubSub(BaseClass):
    """
    Class for handling Robonomics pubsub rpc requests

    WARNING: THIS MODULE IS UNDER CONSTRUCTION, USE AT YOUR OWN RISK! TO BE UPDATED SOON
    """

    def connect(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Connect to peer and add it into swarm.

        :param address: Multiaddr address of the peer to connect to.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_connect", [address], result_handler)

    def listen(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Listen address for incoming connections.

        :param address: Multiaddr address of the peer to connect to.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_listen", [address], result_handler)

    def get_listeners(self, result_handler: tp.Optional[tp.Callable] = None) -> ListenersResponse:
        """
        Returns a list of node addresses.

        :param result_handler: Callback function that processes the result received from the node.

        :return: List of node addresses in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_listeners", None, result_handler)

    def get_peer(self, result_handler: tp.Optional[tp.Callable] = None) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Returns local peer ID.

        :return: Local peer ID in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_peer", None, result_handler)

    def publish(
        self, topic_name: str, message: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Publish message into the topic by name.

        :param topic_name: Topic name.
        :param message: Message to be published.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_publish", [topic_name, message], result_handler)

    def subscribe(
        self, topic_name: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Listen address for incoming connections.

        :param topic_name: Topic name to subscribe to.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Subscription ID in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_subscribe", [topic_name], result_handler)

    def unsubscribe(
        self, subscription_id: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, bool, int]]:
        """
        Unsubscribe for incoming messages from topic.

        :param subscription_id: Subscription ID obtained when subscribed.
        :param result_handler: Callback function that processes the result received from the node.

        :return: Success flag in JSON message.

        """

        return self._service_functions.rpc_request("pubsub_unsubscribe", [subscription_id], result_handler)
