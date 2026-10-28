"""The core works without the ``[sr25519]`` extra, and asks for it clearly when needed."""

import importlib
import sys

import pytest

from robonomicsinterface._extras import require


def test_installed_module_is_returned() -> None:
    pytest.importorskip("rbcl")
    pytest.importorskip("sr25519")
    assert require("rbcl").__name__ == "rbcl"
    assert require("sr25519").__name__ == "sr25519"


def test_missing_extra_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sr25519", None)
    with pytest.raises(ImportError, match=r"robonomics-interface\[sr25519\]"):
        require("sr25519")


def test_core_imports_without_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [m for m in sys.modules if m.split(".")[0] == "robonomicsinterface"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "sr25519", None)
    monkeypatch.setitem(sys.modules, "rbcl", None)

    package = importlib.import_module("robonomicsinterface")

    assert package.Keypair.from_mnemonic(package.generate_mnemonic()).has_secret


def test_sr25519_keys_without_the_extra_ask_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from robonomicsinterface import Keypair

    monkeypatch.setitem(sys.modules, "sr25519", None)
    with pytest.raises(ImportError, match=r"robonomics-interface\[sr25519\]"):
        Keypair.from_seed(bytes(32), crypto_type="sr25519")
    assert Keypair.from_seed(bytes(32)).has_secret
