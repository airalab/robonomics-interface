import pytest

from robonomicsinterface.classes.account import Account
from robonomicsinterface.constants import REMOTE_WS, TYPE_REGISTRY
from robonomicsinterface.exceptions import NoPrivateKeyException

MNEMONIC = "bottom drive obey lake curtain smoke basket hold race lonely fit walk"


def test_account_creates_keypair_from_development_uri():
    account = Account(seed="//Alice")

    assert account.get_address() == "4GzMLepDF5nKTWDM6XpB3CrBcFmwgazcVFAD3ZBNAjKT6hQJ"


def test_account_creates_keypair_from_raw_seed():
    account = Account(seed="0x" + "01" * 32)

    assert account.get_address() == "4CkPG37kTzsJeCMmsbgSJDjkGAUrpLexKAPg21rvT2YM7SiA"


def test_account_creates_keypair_from_mnemonic():
    account = Account(seed=MNEMONIC)

    assert account.get_address() == "4Do6h3zbQtr3nYLETbSQPK5pmYyjzoqy6E8yy1vATg4N24aL"


def test_account_without_seed_uses_default_connection_settings():
    account = Account()

    assert account.keypair is None
    assert account.remote_ws == REMOTE_WS
    assert account.type_registry == TYPE_REGISTRY


def test_account_without_seed_has_no_address():
    account = Account()

    with pytest.raises(NoPrivateKeyException):
        account.get_address()


@pytest.mark.xfail(
    reason="Account dataclass declares no fields, so all instances compare equal"
)
def test_accounts_with_different_keys_are_not_equal():
    """Accounts should compare by meaningful state, not as empty dataclasses."""
    assert Account(seed="//Alice") != Account(seed="//Bob")
