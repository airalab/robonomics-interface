"""Calls, signed extrinsics, and what the chain says about them afterwards.

Everything here is offline: it takes a :class:`~robonomicsinterface.runtime.Runtime`
and produces bytes, or takes bytes from the chain and explains them. The
client does the talking.

Signed extensions are read from the runtime metadata, in its order. Each one
contributes an explicit part (sent in the extrinsic) and an implicit part (only
signed); the values come from :data:`EXTENSION_VALUES`. An extension this
library does not know is fine if both its parts are empty, and an
:class:`~robonomicsinterface.errors.UnsupportedExtension` otherwise — never a
silently wrong signature.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import EncodeError, MetadataError, UnsupportedExtension
from .keys import Keypair
from .runtime import Runtime

__all__ = [
    "EXTENSION_VALUES",
    "Call",
    "Era",
    "Event",
    "ExtrinsicResult",
    "SignedExtrinsic",
    "SigningContext",
    "compose_call",
    "decode_events",
    "dispatch_error_message",
    "explain_invalid_transaction",
    "extrinsic_hash",
    "sign_extrinsic",
]

_SIGNED_BIT = 0b1000_0000
_MAX_UNHASHED_PAYLOAD = 256
DEFAULT_ERA_PERIOD = 64


def _blake2_256(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32).digest()


def extrinsic_hash(data: bytes) -> str:
    """The hash nodes and explorers identify an extrinsic by."""

    return "0x" + _blake2_256(data).hex()


def _compact(value: int) -> bytes:
    if value < 1 << 6:
        return bytes([value << 2])
    if value < 1 << 14:
        return ((value << 2) | 0b01).to_bytes(2, "little")
    if value < 1 << 30:
        return ((value << 2) | 0b10).to_bytes(4, "little")
    raw = value.to_bytes((value.bit_length() + 7) // 8, "little")
    return bytes([((len(raw) - 4) << 2) | 0b11]) + raw


# Era


@dataclass(frozen=True, slots=True)
class Era:
    """How long a signed extrinsic stays valid.

    An immortal extrinsic is valid until its nonce is used. A mortal one is
    valid for ``period`` blocks from the block it names, so a lost or stuck
    transaction cannot land much later — and cannot be replayed if the account
    is ever reaped and its nonce starts again from zero.
    """

    period: int | None = None
    phase: int = 0

    @classmethod
    def immortal(cls) -> Era:
        return cls()

    @classmethod
    def mortal(cls, period: int, current_block: int) -> Era:
        """Valid for about ``period`` blocks (rounded to a power of two, 4..65536)."""

        period = max(4, min(1 << 16, 1 << (max(period, 1) - 1).bit_length()))
        quantize = max(period >> 12, 1)
        phase = current_block % period // quantize * quantize
        return cls(period, phase)

    @property
    def is_immortal(self) -> bool:
        return self.period is None

    def birth(self, current_block: int) -> int:
        """The block whose hash the extrinsic commits to."""

        if self.period is None:
            return 0
        return (
            max(current_block, self.phase) - self.phase
        ) // self.period * self.period + self.phase

    def encode(self) -> bytes:
        if self.period is None:
            return b"\x00"
        quantize = max(self.period >> 12, 1)
        low = min(15, max(1, (self.period & -self.period).bit_length() - 2))
        return (low | (self.phase // quantize) << 4).to_bytes(2, "little")


# Calls


@dataclass(frozen=True)
class Call:
    """An encoded call, ready to sign or to nest (``RWS.call``, ``Utility.batch``)."""

    pallet: str
    function: str
    args: Mapping[str, Any]
    data: bytes = field(repr=False)
    scale_value: dict[str, Any] = field(repr=False, compare=False)
    spec_version: int = field(default=0, compare=False)

    @property
    def hex(self) -> str:
        return "0x" + self.data.hex()


def _adapt(runtime: Runtime, type_id: int, value: Any) -> Any:
    """Turn a natural Python value into what scalecodec expects for ``type_id``.

    - ``bytes`` become hex, a :class:`Keypair` becomes its public key and a
      :class:`Call` its nested form, at any depth;
    - a single-field wrapper such as ``BoundedVec<T, S>`` takes the inner value
      directly: ``devices=[a, b]``, not the ``[[a, b]]`` scalecodec wants.
    """

    if isinstance(value, Call):
        return value.scale_value
    if isinstance(value, Keypair):
        value = value.public_key
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()

    definition = runtime.type_info(type_id)["def"]
    if "composite" in definition:
        fields = definition["composite"]["fields"]
        if len(fields) == 1 and fields[0]["name"] is None:
            scale_class = runtime.scale_class(type_id)
            mapping = getattr(scale_class, "type_mapping", None)
            if _is_tuple_class(scale_class) and mapping is not None and len(mapping) == 1:
                return (_adapt(runtime, fields[0]["type"], value),)
            return value
        if isinstance(value, Mapping) and all(f["name"] for f in fields):
            return {
                f["name"]: _adapt(runtime, f["type"], value[f["name"]])
                for f in fields
                if f["name"] in value
            }
        if isinstance(value, (list, tuple)) and len(value) == len(fields):
            return [_adapt(runtime, f["type"], v) for f, v in zip(fields, value, strict=True)]
        return value
    if "sequence" in definition and isinstance(value, (list, tuple)):
        return [_adapt(runtime, definition["sequence"]["type"], v) for v in value]
    if "array" in definition and isinstance(value, (list, tuple)):
        return [_adapt(runtime, definition["array"]["type"], v) for v in value]
    if "tuple" in definition and isinstance(value, (list, tuple)):
        types = definition["tuple"]
        if len(types) == len(value):
            return [_adapt(runtime, t, v) for t, v in zip(types, value, strict=True)]
        return value
    if "variant" in definition and isinstance(value, Mapping) and len(value) == 1:
        ((name, inner),) = value.items()
        for variant in definition["variant"]["variants"]:
            if variant["name"] != name:
                continue
            fields = variant["fields"]
            if len(fields) == 1 and fields[0]["name"] is None:
                return {name: _adapt(runtime, fields[0]["type"], inner)}
            if isinstance(inner, Mapping):
                return {
                    name: {
                        f["name"]: _adapt(runtime, f["type"], inner[f["name"]])
                        for f in fields
                        if f["name"] in inner
                    }
                }
            if isinstance(inner, (list, tuple)) and len(inner) == len(fields):
                adapted = [
                    _adapt(runtime, f["type"], v) for f, v in zip(fields, inner, strict=True)
                ]
                return {name: adapted}
        return value
    return value


def _is_tuple_class(scale_class: Any) -> bool:
    from scalecodec.types import Tuple

    return isinstance(scale_class, type) and issubclass(scale_class, Tuple)


def compose_call(
    runtime: Runtime, pallet: str, function: str, args: Mapping[str, Any] | None = None
) -> Call:
    """Encode ``pallet.function(**args)`` for this runtime.

    Arguments are checked against the metadata: a missing or unknown one is an
    :class:`~robonomicsinterface.errors.EncodeError`, as is a value that does
    not fit its type.
    """

    args = dict(args or {})
    fields = runtime.call_fields(pallet, function)
    names = [name for name, _ in fields]
    missing = [name for name in names if name not in args]
    unknown = [name for name in args if name not in names]
    if missing or unknown:
        raise EncodeError(
            f"{pallet}.{function} takes ({', '.join(str(n) for n in names)}); "
            f"missing {missing or 'nothing'}, unknown {unknown or 'nothing'}"
        )
    adapted = {name: _adapt(runtime, type_id, args[name]) for name, type_id in fields if name}
    scale_value = {"call_module": pallet, "call_function": function, "call_args": adapted}
    try:
        scale_call = runtime.scale_config.create_scale_object(
            "Call", metadata=runtime.scale_metadata
        )
        data = bytes(scale_call.encode(scale_value).data)
    except Exception as e:
        raise EncodeError(f"{pallet}.{function}: the arguments do not encode ({e})") from e
    return Call(pallet, function, args, data, scale_value, runtime.version.spec_version)


# Signing


@dataclass(frozen=True, slots=True)
class SigningContext:
    """What a signature commits to besides the call: nonce, era, tip, chain."""

    nonce: int
    era: Era
    birth_hash: str
    genesis_hash: str
    spec_version: int
    transaction_version: int
    tip: int = 0


ExtensionValue = Callable[[SigningContext], Any]

# identifier -> (explicit value, implicit value). ``None`` means the part must be empty.
EXTENSION_VALUES: dict[str, tuple[ExtensionValue | None, ExtensionValue | None]] = {
    "CheckMortality": (lambda c: c.era.encode(), lambda c: c.birth_hash),
    "CheckEra": (lambda c: c.era.encode(), lambda c: c.birth_hash),
    "CheckNonce": (lambda c: c.nonce, None),
    "ChargeTransactionPayment": (lambda c: c.tip, None),
    "ChargeAssetTxPayment": (lambda c: {"tip": c.tip, "asset_id": None}, None),
    "CheckMetadataHash": (lambda c: "Disabled", lambda c: None),
    "CheckSpecVersion": (None, lambda c: c.spec_version),
    "CheckTxVersion": (None, lambda c: c.transaction_version),
    "CheckGenesis": (None, lambda c: c.genesis_hash),
}
_RAW_ERA_EXTENSIONS = {"CheckMortality", "CheckEra"}


def _extension_parts(runtime: Runtime, context: SigningContext) -> tuple[bytes, bytes]:
    explicit, implicit = b"", b""
    for extension in runtime.signed_extensions:
        explicit_value, implicit_value = EXTENSION_VALUES.get(extension.identifier, (None, None))
        for type_id, value, part in (
            (extension.explicit_type, explicit_value, "explicit"),
            (extension.implicit_type, implicit_value, "implicit"),
        ):
            if runtime.is_empty_type(type_id):
                continue
            if value is None:
                raise UnsupportedExtension(
                    f"the runtime requires signed extension {extension.identifier} "
                    f"({part} part), which this library cannot fill in"
                )
            if part == "explicit" and extension.identifier in _RAW_ERA_EXTENSIONS:
                encoded = value(context)  # the era is already encoded
            else:
                encoded = runtime.encode(f"scale_info::{type_id}", value(context))
            if part == "explicit":
                explicit += encoded
            else:
                implicit += encoded
    return explicit, implicit


@dataclass(frozen=True)
class SignedExtrinsic:
    """A signed extrinsic, ready for ``author_submitExtrinsic``."""

    data: bytes = field(repr=False)
    hash: str
    call: Call
    signer: str
    nonce: int
    era: Era

    @property
    def hex(self) -> str:
        return "0x" + self.data.hex()


def sign_extrinsic(
    runtime: Runtime, call: Call, keypair: Keypair, context: SigningContext
) -> SignedExtrinsic:
    """Sign ``call`` with ``keypair`` as a version-4 extrinsic."""

    if runtime.extrinsic_version != 4:
        raise MetadataError(f"extrinsic version {runtime.extrinsic_version} is not supported")
    explicit, implicit = _extension_parts(runtime, context)
    payload = call.data + explicit + implicit
    if len(payload) > _MAX_UNHASHED_PAYLOAD:
        payload = _blake2_256(payload)
    signature = keypair.sign(payload)

    address = runtime.encode(
        f"scale_info::{runtime.extrinsic_param_type('Address')}",
        _adapt_multi(runtime, "Address", {"Id": "0x" + keypair.public_key.hex()}),
    )
    signature_bytes = runtime.encode(
        f"scale_info::{runtime.extrinsic_param_type('Signature')}",
        _adapt_multi(runtime, "Signature", {"Ed25519": "0x" + signature.hex()}),
    )
    body = bytes([_SIGNED_BIT | 4]) + address + signature_bytes + explicit + call.data
    data = _compact(len(body)) + body
    return SignedExtrinsic(
        data=data,
        hash=extrinsic_hash(data),
        call=call,
        signer=keypair.address,
        nonce=context.nonce,
        era=context.era,
    )


def _adapt_multi(runtime: Runtime, param: str, value: dict[str, str]) -> Any:
    """Use the enum form for MultiAddress/MultiSignature, the bare value otherwise."""

    definition = runtime.type_info(runtime.extrinsic_param_type(param))["def"]
    if "variant" in definition:
        return value
    return next(iter(value.values()))


# What the chain says


_INVALID_TRANSACTION = (
    "Call",
    "Payment",
    "Future",
    "Stale",
    "BadProof",
    "AncientBirthBlock",
    "ExhaustsResources",
    "Custom",
    "BadMandatory",
    "MandatoryValidation",
    "BadSigner",
    "IndeterminateImplicit",
    "UnknownOrigin",
)
_UNKNOWN_TRANSACTION = ("CannotLookup", "NoUnsignedValidator", "Custom")

INVALID_EXPLANATIONS = {
    "Payment": (
        "the signer cannot pay for the transaction. On Robonomics this usually means the "
        "account does not exist on chain: its balance is below the existential deposit "
        "(0.000001 XRT). RWS calls are free, but the signer must exist — send it the "
        "existential deposit once"
    ),
    "Future": "the nonce is ahead of the account's; an earlier transaction is still pending",
    "Stale": "the nonce was already used; this transaction was probably sent already",
    "BadProof": ("the signature does not verify: it was made for another chain or runtime version"),
    "AncientBirthBlock": "the transaction's era refers to a block too old; sign it again",
    "ExhaustsResources": "the block is full; try again shortly",
    "Call": "the call is not allowed by the runtime",
    "BadSigner": "the signer is not allowed to send this transaction",
    "CannotLookup": "an account in the transaction could not be looked up",
}


def explain_invalid_transaction(raw: bytes) -> tuple[str, str] | None:
    """Decode a ``TransactionValidity``: ``None`` if valid, else ``(kind, explanation)``.

    ``raw`` is the answer of ``TaggedTransactionQueue_validate_transaction``.
    """

    if not raw or raw[0] == 0:
        return None
    if len(raw) < 3:
        return "Unreadable", "the runtime returned an unreadable validity"
    table = _INVALID_TRANSACTION if raw[1] == 0 else _UNKNOWN_TRANSACTION
    kind = table[raw[2]] if raw[2] < len(table) else f"Unknown#{raw[2]}"
    if kind == "Custom":
        code = raw[3] if len(raw) > 3 else None
        return f"Custom({code})", "rejected by a runtime-specific check"
    return kind, INVALID_EXPLANATIONS.get(kind, "rejected by the runtime")


@dataclass(frozen=True, slots=True)
class Event:
    """One runtime event, e.g. ``Event("Datalog", "NewRecord", (...))``."""

    pallet: str
    name: str
    attributes: Any
    extrinsic_index: int | None


def decode_events(records: list[dict[str, Any]]) -> list[Event]:
    """Turn decoded ``System.Events`` records into :class:`Event` objects."""

    return [
        Event(
            pallet=record["module_id"],
            name=record["event_id"],
            attributes=record.get("attributes"),
            extrinsic_index=record.get("extrinsic_idx"),
        )
        for record in records
    ]


@dataclass(frozen=True)
class ExtrinsicResult:
    """An extrinsic that made it into a block, and the events it produced."""

    extrinsic_hash: str
    block_hash: str
    block_number: int
    index: int
    events: tuple[Event, ...]
    finalized: bool

    def find(self, pallet: str, name: str) -> Event | None:
        """The first event ``pallet.name`` of this extrinsic, if any."""

        return next((e for e in self.events if e.pallet == pallet and e.name == name), None)


MODULE_HINTS = {
    ("RWS", "NotLinkedDevice"): (
        "the signer is not in the subscription's device list; the owner adds it with "
        "RWS.set_devices"
    ),
    ("RWS", "FreeWeightIsNotEnough"): (
        "the subscription has no free transaction allowance left: it has expired (an "
        "expired daily subscription stays on chain but stops accruing), or it is used up "
        "for now — wait and try again, or send less often"
    ),
    ("RWS", "NoSubscription"): "the subscription owner has no RWS subscription",
    ("Datalog", "RecordTooBig"): "a datalog record is limited to 512 bytes",
}


def dispatch_error_message(
    runtime: Runtime, dispatch_error: Any
) -> tuple[str | None, str, str, str]:
    """Explain a ``DispatchError``: ``(pallet, error, docs, message)``."""

    if isinstance(dispatch_error, Mapping) and "Module" in dispatch_error:
        module = dispatch_error["Module"]
        error = module["error"]
        error_index = (
            bytes.fromhex(error.removeprefix("0x"))[0] if isinstance(error, str) else int(error)
        )
        resolved = runtime.module_error(int(module["index"]), error_index)
        if resolved is None:
            name = f"module {module['index']} error {error_index}"
            return None, name, "", f"the call failed: {name}"
        hint = MODULE_HINTS.get((resolved.pallet, resolved.name)) or resolved.docs
        message = f"{resolved.pallet}.{resolved.name}" + (f": {hint}" if hint else "")
        return resolved.pallet, resolved.name, resolved.docs, message
    if isinstance(dispatch_error, Mapping) and len(dispatch_error) == 1:
        ((kind, detail),) = dispatch_error.items()
        name = f"{kind}.{detail}" if isinstance(detail, str) else str(kind)
        return None, name, "", f"the call failed: {name}"
    return None, str(dispatch_error), "", f"the call failed: {dispatch_error}"
