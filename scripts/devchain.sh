#!/usr/bin/env bash
# Run a Robonomics development node for the integration tests.
#
#   scripts/devchain.sh            # node on ws://127.0.0.1:9944, in the foreground
#   PORT=9955 scripts/devchain.sh
#
# Downloads pinned, checksum-verified releases into $DEVCHAIN_DIR (default
# .devchain): polkadot-omni-node and chain-spec-builder from Parity, and the
# Robonomics runtime that runs on mainnet. Builds the `development` chain spec
# and patches it for ED25519 dev accounts (scripts/dev_chain_spec.py).
set -euo pipefail

POLKADOT_SDK="polkadot-stable2606-2"
RUNTIME_TAG="v50"
RUNTIME="robonomics_runtime.compact.compressed.wasm"
RUNTIME_SHA256="136a37bad459b92f9994147ec43166901a94c00a6cb2f34f3475869b64501820"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)
    SUFFIX=""
    NODE_SHA256="b85f59bdea6fd005fcb948bdb48ab90e6814e5511c5406c0556bb3efa77e45a9"
    BUILDER_SHA256="1e229496d6f5c948bb6e510c3e481de3cac0040707659be55b9133e91f446419"
    ;;
  Darwin-arm64)
    SUFFIX="-aarch64-apple-darwin"
    NODE_SHA256="1fa97ad532da1f74eb51031f260fa48402a4bbbdaedd1198b2f65d936e9d37b1"
    BUILDER_SHA256="cf05112e772a9a355384ce5b6950b9a074fb7fe061a89b012a8c62e79242570e"
    ;;
  *)
    echo "no prebuilt polkadot-omni-node for $(uname -s)-$(uname -m)" >&2
    exit 1
    ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${DEVCHAIN_DIR:-$ROOT/.devchain}"
PORT="${PORT:-9944}"
mkdir -p "$DIR"

fetch() {  # url file sha256
  local url="$1" file="$DIR/$2" sum="$3"
  if [ ! -f "$file" ] || ! echo "$sum  $file" | shasum -a 256 -c --status; then
    echo "downloading $2"
    curl -fsSL --retry 3 -o "$file.part" "$url"
    echo "$sum  $file.part" | shasum -a 256 -c --status || {
      echo "checksum mismatch for $2" >&2
      rm -f "$file.part"
      exit 1
    }
    mv "$file.part" "$file"
    chmod +x "$file"
  fi
}

SDK_URL="https://github.com/paritytech/polkadot-sdk/releases/download/$POLKADOT_SDK"
fetch "$SDK_URL/polkadot-omni-node$SUFFIX" polkadot-omni-node "$NODE_SHA256"
fetch "$SDK_URL/chain-spec-builder$SUFFIX" chain-spec-builder "$BUILDER_SHA256"
fetch "https://github.com/airalab/robonomics/releases/download/$RUNTIME_TAG/$RUNTIME" \
  "$RUNTIME" "$RUNTIME_SHA256"

SPEC="$DIR/spec.json"
"$DIR/chain-spec-builder" -c "$SPEC" create -t development -r "$DIR/$RUNTIME" \
  --relay-chain rococo-local --para-id 2048 named-preset development
(cd "$ROOT" && ${PYTHON:-uv run python} scripts/dev_chain_spec.py "$SPEC")

exec "$DIR/polkadot-omni-node" --chain "$SPEC" --dev --rpc-port "$PORT" --dev-block-time 1000
