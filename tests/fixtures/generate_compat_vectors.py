"""Regenerate compat_vectors.json from the 2.x stack (substrate-interface 1.7).

Not run in CI. The vectors pin what the old stack produced, so 3.0 can prove it
derives the same addresses and reads the same ciphertexts:

    uv venv -p 3.12 oldstack && uv pip install -p oldstack substrate-interface==1.7.11
    oldstack/bin/python tests/fixtures/generate_compat_vectors.py > tests/fixtures/compat_vectors.json

All mnemonics are public test phrases; never put a real account here.
"""

import json

from bip39 import bip39_to_mini_secret
from substrateinterface import Keypair, KeypairType

DEV_PHRASE = "bottom drive obey lake curtain smoke basket hold race lonely fit walk"
MNEMONICS = [
    DEV_PHRASE,
    "frozen woman pet meat entire question balcony wing echo excess adjust sleep",
    "lens exchange drum inside current bullet include stamp purity decline absurd play",
    "legal winner thank year wave sausage worth useful legal winner thank yellow",
    "letter advice cage absurd amount doctor acoustic avoid letter advice cage absurd amount doctor acoustic avoid letter always",
    "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo vote",
]
PASSWORDS = ["", "Substrate", "пароль"]
SEEDS = [
    "0x" + "00" * 32,
    "0x9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
]
FIXED_NONCE = bytes(range(24))
WARNING = (
    "PUBLIC TEST KEYS. Every mnemonic and seed here is a published test secret "
    "(Substrate dev phrase, BIP39/RFC 8032 vectors, throwaway accounts). Anyone can "
    "derive their keys: never fund these accounts, give them a subscription, or use "
    "them for a real site."
)
MESSAGES = ["", "report payload", "отчёт 📦", "x" * 4096]


def ed25519(**kwargs):
    return dict(crypto_type=KeypairType.ED25519, **kwargs)


def main():
    accounts = []
    for mnemonic in MNEMONICS:
        for password in PASSWORDS:
            mini = bytes(bip39_to_mini_secret(mnemonic, password))
            kp = Keypair.create_from_seed(mini.hex(), **ed25519(ss58_format=32))
            entry = {
                "mnemonic": mnemonic,
                "password": password,
                "mini_secret_hex": mini.hex(),
                "public_key_hex": kp.public_key.hex(),
                "address_32": kp.ss58_address,
                "address_42": Keypair.create_from_seed(
                    mini.hex(), **ed25519(ss58_format=42)
                ).ss58_address,
            }
            if password == "":
                via_mnemonic = Keypair.create_from_mnemonic(mnemonic, **ed25519(ss58_format=32))
                assert via_mnemonic.public_key == kp.public_key
            accounts.append(entry)

    seeds = []
    for seed in SEEDS:
        kp = Keypair.create_from_seed(seed, **ed25519(ss58_format=32))
        seeds.append(
            {"seed_hex": seed, "public_key_hex": kp.public_key.hex(), "address_32": kp.ss58_address}
        )

    sender = Keypair.create_from_mnemonic(MNEMONICS[1], **ed25519(ss58_format=32))
    recipient = Keypair.create_from_mnemonic(MNEMONICS[2], **ed25519(ss58_format=32))
    encryption = []
    signatures = []
    for message in MESSAGES:
        box = sender.encrypt_message(message, recipient.public_key, nonce=FIXED_NONCE)
        assert recipient.decrypt_message(box, sender.public_key) == message.encode()
        encryption.append(
            {"plaintext": message, "nonce_hex": FIXED_NONCE.hex(), "box_hex": bytes(box).hex()}
        )
        signatures.append({"message": message, "signature_hex": sender.sign(message).hex()})

    print(
        json.dumps(
            {
                "warning": WARNING,
                "generator": "substrate-interface 1.7.11, ed25519",
                "accounts": accounts,
                "seeds": seeds,
                "encryption": {
                    "sender_mnemonic": MNEMONICS[1],
                    "recipient_mnemonic": MNEMONICS[2],
                    "vectors": encryption,
                },
                "signatures": {"signer_mnemonic": MNEMONICS[1], "vectors": signatures},
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
