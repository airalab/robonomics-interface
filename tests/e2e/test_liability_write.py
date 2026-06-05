import pytest
from helpers import HASH_A, HASH_B, events_from_result, has_event, require_runtime_call

from robonomicsinterface.classes.liability import Liability


@pytest.mark.e2e
def test_liability_create_and_finalize(e2e_substrate, e2e_alice, e2e_bob):
    """Create a Liability agreement and finalize it with the promisor account."""
    require_runtime_call(e2e_substrate, "Liability", "create")
    require_runtime_call(e2e_substrate, "Liability", "finalize")
    promisee_liability = Liability(
        e2e_alice,
        wait_for_inclusion=True,
        return_block_num=True,
    )
    promisor_liability = Liability(
        e2e_bob,
        wait_for_inclusion=True,
        return_block_num=True,
    )
    price = 1

    promisee_signature = promisee_liability.sign_liability(HASH_A, price)
    promisor_signature = promisor_liability.sign_liability(HASH_A, price)
    liability_id, create_result = promisee_liability.create(
        HASH_A,
        price,
        e2e_alice.get_address(),
        e2e_bob.get_address(),
        promisee_signature,
        promisor_signature,
    )
    assert has_event(
        events_from_result(e2e_substrate, create_result),
        "Liability",
        "NewLiability",
    )

    agreement = promisee_liability.get_agreement(liability_id)
    assert agreement["promisee"] == e2e_alice.get_address()
    assert agreement["promisor"] == e2e_bob.get_address()

    finalize_result = promisor_liability.finalize(liability_id, HASH_B)
    assert has_event(
        events_from_result(e2e_substrate, finalize_result),
        "Liability",
        "NewReport",
    )

    report = promisee_liability.get_report(liability_id)
    assert report is not None
    assert report["sender"] == e2e_bob.get_address()
