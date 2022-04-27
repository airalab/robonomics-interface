import hashlib
import logging

import substrateinterface as substrate
import typing as tp

from base58 import b58decode, b58encode

DatalogTyping = tp.Tuple[int, tp.Union[int, str]]
LiabilityTyping = tp.Dict[str, tp.Union[tp.Dict[str, tp.Union[str, int]], str]]
ReportTyping = tp.Dict[str, tp.Union[int, str, tp.Dict[str, str]]]
NodeTypes = tp.Dict[str, tp.Dict[str, tp.Union[str, tp.Any]]]

logger = logging.getLogger(__name__)


def create_keypair(seed: str) -> substrate.Keypair:
    """
    Create a keypair for further use.

    :param seed: Account seed (mnemonic or raw) as a key to sign transactions.

    :return: A Keypair instance used by substrate to sign transactions.

    """

    if seed.startswith("0x"):
        return substrate.Keypair.create_from_seed(seed_hex=hex(int(seed, 16)), ss58_format=32)
    else:
        return substrate.Keypair.create_from_mnemonic(seed, ss58_format=32)


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
