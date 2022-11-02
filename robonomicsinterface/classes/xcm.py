from logging import getLogger

import substrateinterface as substrate

from .base import BaseClass

logger = getLogger(__name__)


class XCM(BaseClass):
    """
    Class for executing XCM calls (interacting with other parachains using the HRMP protocol)
    """

    @staticmethod
    def _get_encoded_crust_extrinsic(file_ipfs_cid: str, file_size_bytes: int) -> str:
        """
        Get encoded (hex) call data for the xstorage.placeStorageOrderThroughParachain(cid, size) extrinsic in Crust

        :param file_ipfs_cid: An IPFS CID (file hash) of the file to be pinned. File must be uploaded to IPFS first.
        :param file_size_bytes: Size of the provided file in bytes. Can be obtained using command
            'ipfs object stat YOUR_CID' ('CumulativeSize' parameter). Also returned by the 'ipfs_upload_content' function
            found in 'utils' module.
        :return: Encoded (hex) call data for the xstorage.placeStorageOrderThroughParachain(cid, size) extrinsic in Crust
        """
        interface = substrate.SubstrateInterface(
            url="wss://rpc-shadow.crust.network/",
            ss58_format=66,
        )
        call = interface.compose_call(
            call_module="Xstorage",
            call_function="place_storage_order_through_parachain",
            call_params={"cid": file_ipfs_cid, "size": file_size_bytes},
        )
        return str(call.data)

    def place_file_pin_order_in_crust(self, file_ipfs_cid: str, file_size_bytes: int) -> str:
        """
        Perform an XCM call to Crust Shadow parachain and place an order to pin the provided IPFS CID

        :param file_ipfs_cid: An IPFS CID (file hash) of the file to be pinned. File must be uploaded to IPFS first.
        :param file_size_bytes: Size of the provided file in bytes. Can be obtained using command
            'ipfs object stat YOUR_CID' ('CumulativeSize' parameter). Also returned by the 'ipfs_upload_content' function
            found in 'utils' module.
        :return: Extrinsic hash of the XCM call performed in the Robonomics Network.
        """
        crust_encoded_call_data: str = self._get_encoded_crust_extrinsic(
            file_ipfs_cid=file_ipfs_cid,
            file_size_bytes=file_size_bytes,
        )
        params = {
            "dest": {
                "V1": {
                    "parents": 1,
                    "interior": {
                        "X1": {
                            "Parachain": "2,012",
                        }
                    },
                }
            },
            "message": {
                "V2": [
                    {
                        "WithdrawAsset": [
                            {
                                "id": {"Concrete": {"parents": 0, "interior": "Here"}},
                                "fun": {"Fungible": "1,000,000,000,000"},
                            }
                        ]
                    },
                    {
                        "BuyExecution": {
                            "fees": {
                                "id": {"Concrete": {"parents": 0, "interior": "Here"}},
                                "fun": {
                                    "Fungible": "1,000,000,000,000",
                                },
                            },
                            "weightLimit": "Unlimited",
                        }
                    },
                    {
                        "Transact": {
                            "originType": "Native",
                            "requireWeightAtMost": "1,000,000,000",
                            "call": {
                                "encoded": crust_encoded_call_data,
                            },
                        }
                    },
                    "RefundSurplus",
                    {
                        "DepositAsset": {
                            "assets": {"Wild": "All"},
                            "maxAssets": 1,
                            "beneficiary": {
                                "parents": 0,
                                "interior": {"X1": {"Parachain": "2,048"}},
                            },
                        }
                    },
                ]
            },
        }
        result = self._service_functions.extrinsic(  # TODO: Request review
            call_module="PolkadotXcm",
            call_function="send",
            params=params,
        )

        if isinstance(result, tuple):
            extrinsic_hash, block_number = result
        else:
            extrinsic_hash = result

        return extrinsic_hash
