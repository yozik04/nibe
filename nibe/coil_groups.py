from __future__ import annotations

from dataclasses import dataclass

from .heatpump import Series


@dataclass
class CoilGroup:
    name: str


@dataclass
class SystemCoilGroup(CoilGroup):
    prio: int
    cooling_with_room_sensor: int


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


UNIT_COIL_GROUPS_F = {
    "main": SystemCoilGroup(
        key="main", name="Main", prio=43086, cooling_with_room_sensor=47340
    ),
}

UNIT_COIL_GROUPS_S = {
    "main": SystemCoilGroup(
        key="main", name="Main", prio=31029, cooling_with_room_sensor=40171
    )
}

UNIT_COIL_GROUPS = {
    Series.F: UNIT_COIL_GROUPS_F,
    Series.S: UNIT_COIL_GROUPS_S,
}

CLIMATE_COIL_GROUPS_F = {
    "s1": ClimateCoilGroup(
        key="s1",
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

CLIMATE_COIL_GROUPS_S = {
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

CLIMATE_COIL_GROUPS = {
    Series.F: CLIMATE_COIL_GROUPS_F,
    Series.S: CLIMATE_COIL_GROUPS_S,
}
