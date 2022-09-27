import unittest
from unittest.mock import Mock

import pytest

from nibe.exceptions import CoilNotFoundException, ModelIdentificationFailed
from nibe.heatpump import HeatPump, Model, ProductInfo


class HeatpumpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.heat_pump = HeatPump(Model.F1255)
        self.heat_pump.initialize()

        assert len(self.heat_pump._address_to_coil) > 100

    def test_get_coils(self):
        coils = self.heat_pump.get_coils()
        assert isinstance(coils, list)

    def test_get_coil_by_returns_same(self):
        coil_address = 40004

        a = self.heat_pump.get_coil_by_address(coil_address)
        b = self.heat_pump.get_coil_by_address(str(coil_address))

        assert coil_address == a.address

        assert a is b

        c = self.heat_pump.get_coil_by_name("bt1-outdoor-temperature-40004")

        assert a is c

    def test_get_missing_coil_raises_exception(self):
        with pytest.raises(CoilNotFoundException):
            self.heat_pump.get_coil_by_address(0xFFFF)

        with pytest.raises(CoilNotFoundException):
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
        assert coil.value == 1576


class HeatpumpWordSwapTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.heat_pump = HeatPump(Model.F1255)
        self.heat_pump.word_swap = False
        self.heat_pump.initialize()

    def test_word_swap_is_false(self):
        coil = self.heat_pump.get_coil_by_address(43420)
        coil.raw_value = b"\x00\x00(\x06"
        assert coil.value == 1576


class HeatpumpIntialization(unittest.TestCase):
    def setUp(self) -> None:
        self.heat_pump = HeatPump()

    def test_initalize_with_model(self):
        self.heat_pump.model = Model.F1255
        self.heat_pump.initialize()
        self.heat_pump.get_coil_by_address(43420)

    def test_initalize_with_product_info(self):
        self.heat_pump.product_info = ProductInfo("F1255-12 R", 0)
        self.heat_pump.initialize()
        self.heat_pump.get_coil_by_address(43420)

    def test_initalization_failed(self):
        with pytest.raises(AssertionError):
            self.heat_pump.initialize()


class ProductInfoTestCase(unittest.TestCase):
    def test_identify_model(self):
        product_info = ProductInfo("F1255-12 R", 0)

        assert product_info.identify_model() == Model.F1255

        product_info = ProductInfo("F1155-16", 0)

        assert product_info.identify_model() == Model.F1155

    def test_identify_model_error(self):
        product_info = ProductInfo("Tehowatti Air", 0)

        with pytest.raises(ModelIdentificationFailed):
            product_info.identify_model()


if __name__ == "__main__":
    unittest.main()
