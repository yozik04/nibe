from __future__ import annotations

from ast import literal_eval
from contextlib import AbstractAsyncContextManager
import io
import logging
from pathlib import Path
import re
from typing import IO

import asyncclick as click

from ..coil import CoilData
from ..connection import Connection
from ..connection.modbus import Modbus
from ..connection.nibegw import Block, NibeGW
from ..exceptions import CoilNotFoundException, NibeException
from ..heatpump import HeatPump, Model, Series
from ..log_set import (
    DATABASE_VERSION,
    MODBUS40_SLOTS,
    format_log_set,
    log_set_slots,
    parse_log_set,
)


@click.group()
@click.option("-v", "--verbose", count=True)
async def cli(verbose: int):
    if verbose == 0:
        log_level = logging.WARNING
    elif verbose == 1:
        log_level = logging.INFO
    else:
        log_level = logging.DEBUG

    logging.basicConfig(
        format="[%(levelname)-8s] %(message)s",
        level=log_level,
    )
    logging.log(logging.INFO, "Log level set to %r", log_level)


class ConnectionContext(AbstractAsyncContextManager):
    def __init__(self, heatpump: HeatPump, connection: Connection) -> None:
        self.heatpump = heatpump
        self.connection = connection

    async def __aenter__(self) -> ConnectionContext:
        await self.connection.start()
        return self

    async def __aexit__(self, __exc_type, __exc_value, __traceback):
        await self.connection.stop()


@cli.group(chain=True, help="Connect using nibegw protocol")
@click.argument("remote_ip", type=str)
@click.option("--listening_ip", type=str)
@click.option("--listening_port", type=int, default=10090)
@click.option("--remote_read_port", type=int, default=10091)
@click.option("--remote_write_port", type=int, default=10092)
@click.option(
    "--model",
    type=click.Choice([model.name for model in Model.__members__.values()]),
    default=None,
)
@click.pass_context
async def nibegw(
    ctx: click.Context,
    remote_ip: str,
    listening_port: int,
    listening_ip: str | None,
    remote_read_port: int,
    remote_write_port: int,
    model: str | None,
):
    heatpump = HeatPump()
    if model:
        heatpump.model = Model[model]
        await heatpump.initialize()

    connection = NibeGW(
        heatpump=heatpump,
        remote_ip=remote_ip,
        listening_port=listening_port,
        listening_ip=listening_ip,
        remote_read_port=remote_read_port,
        remote_write_port=remote_write_port,
    )

    ctx.obj = await ctx.with_async_resource(ConnectionContext(heatpump, connection))


@cli.group(chain=True, help="Connect using modbus protocol")
@click.argument("remote_ip", type=str)
@click.option("--remote_port", type=int, default=502)
@click.option("--slave_id", type=int, default=1)
@click.option(
    "--model",
    type=click.Choice([model.name for model in Model]),
    default=Model.F1155.name,
)
@click.pass_context
async def modbus(
    ctx: click.Context, remote_ip: str, remote_port: str, model: str, slave_id: int
):
    heatpump = HeatPump(Model[model])
    await heatpump.initialize()
    connection = Modbus(
        heatpump=heatpump,
        url=f"tcp://{remote_ip}:{remote_port}",
        slave_id=slave_id,
    )

    ctx.obj = await ctx.with_async_resource(ConnectionContext(heatpump, connection))


def add_connect_command(command: click.Command):
    nibegw.add_command(command)
    modbus.add_command(command)


@click.command(help="Monitor data sent by pump out of band")
@click.pass_obj
async def monitor(obj: ConnectionContext):
    # Imported here so other commands start without loading textual.
    from .tui_monitor import MonitorApp

    app = MonitorApp()
    obj.heatpump.subscribe(HeatPump.COIL_UPDATE_EVENT, app.update_coil)
    await app.run_async()


add_connect_command(monitor)


@click.command()
@click.pass_obj
async def product(obj: ConnectionContext):
    product_info = await obj.connection.read_product_info()
    click.echo(product_info)


add_connect_command(product)


@click.command()
@click.pass_obj
@click.argument("parameter", type=int)
async def read(obj: ConnectionContext, parameter: int, **kwargs):
    coil = obj.heatpump.get_coil_by_address(parameter)
    click.echo(await obj.connection.read_coil(coil))


add_connect_command(read)


