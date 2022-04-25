import typing as tp

from account import Account
from logging import getLogger
from sys import path

from custom_functions import CustomFunctions

path.append("../")

from robonomicsinterface.types import AccountTyping

logger = getLogger(__name__)


class CommonFunctions:
    """
    Class for common functions such as getting account information or transferring tokens
    """

    def __init__(self, account: Account):
        """
        Assign Account dataclass parameters and create a custom_functions attribute to be used.

        :param account: Account dataclass with seed, ws address and node type_registry

        """
        self.account: Account = account
        self.custom_functions: CustomFunctions = CustomFunctions(account)

    def account_info(self, addr: tp.Optional[str] = None, block_hash: tp.Optional[str] = None) -> AccountTyping:
        """
        Get account information.

        :param addr: Explored account ss_58 address. Account dataclass address if None.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Account information dictionary.

        """

        account_address: str = addr or self.account.get_address()

        logger.info(f"Getting account {account_address} data")

        return self.custom_functions.custom_chainstate("System", "Account", account_address, block_hash=block_hash)

    def get_account_nonce(self, account_address: tp.Optional[str] = None) -> int:
        """
        Get current account nonce.

        :param account_address: Account ss58_address. Self address via private key is obtained if not passed.

        :return Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with incremented
            nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        """

        logger.info(f"Fetching nonce of account {account_address or self.account.get_address()}")
        return self.custom_functions.custom_rpc_request(
            "system_accountNextIndex", [account_address or self.account.get_address()]
        ).get("result", 0)

    def transfer_tokens(self, target_address: str, tokens: int, nonce: tp.Optional[int] = None) -> str:
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

        return self.custom_functions.custom_extrinsic(
            "Balances", "transfer", {"dest": {"Id": target_address}, "value": tokens}, nonce
        )
