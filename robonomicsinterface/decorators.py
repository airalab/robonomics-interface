import substrateinterface as substrate

from functools import wraps


def connect_close_substrate_node(func):
    """
    Open and close substrate node connection each time needed.

    :param func: wrapped function.

    :return: wrapped function after augmentations.

    """

    @wraps(func)
    def wrapper(ri_instance, *args, **kwargs):
        """
        Wrap decorated function with interface opening/closing.

        :param ri_instance: RobonomicsInterface instance in a decorated function.
        :param args: Wrapped function args.
        :param kwargs: Wrapped function kwargs.

        """
        ri_instance.interface = substrate.SubstrateInterface(
            url=ri_instance.remote_ws,
            ss58_format=32,
            type_registry_preset="substrate-node-template",
            type_registry=ri_instance.type_registry,
        )
        res = func(ri_instance, *args, **kwargs)
        ri_instance.interface.close()
        return res

    return wrapper
