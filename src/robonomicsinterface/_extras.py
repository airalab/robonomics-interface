"""Imports for the optional ``[sr25519]`` extra, made when first needed."""

from importlib import import_module
from types import ModuleType

__all__ = ["require"]


def require(name: str) -> ModuleType:
    """Import a module of the ``sr25519`` extra, or say how to install it."""

    try:
        return import_module(name)
    except ImportError as e:
        raise ImportError(
            f"sr25519 needs the {name!r} package: pip install 'robonomics-interface[sr25519]'"
        ) from e
