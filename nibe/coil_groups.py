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


@dataclass
class HeatingCurveCoilGroup(CoilGroup):
    curve: int
    offset: int
    min_supply: int
    max_supply: int
    use_room_sensor: int
    room_setpoint: int
    room_factor: int
    room_temperature: int
    calculated_supply: int
    outdoor_temperature: int
    supply_temperature: int
    return_temperature: int


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

_HEATING_CURVE_COILGROUPS_F = {
    "s1": HeatingCurveCoilGroup(
        name="Heating Curve S1",
        curve=47007,
        offset=47011,
        min_supply=47015,
        max_supply=47019,
        use_room_sensor=47394,
        room_setpoint=47398,
        room_factor=47402,
        room_temperature=40195,
        calculated_supply=43009,
        outdoor_temperature=40067,
        supply_temperature=40008,
        return_temperature=40012,
    ),
    "s2": HeatingCurveCoilGroup(
        name="Heating Curve S2",
        curve=47006,
        offset=47010,
        min_supply=47014,
        max_supply=47018,
        use_room_sensor=47393,
        room_setpoint=47397,
        room_factor=47401,
        room_temperature=40194,
        calculated_supply=43008,
        outdoor_temperature=40067,
        supply_temperature=40007,
        return_temperature=40129,
    ),
    "s3": HeatingCurveCoilGroup(
        name="Heating Curve S3",
        curve=47005,
        offset=47009,
        min_supply=47013,
        max_supply=47017,
        use_room_sensor=47392,
        room_setpoint=47396,
        room_factor=47400,
        room_temperature=40193,
        calculated_supply=43007,
        outdoor_temperature=40067,
        supply_temperature=40006,
        return_temperature=40128,
    ),
    "s4": HeatingCurveCoilGroup(
        name="Heating Curve S4",
        curve=47004,
        offset=47008,
        min_supply=47012,
        max_supply=47016,
        use_room_sensor=47391,
        room_setpoint=47395,
        room_factor=47399,
        room_temperature=40192,
        calculated_supply=43006,
        outdoor_temperature=40067,
        supply_temperature=40005,
        return_temperature=40127,
    ),
    "s5": HeatingCurveCoilGroup(
        name="Heating Curve S5",
        curve=48489,
        offset=48494,
        min_supply=48498,
        max_supply=48502,
        use_room_sensor=48678,
        room_setpoint=48683,
        room_factor=48688,
        room_temperature=40191,
        calculated_supply=40220,
        outdoor_temperature=40067,
        supply_temperature=40162,
        return_temperature=40166,
    ),
    "s6": HeatingCurveCoilGroup(
        name="Heating Curve S6",
        curve=48488,
        offset=48493,
        min_supply=48497,
        max_supply=48501,
        use_room_sensor=48677,
        room_setpoint=48682,
        room_factor=48687,
        room_temperature=40190,
        calculated_supply=40219,
        outdoor_temperature=40067,
        supply_temperature=40161,
        return_temperature=40165,
    ),
    "s7": HeatingCurveCoilGroup(
        name="Heating Curve S7",
        curve=47567,
        offset=48492,
        min_supply=48496,
        max_supply=48500,
        use_room_sensor=48676,
        room_setpoint=48681,
        room_factor=48686,
        room_temperature=40189,
        calculated_supply=40218,
        outdoor_temperature=40067,
        supply_temperature=40160,
        return_temperature=40164,
    ),
    "s8": HeatingCurveCoilGroup(
        name="Heating Curve S8",
        curve=47525,
        offset=48491,
        min_supply=48495,
        max_supply=48499,
        use_room_sensor=48675,
        room_setpoint=48680,
        room_factor=48685,
        room_temperature=40188,
        calculated_supply=40217,
        outdoor_temperature=40067,
        supply_temperature=40159,
        return_temperature=40163,
    ),
}

_HEATING_CURVE_COILGROUPS_S = {
    "s1": HeatingCurveCoilGroup(
        name="Heating Curve S1",
        curve=40027,
        offset=40031,
        min_supply=40035,
        max_supply=40039,
        use_room_sensor=40203,
        room_setpoint=40207,
        room_factor=40211,
        room_temperature=30117,
        calculated_supply=31018,
        outdoor_temperature=30038,
        supply_temperature=30006,
        return_temperature=30008,
    ),
    "s2": HeatingCurveCoilGroup(
        name="Heating Curve S2",
        curve=40026,
        offset=40030,
        min_supply=40034,
        max_supply=40038,
        use_room_sensor=40202,
        room_setpoint=40206,
        room_factor=40210,
        room_temperature=30116,
        calculated_supply=31017,
        outdoor_temperature=30038,
        supply_temperature=30005,
        return_temperature=30078,
    ),
    "s3": HeatingCurveCoilGroup(
        name="Heating Curve S3",
        curve=40025,
        offset=40029,
        min_supply=40033,
        max_supply=40037,
        use_room_sensor=40201,
        room_setpoint=40205,
        room_factor=40209,
        room_temperature=30115,
        calculated_supply=31016,
        outdoor_temperature=30038,
        supply_temperature=30004,
        return_temperature=30077,
    ),
}

HEATING_CURVE_COILGROUPS = {
    Series.F: _HEATING_CURVE_COILGROUPS_F,
    Series.S: _HEATING_CURVE_COILGROUPS_S,
}
