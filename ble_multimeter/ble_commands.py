from time import sleep
from rich.console import Console
import typer
from typer import Typer
import pendulum

import asyncio
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice

from ble_multimeter.mm_ble_message import MmBleMessage

class MmDisconnectException(Exception):
    """
    Exception to throw when we want to disconnect from the device
    """
    pass

app = Typer(add_completion=True, no_args_is_help=True)
console = Console()
err_console = Console(stderr=True, style="red")

global_opts = {
    'verbose': False
}

MM_DEVICE_NAME = "QM1578_DMM"

date_format = 'YYYY-MM-DD HH:mm:ss.SSSSSSZ'

mm_msg = MmBleMessage(15, b"\xd5\xf0\x00\x0a")
last_msg_dttm = pendulum.now()

@app.callback()
def callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
):
    """
    Bluetooth BLE utilities
    """
    global global_opts
    global_opts['verbose'] = verbose


@app.command("scan")
def mm_scan():
    """
    Scan for all available bluetooth devices
    """
    with console.status("Scanning for BLE devices ..."):
        devices = asyncio.run(BleakScanner.discover())
    for d in devices:
        console.print(d)


def mm_reader_raw(sender: int, data: bytearray) -> None:
    console.print(f"{pendulum.now().format(date_format)} sender: {sender}: {data.hex('-')}")


def mm_reader_msg(sender: int, data: bytearray) -> None:
    """
    Read the incoming bytes and assemble into completed messages.
    Assumes each call back will contain either a complete message or a partial message.
    There won't be multiple messages is a single call back.
    """
    global mm_msg, last_msg_dttm, global_opts, date_format
    for b in data:
        if global_opts['verbose']:
            console.print(f"sender: {sender}: {b:02x}")
        mm_msg.do_byte(b)
    if mm_msg.last_msg_dttm > last_msg_dttm:
        last_msg_dttm = mm_msg.last_msg_dttm
        console.print(f"{last_msg_dttm.format(date_format)}: sender: {sender}: {mm_msg.payload.hex('-')}")

def mm_reader_monitor(sender: int, data: bytearray) -> None:
    """
    Read incoming and assemble into completed messages.
    Prints out formated information on device readings.
    """
    global mm_msg, last_msg_dttm, global_opts, date_format
    for b in data:
        # if global_opts['verbose']:
        #     console.print(f"sender: {sender}: {b:02x}")
        mm_msg.do_byte(b)
    if mm_msg.last_msg_dttm > last_msg_dttm:
        last_msg_dttm = mm_msg.last_msg_dttm
        try:
            mm_reading = {
                'timestamp': last_msg_dttm.format(date_format),
                'mode': mm_msg.mm_mode(),
                'value': f"{mm_msg.mm_value():.{mm_msg.mm_decimal_places()}f}",
                'units': mm_msg.mm_units(),
            }
            console.print(mm_reading)
        except ValueError as e:
            if global_opts['verbose']:
                err_console.print(f"Invalid value: {mm_msg.payload.hex('-')}")
            # skip invalid value messages
            pass




async def find_mm_device(device_name: str) -> BLEDevice:
    """
    Find a given BLE device by name.

    Return the BLEDevice, if found, otherwise None
    """
    global global_opts
    with console.status("Scanning for multimeter bluetooth ..."):
        devices = await BleakScanner.discover()
    device = None
    for d in devices:
        if d.name == device_name:
            device = d
    if device:
        console.print(f"Found multimeter device: {device}")
    else:
        err_console.print("Multimeter device not found.")

    if global_opts['verbose']:
        console.print(f"address: {device.address}")
        console.print(f"details: {device.details}")
        console.print(f"metadata: {device.metadata}")
        console.print(f"name: {device.name}")
        console.print(f"rssi: {device.rssi}")

    return device


async def mm_start_listening(device: BLEDevice, snoop: bool = False, monitor=True) -> None:
    """
    mm client
    """
    disconnected_event = asyncio.Event()
    def mm_disconnected(client:BleakClient) -> None:
        err_console.print("--- device disconnected ---")
        disconnected_event.set()

    async with BleakClient(device, disconnected_callback=mm_disconnected) as client:
        # for s in client.services:
        #     console.print(f"service: {s}")
        #     characteristicts = s.characteristics
        #     for c in characteristicts:
        #         console.print(f"characteristic: {c}")
        mm_svc = client.services.get_service("fff0")
        mm_char = mm_svc.get_characteristic("fff2")
        console.print(f"characteristic: {mm_char}")
        if snoop is True:
            await client.start_notify(mm_char, mm_reader_raw)
        elif monitor is True:
            await client.start_notify(mm_char, mm_reader_monitor)
        else:
            await client.start_notify(mm_char, mm_reader_msg)    
        await disconnected_event.wait()


