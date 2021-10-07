import logging
import typing as tp

from substrateinterface import SubstrateInterface, Keypair


class RobonomicsInterface:

    def __init__(self, seed: str or None = None, remote_ws: str = 'wss://main.frontier.rpc.robonomics.network',
                 type_registry: tp.Dict or None = None):
        """
        Instance of a class is an interface with a node. Here this interface is initialized.

        @param seed: account seed in mnemonic/raw form. When not passed, no extrinsics functionality
        @param remote_ws: node url. Default node address is "wss://main.frontier.rpc.robonomics.network".
        Another address may be specified (e.g. "ws://127.0.0.1:9944" for local node).
        @param type_registry: types used in the chain. Defaults are the most frequently used in Robonomics
        """

        self.seed = seed
        if not self.seed:
            logging.warning("No seed specified, you won't be able to sign extrinsics, fetching chainstate only.")
            self.keypair = None
        else:
            try:
                if '0x' in self.seed:
                    self.keypair = Keypair.create_from_seed(
                        seed_hex=hex(int(self.seed, 16)),
                        ss58_format=32)
                else:
                    self.keypair = Keypair.create_from_mnemonic(self.seed, ss58_format=32)
            except Exception as e:
                logging.error(f"Failed to create keypair. Check if seed valid. "
                              f"You won't be able to sign extrinsics, only fetching chainstate. "
                              f"Error: {e}")
                self.keypair = None

        if type_registry:
            logging.warning(f"Using custom type registry for the node")
        else:
            type_registry = {
                "types": {
                    "Record": "Vec<u8>",
                    "Parameter": "Bool",
                    "<T as frame_system::Config>::AccountId": "AccountId",
                    "RingBufferItem": {
                        "type": "struct",
                        "type_mapping": [
                            [
                                "timestamp",
                                "Compact<u64>"
                            ],
                            [
                                "payload",
                                "Vec<u8>"
                            ]
                        ]
                    },
                    "RingBufferIndex": {
                        "type": "struct",
                        "type_mapping": [
                            [
                                "start",
                                "Compact<u64>"
                            ],
                            [
                                "end",
                                "Compact<u64>"
                            ]
                        ]
                    }
                }
            }

        try:
            logging.info("Establishing connection to Robonomics node")
            self.interface = SubstrateInterface(
                url=remote_ws,
                ss58_format=32,
                type_registry_preset="substrate-node-template",
                type_registry=type_registry,
            )
            logging.info("Successfully established connection to Robonomics node")
        except Exception as e:
            logging.error(f"Failed to connect to Robonomics node: {e}")

    def custom_chainstate(self, module: str, storage_function: str, params: tp.List or str or None = None) -> tp.Any:
        """
        Create custom queries to fetch data from the Chainstate. Module names and storage functions, as well as required
        parameters are available at https://parachain.robonomics.network/#/chainstate

        @param module: chainstate module
        @param storage_function: storage function
        @param params: query parameters. None if no parameters. Include in list, if several

        @return: output of the query in any form
        """

        logging.info("Performing query")
        try:
            if params:
                resp = self.interface.query(module, storage_function, [params])
                return resp
            else:
                resp = self.interface.query(module, storage_function)
                return resp
        except Exception as e:
            logging.error(f"Failed to perform query: {e}")
            return None

    def fetch_datalog(self, addr: str, index: int or None = None) -> tp.Dict or None:
        """
        Fetch datalog record of a provided account.

        @param addr: ss58 type 32 address of an account which datalog is to be fetched.
        @param index: record index. case int: fetch datalog by specified index
                                    case None: fetch latest datalog

        @return: Dictionary. Datalog of the account with a timestamp, None if no records.
        """

        logging.info(f"Fetching {'latest datalog record' if not index else 'datalog record #' + str(index)}"
                     f" of {addr}.")
        try:
            if index:
                record = self.custom_chainstate("Datalog", "DatalogItem", [addr, index])
                if record.value['timestamp'] == 0:
                    logging.error(f"No datalog with index {index} found")
                    record = None
                return record
            else:
                index = self.custom_chainstate("Datalog", "DatalogIndex", addr).value['end'] - 1
                if index == -1:
                    logging.error(f"No datalogs from {addr}")
                    return None
                else:
                    record = self.custom_chainstate("Datalog", "DatalogItem", [addr, index])
                    return record
        except Exception as e:
            logging.error(f"Error fetching datalog:\n{e}")
            return None

    def custom_extrinsic(self, call_module: str, call_function: str, params: tp.Dict or None = None) -> str or None:
        """
        Create an extrinsic, sign&submit it. Module names and functions, as well as required parameters are available
        at https://parachain.robonomics.network/#/extrinsics

        @param call_module: Call module from extrinsic tab
        @param call_function: Call function from extrinsic tab
        @param params: Call parameters as a dictionary. None of no parameters

        @return: Extrinsic hash or None if failed
        """

        try:
            if not self.keypair:
                raise NoPrivateKey("No seed was provided, unable to use extrinsics.")

            logging.info(f"Creating a call {call_module}:{call_function}")
            if params:
                call = self.interface.compose_call(
                    call_module=call_module,
                    call_function=call_function,
                    call_params=params
                )
            else:
                call = self.interface.compose_call(
                    call_module=call_module,
                    call_function=call_function
                )

            logging.info("Creating extrinsic")
            extrinsic = self.interface.create_signed_extrinsic(call=call, keypair=self.keypair)

            logging.info("Submitting extrinsic")
            receipt = self.interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
            logging.info(f"Extrinsic {receipt.extrinsic_hash} for RPC {call_module}:{call_function} submitted and "
                         f"included in block {receipt.block_hash}")
            return receipt.extrinsic_hash
        except Exception as e:
            logging.error(f"Error while creating a call, creating or submitting extrinsic: {e}")
            return None

    def write_datalog(self, data: str) -> str or None:
        """
        Write any string to datalog

        @param data: string to be stored in datalog

        @return: Hash of the datalog transaction
        """

        logging.info(f"Writing datalog {data}")
        r = self.custom_extrinsic("Datalog", "record", {'record': data})
        return r

    def send_launch(self, target_address: str, on_off: bool) -> str or None:
        """
        Send Launch command to device

        @param target_address: device to be triggered with launch
        @param on_off: (true == on, false == off)

        @return: Hash of the launch transaction if success
        """

        logging.info(f"Sending launch command {on_off} to {target_address}")
        r = self.custom_extrinsic("Launch", "launch", {'robot': target_address,
                                                       'param': True if on_off else False})
        return r


class NoPrivateKey(Exception):
    pass


if __name__ == "__main__":
    pass
