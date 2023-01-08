from typer import Typer
from rich.console import Console

from ble_multimeter import VERSION
import ble_multimeter.ble_commands as ble_commands


app = Typer(add_completion=True, no_args_is_help=True)
app.add_typer(ble_commands.app, name="ble", short_help="Bluetooth BLE utilities")
console = Console()


@app.command("version")
def version():
    """
    cli version
    """
    console.print(VERSION)
