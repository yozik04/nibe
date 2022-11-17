from __future__ import annotations

from ast import literal_eval
import asyncio
import io
import logging
from typing import IO

import asyncclick as click
from construct import Const, GreedyRange, Int8ul, RawCopy, Select, Struct, Terminated

from .coil import Coil
from .connection.modbus import Modbus
from .connection.nibegw import NibeGW, Request, Response
from .heatpump import HeatPump, Model

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
async def cli():
    pass


_global_options = [
    click.argument("remote_ip", type=str),
    click.option(
        "--remote_type", type=click.Choice(["nibegw", "modbus"]), default="nibegw"
    ),
    click.option("--listening_ip", type=str),
    click.option("--listening_port", type=int, default=10090),
    click.option("--remote_read_port", type=int, default=10091),
    click.option("--remote_write_port", type=int, default=10092),
    click.option("--slave_id", type=int, default=1),
    click.option(
        "--model",
        type=click.Choice([model.name for model in Model]),
        default=Model.F1155.name,
    ),
    click.option("-v", "--verbose", count=True),
]


def global_options(func):
    for option in reversed(_global_options):
        func = option(func)
    return func


async def global_setup(
    remote_ip: str,
    remote_type: str,
    listening_port: int,
    listening_ip: str | None,
    remote_read_port: int,
    remote_write_port: int,
    model: str,
    verbose: int,
    slave_id: int,
):
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

    heatpump = HeatPump(Model[model])
    heatpump.initialize()
    if remote_type == "nibegw":
        connection = NibeGW(
            heatpump=heatpump,
            remote_ip=remote_ip,
            listening_port=listening_port,
            listening_ip=listening_ip,
            remote_read_port=remote_read_port,
            remote_write_port=remote_write_port,
        )
    elif remote_type == "modbus":
        connection = Modbus(
            heatpump=heatpump,
            url=f"tcp://{remote_ip}:{remote_read_port}",
            slave_id=slave_id,
        )

    await connection.start()

    return heatpump, connection


@cli.command()
@global_options
async def monitor(**kwargs):
    heatpump, _ = await global_setup(**kwargs)

    def on_coil_update(coil: Coil):
        click.echo(f"{coil.name}: {coil.value}")

    heatpump.subscribe(HeatPump.COIL_UPDATE_EVENT, on_coil_update)

    while True:
        await asyncio.sleep(1)


@cli.command()
@global_options
@click.argument("parameter", type=int)
async def read(parameter: int, **kwargs):
    heatpump, connection = await global_setup(**kwargs)

    coil = heatpump.get_coil_by_address(parameter)
    click.echo(await connection.read_coil(coil))


@cli.command()
@global_options
@click.argument("parameter", type=int)
@click.argument("value", type=str)
async def write(parameter: int, value: str, **kwargs):
    heatpump, connection = await global_setup(**kwargs)

    coil = heatpump.get_coil_by_address(parameter)
    if coil.mappings:
        coil.value = value
    else:
        coil.value = float(value)
    click.echo(await connection.write_coil(coil))


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


try:
    cli()
except (KeyboardInterrupt, SystemExit):
    pass
