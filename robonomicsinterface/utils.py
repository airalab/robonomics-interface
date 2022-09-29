import hashlib
import logging
import requests
import typing as tp

from ast import literal_eval
from base58 import b58decode, b58encode
from scalecodec.base import RuntimeConfiguration, ScaleBytes, ScaleType
from substrateinterface import Keypair, KeypairType

from .constants import W3GW, W3PS
from .exceptions import FailedToPinFile, FailedToUploadFile

logger = logging.getLogger(__name__)


def create_keypair(seed: str, crypto_type: int = KeypairType.SR25519) -> Keypair:
    """
    Create a keypair for further use.

    :param seed: Account seed (mnemonic or raw) as a key to sign transactions. ``//Alice``, ``//Bob`` etc. supported.
    :param crypto_type: Use KeypairType.SR25519 or KeypairType.ED25519 cryptography for generating the Keypair.

    :return: A Keypair instance used by substrate to sign transactions.

    """

    if seed.startswith("0x"):
        return Keypair.create_from_seed(seed_hex=hex(int(seed, 16)), ss58_format=32, crypto_type=crypto_type)
    elif seed.startswith("//"):
        return Keypair.create_from_uri(suri=seed, ss58_format=32, crypto_type=crypto_type)
    else:
        return Keypair.create_from_mnemonic(seed, ss58_format=32, crypto_type=crypto_type)


def dt_encode_topic(topic: str) -> str:
    """
    Encode any string to be accepted by Digital Twin setSource. Use byte encoding and sha256-hashing.

    :param topic: Topic name to be encoded.

    :return: Hashed-encoded topic name

    """

    return f"0x{hashlib.sha256(topic.encode('utf-8')).hexdigest()}"


def ipfs_32_bytes_to_qm_hash(string_32_bytes: str) -> str:
    """
    Transform 32 bytes sting (without 2 heading bytes) to an IPFS base58 Qm... hash.

    :param string_32_bytes: 32 bytes sting (without 2 heading bytes).

    :return: IPFS base58 Qm... hash.

    """

    if string_32_bytes.startswith("0x"):
        string_32_bytes = string_32_bytes[2:]
    return b58encode(b"\x12 " + bytes.fromhex(string_32_bytes)).decode("utf-8")


def ipfs_qm_hash_to_32_bytes(ipfs_qm: str) -> str:
    """
    Transform IPFS base58 Qm... hash to a 32 bytes sting (without 2 heading '0x' bytes).

    :param ipfs_qm: IPFS base58 Qm... hash.

    :return: 32 bytes sting (without 2 heading bytes).

    """

    return f"0x{b58decode(ipfs_qm).hex()[4:]}"


def str_to_scalebytes(data: tp.Union[int, str], type_str: str) -> ScaleBytes:
    """
    Encode string to a desired ScaleBytes data.

    :param data: String to encode.
    :param type_str: Type (``U32``, ``Compact<Balance>``, etc.).

    :return: ScaleBytes object

    """

    scale_obj: ScaleType = RuntimeConfiguration().create_scale_object(type_str)
    return scale_obj.encode(data)


def ipfs_upload_content(seed: str, content: tp.Any, pin: bool = False) -> tp.Tuple[str, int]:
    """
    Upload content to IPFS and pin the CID for some time via IPFS Web3 Gateway with private-key-signed message.
        The signed message is user's pubkey. https://wiki.crust.network/docs/en/buildIPFSWeb3AuthGW#usage.

    :param seed: Account seed in raw/mnemonic form.
    :param content: Content to upload to IPFS. To upload media use open(.., "rb") and read().
    :param pin: Whether pin file or not.

    :return: IPFS cid and file size.

    """

    keypair: Keypair = create_keypair(seed)

    response = requests.post(
        W3GW + "/api/v0/add",
        auth=(f"sub-{keypair.ss58_address}", f"0x{keypair.sign(keypair.ss58_address).hex()}"),
        files={"file@": (None, content)},
    )

    if response.status_code == 200:
        resp = literal_eval(response.content.decode("utf-8"))
        cid = resp["Hash"]
        size = resp["Size"]
    else:
        raise FailedToUploadFile(response.status_code)

    if pin:
        _pin_ipfs_cid(keypair, cid)

    return cid, size


def _pin_ipfs_cid(keypair: Keypair, ipfs_cid: str) -> bool:
    """
    Pin file for some time via Web3 IPFS pinning service. This may help to spread the file wider across IPFS.

    :param keypair: Account keypair.
    :param ipfs_cid: Uploaded file cid.

    :return: Server response flag.
    """

    body = {"cid": ipfs_cid}

    response = requests.post(
        W3PS + "/psa/pins",
        auth=(f"sub-{keypair.ss58_address}", f"0x{keypair.sign(keypair.ss58_address).hex()}"),
        json=body,
    )

    if response.status_code == 200:
        return True
    else:
        raise FailedToPinFile(response.status_code)


def ipfs_get_content(cid: str) -> tp.Any:
    """
    Get content file in IPFS network

    :param cid: IPFS cid.

    :return: Content of a file stored.

    """

    return requests.get(W3GW + "/ipfs/" + cid).content
