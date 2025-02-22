import asyncio
import binascii
import time
from typing import Any
from unittest.mock import Mock, call

import pytest

from nibe.coil import CoilData
from nibe.connection.nibegw import ConnectionStatus, NibeGW
from nibe.exceptions import NoMappingException, ReadTimeoutException, WriteException
from nibe.heatpump import HeatPump, Model, ProductInfo


@pytest.fixture(name="heatpump")
async def fixture_heatpump() -> HeatPump:
    heatpump = HeatPump(Model.F1255)
    heatpump.word_swap = True
    await heatpump.initialize()
    return heatpump


@pytest.fixture(name="transport")
async def fixture_transport():
    return Mock()


@pytest.fixture(name="nibegw")
async def fixture_nibegw(heatpump: HeatPump, transport: Mock):
    nibegw = NibeGW(heatpump, "127.0.0.1")
    assert nibegw.status == ConnectionStatus.UNKNOWN
    nibegw.connection_made(transport)
    return nibegw


def _enqueue_datagram(nibegw: NibeGW, data: str):
    asyncio.get_event_loop().call_soon(
        nibegw.datagram_received, binascii.unhexlify(data), ("127.0.0.1", 12345)
    )


async def test_status(nibegw: NibeGW, heatpump: HeatPump):
    assert nibegw.status == ConnectionStatus.LISTENING

    connection_status_handler_mock = Mock()
    nibegw.subscribe(NibeGW.CONNECTION_STATUS_EVENT, connection_status_handler_mock)

    coil = heatpump.get_coil_by_address(43424)

    _enqueue_datagram(nibegw, "5c00206a06a0a9f5120000a2")

    await nibegw.read_coil(coil)

    assert nibegw.status == ConnectionStatus.CONNECTED
    connection_status_handler_mock.assert_called_once_with(
        status=ConnectionStatus.CONNECTED
    )

    connection_status_handler_mock.reset_mock()
    _enqueue_datagram(nibegw, "5c00206a06a0a9f5120000a2")
    await nibegw.read_coil(coil)
    connection_status_handler_mock.assert_not_called()


async def test_read_s32_coil(nibegw: NibeGW, heatpump: HeatPump, transport: Mock):
    coil = heatpump.get_coil_by_address(43424)

    _enqueue_datagram(nibegw, "5c00206a06a0a9f5120000a2")

    coil_data = await nibegw.read_coil(coil)
    assert coil_data.value == 4853

    transport.sendto.assert_called_once_with(
        binascii.unhexlify("c06902a0a9a2"), ("127.0.0.1", 9999)
    )


async def test_write_s32_coil(nibegw: NibeGW, heatpump: HeatPump, transport: Mock):
    coil = heatpump.get_coil_by_address(40940)
    coil_data = CoilData(coil, -10)

    _enqueue_datagram(nibegw, "5c00206c01014c")
    await nibegw.write_coil(coil_data)

    transport.sendto.assert_called_once_with(
        binascii.unhexlify("c06b06ec9f9cffffffbd"), ("127.0.0.1", 10000)
    )


async def test_read_coil_decode_failed(
    nibegw: NibeGW, heatpump: HeatPump, transport: Mock
):
    coil = heatpump.get_coil_by_address(43086)

    _enqueue_datagram(nibegw, "5c00206a064ea8f51200004d")

    start = time.time()
    data = await nibegw.read_coil(coil, timeout=0.1)
    assert data.value == "UNKNOWN (245)"

    with pytest.raises(NoMappingException):
        data.validate()

    assert 1 == transport.sendto.call_count
    duration = time.time() - start
    assert duration <= 0.1


async def test_read_coil_timeout(nibegw: NibeGW, heatpump: HeatPump, transport: Mock):
    coil = heatpump.get_coil_by_address(43086)

    start = time.time()
    with pytest.raises(ReadTimeoutException):
        await nibegw.read_coil(coil, timeout=0.1)
    duration = time.time() - start
    assert (
        0.3 <= duration <= 0.4
    ), "Timeout should be between 0.3 and 0.4 seconds. We do 3 retries"
    assert 3 == transport.sendto.call_count, "Should do 3 retries"
    transport.sendto.assert_called_with(b"\xc0i\x02N\xa8M", ("127.0.0.1", 9999))


async def test_write_coil(nibegw: NibeGW, heatpump: HeatPump, transport: Mock):
    coil = heatpump.get_coil_by_address(48132)
    coil_data = CoilData(coil, "One time increase")

    _enqueue_datagram(nibegw, "5c00206c01014c")
    await nibegw.write_coil(coil_data)

    transport.sendto.assert_called_once_with(
        binascii.unhexlify("c06b0604bc0400000011"), ("127.0.0.1", 10000)
    )


