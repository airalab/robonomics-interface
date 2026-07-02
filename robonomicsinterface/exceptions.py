class NoPrivateKeyException(Exception):
    """
    No private key was provided so unable to perform any operations requiring message signing.

    """

    pass


class DigitalTwinMapException(Exception):
    """
    No Digital Twin was created with this index or there is no such topic in Digital Twin map.

    """

    pass


class InvalidHash(Exception):
    """
    Invalid 32-byte hex hash format.
    """

    pass


class InvalidExtrinsicHash(InvalidHash):
    """
    Invalid extrinsic hash format.

    """

    pass


class InvalidExtrinsicIndex(Exception):
    """
    Invalid extrinsic index for block lookup.
    """

    pass


class RPCRequestException(Exception):
    """
    RPC request returned an error or malformed response.
    """

    def __init__(self, message: str, error=None):
        self.error = error
        super().__init__(message)


class AmbiguousExtrinsicSubmissionException(Exception):
    """
    The node connection was lost after submitting an extrinsic.

    The transaction may have reached the node, so the library must not submit it
    again automatically.
    """

    def __init__(self, message: str, extrinsic_hash=None):
        self.extrinsic_hash = extrinsic_hash
        super().__init__(message)
