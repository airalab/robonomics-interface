"""Regenerate sr25519_old_stack.json from the 2.x stack (substrate-interface 1.7).

Not run in CI. The vectors pin what the old stack produced for sr25519, so 3.1 can
prove it derives the same accounts, accepts the same signatures and opens the same
ECIES messages:

    uv venv -p 3.12 oldstack && uv pip install -p oldstack substrate-interface==1.7.11 rbcl
    git clone https://github.com/Fingerling42/py-sr25519-encryption ecies
    git -C ecies checkout bf06b3b7351f969c990c65af5fe620928facb9ed
    oldstack/bin/python tests/fixtures/generate_sr25519_old_stack.py ecies \\
        > tests/fixtures/sr25519_old_stack.json

The ECIES messages come from Ivan Berman's py-sr25519-encryption (Apache-2.0) at the
commit above, unchanged. sr25519 signatures are randomized, so they are stored to be
verified, never compared byte for byte.

All mnemonics are public test phrases; never put a real account here.
"""

import json
import sys
from pathlib import Path

from bip39 import bip39_to_mini_secret
from substrateinterface import Keypair, KeypairType

DEV_PHRASE = "bottom drive obey lake curtain smoke basket hold race lonely fit walk"
MNEMONICS = [
    DEV_PHRASE,
    "frozen woman pet meat entire question balcony wing echo excess adjust sleep",
    "lens exchange drum inside current bullet include stamp purity decline absurd play",
    "legal winner thank year wave sausage worth useful legal winner thank yellow",
    "letter advice cage absurd amount doctor acoustic avoid letter advice cage absurd amount doctor acoustic avoid letter always",
]
PASSWORDS = ["", "Substrate", "пароль"]
# The 2.x stack has no passwords in an sr25519 URI; polkadot.js covers `///` (generate_sr25519_js.mjs).
URIS = [
    "//Alice",
    "//Bob",
    "//Alice//stash",
    "//Alice/stash",
    "//Alice/stash//x/y",
    "//Bob//Charlie",
    "//1",
    DEV_PHRASE + "/1",
    DEV_PHRASE + "/soft",
    "//" + "a" * 40,  # longer than a chain code: hashed
    MNEMONICS[1] + "//hard/soft",
]
MESSAGES = ["", "report payload", "отчёт 📦", "x" * 300, "x" * 4096]
ECIES_MESSAGES = [b"", b"Some bytes", "отчёт 📦".encode(), bytes(range(32)), b"x" * 4096]
WARNING = (
    "PUBLIC TEST KEYS. Every mnemonic and URI here is a published test secret "
    "(Substrate dev phrase, BIP39 vectors, throwaway accounts). Anyone can "
    "derive their keys: never fund these accounts, give them a subscription, or use "
    "them for a real site."
)


def sr25519(**kwargs):
    return dict(crypto_type=KeypairType.SR25519, **kwargs)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
    from sr25519_ecies_decrypt import sr25519_decrypt
    from sr25519_ecies_encrypt import sr25519_encrypt

    accounts = []
    for mnemonic in MNEMONICS:
        for password in PASSWORDS:
            mini = bytes(bip39_to_mini_secret(mnemonic, password))
            kp = Keypair.create_from_seed(mini.hex(), **sr25519(ss58_format=32))
            if password == "":
                via_mnemonic = Keypair.create_from_mnemonic(mnemonic, **sr25519(ss58_format=32))
                assert via_mnemonic.public_key == kp.public_key
            accounts.append(
                {
                    "mnemonic": mnemonic,
                    "password": password,
                    "mini_secret_hex": mini.hex(),
                    "public_key_hex": kp.public_key.hex(),
                    "secret_key_hex": kp.private_key.hex(),  # 64 bytes, schnorrkel native form
                    "address_32": kp.ss58_address,
                    "address_42": Keypair.create_from_seed(
                        mini.hex(), **sr25519(ss58_format=42)
                    ).ss58_address,
                }
            )

    uris = []
    for uri in URIS:
        kp = Keypair.create_from_uri(uri, **sr25519(ss58_format=32))
        uris.append(
            {"uri": uri, "public_key_hex": kp.public_key.hex(), "address_32": kp.ss58_address}
        )

    signer = Keypair.create_from_mnemonic(MNEMONICS[1], **sr25519(ss58_format=32))
    signatures = []
    for message in MESSAGES:
        signature = signer.sign(message)
        assert signer.verify(message, signature)
        signatures.append({"message": message, "signature_hex": bytes(signature).hex()})

    receiver = Keypair.create_from_mnemonic(MNEMONICS[2], **sr25519(ss58_format=32))
    sender = Keypair.create_from_mnemonic(MNEMONICS[1], **sr25519(ss58_format=32))
    ecies = []
    for message in ECIES_MESSAGES:
        for sender_keypair, kind in ((None, "ephemeral"), (sender, "sender_key")):
            blob = sr25519_encrypt(message, receiver.public_key, sender_keypair)
            opened, message_public_key = sr25519_decrypt(blob, receiver.private_key)
            assert opened == message
            ecies.append(
                {
                    "kind": kind,
                    "plaintext_hex": message.hex(),
                    "message_public_key_hex": message_public_key.hex(),
                    "blob_hex": blob.hex(),
                }
            )

    print(
        json.dumps(
            {
                "warning": WARNING,
                "generator": "substrate-interface 1.7.11, sr25519; "
                "py-sr25519-encryption bf06b3b7351f969c990c65af5fe620928facb9ed",
                "accounts": accounts,
                "uris": uris,
                "signatures": {"signer_mnemonic": MNEMONICS[1], "vectors": signatures},
                "ecies": {"recipient_mnemonic": MNEMONICS[2], "vectors": ecies},
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
