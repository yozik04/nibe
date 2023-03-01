import asyncio
import binascii
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

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

    async def test_read_multiple_with_u32(self):
        on_coil_update_mock = Mock()
        self.heatpump.subscribe("coil_update", on_coil_update_mock)
        self.nibegw.datagram_received(
            binascii.unhexlify(
                "5c00206850c9af0000889c7100a9a90a00a3a91400aba90000939c0000949c0000919c0000929c00008f9c0000909c00003ab95000ada94600a7a91400faa90200ffff0000ffff0000ffff0000ffff0000ffff0000cc"
            ),
            ("127.0.0.1", 12345),
        )

        on_coil_update_mock.assert_any_call(
            CoilData(self.heatpump.get_coil_by_address(45001), 0.0)
        )
        on_coil_update_mock.assert_any_call(
            CoilData(self.heatpump.get_coil_by_address(43514), 2.0)
        )
