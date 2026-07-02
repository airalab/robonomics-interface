import typing as tp

from logging import getLogger

from .base import BaseClass
from ..exceptions import RPCRequestException
from ..types import AccountTyping

logger = getLogger(__name__)


class CommonFunctions(BaseClass):
    """
    Class for common functions such as getting account information or transferring tokens
    """

    def get_account_info(self, addr: tp.Optional[str] = None, block_hash: tp.Optional[str] = None) -> AccountTyping:
        """
        Get account information.

        :param addr: Explored account ss58 address. Account dataclass address if None.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Account information dictionary.

        """

        account_address: str = addr or self.account.get_address()

        logger.info(f"Getting account {account_address} data")

        return self._service_functions.chainstate_query("System", "Account", account_address, block_hash=block_hash)

    def get_account_nonce(self, addr: tp.Optional[str] = None) -> int:
        """
        Get current account nonce.

        :param addr: Account ss58 address. Self address via private key is obtained if not passed.

        :return Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with incremented
            nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        """

        account_address: str = addr or self.account.get_address()

        logger.info(f"Fetching nonce of account {account_address}")

        response = self._service_functions.rpc_request(
            "system_accountNextIndex", [account_address], result_handler=None
        )
        if "error" in response:
            raise RPCRequestException(
                "Failed to fetch account nonce from system_accountNextIndex",
                error=response["error"],
            )
        if "result" not in response:
            raise RPCRequestException(
                "Malformed system_accountNextIndex response: missing result"
            )
        return response["result"]

    def transfer_tokens(self, target_address: str, tokens: int, nonce: tp.Optional[int] = None) -> str:
        """
        Send tokens to target address and keep the sender account alive.

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

        return self._service_functions.extrinsic(
            "Balances",
            "transfer_keep_alive",
            {"dest": {"Id": target_address}, "value": tokens},
            nonce,
        )

    def transfer_tokens_allow_death(self, target_address: str, tokens: int, nonce: tp.Optional[int] = None) -> str:
        """
        Send tokens to target address and allow the sender account to be reaped.

        :param target_address: Account that will receive tokens.
        :param tokens: Number of tokens to be sent, in Wei, so if you want to send 1 XRT, you should send
            "1 000 000 000" units.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib,
            to create an extrinsic with incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Hash of the transfer transaction.

        """

        logger.info(f"Sending tokens to {target_address} and allowing account death")

        return self._service_functions.extrinsic(
            "Balances",
            "transfer_allow_death",
            {"dest": {"Id": target_address}, "value": tokens},
            nonce,
        )
