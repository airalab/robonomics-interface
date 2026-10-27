"""The API the Report Service projects rely on (feedback on 3.0.0rc1).

Changing anything here between release candidates and 3.0.0 breaks them: such a
change must be listed under "Stable API" in MIGRATION.md, and this test updated
in the same commit.
"""

import inspect
from dataclasses import fields

import pytest

import robonomicsinterface as r
from robonomicsinterface.pallets import RWS, Datalog, System


def parameters(function: object) -> list[str]:
    return list(inspect.signature(function).parameters)  # type: ignore[arg-type]


def test_client_construction_and_lifecycle() -> None:
    for name in ("endpoints", "genesis_hash", "ssl", "timeout", "retries"):
        assert name in parameters(r.RobonomicsClient)
    for name in ("connect", "close", "__aenter__", "__aexit__"):
        assert callable(getattr(r.RobonomicsClient, name))
    for name in ("connect", "close", "__enter__", "__exit__"):
        assert callable(getattr(r.RobonomicsSync, name))
    assert "endpoints" in parameters(r.RobonomicsSync)


@pytest.mark.parametrize(
    ("section", "methods"),
    [
        (Datalog, ["items", "record", "window_size"]),
        (RWS, ["devices", "ledger", "set_devices"]),
        (System, ["account", "exists"]),
    ],
)
def test_pallet_helpers(section: type, methods: list[str]) -> None:
    for method in methods:
        assert inspect.iscoroutinefunction(getattr(section, method)), method


def test_datalog_record_subscription_owner() -> None:
    assert "subscription_owner" in parameters(Datalog.record)


def test_keys_addresses_and_envelope() -> None:
    for name in ("from_secret", "from_mnemonic", "verify", "encrypt_message", "decrypt_message"):
        assert callable(getattr(r.Keypair, name))
    for name in ("address", "public_key"):
        assert isinstance(inspect.getattr_static(r.Keypair, name), property)
    for name in (
        "generate_mnemonic",
        "is_valid_address",
        "decode_address",
        "encode_address",
        "address_format",
        "encrypt_for_recipients",
        "decrypt_package",
        "parse_decrypted",
    ):
        assert callable(getattr(r, name)), name


def test_value_types() -> None:
    assert {"index", "timestamp_ms", "data"} <= {f.name for f in fields(r.DatalogItem)}
    assert isinstance(inspect.getattr_static(r.DatalogItem, "text"), property)
    assert {"kind", "days", "free_weight"} <= {f.name for f in fields(r.Ledger)}
    for name in ("issued_at", "expires_at"):
        assert isinstance(inspect.getattr_static(r.Ledger, name), property)
    assert "free" in {f.name for f in fields(r.AccountInfo)}
    assert isinstance(inspect.getattr_static(r.AccountInfo, "exists"), property)
    assert r.XRT == 10**9
    assert r.ROBONOMICS_GENESIS_HASH.startswith("0x29f4371d")


def test_errors() -> None:
    for sub in (r.ConnectionLost, r.RequestTimeout, r.ConnectionFailed, r.AllEndpointsFailed):
        assert issubclass(sub, r.TransportError)
    for sub in (
        r.ExtrinsicFailed,
        r.ExtrinsicOutcomeUnknown,
        r.ExtrinsicDropped,
        r.InvalidTransaction,
    ):
        assert issubclass(sub, r.TransactionError)
    assert issubclass(r.RecipientError, r.EnvelopeError)

    rpc = r.RpcError("state_call", -32000, "message")
    assert (rpc.method, rpc.code, rpc.message) == ("state_call", -32000, "message")
    failed = r.ExtrinsicFailed("x", pallet="RWS", error="NotLinkedDevice", docs="", result=None)
    assert (failed.pallet, failed.error) == ("RWS", "NotLinkedDevice")
    assert r.ExtrinsicOutcomeUnknown("0x01", "lost").extrinsic_hash == "0x01"
    invalid = r.InvalidTransaction("Payment", "explanation")
    assert (invalid.kind, invalid.explanation) == ("Payment", "explanation")
