"""Exceptions raised by the library.

Everything derives from :class:`RobonomicsError`, so a caller can catch the
library as a whole. Input errors also derive from :class:`ValueError`: they
describe bad data, and retrying them is pointless.

Messages never contain secrets: no mnemonic, seed or private key is ever
formatted into an exception, including the input that failed to parse.
"""


class RobonomicsError(Exception):
    """Base class for every error raised by robonomics-interface."""


class InvalidMnemonic(RobonomicsError, ValueError):
    """The text is not a valid BIP39 English mnemonic."""


class InvalidAddress(RobonomicsError, ValueError):
    """The text is not a valid SS58 address, or it has an unexpected format."""


class InvalidKey(RobonomicsError, ValueError):
    """A seed, public key or derivation path cannot be used."""


class NoSecretKey(RobonomicsError):
    """The keypair holds a public key only, so it cannot sign or decrypt."""


class DecryptionError(RobonomicsError):
    """A box does not open: wrong keys, or the ciphertext was damaged."""


class MetadataError(RobonomicsError):
    """The runtime metadata cannot be used, or does not describe what was asked."""


class NoSuchPallet(MetadataError, LookupError):
    """The runtime has no pallet with this name."""


class NoSuchStorage(MetadataError, LookupError):
    """The pallet has no storage item with this name."""


class NoSuchConstant(MetadataError, LookupError):
    """The pallet has no constant with this name."""


class EncodeError(RobonomicsError, ValueError):
    """A value does not fit the type the runtime expects, e.g. a bad storage key."""


class DecodeError(RobonomicsError, ValueError):
    """Bytes from the chain do not decode as the type the metadata describes."""


class TransportError(RobonomicsError):
    """The node could not be reached or stopped answering. Retrying may help.

    Every subclass is a network-level failure: the request may not have reached
    the node at all, so nothing is known about its effect.
    """

    retryable = True


class ConnectionFailed(TransportError):
    """A connection to an endpoint could not be opened, or the node is unusable."""

    def __init__(self, endpoint: str, reason: str) -> None:
        super().__init__(f"{endpoint}: {reason}")
        self.endpoint = endpoint
        self.reason = reason


class ConnectionLost(TransportError):
    """The connection closed while a request or subscription was in flight."""


class RequestTimeout(TransportError, TimeoutError):
    """The node did not answer in time."""


class AllEndpointsFailed(TransportError):
    """No endpoint could be used; ``failures`` says why for each of them."""

    def __init__(self, failures: list[ConnectionFailed]) -> None:
        reasons = "; ".join(str(failure) for failure in failures) or "no endpoints configured"
        super().__init__(f"no usable Robonomics node: {reasons}")
        self.failures = failures


class RpcError(RobonomicsError):
    """The node answered with a JSON-RPC error. Repeating the same request will not help."""

    def __init__(self, method: str, code: int | None, message: str, data: object = None) -> None:
        detail = f": {data}" if data not in (None, "") else ""
        super().__init__(f"{method} failed ({code}): {message}{detail}")
        self.method = method
        self.code = code
        self.message = message
        self.data = data


class EnvelopeError(RobonomicsError):
    """Base class for multi-recipient envelope errors."""


class RecipientError(EnvelopeError, ValueError):
    """A recipient address cannot be used to wrap the key."""


class PackageError(EnvelopeError, ValueError):
    """The package is malformed, or not addressed to this recipient."""


class PayloadError(EnvelopeError):
    """The package is well formed but could not be decrypted."""
