import substrateinterface as substrate

from functools import wraps
from websocket._exceptions import WebSocketConnectionClosedException


def check_socket_opened(func):
    """
    Open and substrate node connection each time needed.

    :param func: wrapped function.

    :return: wrapped function after augmentations.

    """

    @wraps(func)
    def wrapper(ri_instance, *args, **kwargs):
        """
        Wrap decorated function with interface opening if it was closed.

        :param ri_instance: RobonomicsInterface instance in a decorated function.
        :param args: Wrapped function args.
        :param kwargs: Wrapped function kwargs.

        """

        if not ri_instance.interface:
            open_interface(ri_instance)

        try:
            res = func(ri_instance, *args, **kwargs)
        except (BrokenPipeError, WebSocketConnectionClosedException):
            open_interface(ri_instance)
            res = func(ri_instance, *args, **kwargs)

        return res

    return wrapper


def open_interface(ri_instance):

    ri_instance.interface = substrate.SubstrateInterface(
        url=ri_instance.remote_ws,
        ss58_format=32,
        type_registry_preset="substrate-node-template",
        type_registry=ri_instance.type_registry,
    )
