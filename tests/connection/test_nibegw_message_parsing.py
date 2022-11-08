import binascii
import unittest

from construct import ChecksumError, Container, Int16sl, Int32ul
import pytest

from nibe.connection.nibegw import Request, Response


class MessageResponseParsingTestCase(unittest.TestCase):
    def test_parse_read_response(self):
        data = self._parse_hexlified_raw_message("5c00206a060cb901000000f8")

        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_READ_RESP"
        assert data.data.coil_address == 47372
        assert data.data.value == b"\x01\x00\x00\x00"

    def test_parse_escaped_read_response(self):
        data = self._parse_hexlified_raw_message("5c00206a074f9c5c5c002c00b2")

        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_READ_RESP"
        assert data.data.coil_address == 40015

        assert Int16sl.parse(data.data.value) / 10 == 9.2

    def test_parse_read_response_with_wrong_crc(self):
        with pytest.raises(ChecksumError):
            self._parse_hexlified_raw_message("5c00206a060cb901000000f9")

    def test_parse_multiple_read_request(self):
        data = self._parse_hexlified_raw_message(
            "5c00206850449c9600489c49014c9c21014d9cb4014e9c8d014f9c2401509c0d01619ce400fda700004ea80"
            + "a0080a80000ada90000afa9000004bc000067be0000a3b7fd0063bef6006d9cec006e9c0101eeac4600fb"
        )
        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_DATA_MSG"
        assert isinstance(data.data, list)
        assert data.data == [
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
        ]

    def test_parse_multiple_with_5c_checksum(self):
        data = self._parse_hexlified_raw_message(
            "5c00206850449c2d00489cf4014c9c56014d9cf8014e9cc4014f9c4b00509c2800619cef00fda700004ea80a0080a80000ada90000afa9000004bc000067be0000a3b7010063befd006d9cf8006e9cff00eeacc800c5"
        )
        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_DATA_MSG"
        assert isinstance(data.data, list)

    def test_parse_multiple_escaped_value(self):
        data = self._parse_hexlified_raw_message(
            "5c00206851449c2c00489cf1014c9c59014d9cf8014e9cc4014f9c5c5c00509c2d00619cee00fda700004ea80a0080a80000ada90000afa9000004bc000067be0000a3b7010063befd006d9cf8006e9cff00eeacc80019"
        )
        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_DATA_MSG"
        assert isinstance(data.data, list)

        assert data.data[4].value == b"\xc4\x01"
        assert data.data[5].coil_address == 40015
        assert data.data[5].value == b"\x5c\x00"
        assert data.data[6].coil_address == 40016

        assert data.data[19].coil_address == 44270
        assert data.data[19].value == b"\xc8\x00"

    def test_parse_multiple_heavily_escaped_value(self):
        data = self._parse_hexlified_raw_message(
            "5c0020685401a81f0100a86400fda7d003449c1e004f9ca000509c7800519c0301529c1b01879c14014e9cc601479c010115b9b0ff3ab94b00c9af0000489c0d014c9ce7004b9c0000ffff0000ffff00005c5c5c5c5c5c5c5c41"
        )
        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_DATA_MSG"
        assert isinstance(data.data, list)

    def test_special_len(self):
        data = self._parse_hexlified_raw_message(
            "5c00206851449c2500489cfc004c9cf1004e9cc7014d9c0b024f9c2500509c3300519c0b01529c5c5c01569c3100c9af000001a80c01fda716fafaa9070098a91b1bffff0000a0a9ca02ffff00009ca99212ffff0000be"
        )
        assert data.address == "MODBUS40"
        assert data.cmd == "MODBUS_DATA_MSG"
        assert isinstance(data.data, list)

    def test_succesfull_write_response(self):
        data = self._parse_hexlified_raw_message("5c00206c01014c")

        assert data.data.result

    def test_failed_write_response(self):
        data = self._parse_hexlified_raw_message("5c00206c01004d")

        assert not data.data.result

    def test_parse_product_data(self):
        data = self._parse_hexlified_raw_message("5c00206d0b0124e346313135352d3136ec")
        assert data.data._unknown == b"\x01"
        assert data.data.model == "F1155-16"
        assert data.data.version == 9443

        data = self._parse_hexlified_raw_message(
            "5c00206d100724575465686f7761747469204169721a"
        )
        assert data.data._unknown == b"\x07"
        assert data.data.model == "Tehowatti Air"
        assert data.data.version == 9303

        data = self._parse_hexlified_raw_message(
            "5c00206d0d0124e346313235352d313220529f"
        )
        assert data.data._unknown == b"\x01"
        assert data.data.model == "F1255-12 R"
        assert data.data.version == 9443

    def test_parse_rmu_data(self):
        self.maxDiff = None

        data = self._parse_hexlified_raw_message(
            "5c001a62199b0029029ba00000e20000000000000239001f0003000001002e"
        )
        assert data.data == Container(
            alarm=0,
            bt1_outdoor_temperature=15.0,
            bt50_room_temp_sX=22.1,
            bt7_hw_top=54.8,
            clock_time_hour=0,
            clock_time_min=31,
            fan_mode=0,
            fan_time_hour=0,
            fan_time_min=0,
            flags=Container(
                unknown_8000=False,
                unknown_4000=False,
                unknown_2000=False,
                unknown_1000=False,
                unknown_0800=False,
                allow_cooling=False,
                allow_heating=True,
                allow_additive_heating=False,
                use_room_sensor_s4=False,
                use_room_sensor_s3=False,
                use_room_sensor_s2=True,
                use_room_sensor_s1=True,
                unknown_0008=True,
                unknown_0004=False,
                unknown_0002=False,
                hw_production=True,
            ),
            hw_time_hour=0,
            hw_time_min=0,
            operational_mode=0,
            setpoint_or_offset_s1=20.5,
            setpoint_or_offset_s2=21.0,
            setpoint_or_offset_s3=0.0,
            setpoint_or_offset_s4=0.0,
            temporary_lux=0,
            unknown4=b"\x03",
            unknown5=b"\x01\x00",
        )

        data = self._parse_hexlified_raw_message(
            "5c001962199b0028029ba00000e20000000000000239002100030000010012"
        )

        assert data.data == Container(
            alarm=0,
            bt1_outdoor_temperature=15.0,
            bt50_room_temp_sX=22.1,
            bt7_hw_top=54.7,
            clock_time_hour=0,
            clock_time_min=33,
            fan_mode=0,
            fan_time_hour=0,
            fan_time_min=0,
            flags=Container(
                unknown_8000=False,
                unknown_4000=False,
                unknown_2000=False,
                unknown_1000=False,
                unknown_0800=False,
                allow_cooling=False,
                allow_heating=True,
                allow_additive_heating=False,
                use_room_sensor_s4=False,
                use_room_sensor_s3=False,
                use_room_sensor_s2=True,
                use_room_sensor_s1=True,
                unknown_0008=True,
                unknown_0004=False,
                unknown_0002=False,
                hw_production=True,
            ),
            hw_time_hour=0,
            hw_time_min=0,
            operational_mode=0,
            setpoint_or_offset_s1=20.5,
            setpoint_or_offset_s2=21.0,
            setpoint_or_offset_s3=0.0,
            setpoint_or_offset_s4=0.0,
            temporary_lux=0,
            unknown4=b"\x03",
            unknown5=b"\x01\x00",
        )

    def test_parse_strings(self):
        data = self._parse_hexlified_raw_message("5c0019b10901382776e4726d650057")
        self.assertEqual(data.cmd, "STRING_MSG")
        self.assertEqual(data.data.unknown, 1)
        self.assertEqual(data.data.id, 10040)
        self.assertEqual(data.data.string, "värme")

    def test_parse_nibegw_ports(self):
        data = self._parse_hexlified_raw_message(
            "5c0020ff08" "20690f27" "206b1027" "ca"
        )
        assert data.address == "MODBUS40"
        assert data.cmd == "NIBEGW_PORTS"
        assert data.data == [
            dict(address=0x20, cmd=0x69, port=9999),
            dict(address=0x20, cmd=0x6B, port=10000),
        ]

    @staticmethod
    def _parse_hexlified_raw_message(txt_raw):
        raw = binascii.unhexlify(txt_raw)
        data = Response.parse(raw)
        value = data.fields.value
        return value


