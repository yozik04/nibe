import unittest
from unittest.mock import Mock

from nibe.exceptions import CoilNotFoundException
from nibe.heatpump import HeatPump, Model


class HeatpumpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.heat_pump = HeatPump(Model.F1255)
        self.heat_pump.initialize()

        self.assertGreater(len(self.heat_pump._address_to_coil), 100)

    def test_get_coil_by_returns_same(self):
        coil_address = 40004

        a = self.heat_pump.get_coil_by_address(coil_address)
        b = self.heat_pump.get_coil_by_address(str(coil_address))

        self.assertEqual(coil_address, a.address)

        self.assertIs(a, b)

        c = self.heat_pump.get_coil_by_name("bt1-outdoor-temperature-40004")

        self.assertIs(a, c)

    def test_get_missing_coil_raises_exception(self):
        with self.assertRaises(CoilNotFoundException):
            self.heat_pump.get_coil_by_address(0xFFFF)

        with self.assertRaises(CoilNotFoundException):
            self.heat_pump.get_coil_by_name("no-beer-today")

    def test_listener(self):
        mock = Mock()
        coil = self.heat_pump.get_coil_by_address(40004)
        self.heat_pump.subscribe(self.heat_pump.COIL_UPDATE_EVENT, mock)

        mock.assert_not_called()

        self.heat_pump.notify_coil_update(coil)

        mock.assert_called_with(coil)

    def test_listener_with_exception(self):
        mock = Mock(side_effect=Exception("Test exception that needs to be logged"))
        coil = self.heat_pump.get_coil_by_address(40004)
        self.heat_pump.subscribe(self.heat_pump.COIL_UPDATE_EVENT, mock)

        self.heat_pump.notify_coil_update(
            coil
        )  # Error should be logged but not thrown out


if __name__ == "__main__":
    unittest.main()
