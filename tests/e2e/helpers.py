import pytest
from substrateinterface.utils.ss58 import ss58_decode

HASH_A = "0x" + "ab" * 32
HASH_B = "0x" + "cd" * 32
RWS_E2E_TPS = 1_000_000
LOCAL_DEV_CHAIN_NAMES = {
    "Development",
    "Robonomics Local Development",
    "Robonomics Local Develoment",
}


def is_local_dev_chain(chain_name):
    return chain_name in LOCAL_DEV_CHAIN_NAMES


def has_runtime_call(substrate, module_name, call_name):
    try:
        return substrate.get_metadata_call_function(module_name, call_name) is not None
    except Exception:
        return False


def require_runtime_call(substrate, module_name, call_name):
    if not has_runtime_call(substrate, module_name, call_name):
        pytest.skip(f"Local runtime does not expose {module_name}.{call_name}")


def assert_successful_receipt(receipt):
    assert receipt.is_success, receipt.error_message


def account_id_call_param(address):
    return [f"0x{ss58_decode(address, valid_ss58_format=32)}"]


def block_number_from_result(extrinsic_result):
    if not isinstance(extrinsic_result, tuple):
        pytest.fail("Wrapper was expected to run with return_block_num=True")
    return int(extrinsic_result[1].split("-", 1)[0])


def events_at_block(substrate, block_number):
    block_hash = substrate.get_block_hash(block_number)
    return substrate.query("System", "Events", block_hash=block_hash).value


def events_from_result(substrate, extrinsic_result):
    return events_at_block(substrate, block_number_from_result(extrinsic_result))


def _event_body(event):
    return event.get("event", event)


def event_module(event):
    body = _event_body(event)
    return body.get("module_id") or body.get("module_name") or body.get("module")


def event_id(event):
    body = _event_body(event)
    return body.get("event_id") or body.get("event_name") or body.get("name")


def has_event(events, module_name, event_name):
    return any(
        event_module(event) == module_name and event_id(event) == event_name
        for event in events
    )


def record_payload_to_text(record_payload):
    if isinstance(record_payload, str):
        return record_payload
    if isinstance(record_payload, bytes):
        return record_payload.decode()
    if isinstance(record_payload, list):
        return bytes(record_payload).decode()
    return str(record_payload)
