import typing as tp

from logging import getLogger
from scalecodec.base import ScaleBytes
from substrateinterface import KeypairType

from .base import BaseClass
from ..exceptions import NoPrivateKeyException
from ..types import LiabilityTyping, ReportTyping
from ..utils import ipfs_qm_hash_to_32_bytes, str_to_scalebytes

logger = getLogger(__name__)

KEYPAIR_TYPE = ["Ed25519", "Sr25519", "Ecdsa"]


class Liability(BaseClass):
    """
    Class for interacting with Robonomics Liability. Create and finalize ones, get information.
    """

    def get_agreement(self, index: int, block_hash: tp.Optional[str] = None) -> tp.Optional[LiabilityTyping]:
        """
        Fetch information about existing liabilities.

        :param index: Liability item index.
        :param block_hash: Retrieves data as of passed block hash.

        :return: Liability information: ``technics``, ``economics``, ``promisee``, ``promisor``, ``signatures``.
            ``None`` if no such liability.

        """
        logger.info(f"Fetching information about liability with index {index}")

        return self._service_functions.chainstate_query("Liability", "AgreementOf", index, block_hash=block_hash)

    def get_latest_index(self, block_hash: tp.Optional[str] = None) -> tp.Optional[int]:
        """
        Fetch total number of liabilities in chain (method returns the latest liability index +1).

        :param block_hash: Retrieves data as of passed block hash.

        :return: Total number of liabilities in chain (method returns the latest liability index +1). None if no
            liabilities.

        """

        logger.info("Fetching total number of liabilities in chain.")

        return self._service_functions.chainstate_query("Liability", "LatestIndex", block_hash=block_hash)

    def get_report(self, index: int, block_hash: tp.Optional[str] = None) -> tp.Optional[ReportTyping]:
        """
        Fetch information about existing liability reports.

        :param index: Reported liability item index.
        :param block_hash: block_hash: Retrieves data as of passed block hash.

        :return: Liability report information: ``index``, ``promisor``, ``report``, ``signature``. ``None`` if no such
            liability report.

        """

        logger.info(f"Fetching information about reported liability with index {index}")

        return self._service_functions.chainstate_query("Liability", "ReportOf", index, block_hash=block_hash)

    def create(
        self,
        technics_hash: str,
        economics: int,
        promisee: str,
        promisor: str,
        promisee_params_signature: str,
        promisor_params_signature: str,
        nonce: tp.Optional[int] = None,
        promisee_signature_crypto_type: int = KeypairType.SR25519,
        promisor_signature_crypto_type: int = KeypairType.SR25519,
    ) -> tp.Tuple[int, str]:
        """
        Create a liability to ensure economical relationships between robots! This is a contract to be assigned to a
        ``promisor`` by ``promisee``. As soon as the job is done and reported, the ``promisor`` gets his reward.
        This extrinsic may be submitted by another address, but there should be ``promisee`` and ``promisor``
        signatures.

        :param technics_hash: Details of the liability, where the ``promisee`` order is described.
            Accepts any 32-bytes data or a base58 (``Qm...``) IPFS hash.
        :param economics: ``Promisor`` reward in Weiners.
        :param promisee: ``Promisee`` (customer) ss58 address
        :param promisor: ``Promisor`` (worker) ss58 address
        :param promisee_params_signature: An agreement proof. This is a private key signed message containing
            ``technics`` and ``economics``. Both sides need to do this. Signed by ``promisee``.
        :param promisor_params_signature: An agreement proof. This is a private key signed message containing
            ``technics`` and ``economics``. Both sides need to do this. Signed by ``promisor``.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with
            incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.
        :param promisee_signature_crypto_type: Crypto type used to create promisee account.
        :param promisor_signature_crypto_type: Crypto type used to create promisor account.

        :return: New liability index and hash of the liability creation transaction.

        """

        logger.info(
            f"Creating new liability with promisee {promisee}, promisor {promisor}, technics {technics_hash} and"
            f"economics {economics}."
        )

        if technics_hash.startswith("Qm"):
            technics_hash = ipfs_qm_hash_to_32_bytes(technics_hash)

        liability_creation_transaction_hash: str = self._service_functions.extrinsic(
            "Liability",
            "create",
            {
                "agreement": {
                    "technics": {"hash": technics_hash},
                    "economics": {"price": economics},
                    "promisee": promisee,
                    "promisor": promisor,
                    "promisee_signature": {KEYPAIR_TYPE[promisee_signature_crypto_type]: promisee_params_signature},
                    "promisor_signature": {KEYPAIR_TYPE[promisor_signature_crypto_type]: promisor_params_signature},
                }
            },
            nonce=nonce,
        )

        liability_total: int = self.get_latest_index()
        if not liability_total:
            liability_total = 1
        index: int = liability_total - 1
        for liabilities in reversed(range(liability_total)):
            if (
                self.get_agreement(liabilities)["promisee_signature"][KEYPAIR_TYPE[promisee_signature_crypto_type]]
                == promisee_params_signature
            ):
                index = liabilities
                break

        return index, liability_creation_transaction_hash

    def sign_liability(self, technics_hash: str, economics: int) -> str:
        """
        Sign liability params approve message with a private key. This function is meant to sign ``technics`` and
        ``economics``details message to state the agreement of ``promisee`` and ``promisor``. Both sides need to do this.

        :param technics_hash: Details of the liability, where the ``promisee`` order is described.
            Accepts any 32-bytes data or a base58 (``Qm...``) IPFS hash.
        :param economics: ``Promisor`` reward in Weiners.

        :return: Signed message 64-byte hash in sting form.

        """

        if not self.account.keypair:
            raise NoPrivateKeyException("No private key, unable to sign a liability")

        if technics_hash.startswith("Qm"):
            technics_hash = ipfs_qm_hash_to_32_bytes(technics_hash)

        logger.info(f"Signing proof with technics {technics_hash} and economics {economics}.")

        data_to_sign: ScaleBytes = str_to_scalebytes(technics_hash, "H256") + str_to_scalebytes(
            economics, "Compact<Balance>"
        )

        return f"0x{self.account.keypair.sign(data_to_sign).hex()}"

    def finalize(
        self,
        index: int,
        report_hash: str,
        promisor: tp.Optional[str] = None,
        promisor_signature_crypto_type: int = KeypairType.SR25519,
        promisor_finalize_signature: tp.Optional[str] = None,
        nonce: tp.Optional[int] = None,
    ) -> str:
        """
        Report on a completed job to receive a deserved award. This may be done by another address, but there should be
        a liability ``promisor`` signature.

        :param index: Liability item index.
        :param report_hash: IPFS hash of a report data (videos, text, etc.). Accepts any 32-bytes data or a base58
            (``Qm...``) IPFS hash.
        :param promisor: ``Promisor`` (worker) ss58 address. If not passed, replaced with transaction author address.
        :param promisor_signature_crypto_type: Crypto type used to create promisor account.
        :param promisor_finalize_signature: 'Job done' proof. A message containing liability index and report data
            signed by ``promisor``. If not passed, this message is signed by a transaction author which should be a
            ``promisor`` so.
        :param nonce: Account nonce. Due to the feature of substrate-interface lib, to create an extrinsic with
            incremented nonce, pass account's current nonce. See
            https://github.com/polkascan/py-substrate-interface/blob/85a52b1c8f22e81277907f82d807210747c6c583/substrateinterface/base.py#L1535
            for example.

        :return: Liability finalization transaction hash

        """

        logger.info(f"Finalizing liability {index} by promisor {promisor or self.account.get_address()}.")

        if report_hash.startswith("Qm"):
            report_hash = ipfs_qm_hash_to_32_bytes(report_hash)

        return self._service_functions.extrinsic(
            "Liability",
            "finalize",
            {
                "report": {
                    "index": index,
                    "sender": promisor or self.account.get_address(),
                    "payload": {"hash": report_hash},
                    "signature": {
                        KEYPAIR_TYPE[promisor_signature_crypto_type]: promisor_finalize_signature
                        or self.sign_report(index, report_hash)
                    },
                }
            },
            nonce=nonce,
        )

    def sign_report(self, index: int, report_hash: str) -> str:
        """
        Sing liability finalization parameters proof message with a private key. This is meant to state that the job is
        done by ``promisor``.

        :param index: Liability item index.
        :param report_hash: IPFS hash of a report data (videos, text, etc.). Accepts any 32-bytes data or a base58
            (``Qm...``) IPFS hash.

        :return: Signed message 64-byte hash in sting form.

        """

        if not self.account.keypair:
            raise NoPrivateKeyException("No private key, unable to sign a report")

        if report_hash.startswith("Qm"):
            report_hash = ipfs_qm_hash_to_32_bytes(report_hash)

        logger.info(f"Signing report for liability {index} with report_hash {report_hash}.")

        data_to_sign: ScaleBytes = str_to_scalebytes(index, "U32") + str_to_scalebytes(report_hash, "H256")

        return f"0x{self.account.keypair.sign(data_to_sign).hex()}"
