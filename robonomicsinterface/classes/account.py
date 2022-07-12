import typing as tp

from dataclasses import dataclass
from logging import getLogger
from substrateinterface import Keypair, KeypairType

from ..constants import REMOTE_WS, TYPE_REGISTRY
from ..exceptions import NoPrivateKeyException
from ..types import TypeRegistryTyping
from ..utils import create_keypair

logger = getLogger(__name__)


@dataclass
class Account:
    """
    Dataclass to hold account info and node connection parameters

    """

    def __init__(
        self,
        seed: tp.Optional[str] = None,
        remote_ws: tp.Optional[str] = None,
        type_registry: tp.Optional[TypeRegistryTyping] = None,
        crypto_type: int = KeypairType.SR25519,
    ) -> None:
        """
        Save node connection parameters and create a keypair to sign transactions and define address if seed was passed
            as a parameter.

        :param seed: Account seed (mnemonic or raw) as a key to sign transactions.
        :param remote_ws: Node url. Default node address is "wss://kusama.rpc.robonomics.network". Another address may
            be specified (e.g. "ws://127.0.0.1:9944" for local node).
        :param type_registry: Types used in the chain. Defaults are the most frequently used in Robonomics.
        :param crypto_type: Use KeypairType.SR25519 or KeypairType.ED25519 cryptography for generating the Keypair.

        """
        self.remote_ws: str = remote_ws or REMOTE_WS
        self.type_registry: TypeRegistryTyping = type_registry or TYPE_REGISTRY
        if seed:
            self.keypair: Keypair = create_keypair(seed, crypto_type)
            self._address: str = self.keypair.ss58_address
        else:
            self.keypair = None

    def get_address(self) -> str:
        """
        Determine account address if seed was passed when creating an instance

        :return: Account ss58 address

        """
        if not self.keypair:
            raise NoPrivateKeyException("No private key was provided, unable to determine account address")
        return str(self.keypair.ss58_address)
