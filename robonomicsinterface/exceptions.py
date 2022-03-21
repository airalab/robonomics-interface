class NoPrivateKey(Exception):
    """
    No private key was provided so unable to perform any operations requiring message signing.

    """
    pass


class DigitalTwinMapError(Exception):
    """
    No Digital Twin was created with this index or there is no such topic in Digital Twin map.

    """
    pass
