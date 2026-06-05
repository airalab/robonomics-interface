#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from substrateinterface import SubstrateInterface
from substrateinterface.utils.ss58 import is_valid_ss58_address, ss58_decode

from robonomicsinterface.constants import REMOTE_WS, TYPE_REGISTRY

DEFAULT_FIXTURE_DIR = Path("tests/fixtures/metadata")
ALICE = "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"
BOB = "4FRC4ae57MnRJViqfbrEHrwDWQm4E3bGzR1szC3h6kQDKwi1"
BOB_ACCOUNT_ID = f"0x{ss58_decode(BOB, valid_ss58_format=32)}"
HASH = "0x" + "ab" * 32
SIGNATURE = "0x" + "11" * 64
SAMPLE_ACCOUNTS = {"ALICE": ALICE, "BOB": BOB}

SUPPORTED_CALL_SAMPLES = [
    ("Balances", "transfer_allow_death", {"dest": {"Id": BOB}, "value": 1}),
    ("Datalog", "record", {"record": "hello"}),
    ("Datalog", "erase", {}),
    ("Launch", "launch", {"robot": BOB, "param": HASH}),
    ("DigitalTwin", "create", {}),
    ("DigitalTwin", "set_source", {"id": 1, "topic": HASH, "source": BOB}),
    ("RWS", "bid", {"index": 1, "amount": 1}),
    # Current scale-info encoding for BoundedVec<T::AccountId> expects each
    # AccountId sample as a one-field list containing the raw 32-byte id.
    ("RWS", "set_devices", {"devices": [[BOB_ACCOUNT_ID]]}),
    (
        "RWS",
        "call",
        {
            "subscription_id": ALICE,
            "call": {
                "call_module": "Datalog",
                "call_function": "record",
                "call_args": {"record": "hello"},
            },
        },
    ),
    (
        "Liability",
        "create",
        {
            "agreement": {
                "technics": {"hash": HASH},
                "economics": {"price": 1},
                "promisee": ALICE,
                "promisor": BOB,
                "promisee_signature": {"Sr25519": SIGNATURE},
                "promisor_signature": {"Sr25519": SIGNATURE},
            }
        },
    ),
    (
        "Liability",
        "finalize",
        {
            "report": {
                "index": 1,
                "sender": BOB,
                "payload": {"hash": HASH},
                "signature": {"Sr25519": SIGNATURE},
            }
        },
    ),
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export a Robonomics runtime metadata contract fixture."
    )
    parser.add_argument("--url", default=REMOTE_WS)
    parser.add_argument("--block-hash")
    parser.add_argument("--block-number", type=int)
    parser.add_argument(
        "--spec-version",
        type=int,
        help=(
            "Expected runtime specVersion. If omitted, the exporter uses the "
            "runtime version loaded from --block-hash/--block-number/latest."
        ),
    )
    parser.add_argument(
        "--allow-any-spec-version",
        action="store_true",
        help="Do not fail when --spec-version differs from the loaded runtime.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_FIXTURE_DIR),
        help="Directory for automatically named robonomics_spec_<N>.json files.",
    )
    parser.add_argument(
        "--output",
        help="Explicit output path. Overrides --output-dir.",
    )
    return parser.parse_args()


def add_pallet(pallets, module_name):
    return pallets.setdefault(
        module_name,
        {"calls": [], "storage": [], "constants": [], "events": []},
    )


def serialize_event(module, event, spec_version):
    module_prefix = (
        module.value["storage"]["prefix"] if module.value["storage"] else None
    )
    return {
        "event_name": event.name,
        "event_id": event.name,
        "event_args": event.args,
        "documentation": "\n".join(event.docs),
        "module_name": module.name,
        "module_prefix": module_prefix,
        "spec_version": spec_version,
    }


def group_metadata(substrate):
    pallets = {}

    for item in substrate.get_metadata_call_functions():
        add_pallet(pallets, item["module_name"])["calls"].append(item)

    for item in substrate.get_metadata_storage_functions():
        add_pallet(pallets, item["module_name"])["storage"].append(item)

    for item in substrate.get_metadata_constants():
        add_pallet(pallets, item["module_name"])["constants"].append(item)

    for module in substrate.metadata.pallets:
        for event in module.events or []:
            add_pallet(pallets, module.name)["events"].append(
                serialize_event(module, event, substrate.runtime_version)
            )

    return pallets


