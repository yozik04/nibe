from __future__ import annotations

from ast import literal_eval
import asyncio
from contextlib import AbstractAsyncContextManager
import io
import logging
from typing import IO

import asyncclick as click
from construct import Const, GreedyRange, Int8ul, RawCopy, Select, Struct, Terminated

from ..coil import Coil
from ..connection import Connection
from ..connection.modbus import Modbus
from ..connection.nibegw import NibeGW, Request, Response
from ..exceptions import NibeException
from ..heatpump import HeatPump, Model

Ack = Struct("fields" / RawCopy(Struct("Ack" / Const(0x06, Int8ul))))

Nak = Struct("fields" / RawCopy(Struct("Nak" / Const(0x15, Int8ul))))

Block = Select(
    Terminated,
    Response,
    Request,
    Ack,
    Nak,
)

Stream = GreedyRange(Block)


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
    def on_coil_update(coil: Coil):
        click.echo(f"{coil.name}: {coil.value}")

    obj.heatpump.subscribe(HeatPump.COIL_UPDATE_EVENT, on_coil_update)

    while True:
        await asyncio.sleep(1)


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
    if coil.mappings:
        coil.value = value
    else:
        coil.value = float(value)
    click.echo(await obj.connection.write_coil(coil))


add_connect_command(read)


@cli.command()
@click.argument("data", type=str)
@click.option("--type", type=click.Choice(["hex", "bytes"]), default="hex")
async def parse_data(data: str, type: str):
    if type == "hex":
        raw = bytes.fromhex(data)
    elif type == "bytes":
        raw = bytes(literal_eval(data))
    request = Block.parse(raw)
    click.echo(request)


def read_bytes_socat(file: IO):
    lines: list[str] = file.readlines()

    for line in lines:
        if line.startswith("> "):
            continue
        yield from bytes.fromhex(line)


def parse_stream(stream: io.RawIOBase):
    while block := Block.parse_stream(stream):
        yield block


@cli.command()
@click.argument("file", type=click.File())
def parse_file(file: IO):

    with io.BytesIO(bytes(read_bytes_socat(file))) as stream:

        for packet in parse_stream(stream):
            click.echo(packet.fields.value)

        remaining = stream.read()
        if remaining:
            click.echo(f"Remaining: {stream.read()}")


def main():
    try:
        cli()
    except NibeException as exception:
        click.echo(repr(exception))
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