class MessageRequestParsingTestCase(unittest.TestCase):
    @staticmethod
    def _parse_hexlified_raw_message(txt_raw):
        raw = binascii.unhexlify(txt_raw)
        data = Request.parse(raw)
        value = data.fields.value
        return value

    def test_build_read_request(self):
        raw = Request.build(
            dict(
                fields=dict(
                    value=dict(
                        cmd="MODBUS_READ_REQ",
                        data=dict(coil_address=12345),
                    )
                )
            )
        )

        assert binascii.hexlify(raw) == b"c069023930a2"

    def test_build_write_request(self):
        raw = Request.build(
            dict(
                fields=dict(
                    value=dict(
                        cmd="MODBUS_WRITE_REQ",
                        data=dict(coil_address=12345, value=Int32ul.build(987654)),
                    )
                )
            )
        )

        assert binascii.hexlify(raw) == b"c06b06393006120f00bf"

    def test_parse_write_request(self):
        hex = bytes([192, 107, 6, 115, 176, 1, 0, 0, 0, 111]).hex()
        self._parse_hexlified_raw_message(hex)

    def test_parse_version_request(self):
        hex = bytes([192, 238, 3, 238, 3, 1, 193]).hex()
        data = self._parse_hexlified_raw_message(hex)
        assert data.cmd == "ACCESSORY_VERSION_REQ"
        assert data.data.modbus.version == 1006
        assert data.data.modbus.unknown == 1

        hex = bytes([192, 238, 3, 238, 3, 1, 193]).hex()
        data = self._parse_hexlified_raw_message(hex)
        assert data.cmd == "ACCESSORY_VERSION_REQ"
        assert data.data.rmu.version == 259
        assert data.data.rmu.unknown == 238

    def test_parse_rmu_write_request(self):
        hex = bytes([192, 96, 2, 99, 2, 195]).hex()
        data = self._parse_hexlified_raw_message(hex)
        assert data.cmd == "RMU_WRITE_REQ"
        assert data.data.index == 99
        assert data.data.value == 2

        hex = bytes([192, 96, 3, 6, 217, 0, 124]).hex()
        data = self._parse_hexlified_raw_message(hex)
        assert data.cmd == "RMU_WRITE_REQ"
        assert data.data.index == "TEMPERATURE"
        assert data.data.value == 21.0


if __name__ == "__main__":
    unittest.main()
