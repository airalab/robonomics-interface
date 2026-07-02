import substrateinterface as substrate

from functools import wraps
from time import sleep
from websocket._exceptions import WebSocketConnectionClosedException


def check_socket_opened(func=None, *, retry=True, backoff_seconds=0.2):
    """
    Open and substrate node connection each time needed.

    :param func: wrapped function.
    :param retry: Whether to retry the wrapped function once after reconnecting.
    :param backoff_seconds: Delay before retrying after a socket error.

    :return: wrapped function after augmentations.

    """

    def decorator(wrapped_func):
        @wraps(wrapped_func)
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
                res = wrapped_func(ri_instance, *args, **kwargs)
            except (BrokenPipeError, WebSocketConnectionClosedException):
                if not retry:
                    raise
                sleep(backoff_seconds)
                open_interface(ri_instance)
                res = wrapped_func(ri_instance, *args, **kwargs)

            return res

        return wrapper

    if func is None:
        return decorator

    return decorator(func)


def open_interface(ri_instance):

    ri_instance.interface = substrate.SubstrateInterface(
        url=ri_instance.remote_ws,
        ss58_format=32,
        type_registry_preset="substrate-node-template",
        type_registry=ri_instance.type_registry,
    )
