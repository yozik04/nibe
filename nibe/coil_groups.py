from __future__ import annotations

from dataclasses import dataclass

from .heatpump import Series


@dataclass
class CoilGroup:
    name: str


@dataclass
class UnitCoilGroup(CoilGroup):
    prio: int
    cooling_with_room_sensor: int
    alarm: int
    alarm_reset: int


@dataclass
class CompressorCoilGroup(CoilGroup):
    pass


@dataclass
class ClimateCoilGroup(CoilGroup):
    active_accessory: int | None
    current: int
    setpoint_heat: int
    setpoint_cool: int
    mixing_valve_state: int
    use_room_sensor: int


@dataclass
class WaterHeaterCoilGroup(CoilGroup):
    hot_water_load: int
    hot_water_comfort_mode: int
    start_temperature: dict[str, int]
    stop_temperature: dict[str, int]
    active_accessory: int | None
    temporary_lux: int | None


@dataclass
class FanCoilGroup(CoilGroup):
    speed: int | None
    speeds: dict[str, int]


_UNIT_COILGROUPS_F = {
    "main": UnitCoilGroup(
        name="Main",
        prio=43086,
        cooling_with_room_sensor=47340,
        alarm=45001,
        alarm_reset=45171,
    ),
}

_UNIT_COILGROUPS_S = {
    "main": UnitCoilGroup(
        name="Main",
        prio=31029,
        cooling_with_room_sensor=40171,
        alarm=31976,
        alarm_reset=40023,
    ),
}

UNIT_COILGROUPS = {
    Series.F: _UNIT_COILGROUPS_F,
    Series.S: _UNIT_COILGROUPS_S,
}

_CLIMATE_COILGROUPS_F = {
    "s1": ClimateCoilGroup(
        name="Climate System S1",
        current=40033,
        setpoint_heat=47398,
        setpoint_cool=48785,
        mixing_valve_state=43096,
        active_accessory=None,
        use_room_sensor=47394,
    ),
    "s2": ClimateCoilGroup(
        name="Climate System S2",
        current=40032,
        setpoint_heat=47397,
        setpoint_cool=48784,
        mixing_valve_state=43095,
        active_accessory=47302,
        use_room_sensor=47393,
    ),
    "s3": ClimateCoilGroup(
        name="Climate System S3",
        current=40031,
        setpoint_heat=47396,
        setpoint_cool=48783,
        mixing_valve_state=43094,
        active_accessory=47303,
        use_room_sensor=47392,
    ),
    "s4": ClimateCoilGroup(
        name="Climate System S4",
        current=40030,
        setpoint_heat=47395,
        setpoint_cool=48782,
        mixing_valve_state=43093,
        active_accessory=47304,
        use_room_sensor=47391,
    ),
}

_CLIMATE_COILGROUPS_S = {
    "s1": ClimateCoilGroup(
        name="Climate System S1",
        current=30027,
        setpoint_heat=40207,
        setpoint_cool=40989,
        mixing_valve_state=31034,
        active_accessory=None,
        use_room_sensor=40203,
    ),
    "s2": ClimateCoilGroup(
        name="Climate System S2",
        current=30026,
        setpoint_heat=40206,
        setpoint_cool=40988,
        mixing_valve_state=31033,
        active_accessory=None,
        use_room_sensor=40202,
    ),
    "s3": ClimateCoilGroup(
        name="Climate System S3",
        current=30025,
        setpoint_heat=40205,
        setpoint_cool=40987,
        mixing_valve_state=31032,
        active_accessory=None,
        use_room_sensor=40201,
    ),
    "s4": ClimateCoilGroup(
        name="Climate System S4",
        current=30024,
        setpoint_heat=40204,
        setpoint_cool=40986,
        mixing_valve_state=31031,
        active_accessory=None,
        use_room_sensor=40200,
    ),
}

CLIMATE_COILGROUPS = {
    Series.F: _CLIMATE_COILGROUPS_F,
    Series.S: _CLIMATE_COILGROUPS_S,
}

_WATER_HEATER_COILGROUPS_F = {
    "hw1": WaterHeaterCoilGroup(
        name="Hot Water",
        hot_water_load=40014,
        hot_water_comfort_mode=47041,
        start_temperature={
            "ECONOMY": 47045,
            "NORMAL": 47044,
            "LUXURY": 47043,
        },
        stop_temperature={
            "ECONOMY": 47049,
            "NORMAL": 47048,
            "LUXURY": 47047,
        },
        active_accessory=None,
        temporary_lux=48132,
    ),
}

_WATER_HEATER_COILGROUPS_S = {
    "hw1": WaterHeaterCoilGroup(
        name="Hot Water",
        hot_water_load=30010,
        hot_water_comfort_mode=31039,
        start_temperature={
            "LOW": 40061,
            "NORMAL": 40060,
            "HIGH": 40059,
        },
        stop_temperature={
            "LOW": 40065,
            "NORMAL": 40064,
            "HIGH": 40063,
        },
        active_accessory=None,
        temporary_lux=None,
    ),
}

WATER_HEATER_COILGROUPS = {
    Series.F: _WATER_HEATER_COILGROUPS_F,
    Series.S: _WATER_HEATER_COILGROUPS_S,
}

_FAN_COILGROUPS_F = {
    "exhaust": FanCoilGroup(
        name="Exhaust",
        speed=47260,
        speeds={
            "0": 47265,
            "1": 47264,
            "2": 47263,
            "3": 47262,
            "4": 47261,
        },
    ),
    "supply": FanCoilGroup(
        name="Supply",
        speed=47260,
        speeds={
            "0": 47270,
            "1": 47269,
            "2": 47268,
            "3": 47267,
            "4": 47266,
        },
    ),
}

_FAN_COILGROUPS_S = {}

FAN_COILGROUPS = {
    Series.F: _FAN_COILGROUPS_F,
    Series.S: _FAN_COILGROUPS_S,
}
