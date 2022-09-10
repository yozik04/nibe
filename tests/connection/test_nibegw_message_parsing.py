import binascii
import unittest

from construct import ChecksumError, Int16sl, Int32ul

from nibe.connection.nibegw import ReadRequest, Response, WriteRequest


class MessageResponseParsingTestCase(unittest.TestCase):
    def test_parse_read_response(self):
        data = self._parse_hexlified_raw_message("5c00206a060cb901000000f8")

        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_READ_RESP")
        self.assertEqual(data.data.coil_address, 47372)
        self.assertEqual(data.data.value, b"\x01\x00\x00\x00")

    def test_parse_escaped_read_response(self):
        data = self._parse_hexlified_raw_message("5c00206a074f9c5c5c002c00b2")

        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_READ_RESP")
        self.assertEqual(data.data.coil_address, 40015)

        self.assertEqual(Int16sl.parse(data.data.value) / 10, 9.2)

    def test_parse_read_response_with_wrong_crc(self):
        self.assertRaises(
            ChecksumError, self._parse_hexlified_raw_message, "5c00206a060cb901000000f9"
        )

    def test_parse_multiple_read_request(self):
        data = self._parse_hexlified_raw_message(
            "5c00206850449c9600489c49014c9c21014d9cb4014e9c8d014f9c2401509c0d01619ce400fda700004ea80"
            + "a0080a80000ada90000afa9000004bc000067be0000a3b7fd0063bef6006d9cec006e9c0101eeac4600fb"
        )
        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_DATA_MSG")
        self.assertIsInstance(data.data, list)
        self.assertListEqual(
            data.data,
            [
                dict(coil_address=40004, value=b"\x96\x00"),
                dict(coil_address=40008, value=b"I\x01"),
                dict(coil_address=40012, value=b"!\x01"),
                dict(coil_address=40013, value=b"\xb4\x01"),
                dict(coil_address=40014, value=b"\x8d\x01"),
                dict(coil_address=40015, value=b"$\x01"),
                dict(coil_address=40016, value=b"\r\x01"),
                dict(coil_address=40033, value=b"\xe4\x00"),
                dict(coil_address=43005, value=b"\x00\x00"),
                dict(coil_address=43086, value=b"\n\x00"),
                dict(coil_address=43136, value=b"\x00\x00"),
                dict(coil_address=43437, value=b"\x00\x00"),
                dict(coil_address=43439, value=b"\x00\x00"),
                dict(coil_address=48132, value=b"\x00\x00"),
                dict(coil_address=48743, value=b"\x00\x00"),
                dict(coil_address=47011, value=b"\xfd\x00"),
                dict(coil_address=48739, value=b"\xf6\x00"),
                dict(coil_address=40045, value=b"\xec\x00"),
                dict(coil_address=40046, value=b"\x01\x01"),
                dict(coil_address=44270, value=b"F\x00"),
            ],
        )

    def test_parse_multiple_with_5c_checksum(self):
        data = self._parse_hexlified_raw_message(
            "5c00206850449c2d00489cf4014c9c56014d9cf8014e9cc4014f9c4b00509c2800619cef00fda700004ea80a0080a80000ada90000afa9000004bc000067be0000a3b7010063befd006d9cf8006e9cff00eeacc800c5"
        )
        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_DATA_MSG")
        self.assertIsInstance(data.data, list)

    def test_parse_multiple_escaped_value(self):
        data = self._parse_hexlified_raw_message(
            "5c00206851449c2c00489cf1014c9c59014d9cf8014e9cc4014f9c5c5c00509c2d00619cee00fda700004ea80a0080a80000ada90000afa9000004bc000067be0000a3b7010063befd006d9cf8006e9cff00eeacc80019"
        )
        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_DATA_MSG")
        self.assertIsInstance(data.data, list)

        self.assertEqual(b"\xc4\x01", data.data[4].value)
        self.assertEqual(40015, data.data[5].coil_address)
        self.assertEqual(b"\x5c\x00", data.data[5].value)
        self.assertEqual(40016, data.data[6].coil_address)

        self.assertEqual(44270, data.data[19].coil_address)
        self.assertEqual(b"\xc8\x00", data.data[19].value)

    def test_parse_multiple_heavily_escaped_value(self):
        data = self._parse_hexlified_raw_message(
            "5c0020685401a81f0100a86400fda7d003449c1e004f9ca000509c7800519c0301529c1b01879c14014e9cc601479c010115b9b0ff3ab94b00c9af0000489c0d014c9ce7004b9c0000ffff0000ffff00005c5c5c5c5c5c5c5c41"
        )
        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_DATA_MSG")
        self.assertIsInstance(data.data, list)

    def test_special_len(self):
        data = self._parse_hexlified_raw_message(
            "5c00206851449c2500489cfc004c9cf1004e9cc7014d9c0b024f9c2500509c3300519c0b01529c5c5c01569c3100c9af000001a80c01fda716fafaa9070098a91b1bffff0000a0a9ca02ffff00009ca99212ffff0000be"
        )
        self.assertEqual(data.address, "MODBUS40")
        self.assertEqual(data.cmd, "MODBUS_DATA_MSG")
        self.assertIsInstance(data.data, list)

    def test_succesfull_write_response(self):
        data = self._parse_hexlified_raw_message("5c00206c01014c")

        self.assertTrue(data.data.result)

    def test_failed_write_response(self):
        data = self._parse_hexlified_raw_message("5c00206c01004d")

        self.assertFalse(data.data.result)


    def test_parse_product_data(self):
        data = self._parse_hexlified_raw_message("5c00206d0b0124e346313135352d3136ec")
        self.assertEqual(data.data.unknown, b"\x01")
        self.assertEqual(data.data.product, "F1155-16")
        self.assertEqual(data.data.version, 9443)

    @staticmethod
    def _parse_hexlified_raw_message(txt_raw):
        raw = binascii.unhexlify(txt_raw)
        data = Response.parse(raw)
        value = data.fields.value
        return value


class MessageReadRequestParsingTestCase(unittest.TestCase):
    def test_parse_read_request(self):
        raw = ReadRequest.build(dict(fields=dict(value=dict(coil_address=12345))))

        self.assertEqual(binascii.hexlify(raw), b"c069023930a2")


class MessageWriteRequestParsingTestCase(unittest.TestCase):
    def test_parse_read_request(self):
        raw = WriteRequest.build(
            dict(
                fields=dict(value=dict(coil_address=12345, value=Int32ul.build(987654)))
            )
        )

        self.assertEqual(binascii.hexlify(raw), b"c06b06393006120f00bf")


if __name__ == "__main__":
    unittest.main()
