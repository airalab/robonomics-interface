import logging
import substrateinterface as substrate
import sys
import typing as tp

from dataclasses import dataclass

sys.path.append("../")

from robonomicsinterface.constants import REMOTE_WS, TYPE_REGISTRY
from robonomicsinterface.utils import create_keypair
from robonomicsinterface.types import TypeRegistryTyping

logger = logging.getLogger(__name__)


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
    ) -> None:
        """
        Save node connection parameters and create a keypair to sign transactions and define address if seed was passed
            as a parameter.

        :param seed: Account seed (mnemonic or raw) as a key to sign transactions.
        :param remote_ws: Node url. Default node address is "wss://kusama.rpc.robonomics.network". Another address may
            be specified (e.g. "ws://127.0.0.1:9944" for local node).
        :param type_registry: Types used in the chain. Defaults are the most frequently used in Robonomics.

        """
        self.remote_ws: tp.Optional[str] = remote_ws or REMOTE_WS
        self.type_registry: tp.Optional[TypeRegistryTyping] = type_registry or TYPE_REGISTRY
        if seed:
            self.keypair: substrate.Keypair = create_keypair(seed)
            self.address: str = self.keypair.ss58_address