@click.command()
@click.pass_obj
@click.argument("parameter", type=int)
@click.argument("value", type=str)
async def write(obj: ConnectionContext, parameter: int, value: str, **kwargs):
    coil = obj.heatpump.get_coil_by_address(parameter)
    if not coil.mappings:
        value = float(value)

    coil_data = CoilData(coil, value)
    await obj.connection.write_coil(coil_data)
    click.echo(coil_data)


add_connect_command(write)


@cli.command()
@click.argument("data", type=str)
@click.option("--type", type=click.Choice(["hex", "bytes"]), default="hex")
async def parse_data(data: str, type: str):
    if type == "hex":
        raw = bytes.fromhex(data)
    elif type == "bytes":
        raw = bytes(literal_eval(data))

    with io.BytesIO(bytes(raw)) as stream:
        for packet in parse_stream(stream):
            click.echo(packet)

        remaining = stream.read()
        if remaining:
            click.echo(f"Remaining: {stream.read()}")


def read_bytes_socat(file: IO):
    lines: list[str] = file.readlines()

    for line in lines:
        if line.startswith("> "):
            continue
        yield from bytes.fromhex(line)


RE_NIBEPI_LOG = re.compile(r"Serial: \[((?:[0-9]+,?)+)\]")


def read_bytes_nibepi(file: IO):
    lines: list[str] = file.readlines()
    for line in lines:
        data = RE_NIBEPI_LOG.match(line)
        if data:
            yield from map(int, data.group(1).split(","))


def parse_stream(stream: io.RawIOBase):
    while block := Block.parse_stream(stream):
        yield block


@cli.command()
@click.argument("file", type=click.File())
@click.option("--type", type=click.Choice(["hex", "nibepi"]), default="hex")
def parse_file(file: IO, type: str):
    if type == "hex":
        data = read_bytes_socat(file)
    elif type == "nibepi":
        data = read_bytes_nibepi(file)
    else:
        raise ValueError("invalid argument")

    with io.BytesIO(bytes(data)) as stream:
        for packet in parse_stream(stream):
            click.echo(packet)

        remaining = stream.read()
        if remaining:
            click.echo(f"Remaining: {stream.read()}")


LOG_SET_MODELS = [model.name for model in Model if model.series == Series.F]


@cli.command(help="Create a LOG.SET file with the registers MODBUS40 should send")
@click.argument("model", type=click.Choice(LOG_SET_MODELS), metavar="MODEL")
@click.argument("addresses", type=int, nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default="LOG.SET",
    show_default=True,
)
@click.option("--database-version", default=DATABASE_VERSION, show_default=True)
async def log_set(
    model: str, addresses: tuple[int, ...], output: Path, database_version: str
):
    heatpump = HeatPump(Model[model])
    await heatpump.initialize()
    try:
        coils = [heatpump.get_coil_by_address(address) for address in addresses]
    except CoilNotFoundException as exception:
        raise click.BadParameter(str(exception), param_hint="ADDRESSES") from exception

    slots = log_set_slots(coils)
    if slots > MODBUS40_SLOTS:
        click.echo(
            f"Warning: the registers take {slots} slots,"
            f" MODBUS40 only sends the first {MODBUS40_SLOTS}",
            err=True,
        )
    output.write_bytes(format_log_set(coils, database_version=database_version))
    click.echo(f"Wrote {len(coils)} registers ({slots} slots) to {output}")


@cli.command(help="Select the registers of a LOG.SET file interactively")
@click.argument("model", type=click.Choice(LOG_SET_MODELS), metavar="MODEL")
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default="LOG.SET",
    show_default=True,
    help="File to edit, its registers are loaded when it exists",
)
@click.option("--database-version", default=DATABASE_VERSION, show_default=True)
async def log_set_edit(model: str, output: Path, database_version: str):
    # Imported here so other commands start without loading textual.
    from .tui_log_set import LogSetApp

    heatpump = HeatPump(Model[model])
    await heatpump.initialize()
    selected = parse_log_set(output.read_bytes()) if output.exists() else []
    try:
        for address in selected:
            heatpump.get_coil_by_address(address)
    except CoilNotFoundException as exception:
        raise click.BadParameter(str(exception), param_hint="--output") from exception
    await LogSetApp(
        heatpump.get_coils(), selected, output, database_version
    ).run_async()


def main():
    try:
        cli()
    except NibeException as exception:
        click.echo(repr(exception))
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
