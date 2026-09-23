"""Calls, eras, signatures and event decoding, offline."""

import gzip
import hashlib
from dataclasses import replace
from typing import Any

import pytest

from conftest import FIXTURES, load_fixture
from fake_node import recorded_runtime
from robonomicsinterface import EncodeError, Keypair, NoSuchCall, UnsupportedExtension
from robonomicsinterface.extrinsic import (
    Era,
    SigningContext,
    _extension_parts,
    compose_call,
    decode_events,
    dispatch_error_message,
    explain_invalid_transaction,
    sign_extrinsic,
)
from robonomicsinterface.runtime import Runtime, RuntimeVersion, SignedExtension

VECTORS = load_fixture("extrinsic_vectors.json")


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


@pytest.fixture(scope="module")
def runtime43() -> Runtime:
    """The runtime the rrs-ha-integration vectors were built against."""

    metadata = gzip.decompress((FIXTURES / "metadata_spec43.hex.gz").read_bytes()).decode().strip()
    version = RuntimeVersion("robonomics", VECTORS["spec_version"], VECTORS["transaction_version"])
    return Runtime(metadata, version, VECTORS["genesis_hash"])


def context(runtime: Runtime, **changes: Any) -> SigningContext:
    base = SigningContext(
        nonce=0,
        era=Era.immortal(),
        birth_hash=runtime.genesis_hash,
        genesis_hash=runtime.genesis_hash,
        spec_version=runtime.version.spec_version,
        transaction_version=runtime.version.transaction_version,
    )
    return replace(base, **changes)


# Era — vectors from sp_runtime::generic::Era's own tests


def test_immortal_era() -> None:
    assert Era.immortal().encode() == b"\x00"
    assert Era.immortal().is_immortal


