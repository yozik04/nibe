import asyncio
from dataclasses import fields

import pytest
from syrupy.extensions.image import SVGImageSnapshotExtension

from nibe.coil import CoilData
from nibe.coil_groups import HEATING_CURVE_COILGROUPS, HeatingCurveCoilGroup
from nibe.heating_curve import HeatingCurve, HeatingCurveCoilGroupData
from nibe.heatpump import HeatPump, Model


def _heatpump(model: Model) -> HeatPump:
    heatpump = HeatPump(model)
    asyncio.run(heatpump.initialize())
    return heatpump


@pytest.mark.parametrize(
    ("curve", "offset", "readings"),
    [
        # Read from the curve screen of an F1155, rounded to whole degrees.
        (10, 1, {20: 24, 15: 31, 10: 36, 5: 41, 0: 46, -5: 50, -10: 54, -15: 59}),
        (10, 0, {20: 21, 0: 44, -20: 61}),
        (5, 1, {20: 23, 0: 34, -20: 42}),
        (15, 1, {20: 25, 0: 58, -20: 65}),
    ],
)
def test_supply_matches_pump(curve, offset, readings):
    heating_curve = HeatingCurve(curve, offset, min_supply=20, max_supply=65)
    for outdoor, supply in readings.items():
        assert heating_curve.supply(outdoor) == pytest.approx(supply, abs=1.0)


def test_room_adjustment():
    heating_curve = HeatingCurve(
        10,
        1,
        min_supply=20,
        max_supply=65,
        use_room_sensor=True,
        room_factor=3,
        room_setpoint=20.5,
        room_temperature=20.7,
    )
    assert heating_curve.room_adjustment == pytest.approx(-0.6)
    assert heating_curve.supply(5) < heating_curve.supply(5, room_sensor=False)

    disabled = HeatingCurve(
        10,
        1,
        min_supply=20,
        max_supply=65,
        room_factor=3,
        room_setpoint=20.5,
        room_temperature=20.7,
    )
    assert disabled.room_adjustment == 0
    assert disabled.supply(5) == disabled.supply(5, room_sensor=False)


@pytest.mark.parametrize(
    ("model", "systems"),
    [
        (Model.F1155, ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]),
        (Model.S1155, ["s1", "s2", "s3"]),
    ],
)
def test_coil_groups_exist(model, systems):
    heatpump = _heatpump(model)
    groups = HEATING_CURVE_COILGROUPS[model.series]
    assert list(groups) == systems
    for group in groups.values():
        for field in fields(HeatingCurveCoilGroup):
            if field.name != "name":
                heatpump.get_coil_by_address(getattr(group, field.name))


def _data(**values) -> HeatingCurveCoilGroupData:
    heatpump = _heatpump(Model.F1155)
    group = HEATING_CURVE_COILGROUPS[Model.F1155.series]["s1"]
    return HeatingCurveCoilGroupData(
        **{
            name: CoilData(heatpump.get_coil_by_address(getattr(group, name)), value)
            for name, value in values.items()
        }
    )


SETTINGS = {"curve": 10, "offset": 1, "min_supply": 20.0, "max_supply": 65.0}
ROOM_SENSOR = {"room_factor": 3.0, "room_setpoint": 20.5, "room_temperature": 20.7}
READINGS = {
    "outdoor_temperature": 6.3,
    "calculated_supply": 38.1,
    "supply_temperature": 36.4,
    "return_temperature": 31.2,
}


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({**SETTINGS, "curve": 0}, id="own_curve"),
        pytest.param({"curve": 10, "max_supply": 65.0}, id="missing_min_supply"),
    ],
)
def test_data_without_curve(values):
    data = _data(**values)
    assert data.heating_curve() is None
    assert data.svg() is None


@pytest.mark.parametrize(
    ("use_room_sensor", "adjusted"),
    [("ON", True), ("OFF", False), (None, False)],
)
def test_data_room_sensor(use_room_sensor, adjusted):
    values = {**SETTINGS, **ROOM_SENSOR}
    if use_room_sensor is not None:
        values["use_room_sensor"] = use_room_sensor
    heating_curve = _data(**values).heating_curve()
    assert heating_curve is not None
    assert (heating_curve.room_adjustment != 0) is adjusted


@pytest.mark.parametrize(
    "values",
    [
        pytest.param(SETTINGS, id="curve_only"),
        pytest.param({**SETTINGS, **READINGS}, id="readings"),
        pytest.param(
            {**SETTINGS, **ROOM_SENSOR, **READINGS, "use_room_sensor": "ON"},
            id="room_sensor",
        ),
        pytest.param(
            {
                "curve": 15,
                "offset": 0,
                "min_supply": 20.0,
                "max_supply": 80.0,
                "outdoor_temperature": -45.0,
                "calculated_supply": 80.0,
            },
            id="clamped",
        ),
        pytest.param(
            {"curve": 10, "offset": -10, "min_supply": 5.0, "max_supply": 65.0},
            id="axis_from_zero",
        ),
        pytest.param(
            {**SETTINGS, "calculated_supply": 38.1, "supply_temperature": 36.4},
            id="no_outdoor",
        ),
    ],
)
def test_svg(values, snapshot):
    svg = _data(**values).svg()
    assert svg is not None
    assert svg.decode() == snapshot(extension_class=SVGImageSnapshotExtension)
