import asyncio
import binascii
from unittest import TestCase
from unittest.mock import Mock

from nibe.connection.nibegw import NibeGW
from nibe.exceptions import CoilReadException, CoilReadTimeoutException
from nibe.heatpump import HeatPump, Model, ProductInfo


class TestNibeGW(TestCase):
    def setUp(self) -> None:
        self.loop = asyncio.get_event_loop_policy().get_event_loop()

        self.heatpump = HeatPump(Model.F1255)
        self.heatpump.initialize()
        self.nibegw = NibeGW(self.heatpump, "127.0.0.1")

        self.transport = Mock()
        self.nibegw.connection_made(self.transport)

    def test_read_s32_coil(self):
        coil = self.heatpump.get_coil_by_address(43424)

        async def send_receive():
            task = self.loop.create_task(self.nibegw.read_coil(coil))
            await asyncio.sleep(0)
            self.nibegw.datagram_received(
                binascii.unhexlify("5c00206a06a0a9f5120000a2"), ("127.0.0.1", 12345)
            )

            return await task

        coil = self.loop.run_until_complete(send_receive())
        self.assertEqual(4853, coil.value)

        self.transport.sendto.assert_called_with(
            binascii.unhexlify("c06902a0a9a2"), ("127.0.0.1", 9999)
        )

    def test_read_coil_decode_exception(self):
        coil = self.heatpump.get_coil_by_address(43086)

        async def send_receive():
            task = self.loop.create_task(self.nibegw.read_coil(coil))
            await asyncio.sleep(0)
            self.nibegw.datagram_received(
                binascii.unhexlify("5c00206a064ea8f51200004d"), ("127.0.0.1", 12345)
            )

            return await task

        with self.assertRaises(CoilReadException):
            self.loop.run_until_complete(send_receive())

    def test_read_coil_timeout_exception(self):
        coil = self.heatpump.get_coil_by_address(43086)

        with self.assertRaises(CoilReadTimeoutException):
            self.loop.run_until_complete(self.nibegw.read_coil(coil, 0.1))

    def test_write_coil(self):
        coil = self.heatpump.get_coil_by_address(48132)
        coil.value = "One time increase"

        async def send_receive():
            task = self.loop.create_task(self.nibegw.write_coil(coil))
            await asyncio.sleep(0)
            self.nibegw.datagram_received(
                binascii.unhexlify("5c00206c01014c"), ("127.0.0.1", 12345)
            )

            return await task

        coil = self.loop.run_until_complete(send_receive())

        self.transport.sendto.assert_called_with(
            binascii.unhexlify("c06b0604bc0400000011"), ("127.0.0.1", 10000)
        )

    def test_read_product_info(self):
        async def read_product_info():
            task = self.loop.create_task(self.nibegw.read_product_info())
            await asyncio.sleep(0)
            self.nibegw.datagram_received(
                binascii.unhexlify("5c00206d0d0124e346313235352d313220529f"),
                ("127.0.0.1", 12345),
            )

            return await task

        product = self.loop.run_until_complete(read_product_info())

        assert isinstance(product, ProductInfo)
        assert product.model == "F1255-12 R"
