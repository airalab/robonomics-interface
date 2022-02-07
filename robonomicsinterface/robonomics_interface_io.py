import click
import sys

from robonomicsinterface import RobonomicsInterface as RI, constants, Subscriber, SubEvent


def callback(data):
    """
    callback executed when subscription event triggered. Simply outputs incoming info to console

    @param data: data to be output
    """
    click.echo(data)


@click.group()
def cli():
    pass


@cli.group(help="Send various extrinsics (launch commands or record datalogs)")
def write():
    pass


@cli.group(help="Subscribe to datalog/launch events in the chain")
def read():
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
    interface: RI = RI(remote_ws=remote_ws, seed=s)
    transaction_hash: str = interface.record_datalog(input_string.readline()[:-1])
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
def launch(command, remote_ws, s, r) -> None:
    """
    Send ON|OFF launch commands using pipeline:  <echo "ON" | robonomics_interface io write launch (params)>
    If nothing passed, waits for a string in a new line. Sends "True" if "ON" passed, anything else results in "OFF".
    """
    interface: RI = RI(remote_ws=remote_ws, seed=s)
    if command.readline()[:-1] == "ON":
        transaction_hash: str = interface.send_launch(r, True)
        click.echo((transaction_hash, f"{interface.define_address()} -> {r}: true"))
    else:
        transaction_hash: str = interface.send_launch(r, False)
        click.echo((transaction_hash, f"{interface.define_address()} -> {r}: false"))


@read.command()
@click.option(
    "--remote_ws",
    type=str,
    default=constants.REMOTE_WS,
    help="Node websocket address used to connect to any node. E.g. local is ws://127.0.0.1:9944. Default is "
    "wss://kusama.rpc.robonomics.network",
)
@click.option("-r", type=str, help="Target account ss58_address.")
def datalog(remote_ws: str, r: str):
    """
    Listen to datalogs in the chain whether address-specified or all of them
    """
    interface: RI = RI(remote_ws=remote_ws)
    subscriber: Subscriber = Subscriber(interface, SubEvent.NewRecord, subscription_handler=callback, addr=r)
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
def launch(remote_ws: str, r: str):
    """
    Listen to datalogs in the chain whether address-specified or all of them
    """
    interface: RI = RI(remote_ws=remote_ws)
    subscriber: Subscriber = Subscriber(interface, SubEvent.NewLaunch, subscription_handler=callback, addr=r)
    pass


if __name__ == "__main__":
    cli()
