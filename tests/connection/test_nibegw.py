import asyncio
import binascii
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, call

import pytest

from nibe.coil import CoilData
from nibe.connection.nibegw import ConnectionStatus, NibeGW
from nibe.exceptions import ReadException, ReadTimeoutException, WriteException
from nibe.heatpump import HeatPump, Model, ProductInfo


class TestNibeGW(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.loop = asyncio.get_running_loop()

        self.heatpump = HeatPump(Model.F1255)
        self.heatpump.word_swap = True
        await self.heatpump.initialize()
        self.nibegw = NibeGW(self.heatpump, "127.0.0.1")

        self.transport = Mock()
        assert self.nibegw.status == ConnectionStatus.UNKNOWN
        self.nibegw.connection_made(self.transport)

    async def test_status(self):
        assert self.nibegw.status == ConnectionStatus.LISTENING

        connection_status_handler_mock = Mock()
        self.nibegw.subscribe(
            NibeGW.CONNECTION_STATUS_EVENT, connection_status_handler_mock
        )

        coil = self.heatpump.get_coil_by_address(43424)

        self._enqueue_datagram(binascii.unhexlify("5c00206a06a0a9f5120000a2"))

        await self.nibegw.read_coil(coil)

        assert self.nibegw.status == ConnectionStatus.CONNECTED
        connection_status_handler_mock.assert_called_once_with(
            status=ConnectionStatus.CONNECTED
        )

        connection_status_handler_mock.reset_mock()
        self._enqueue_datagram(binascii.unhexlify("5c00206a06a0a9f5120000a2"))
        await self.nibegw.read_coil(coil)
        connection_status_handler_mock.assert_not_called()

    def _enqueue_datagram(self, data):
        asyncio.get_event_loop().call_soon(
            self.nibegw.datagram_received, data, ("127.0.0.1", 12345)
        )

    async def test_read_s32_coil(self):
        coil = self.heatpump.get_coil_by_address(43424)

        self._enqueue_datagram(binascii.unhexlify("5c00206a06a0a9f5120000a2"))

        coil_data = await self.nibegw.read_coil(coil)
        assert coil_data.value == 4853

        self.transport.sendto.assert_called_once_with(
            binascii.unhexlify("c06902a0a9a2"), ("127.0.0.1", 9999)
        )

    async def test_write_s32_coil(self):
        coil = self.heatpump.get_coil_by_address(40940)
        coil_data = CoilData(coil, -10)

        self._enqueue_datagram(binascii.unhexlify("5c00206c01014c"))
        await self.nibegw.write_coil(coil_data)

        self.transport.sendto.assert_called_once_with(
            binascii.unhexlify("c06b06ec9f9cffffffbd"), ("127.0.0.1", 10000)
        )

    async def test_read_coil_decode_failed(self):
        coil = self.heatpump.get_coil_by_address(43086)

        self._enqueue_datagram(binascii.unhexlify("5c00206a064ea8f51200004d"))

        start = time.time()
        with pytest.raises(ReadException) as excinfo:
            await self.nibegw.read_coil(coil, timeout=0.1)
            assert "Decode failed" in str(excinfo.value)
        assert 1 == self.transport.sendto.call_count
        duration = time.time() - start
        assert duration <= 0.1

    async def test_read_coil_timeout(self):
        coil = self.heatpump.get_coil_by_address(43086)

        start = time.time()
        with pytest.raises(ReadTimeoutException):
            await self.nibegw.read_coil(coil, timeout=0.1)
        duration = time.time() - start
        assert (
            0.3 <= duration <= 0.4
        ), "Timeout should be between 0.3 and 0.4 seconds. We do 3 retries"
        assert 3 == self.transport.sendto.call_count, "Should do 3 retries"
        self.transport.sendto.assert_called_with(
            b"\xc0i\x02N\xa8M", ("127.0.0.1", 9999)
        )

    async def test_write_coil(self):
        coil = self.heatpump.get_coil_by_address(48132)
        coil_data = CoilData(coil, "One time increase")

        self._enqueue_datagram(binascii.unhexlify("5c00206c01014c"))
        await self.nibegw.write_coil(coil_data)

        self.transport.sendto.assert_called_once_with(
            binascii.unhexlify("c06b0604bc0400000011"), ("127.0.0.1", 10000)
        )

    async def test_write_coil_failed(self):
        coil = self.heatpump.get_coil_by_address(48132)
        coil_data = CoilData(coil, "One time increase")

        self._enqueue_datagram(binascii.unhexlify("5c00206c01004d"))
        with pytest.raises(WriteException):
            await self.nibegw.write_coil(coil_data)

        assert 1 == self.transport.sendto.call_count, "Should only send once, no retry"

    async def test_read_product_info(self):
        self._enqueue_datagram(
            binascii.unhexlify("5c00206d0d0124e346313235352d313220529f")
        )
        product = await self.nibegw.read_product_info()

        assert isinstance(product, ProductInfo)
        assert "F1255-12 R" == product.model

    async def test_read_multiple_with_u32_1(self):
        on_coil_update_mock = Mock()
        self.heatpump.subscribe("coil_update", on_coil_update_mock)
        self.nibegw.datagram_received(
            binascii.unhexlify(
                "5c00206850c9af0000889c7100a9a90a00a3a91400aba90000939c0000949c0000919c3c00929c00008f9c0000909c00003ab95000ada94600a7a91400faa90200ffff0000ffff0000ffff0000ffff0000ffff0000f0"
            ),
            ("127.0.0.1", 12345),
        )

        def _call(address, value):
            return call(CoilData(self.heatpump.get_coil_by_address(address), value))

        assert on_coil_update_mock.mock_calls == [
            _call(40072, 11.3),
            _call(40079, 0.0),
            _call(40081, 6.0),
            _call(40083, 0.0),
            _call(43427, "STOPPED"),
            _call(43431, "ON"),
            _call(43433, "OFF"),
            _call(43435, "OFF"),
            _call(43437, 70),
            _call(43514, 2),
            _call(45001, 0),
            _call(47418, 80),
        ]

    async def test_read_multiple_with_u32_2(self):
        on_coil_update_mock = Mock()
        self.heatpump.subscribe("coil_update", on_coil_update_mock)
        self.nibegw.datagram_received(
            binascii.unhexlify(
                "5c00206850 489ce400 4c9ce300 4e9ca101 889c4500 d5a1ae00 d6a1a300 fda718f8 c5a5ad98c6a50100 cda5d897cea50100 cfa51fb7d0a50600 98a96d23 99a90000 a0a9cf05 a1a90000 9ca9a01a 9da90000 449c4500 e5".replace(
                    " ", ""
                )
            ),
            ("127.0.0.1", 12345),
        )

        def _call(address, value):
            return call(CoilData(self.heatpump.get_coil_by_address(address), value))

        # Values with 0000 will not be included in the call list
        assert on_coil_update_mock.mock_calls == [
            _call(40004, 6.9),
            _call(40008, 22.8),
            _call(40012, 22.7),
            _call(40014, 41.7),
            _call(40072, 6.9),
            _call(41429, 17.4),
            _call(41430, 16.3),
            _call(
                42437, 10462.1
            ),  # 32-bit register occupies two addresses (42437, 42438): c5a5 ad98 c6a5 0100
            _call(
                42445, 10440.8
            ),  # 32-bit register occupies two addresses (42445, 42446): cda5 d897 cea5 0100
            _call(
                42447, 44009.5
            ),  # 32-bit register occupies two addresses (42447, 42448): cfa5 1fb7 d0a5 0600
            _call(43005, -202.4),
            _call(43416, 9069),
            _call(43420, 6816),
            _call(43424, 1487),
        ]