def test_mortal_era_vectors() -> None:
    assert Era.mortal(64, 42).encode() == bytes([5 + 42 % 16 * 16, 42 // 16])
    assert Era.mortal(32768, 20000).encode() == bytes([14 + 2500 % 16 * 16, 2500 // 16])


def test_mortal_era_period_rounding() -> None:
    assert Era.mortal(60, 0).period == 64
    assert Era.mortal(1, 0).period == 4
    assert Era.mortal(100_000, 0).period == 65536


def test_era_birth() -> None:
    era = Era.mortal(4, 6)
    assert [era.birth(n) for n in range(6, 10)] == [6, 6, 6, 6]
    assert Era.mortal(64, 1000).birth(1000) == 1000


# The rrs-ha-integration vectors, byte for byte (built by substrate-interface)


def test_integration_calls(runtime43: Runtime) -> None:
    record = compose_call(runtime43, "Datalog", "record", {"record": VECTORS["cid"]})
    assert record.hex == VECTORS["calls"]["datalog_record"]
    rws = compose_call(
        runtime43, "RWS", "call", {"subscription_id": VECTORS["subscription_owner"], "call": record}
    )
    assert rws.hex == VECTORS["calls"]["rws_call"]


def test_integration_extrinsics(runtime43: Runtime) -> None:
    keypair = Keypair.from_mnemonic(VECTORS["mnemonic"])
    record = compose_call(runtime43, "Datalog", "record", {"record": VECTORS["cid"]})
    calls = {
        "datalog_record": record,
        "rws_call": compose_call(
            runtime43,
            "RWS",
            "call",
            {"subscription_id": VECTORS["subscription_owner"], "call": record},
        ),
    }
    for vector in VECTORS["extrinsics"]:
        signed = sign_extrinsic(
            runtime43, calls[vector["call"]], keypair, context(runtime43, nonce=vector["nonce"])
        )
        assert signed.hex == vector["hex"]
        assert signed.hash == "0x" + hashlib.blake2b(signed.data, digest_size=32).hexdigest()


# Composing calls


def test_set_devices_takes_a_flat_list(runtime: Runtime) -> None:
    a, b = Keypair.from_uri("//Alice"), Keypair.from_uri("//Bob")
    call = compose_call(runtime, "RWS", "set_devices", {"devices": [a.address, b]})
    expected = "0x3702" + "08" + a.public_key.hex() + b.public_key.hex()
    assert call.hex == expected


def test_record_bytes_are_literal(runtime: Runtime) -> None:
    call = compose_call(runtime, "Datalog", "record", {"record": b"0x12"})
    assert call.data == bytes([0x33, 0x00, 4 << 2]) + b"0x12"


def test_call_argument_errors(runtime: Runtime) -> None:
    with pytest.raises(EncodeError, match="missing"):
        compose_call(runtime, "Datalog", "record", {})
    with pytest.raises(EncodeError, match="unknown"):
        compose_call(runtime, "Datalog", "record", {"record": "x", "extra": 1})
    with pytest.raises(EncodeError):
        compose_call(runtime, "RWS", "set_devices", {"devices": ["not an address"]})
    with pytest.raises(NoSuchCall):
        compose_call(runtime, "Datalog", "nope")


# Signing


def test_mortal_extrinsic_layout(runtime: Runtime) -> None:
    keypair = Keypair.from_uri("//Alice")
    call = compose_call(runtime, "Datalog", "record", {"record": b"x"})
    era = Era.mortal(64, 1000)
    signed = sign_extrinsic(runtime, call, keypair, context(runtime, nonce=5, era=era, tip=0))
    body = signed.data[2:] if signed.data[0] & 0b11 == 0b01 else signed.data[1:]
    assert body[0] == 0x84
    assert body[1:34] == b"\x00" + keypair.public_key  # MultiAddress::Id
    assert body[34] == 0x00  # MultiSignature::Ed25519
    assert body[99:101] == era.encode()
    assert body.endswith(call.data)


def test_long_payloads_are_signed_as_a_hash(runtime: Runtime) -> None:
    keypair = Keypair.from_uri("//Alice")
    call = compose_call(runtime, "Datalog", "record", {"record": b"x" * 400})
    ctx = context(runtime)
    signed = sign_extrinsic(runtime, call, keypair, ctx)
    explicit, implicit = _extension_parts(runtime, ctx)
    digest = hashlib.blake2b(call.data + explicit + implicit, digest_size=32).digest()
    signature = signed.data[signed.data.index(keypair.public_key) + 33 :][:64]
    assert keypair.verify(digest, signature)


def test_unknown_extension_with_data_is_refused(runtime: Runtime) -> None:
    u32 = runtime.signed_extensions[1].implicit_type  # CheckSpecVersion's u32
    patched = object.__new__(Runtime)
    patched.__dict__.update(runtime.__dict__)
    call = compose_call(runtime, "Datalog", "record", {"record": b"x"})

    patched.signed_extensions = (*runtime.signed_extensions, SignedExtension("CheckFoo", 34, 34))
    sign_extrinsic(patched, call, Keypair.from_uri("//Alice"), context(runtime))

    patched.signed_extensions = (*runtime.signed_extensions, SignedExtension("CheckFoo", u32, 34))
    with pytest.raises(UnsupportedExtension, match="CheckFoo"):
        sign_extrinsic(patched, call, Keypair.from_uri("//Alice"), context(runtime))


# What the chain says


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("0x010001", "Payment"),
        ("0x010003", "Stale"),
        ("0x010004", "BadProof"),
        ("0x0100072a", "Custom(42)"),
        ("0x010100", "CannotLookup"),
    ],
)
def test_invalid_transactions(raw: str, kind: str) -> None:
    result = explain_invalid_transaction(bytes.fromhex(raw[2:]))
    assert result is not None
    assert result[0] == kind


def test_payment_explained() -> None:
    result = explain_invalid_transaction(bytes.fromhex("010001"))
    assert result is not None
    assert "existential deposit" in result[1]


def test_valid_transaction() -> None:
    assert explain_invalid_transaction(bytes.fromhex("00" + "11" * 20)) is None


def test_module_errors(runtime: Runtime) -> None:
    pallet, error, docs, message = dispatch_error_message(
        runtime, {"Module": {"index": 55, "error": "0x06000000"}}
    )
    assert (pallet, error) == ("RWS", "FreeWeightIsNotEnough")
    assert "free weight" in docs
    assert message.startswith("RWS.FreeWeightIsNotEnough: ")
    assert dispatch_error_message(runtime, {"Module": {"index": 55, "error": "0x05000000"}})[1] == (
        "NotLinkedDevice"
    )


def test_other_dispatch_errors(runtime: Runtime) -> None:
    assert dispatch_error_message(runtime, {"Token": "FundsUnavailable"})[1] == (
        "Token.FundsUnavailable"
    )
    assert dispatch_error_message(runtime, "BadOrigin")[1] == "BadOrigin"
    assert dispatch_error_message(runtime, {"Module": {"index": 250, "error": "0x00"}})[0] is None


def test_recorded_events(runtime: Runtime) -> None:
    samples = load_fixture("event_samples.json")["blocks"]
    entry = runtime.storage_entry("System", "Events")

    failed = decode_events(runtime.decode(entry.value_type, samples["failed_rws_call"]["events"]))
    ours = [e for e in failed if e.extrinsic_index == 2]
    assert ("System", "ExtrinsicFailed") in [(e.pallet, e.name) for e in ours]

    ok = decode_events(runtime.decode(entry.value_type, samples["successful_rws_call"]["events"]))
    names = [(e.pallet, e.name) for e in ok if e.extrinsic_index == 2]
    assert ("Datalog", "NewRecord") in names
    assert ("RWS", "NewCall") in names
