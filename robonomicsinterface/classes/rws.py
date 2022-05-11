import typing as tp

from logging import getLogger
from sys import path

from base import BaseClass

path.append("../")

from robonomicsinterface.types import AuctionTyping, LedgerTyping

logger = getLogger(__name__)


class RWS(BaseClass):
    """
    Class for interacting with Robonomics Web Services subscriptions
    """

    def get_auction(self, index: int, block_hash: tp.Optional[str] = None) -> tp.Optional[AuctionTyping]:
        """
        Get information about subscription auction.

        :param index: Auction index.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Auction info.

        """

        logger.info(f"Fetching auction {index} information")
        return self.custom_functions.custom_chainstate("RWS", "Auction", index, block_hash=block_hash)

    def get_auction_next(self, block_hash: tp.Optional[str] = None) -> int:
        """
        Get index of the next auction to be unlocked.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Auction index.

        """

        logger.info("Fetching index of the next auction to be unlocked")
        return self.custom_functions.custom_chainstate("RWS", "AuctionNext", block_hash=block_hash)

    def get_auction_queue(self, block_hash: tp.Optional[str] = None) -> tp.List[tp.Optional[int]]:
        """
        Get an auction queue of Robonomics Web Services subscriptions.

        :param block_hash: Retrieves data as of passed block hash.

        :return: Auction queue of Robonomics Web Services subscriptions.

        """

        logger.info("Fetching auctions queue list")
        return self.custom_functions.custom_chainstate("RWS", "AuctionQueue", block_hash=block_hash)

    def get_devices(self, addr: str, block_hash: tp.Optional[str] = None) -> tp.List[tp.Optional[str]]:
        """
        Fetch list of RWS added devices.

        :param addr: Subscription owner.
        :param block_hash: Retrieves data as of passed block hash.

        :return: List of added devices. Empty if none.

        """

        logger.info(f"Fetching list of RWS devices set by owner {addr}")
        return self.custom_functions.custom_chainstate("RWS", "Devices", addr, block_hash=block_hash)

    def get_ledger(self, addr: str, block_hash: tp.Optional[str] = None) -> tp.Optional[LedgerTyping]:
        """
        Subscription information.

        :param addr: Subscription owner.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Subscription information. Empty if none.

        """

        logger.info(f"Fetching subscription information by owner {addr}")
        return self.custom_functions.custom_chainstate("RWS", "Ledger", addr, block_hash=block_hash)

    def bid(self, index: int, amount: int) -> str:
        """
        Bid to win a subscription!

        :param index: Auction index.
        :param amount: Your bid in Weiners.

        :return: Transaction hash.

        """

        logger.info(f"Bidding on auction {index} with {amount} Weiners (appx. {round(amount / 10 ** 9, 2)} XRT)")
        return self.custom_functions.custom_extrinsic("RWS", "bid", {"index": index, "amount": amount})

    def set_devices(self, devices: tp.List[str]) -> str:
        """
        Set devices which are authorized to use RWS subscriptions held by the extrinsic author.

        :param devices: Devices authorized to use RWS subscriptions. Include in list.

        :return: Transaction hash.

        """

        logger.info(f"Allowing {devices} to use {self.account.get_address()} subscription")
        return self.custom_functions.custom_extrinsic("RWS", "set_devices", {"devices": devices})
