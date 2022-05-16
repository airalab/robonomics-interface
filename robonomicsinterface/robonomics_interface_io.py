import click
import sys

import typing as tp

from robonomicsinterface import Account, constants, Datalog, Launch, SubEvent, Subscriber


def callback(data: tp.Tuple[tp.Union[str, int]]) -> None:
    """
    callback executed when subscription event triggered. Simply outputs incoming info to console

    :param data: data to be output

    """
    click.echo(data)


@click.group()
def cli() -> None:
    pass


@cli.group(help="Send various extrinsics (launch commands or record datalogs)")
def write() -> None:
    pass


@cli.group(help="Subscribe to datalog/launch events in the chain")
def read() -> None:
    pass


@write.command()
@click.option(
    "--input_string",
    type=click.File("r"),
    default=sys.stdin,
    hidden=True,
    help="Hidden parameter to perform stdin reading of a passed via pipeline sting",
)
@click.option(
    "--remote_ws",
    type=str,
    default=constants.REMOTE_WS,
    help="Node websocket address used to connect to any node. E.g. local is ws://127.0.0.1:9944. Default is "
    "wss://kusama.rpc.robonomics.network",
)
@click.option("-s", type=str, required=True, help="Account seed in mnemonic/raw form.")
def datalog(input_string: sys.stdin, remote_ws: str, s: str) -> None:
    """
    Save string into account's datalog using pipeline:  <echo "blah" | robonomics_interface io write datalog (params)>
    If nothing passed, waits for a string in a new line.
    """
    account: Account = Account(remote_ws=remote_ws, seed=s)
    datalog_: Datalog = Datalog(account)
    transaction_hash: str = datalog_.record(input_string.readline()[:-1])
    click.echo(transaction_hash)


@write.command()
@click.option(
    "--command",
    type=click.File("r"),
    default=sys.stdin,
    hidden=True,
    help="Hidden parameter to perform stdin reading of a passed via pipeline command",
)
@click.option(
    "--remote_ws",
    type=str,
    default=constants.REMOTE_WS,
    help="Node websocket address used to connect to any node. E.g. local is ws://127.0.0.1:9944. Default is "
    "wss://kusama.rpc.robonomics.network",
)
@click.option("-s", type=str, required=True, help="Account seed in mnemonic/raw form.")
@click.option("-r", type=str, required=True, help="Target account ss58_address.")
def launch(command: sys.stdin, remote_ws: str, s: str, r: str) -> None:
    """
    Send launch command accompanied by parameter in IPFS Qm... form or just 32 bytes data using pipeline:
    <echo "Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z" | robonomics_interface io write launch (params)>
    If nothing passed, waits for a string in a new line.
    """
    account: Account = Account(remote_ws=remote_ws, seed=s)
    launch_: Launch = Launch(account)
    parameter: str = command.readline()[:-1]
    transaction_hash: str = launch_.launch(r, parameter)
    click.echo((transaction_hash, f"{account.get_address()} -> {r}: {parameter}"))


@read.command()
@click.option(
    "--remote_ws",
    type=str,
    default=constants.REMOTE_WS,
    help="Node websocket address used to connect to any node. E.g. local is ws://127.0.0.1:9944. Default is "
    "wss://kusama.rpc.robonomics.network",
)
@click.option("-r", type=str, help="Target account ss58_address.")
def datalog(remote_ws: str, r: str) -> None:
    """
    Listen to datalogs in the chain whether address-specified or all of them
    """
    account: Account = Account(remote_ws=remote_ws)
    subscriber: Subscriber = Subscriber(account, SubEvent.NewRecord, subscription_handler=callback, addr=r)
    pass


@read.command()
@click.option(
    "--remote_ws",
    type=str,
    default=constants.REMOTE_WS,
    help="Node websocket address used to connect to any node. E.g. local is ws://127.0.0.1:9944. Default is "
    "wss://kusama.rpc.robonomics.network",
)
@click.option("-r", type=str, help="Target account ss58_address.")
def launch(remote_ws: str, r: str) -> None:
    """
    Listen to datalogs in the chain whether address-specified or all of them
    """
    account: Account = Account(remote_ws=remote_ws)
    subscriber: Subscriber = Subscriber(account, SubEvent.NewLaunch, subscription_handler=callback, addr=r)
    pass


if __name__ == "__main__":
    cli()
