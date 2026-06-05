import os
from urllib.parse import urlparse

import pytest
from helpers import (
    RWS_E2E_TPS,
    account_id_call_param,
    assert_successful_receipt,
    is_local_dev_chain,
    require_runtime_call,
)
from substrateinterface import SubstrateInterface

from robonomicsinterface.classes.account import Account
from robonomicsinterface.constants import TYPE_REGISTRY

DEFAULT_E2E_RPC_URL = "ws://127.0.0.1:9944"
LOCAL_E2E_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_local_e2e_url(rpc_url):
    return urlparse(rpc_url).hostname in LOCAL_E2E_HOSTS


@pytest.fixture(scope="session")
def e2e_rpc_url():
    rpc_url = os.environ.get("ROBONOMICS_E2E_RPC_URL", DEFAULT_E2E_RPC_URL)
    allow_remote = os.environ.get("ROBONOMICS_E2E_ALLOW_REMOTE") == "1"
    if not _is_local_e2e_url(rpc_url) and not allow_remote:
        pytest.skip(
            "Local-node write tests require a loopback RPC URL. Set "
            "ROBONOMICS_E2E_ALLOW_REMOTE=1 to opt in to a remote dev node."
        )
    return rpc_url


@pytest.fixture(scope="session")
def e2e_substrate(e2e_rpc_url):
    try:
        interface = SubstrateInterface(
            url=e2e_rpc_url,
            ss58_format=32,
            type_registry_preset="substrate-node-template",
            type_registry=TYPE_REGISTRY,
        )
        interface.init_runtime()
    except Exception as exc:
        pytest.skip(
            f"Local Robonomics e2e node is not available at {e2e_rpc_url}: {exc}"
        )

    if not is_local_dev_chain(interface.chain):
        pytest.skip(
            f"Refusing to run write e2e tests against non-dev chain: {interface.chain}"
        )

    yield interface
    interface.close()


@pytest.fixture
def e2e_alice(e2e_rpc_url):
    return Account(
        seed=os.environ.get("ROBONOMICS_E2E_ALICE_SEED", "//Alice"),
        remote_ws=e2e_rpc_url,
    )


@pytest.fixture
def e2e_bob(e2e_rpc_url):
    return Account(
        seed=os.environ.get("ROBONOMICS_E2E_BOB_SEED", "//Bob"),
        remote_ws=e2e_rpc_url,
    )


@pytest.fixture
def e2e_rws_subscription(e2e_substrate, e2e_alice):
    """Ensure Alice has an RWS subscription on a local dev node."""
    require_runtime_call(e2e_substrate, "Sudo", "sudo")
    require_runtime_call(e2e_substrate, "RWS", "set_oracle")
    require_runtime_call(e2e_substrate, "RWS", "set_subscription")

    alice_address = e2e_alice.get_address()
    ledger = e2e_substrate.query("RWS", "Ledger", [alice_address]).value
    lifetime = ledger.get("kind", {}).get("Lifetime", {}) if ledger else {}
    if lifetime.get("tps", 0) >= RWS_E2E_TPS:
        return ledger

    sudo_key = e2e_substrate.query("Sudo", "Key").value
    if sudo_key != alice_address:
        pytest.skip("RWS e2e setup requires Alice to be the local dev sudo key")

    oracle = e2e_substrate.query("RWS", "Oracle").value
    if oracle != alice_address:
        set_oracle = e2e_substrate.compose_call(
            call_module="RWS",
            call_function="set_oracle",
            call_params={"new": alice_address},
        )
        sudo_set_oracle = e2e_substrate.compose_call(
            call_module="Sudo",
            call_function="sudo",
            call_params={"call": set_oracle},
        )
        extrinsic = e2e_substrate.create_signed_extrinsic(
            call=sudo_set_oracle,
            keypair=e2e_alice.keypair,
        )
        receipt = e2e_substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
        assert_successful_receipt(receipt)

    set_subscription = e2e_substrate.compose_call(
        call_module="RWS",
        call_function="set_subscription",
        call_params={
            "target": alice_address,
            "subscription": {"Lifetime": {"tps": RWS_E2E_TPS}},
        },
    )
    extrinsic = e2e_substrate.create_signed_extrinsic(
        call=set_subscription,
        keypair=e2e_alice.keypair,
    )
    receipt = e2e_substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    assert_successful_receipt(receipt)

    ledger = e2e_substrate.query("RWS", "Ledger", [alice_address]).value
    assert ledger is not None
    return ledger


@pytest.fixture
def e2e_rws_device(e2e_substrate, e2e_alice, e2e_bob, e2e_rws_subscription):
    """Ensure Bob is linked as an RWS device for Alice's subscription."""
    require_runtime_call(e2e_substrate, "RWS", "set_devices")

    alice_address = e2e_alice.get_address()
    bob_address = e2e_bob.get_address()
    devices = e2e_substrate.query("RWS", "Devices", [alice_address]).value or []
    if bob_address in devices:
        return devices

    set_devices = e2e_substrate.compose_call(
        call_module="RWS",
        call_function="set_devices",
        call_params={"devices": [account_id_call_param(bob_address)]},
    )
    extrinsic = e2e_substrate.create_signed_extrinsic(
        call=set_devices,
        keypair=e2e_alice.keypair,
    )
    receipt = e2e_substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True)
    assert_successful_receipt(receipt)

    devices = e2e_substrate.query("RWS", "Devices", [alice_address]).value or []
    assert bob_address in devices
    return devices
