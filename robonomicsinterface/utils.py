import hashlib
import logging
import typing as tp

from base58 import b58decode, b58encode
from scalecodec.base import RuntimeConfiguration, ScaleBytes, ScaleType
from substrateinterface import Keypair, KeypairType

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
