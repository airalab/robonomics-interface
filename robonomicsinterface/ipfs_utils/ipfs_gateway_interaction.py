"""
A simple utility to upload and download content through ipfs gateways, local or public, with authentication or not.
"""
import logging
import requests
import typing as tp

from ast import literal_eval
from substrateinterface import Keypair

from ..exceptions import FailedToUploadFile
from ..utils import create_keypair

logger = logging.getLogger(__name__)


def web_3_auth(seed: str) -> tp.Tuple[str, str]:
    """
    Get authentication header for a Web3-auth IPFS gateway.

    :param seed: Substrate account seed in any, mnemonic or raw form.

    :return: Authentication header.

    """

    keypair: Keypair = create_keypair(seed)
    return f"sub-{keypair.ss58_address}", f"0x{keypair.sign(keypair.ss58_address).hex()}"


def ipfs_upload_content(
    content: tp.Any, gateway: str = "http://127.0.0.1:5001", auth: tp.Optional[tp.Tuple[str, str]] = None
) -> tp.Tuple[str, int]:
    """
    Upload content to IPFS and pin the CID for some time via IPFS Web3 Gateway with private-key-signed message.
        The signed message is user's pubkey. https://wiki.crust.network/docs/en/buildIPFSWeb3AuthGW#usage.

    :param content: Content to upload to IPFS. To upload media use open(.., "rb") and read().
    :param gateway: Gateway to upload content through. Defaults to local IPFS gateway.
    :param auth: Gateway authentication header if needed. Should be of form (login, password) Defaults to empty.

    :return: IPFS cid and file size.

    """

    response = requests.post(
        f"{gateway}/api/v0/add",
        auth=auth,
        files={"file@": (None, content)},
    )

    if response.status_code == 200:
        resp = literal_eval(response.content.decode("utf-8"))
        cid: str = resp["Hash"]
        size: int = int(resp["Size"])
    else:
        raise FailedToUploadFile(response.status_code)

    return cid, size


def ipfs_get_content(cid: str, gateway: str = "http://127.0.0.1:8080") -> tp.Any:
    """
    Get content file in IPFS network

    :param cid: IPFS cid.
    :param gateway: Gateway to get content through. Defaults to local IPFS gateway.


    :return: Content of a file stored.

    """

    return requests.get(f"{gateway}/ipfs/{cid}").content
