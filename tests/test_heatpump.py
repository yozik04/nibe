import unittest
from unittest.mock import Mock

from nibe.exceptions import CoilNotFoundException, ModelIdentificationFailed
from nibe.heatpump import HeatPump, Model, ProductInfo


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

    def test_word_swap_is_true(self):
        coil = self.heat_pump.get_coil_by_address(43420)
        coil.raw_value = b"(\x06\x00\x00"
        self.assertEqual(1576, coil.value)


class HeatpumpWordSwapTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.heat_pump = HeatPump(Model.F1255)
        self.heat_pump.word_swap = False
        self.heat_pump.initialize()

    def test_word_swap_is_false(self):
        coil = self.heat_pump.get_coil_by_address(43420)
        coil.raw_value = b"\x00\x00(\x06"
        self.assertEqual(1576, coil.value)


class ProductInfoTestCase(unittest.TestCase):
    def test_infer_model(self):
        product_info = ProductInfo("F1255-12 R", 0)

        assert product_info.infer_model() == Model.F1255

        product_info = ProductInfo("F1155-16", 0)

        assert product_info.infer_model() == Model.F1155

    def test_infer_model_error(self):
        product_info = ProductInfo("Tehowatti Air", 0)

        with self.assertRaises(ModelIdentificationFailed):
            product_info.infer_model()


if __name__ == "__main__":
    unittest.main()
