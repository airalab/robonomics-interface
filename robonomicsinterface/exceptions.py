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


class InvalidExtrinsicHash(Exception):
    """
    Invalid extrinsic hash format. Hash length is not 66 signs, or it doesn't start from 0x.

    """

    pass