@app.command("find")
def mm_find():
    """
    Scan for a transmitting Bluetooth enabled multi-meter
    """
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(find_mm_device(MM_DEVICE_NAME))
    except KeyboardInterrupt:
        err_console.print("monitoring aborted")
    finally:
        loop.stop() if loop.is_running() else None
        if not loop.is_closed():
            loop.close()

@app.command("snoop")
def mm_snoop():
    """
    Find and listen to the raw byte stream from a Bluetooth enabled multi-meter
    """
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(mm_start_listening(snoop=True))
    except KeyboardInterrupt:
        err_console.print("monitoring aborted")
    finally:
        loop.stop()
        loop.close()


@app.command("listen")
def mm_listen():
    """
    Find and listen to the binary messages from a Bluetooth enabled multi-meter
    
    Will try and reconnect on disconnect
    """
    retry_attempt = 0
    max_retries = 3
    retry_window = 30 # seconds
    global MM_DEVICE_NAME

    loop = asyncio.get_event_loop() or asyncio.new_event_loop()
    loop.set_debug(True)
    asyncio.set_event_loop(loop)

    with console.status("Scanning for multimeter bluetooth ..."):
        devices = loop.run_until_complete(BleakScanner.discover())
    device = None
    for d in devices:
        if d.name == MM_DEVICE_NAME:
            device = d
    if device is None:
        err_console.print("Multimeter device not found.")
        raise typer.Exit(code=1)

    try:
        retrying = False
        while retry_attempt <= max_retries:
            try:
                if retrying: err_console.print(f"retry attempt: {retry_attempt}")
                last_retry_attempt = pendulum.now()
                loop.run_until_complete(mm_start_listening(device))
                # reset the retry counter if it's been more than X seconds since the last retry attempts
                if last_retry_attempt < pendulum.now().subtract(seconds=retry_window):
                    err_console.print("resetting retry window")
                    retry_attempt = 0
                retry_attempt += 1
                err_console.print(f"--- retrying to connect ---")
            except asyncio.TimeoutError as e:
                err_console.print(f"--- retry timed out ---")
                break
    except KeyboardInterrupt:
        err_console.print("--- monitoring aborted ---")
        typer.Exit(code=200)

@app.command("monitor")
def mm_monitor():
    """
    Find and listen to the binary messages from a Bluetooth enabled multi-meter
    and provide human readable device readings.
    
    Will try and reconnect on disconnect
    """
    retry_attempt = 0
    max_retries = 3
    retry_window = 30 # seconds
    global MM_DEVICE_NAME

    loop = asyncio.get_event_loop() or asyncio.new_event_loop()
    loop.set_debug(True)
    asyncio.set_event_loop(loop)

    with console.status("Scanning for multimeter bluetooth ..."):
        devices = loop.run_until_complete(BleakScanner.discover())
    device = None
    for d in devices:
        if d.name == MM_DEVICE_NAME:
            device = d
    if device is None:
        err_console.print("Multimeter device not found.")
        raise typer.Exit(code=1)

    try:
        retrying = False
        while retry_attempt <= max_retries:
            try:
                if retrying: err_console.print(f"retry attempt: {retry_attempt}")
                last_retry_attempt = pendulum.now()
                loop.run_until_complete(mm_start_listening(device, snoop=False, monitor=True))
                # reset the retry counter if it's been more than X seconds since the last retry attempts
                if last_retry_attempt < pendulum.now().subtract(seconds=retry_window):
                    err_console.print("resetting retry window")
                    retry_attempt = 0
                retry_attempt += 1
                err_console.print(f"--- retrying to connect ---")
            except asyncio.TimeoutError as e:
                err_console.print(f"--- retry timed out ---")
                break
    except KeyboardInterrupt:
        err_console.print("--- monitoring aborted ---")
        typer.Exit(code=200)