async def test_write_coil_failed(nibegw: NibeGW, heatpump: HeatPump, transport: Mock):
    coil = heatpump.get_coil_by_address(48132)
    coil_data = CoilData(coil, "One time increase")

    _enqueue_datagram(nibegw, "5c00206c01004d")
    with pytest.raises(WriteException):
        await nibegw.write_coil(coil_data)

    assert 1 == transport.sendto.call_count, "Should only send once, no retry"


async def test_read_product_info(nibegw: NibeGW):
    _enqueue_datagram(nibegw, "5c00206d0d0124e346313235352d313220529f")
    product = await nibegw.read_product_info()

    assert isinstance(product, ProductInfo)
    assert "F1255-12 R" == product.model


async def test_read_product_info_with_extras(nibegw: NibeGW):
    _enqueue_datagram(
        nibegw,
        "5c0019ee00f7"  # token accessory version
        "c0ee03ee0101c3"  # accessory version from accessory
        "06"  # ack from pump
        "5c00206d0d0124e346313235352d313220529f",
    )
    product = await nibegw.read_product_info()

    assert isinstance(product, ProductInfo)
    assert "F1255-12 R" == product.model


@pytest.mark.parametrize(
    ("raw", "table_processing_mode", "calls"),
    [
        (
            "5c00206850c9af0000889c7100a9a90a00a3a91400aba90000939c0000949c0000919c3c00929c00008f9c0000909c00003ab95000ada94600a7a91400faa90200ffff0000ffff0000ffff0000ffff0000ffff0000f0",
            "strict",
            [
                (40072, 11.3),
                (40079, 0.0),
                (40081, 6.0),
                (40083, 0.0),
                (43427, "STOPPED"),
                (43431, "ON"),
                (43433, "OFF"),
                (43435, "OFF"),
                (43437, 70),
                (43514, 2),
                (45001, 0),
                (47418, 80),
            ],
        ),
        (
            "5c00206850c9af0000889c7100a9a90a00a3a91400aba90000939c0000949c0000919c3c00929c00008f9c0000909c0000 3ab97000 ada94600 a7a91400 faa90200 ffff0000 ffff0000 ffff0000 ffff0000 ffff0000 d0",
            "permissive",
            [
                (40072, 11.3),
                (40079, 0.0),
                (40081, 6.0),
                (40083, 0.0),
                (43427, "STOPPED"),
                (43431, "ON"),
                (43433, "OFF"),
                (43435, "OFF"),
                (43437, 70),
                (43514, 2),
                (45001, 0),
                # (47418, 80), # This coil will be ignored because of decoding error
            ],
        ),
        (
            "5c00206850c9af0000889c7100a9a90a00a3a91400aba90000939c0000949c0000919c3c00929c00008f9c0000909c0000 3ab97000 ada94600 a7a91400 faa90200 ffff0000 ffff0000 ffff0000 ffff0000 ffff0000 d0",
            "strict",
            [
                # All will be ignored because of single decoding error
            ],
        ),
        (
            "5c00206850 489ce400 4c9ce300 4e9ca101 889c4500 d5a1ae00 d6a1a300 fda718f8 c5a5ad98c6a50100 cda5d897cea50100 cfa51fb7d0a50600 98a96d23 99a90000 a0a9cf05 a1a90000 9ca9a01a 9da90000 449c4500 e5",
            "strict",
            [
                (40004, 6.9),
                (40008, 22.8),
                (40012, 22.7),
                (40014, 41.7),
                (40072, 6.9),
                (41429, 17.4),
                (41430, 16.3),
                (
                    42437,
                    10462.1,
                ),  # 32-bit register occupies two addresses (42437, 42438): c5a5 ad98 c6a5 0100
                (
                    42445,
                    10440.8,
                ),  # 32-bit register occupies two addresses (42445, 42446): cda5 d897 cea5 0100
                (
                    42447,
                    44009.5,
                ),  # 32-bit register occupies two addresses (42447, 42448): cfa5 1fb7 d0a5 0600
                (43005, -202.4),
                (43416, 9069),
                (43420, 6816),
                (43424, 1487),
            ],
        ),
    ],
)
async def test_read_multiple_with_u32(
    nibegw: NibeGW,
    heatpump: HeatPump,
    raw: str,
    table_processing_mode: str,
    calls: list[tuple[int, Any]],
):
    nibegw._table_processing_mode = table_processing_mode
    on_coil_update_mock = Mock()
    heatpump.subscribe("coil_update", on_coil_update_mock)
    nibegw.datagram_received(
        binascii.unhexlify(raw.replace(" ", "")),
        ("127.0.0.1", 12345),
    )

    def _call(address, value):
        return call(CoilData(heatpump.get_coil_by_address(address), value))

    # Values with 0000 will not be included in the call list
    assert on_coil_update_mock.mock_calls == [_call(*call) for call in calls]