def payload_fields(signed_extensions):
    fields = ["call"]
    if "CheckMortality" in signed_extensions or "CheckEra" in signed_extensions:
        fields.append("era")
    if "CheckNonce" in signed_extensions:
        fields.append("nonce")
    if "ChargeTransactionPayment" in signed_extensions:
        fields.append("tip")
    if "ChargeAssetTxPayment" in signed_extensions:
        fields.append("asset_id")
    if "CheckMetadataHash" in signed_extensions:
        fields.append("mode")
    if "CheckSpecVersion" in signed_extensions:
        fields.append("spec_version")
    if "CheckTxVersion" in signed_extensions:
        fields.append("transaction_version")
    if "CheckGenesis" in signed_extensions:
        fields.append("genesis_hash")
    if "CheckMortality" in signed_extensions or "CheckEra" in signed_extensions:
        fields.append("block_hash")
    if "CheckMetadataHash" in signed_extensions:
        fields.append("metadata_hash")
    return fields


def validate_static_samples():
    invalid_addresses = {
        name: address
        for name, address in SAMPLE_ACCOUNTS.items()
        if not is_valid_ss58_address(address, valid_ss58_format=32)
    }
    if invalid_addresses:
        raise SystemExit(
            f"Invalid sample SS58 addresses for format 32: {invalid_addresses}"
        )


def call_samples(substrate):
    samples = []
    for module_name, call_name, params in SUPPORTED_CALL_SAMPLES:
        try:
            call = substrate.compose_call(module_name, call_name, params)
            decoded = substrate.decode_scale(
                "Call",
                str(call.data),
                return_scale_obj=True,
            ).value
        except Exception as exc:
            raise RuntimeError(
                f"Failed to compose/decode sample call "
                f"{module_name}.{call_name} with params {params!r}"
            ) from exc
        samples.append(
            {
                "module": module_name,
                "function": call_name,
                "params": params,
                "encoded": str(call.data),
                "decoded": {
                    "call_module": decoded["call_module"],
                    "call_function": decoded["call_function"],
                    "call_args": decoded["call_args"],
                },
            }
        )
    return samples


def init_runtime(substrate, args):
    if args.block_hash:
        substrate.init_runtime(block_hash=args.block_hash)
    elif args.block_number is not None:
        substrate.init_runtime(block_id=args.block_number)
    else:
        substrate.init_runtime()


def resolve_output_path(args, spec_version):
    if args.output:
        return Path(args.output)
    return Path(args.output_dir) / f"robonomics_spec_{spec_version}.json"


def metadata_version(raw_metadata):
    if not raw_metadata.startswith("0x6d657461"):
        raise ValueError("Unexpected runtime metadata prefix")
    return int(raw_metadata[10:12], 16)


def json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return f"0x{bytes(value).hex()}"
    if hasattr(value, "value"):
        return json_safe(value.value)
    if hasattr(value, "value_object"):
        return json_safe(value.value_object)
    return str(value)


def ensure_expected_spec_version(args, actual_spec_version):
    if args.spec_version is None or args.allow_any_spec_version:
        return
    if actual_spec_version != args.spec_version:
        raise SystemExit(
            f"Expected specVersion={args.spec_version}, "
            f"got {actual_spec_version}. Pass --block-hash/--block-number "
            "for a block with the expected runtime, or use "
            "--allow-any-spec-version to export the loaded runtime anyway."
        )


def main():
    args = parse_args()
    validate_static_samples()
    substrate = SubstrateInterface(
        url=args.url,
        ss58_format=32,
        type_registry_preset="substrate-node-template",
        type_registry=TYPE_REGISTRY,
    )

    init_runtime(substrate, args)
    ensure_expected_spec_version(args, substrate.runtime_version)

    raw_metadata = substrate.get_block_metadata(substrate.block_hash, decode=False)[
        "result"
    ]
    signed_extensions = substrate.metadata.get_signed_extensions()
    calls = call_samples(substrate)
    payload = substrate.generate_signature_payload(
        substrate.compose_call("Datalog", "record", {"record": "hello"}),
        nonce=0,
    )

    fixture = {
        "chain": substrate.chain,
        "runtime_version": {
            "specVersion": substrate.runtime_version,
            "transactionVersion": substrate.transaction_version,
        },
        "block_hash": substrate.block_hash,
        "rpc_methods": substrate.rpc_request("rpc_methods", [])
        .get("result", {})
        .get("methods", []),
        "metadata": {
            "raw": raw_metadata,
            "version": metadata_version(raw_metadata),
            "signed_extensions": signed_extensions,
            "pallets": group_metadata(substrate),
        },
        "scale": {
            "calls": calls,
            "signed_payload": {
                "hex": str(payload),
                "fields": payload_fields(signed_extensions),
                "call": {"module": "Datalog", "function": "record"},
            },
        },
    }

    output = resolve_output_path(args, substrate.runtime_version)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(json_safe(fixture), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"Exported Robonomics specVersion={substrate.runtime_version} "
        f"metadata fixture to {output}"
    )


if __name__ == "__main__":
    main()
