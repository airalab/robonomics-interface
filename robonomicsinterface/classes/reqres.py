import typing as tp

from logging import getLogger

from .base import BaseClass

logger = getLogger(__name__)


class ReqRes(BaseClass):
    """
    Class for handling Robonomics reqres rpc requests
    """

    def p2p_get(
        self, address: str, message: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, int]]:
        """
        Returns for p2p rpc get response.

        :param address: Multiaddr address of the peer to connect to. For example:
            "/ip4/127.0.0.1/tcp/61240/<Peer ID of server>."
            This ID may be obtained on node/server initialization.
        :param message: Request message. ``GET`` for example.
        :param result_handler: Callback function that processes the result received from the node. This function accepts
            one argument - response.

        """

        return self._service_functions.rpc_request("p2p_get", [address, message], result_handler)

    def p2p_ping(
        self, address: str, result_handler: tp.Optional[tp.Callable] = None
    ) -> tp.Dict[str, tp.Union[str, int]]:

        """
        Returns for reqres p2p rpc ping to server response

        :param address: Multiaddr address of the peer to connect to. For example:
            "/ip4/127.0.0.1/tcp/61240/<Peer ID of server>."
            This ID may be obtained on node/server initialization.
        :param result_handler: Callback function that processes the result received from the node. This function accepts
            one argument - response.

        """

        return self._service_functions.rpc_request("p2p_ping", [address], result_handler)
