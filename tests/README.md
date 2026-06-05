# Test suite

The default test run is offline:

```bash
poetry run pytest
```

Pytest plugin autoloading is disabled in `pyproject.toml` so globally
installed plugins cannot affect the project test suite.

Read-only checks against the live Robonomics Polkadot RPC endpoint must be
marked with `@pytest.mark.integration` and enabled explicitly:

```bash
poetry run pytest --run-integration -m integration
```

Tests that submit extrinsics must target an explicitly configured local node,
use `@pytest.mark.e2e`, and be enabled explicitly:

```bash
poetry run pytest --run-e2e -m e2e
```

The preferred way to start a local Robonomics dev node is a release binary
matching the runtime version under test. For example, Robonomics `v4.2.0`
matches runtime `specVersion=42`:

```bash
mkdir -p ~/RobonomicsProjects/bin/robonomics-v4.2.0
cd ~/RobonomicsProjects/bin/robonomics-v4.2.0
wget https://github.com/airalab/robonomics/releases/download/v4.2.0/robonomics-v4.2.0-ubuntu-x86_64.tar.gz
tar -xzf robonomics-v4.2.0-ubuntu-x86_64.tar.gz
chmod +x robonomics
./robonomics --dev --tmp --rpc-external
```

Then run the local-node suite from this repository:

```bash
ROBONOMICS_E2E_RPC_URL=ws://127.0.0.1:9944 poetry run pytest --run-e2e tests/e2e
```

E2E write tests accept loopback RPC URLs by default (`127.0.0.1`, `localhost`,
or `::1`). To run them against a remote dev node, set
`ROBONOMICS_E2E_ALLOW_REMOTE=1` explicitly.

Docker can also be used as a fallback, but the published `latest` image may
lag behind the live runtime. The current Docker runtime image needs the binary
name before node flags:

```bash
docker run --rm \
  --name robonomics-dev \
  -p 9944:9944 \
  robonomics/robonomics:latest \
  /usr/local/bin/robonomics \
  --dev \
  --tmp \
  --rpc-external
```

Run the same local-node suite after the Docker node starts:

```bash
ROBONOMICS_E2E_RPC_URL=ws://127.0.0.1:9944 poetry run pytest --run-e2e tests/e2e
```

E2E tests are intentionally kept out of the default GitHub Actions flow until
CI has a reliable current-node artifact. The Docker `latest` image should not
be used for required e2e CI while it lags behind the runtime covered by the
metadata fixtures.

Expected local e2e caveats:

- `DigitalTwin.remove_source` is an expected xfail until the Python wrapper is
  implemented.
- `RWS.set_devices` is an expected xfail until the wrapper encodes the current
  `BoundedVec<AccountId>` shape.
- legacy `RWS.call` creates a local RWS subscription and prepares devices
  during setup. It requires Alice to be the local dev sudo key.

By default, e2e tests use `//Alice` and `//Bob`. Override them with
`ROBONOMICS_E2E_ALICE_SEED` and `ROBONOMICS_E2E_BOB_SEED` if a custom local
genesis needs different funded accounts.

Keep tests in these groups:

- `unit/`: pure logic and mocked wrapper behavior.
- `contract/`: offline runtime metadata fixtures and SCALE contract checks.
- `integration/`: read-only live Polkadot RPC smoke tests.
- `e2e/`: local-node write workflows.
- `fixtures/`: runtime metadata and stable test payloads.

## Runtime metadata fixtures

Contract tests under `tests/contract/` run against every fixture matching:

```bash
tests/fixtures/metadata/robonomics_spec_*.json
```

Export the currently live runtime metadata with:

```bash
poetry run python tools/export_robonomics_metadata_fixture.py
```

Export an expected runtime version, failing if the connected block has a
different `specVersion`:

```bash
poetry run python tools/export_robonomics_metadata_fixture.py --spec-version 42
```

When the live runtime has moved on, pass a historical block:

```bash
poetry run python tools/export_robonomics_metadata_fixture.py --spec-version 42 --block-hash 0x...
```

To validate a freshly exported fixture without copying it into the repository:

```bash
poetry run python tools/export_robonomics_metadata_fixture.py --output-dir /tmp/robonomics-metadata
ROBONOMICS_METADATA_FIXTURE_DIR=/tmp/robonomics-metadata poetry run pytest tests/contract
```
