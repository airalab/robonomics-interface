import pytest
from click.testing import CliRunner

import robonomicsinterface.robonomics_interface_io as cli_io


class FakeAccount:
    def __init__(self, remote_ws=None, seed=None):
        self.remote_ws = remote_ws
        self.seed = seed

    def get_address(self):
        return "alice-address"


@pytest.mark.parametrize(
    ("stdin_value", "expected"),
    [
        ("ON\n", "ON"),
        ("ON", "ON"),
        ("", ""),
    ],
)
def test_write_datalog_preserves_input_without_trailing_newline(
    monkeypatch, stdin_value, expected
):
    """CLI datalog input should trim only newline characters."""
    records = []

    class FakeDatalog:
        def __init__(self, account):
            self.account = account

        def record(self, data):
            records.append(data)
            return "0xrecord"

    monkeypatch.setattr(cli_io, "Account", FakeAccount)
    monkeypatch.setattr(cli_io, "Datalog", FakeDatalog)

    result = CliRunner().invoke(
        cli_io.cli,
        ["write", "datalog", "-s", "//Alice", "--input_string", "-"],
        input=stdin_value,
    )

    assert result.exit_code == 0
    assert records == [expected]
    assert "0xrecord" in result.output


@pytest.mark.parametrize(
    ("stdin_value", "expected"),
    [
        ("ON\n", "ON"),
        ("ON", "ON"),
        ("", ""),
    ],
)
def test_write_launch_preserves_input_without_trailing_newline(
    monkeypatch, stdin_value, expected
):
    """CLI launch input should trim only newline characters."""
    launches = []

    class FakeLaunch:
        def __init__(self, account):
            self.account = account

        def launch(self, target_address, parameter):
            launches.append((target_address, parameter))
            return "0xlaunch"

    monkeypatch.setattr(cli_io, "Account", FakeAccount)
    monkeypatch.setattr(cli_io, "Launch", FakeLaunch)

    result = CliRunner().invoke(
        cli_io.cli,
        ["write", "launch", "-s", "//Alice", "-r", "robot-address", "--command", "-"],
        input=stdin_value,
    )

    assert result.exit_code == 0
    assert launches == [("robot-address", expected)]
    assert "0xlaunch" in result.output
