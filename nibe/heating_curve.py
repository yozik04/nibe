"""Heating curve model and SVG rendering for NIBE heat pumps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
from xml.etree import ElementTree as ET

from .coil import CoilData

ANCHOR_TEMPERATURE = 20.5
REFERENCE_SPAN = 40.0
CURVE_EXPONENT = 0.8

OUTDOOR_WARM = 30
OUTDOOR_COLD = -40

VALUES_USE_ROOM_SENSOR_ON = (1, "ON")


@dataclass(frozen=True)
class HeatingCurve:
    """Settings that define a preset heating curve (curve number 1-15)."""

    curve: float
    offset: float
    min_supply: float
    max_supply: float
    use_room_sensor: bool = False
    room_factor: float = 0.0
    room_setpoint: float | None = None
    room_temperature: float | None = None

    @property
    def room_adjustment(self) -> float:
        """Return how far the room sensor moves the curve's room temperature."""
        if (
            not self.use_room_sensor
            or self.room_setpoint is None
            or self.room_temperature is None
        ):
            return 0.0
        return self.room_factor * (self.room_setpoint - self.room_temperature)

    def supply(self, outdoor: float, *, room_sensor: bool = True) -> float:
        """Return the calculated supply temperature at an outdoor temperature.

        With room_sensor=False it is the curve the pump shows on its display.
        """
        room = ANCHOR_TEMPERATURE + self.offset
        if room_sensor:
            room += self.room_adjustment
        span = max(room - outdoor, 0.0) / REFERENCE_SPAN
        supply = room + self.curve / 10 * REFERENCE_SPAN * span**CURVE_EXPONENT
        return min(max(supply, self.min_supply), self.max_supply)


def _float(data: CoilData | None) -> float | None:
    if data is not None and isinstance(data.value, (int, float)):
        return float(data.value)
    return None


@dataclass(frozen=True)
class HeatingCurveCoilGroupData:
    """Coil data of a HeatingCurveCoilGroup, by the same field names."""

    curve: CoilData | None = None
    offset: CoilData | None = None
    min_supply: CoilData | None = None
    max_supply: CoilData | None = None
    use_room_sensor: CoilData | None = None
    room_setpoint: CoilData | None = None
    room_factor: CoilData | None = None
    room_temperature: CoilData | None = None
    calculated_supply: CoilData | None = None
    outdoor_temperature: CoilData | None = None
    supply_temperature: CoilData | None = None
    return_temperature: CoilData | None = None

    def heating_curve(self) -> HeatingCurve | None:
        """Return the heating curve, or None when it can't be modelled.

        Curve 0 is the user defined curve, which is not modelled.
        """
        curve = _float(self.curve)
        min_supply = _float(self.min_supply)
        max_supply = _float(self.max_supply)
        if not curve or min_supply is None or max_supply is None:
            return None
        return HeatingCurve(
            curve=curve,
            offset=_float(self.offset) or 0.0,
            min_supply=min_supply,
            max_supply=max_supply,
            use_room_sensor=self.use_room_sensor is not None
            and self.use_room_sensor.value in VALUES_USE_ROOM_SENSOR_ON,
            room_factor=_float(self.room_factor) or 0.0,
            room_setpoint=_float(self.room_setpoint),
            room_temperature=_float(self.room_temperature),
        )

    def svg(self) -> bytes | None:
        """Render the heating curve, or None when it can't be modelled."""
        if (curve := self.heating_curve()) is None:
            return None
        return heating_curve_svg(
            curve,
            outdoor=_float(self.outdoor_temperature),
            calculated_supply=_float(self.calculated_supply),
            actual_supply=_float(self.supply_temperature),
            return_temperature=_float(self.return_temperature),
        )


_WIDTH = 400
_HEIGHT = 280
_LEFT = 44
_RIGHT = 388
_TOP = 12
_BOTTOM = 248

_SVG_NAMESPACE = "http://www.w3.org/2000/svg"

# Paths from Material Design Icons (Apache-2.0), drawn on a 24x24 grid.
_ICON_SUPPLY = (
    "M7.95,3L6.53,5.19L7.95,7.4H7.94L5.95,10.5L4.22,9.6L5.64,7.39L4.22,5.19"
    "L6.22,2.09L7.95,3M13.95,2.89L12.53,5.1L13.95,7.3L13.94,7.31L11.95,10.4"
    "L10.22,9.5L11.64,7.3L10.22,5.1L12.22,2L13.95,2.89M20,2.89L18.56,5.1L20"
    ",7.3V7.31L18,10.4L16.25,9.5L17.67,7.3L16.25,5.1L18.25,2L20,2.89M2,22V1"
    "4A2,2 0 0,1 4,12H20A2,2 0 0,1 22,14V22H20V20H4V22H2M6,14A1,1 0 0,0 5,1"
    "5V17A1,1 0 0,0 6,18A1,1 0 0,0 7,17V15A1,1 0 0,0 6,14M10,14A1,1 0 0,0 9"
    ",15V17A1,1 0 0,0 10,18A1,1 0 0,0 11,17V15A1,1 0 0,0 10,14M14,14A1,1 0 "
    "0,0 13,15V17A1,1 0 0,0 14,18A1,1 0 0,0 15,17V15A1,1 0 0,0 14,14M18,14A"
    "1,1 0 0,0 17,15V17A1,1 0 0,0 18,18A1,1 0 0,0 19,17V15A1,1 0 0,0 18,14Z"
)
_ICON_OUTDOOR = (
    "M10 2L7.6 5.4C8.4 5.2 9.2 5 10 5S11.6 5.2 12.4 5.4L10 2M21 13.8V7C21 5"
    ".9 20.1 5 19 5S17 5.9 17 7V13.8C16.4 14.4 16 15.2 16 16C16 17.7 17.3 1"
    "9 19 19S22 17.7 22 16C22 15.1 21.6 14.3 21 13.8M20 8H18V7C18 6.4 18.4 "
    "6 19 6S20 6.4 20 7V8M5.5 6.7L1.3 7L3.1 10.8C3.2 10 3.5 9.2 3.9 8.5C4.4"
    " 7.8 4.9 7.2 5.5 6.7M10 7C7.2 7 5 9.2 5 12S7.2 17 10 17 15 14.8 15 12 "
    "12.8 7 10 7M10 15C8.3 15 7 13.7 7 12S8.3 9 10 9 13 10.3 13 12 11.7 15 "
    "10 15M3.2 13.2L1.4 17L5.5 17.4C5 16.9 4.4 16.2 4 15.5C3.5 14.8 3.3 14 "
    "3.2 13.2M7.6 18.6L10 22L12.4 18.6C11.6 18.8 10.8 19 10 19C9.1 19 8.3 1"
    "8.8 7.6 18.6Z"
)
_ICON_PUMP_CURVE = (
    "M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19"
    "V5C21 3.9 20.1 3 19 3M19 19H5V5H19V19M12 18C15.31 18 18 15.31 18 12S15"
    ".31 6 12 6 6 8.69 6 12 8.69 18 12 18M11.25 15.92C10.7 15.82 10.2 15.6 "
    "9.75 15.3L11.25 13.8V15.92M12.75 15.92V13.81L14.25 15.31C13.8 15.61 13"
    ".3 15.82 12.75 15.92M15.31 14.25L13.81 12.75H15.92C15.82 13.3 15.61 13"
    ".8 15.31 14.25M15.92 11.25H13.81L15.31 9.75C15.61 10.2 15.82 10.7 15.9"
    "2 11.25M12.75 8.08C13.3 8.18 13.8 8.4 14.25 8.7L12.75 10.2V8.08M12 11C"
    "12.55 11 13 11.45 13 12S12.55 13 12 13 11 12.55 11 12 11.45 11 12 11M1"
    "1.25 8.08V10.19L9.75 8.69C10.2 8.39 10.7 8.18 11.25 8.08M8.69 9.75L10."
    "19 11.25H8.08C8.18 10.7 8.39 10.2 8.69 9.75M10.19 12.75L8.69 14.25C8.3"
    "9 13.81 8.18 13.3 8.07 12.75H10.19Z"
)
_ICON_ROOM_SENSOR = (
    "M19 8C20.11 8 21 8.9 21 10V16.76C21.61 17.31 22 18.11 22 19C22 20.66 2"
    "0.66 22 19 22C17.34 22 16 20.66 16 19C16 18.11 16.39 17.31 17 16.76V10"
    "C17 8.9 17.9 8 19 8M19 9C18.45 9 18 9.45 18 10V11H20V10C20 9.45 19.55 "
    "9 19 9M12 5.69L7 10.19V18H14.1L14 19L14.1 20H5V12H2L12 3L16.4 6.96C15."
    "89 7.4 15.5 7.97 15.25 8.61L12 5.69Z"
)
_ICON_CURVE = (
    "M4 19V20H22V22H2V2H4V17C7 17 10 15 12.1 11.4C15.1 6.4 18.4 4 22 4V6C19"
    ".2 6 16.5 8.1 13.9 12.5C11.3 16.6 7.7 19 4 19Z"
)
_ICON_OFFSET = (
    "M3 7H6V4H8V7H11V9H8V12H6V9H3V7M13 15H21V17H13V15M16.04 3H18.35L7.96 21"
    "H5.65L16.04 3Z"
)
_ICON_SUPPLY_TEMPERATURE = (
    "M17.41 11.83L20.58 15L22 13.59L17.41 9L12.82 13.59L14.24 15L17.41 11.8"
    "3M10 13V5C10 3.34 8.66 2 7 2S4 3.34 4 5V13C1.79 14.66 1.34 17.79 3 20S"
    "7.79 22.66 10 21 12.66 16.21 11 14C10.72 13.62 10.38 13.28 10 13M7 4C7"
    ".55 4 8 4.45 8 5V8H6V5C6 4.45 6.45 4 7 4Z"
)
_ICON_RETURN_TEMPERATURE = (
    "M17.41 12.17L14.24 9L12.83 10.41L17.41 15L22 10.41L20.58 9M10 13V5C10 "
    "3.34 8.66 2 7 2S4 3.34 4 5V13C1.79 14.66 1.34 17.79 3 20S7.79 22.66 10"
    " 21 12.66 16.21 11 14C10.72 13.62 10.38 13.28 10 13M7 4C7.55 4 8 4.45 "
    "8 5V8H6V5C6 4.45 6.45 4 7 4Z"
)
_ICON_SIZE = 16
_MARKER_SIZE = 3


_STYLE = """
.axis{stroke:#8a8a8a;stroke-width:1}
.axis-break{fill:none;stroke:#8a8a8a;stroke-width:1}
.grid{stroke:#8a8a8a;stroke-opacity:.2;stroke-width:1}
.clamp{stroke:#8a8a8a;stroke-width:1;stroke-dasharray:2 3}
.guide{fill:none;stroke:#03a9f4;stroke-width:1;stroke-dasharray:4 3}
.curve{fill:none;stroke:#ff6f22;stroke-width:2;stroke-linejoin:round}
.effective{fill:none;stroke:#9c27b0;stroke-width:2;stroke-dasharray:6 4}
.point{fill:#03a9f4}
.supply{fill:#e53935}
.return{fill:#1e88e5}
.delta{stroke:#8a8a8a;stroke-opacity:.4;stroke-width:4;stroke-linecap:round}
.icon{fill:#8a8a8a}
.icon-curve{fill:#ff6f22}
.icon-effective{fill:#9c27b0}
.icon-supply{fill:#e53935}
.icon-return{fill:#1e88e5}
text{fill:#6f6f6f;font-family:Roboto,Noto,sans-serif;font-size:11px}
@media (prefers-color-scheme:dark){text{fill:#b0b0b0}}
"""


def _x(outdoor: float) -> float:
    return _LEFT + (OUTDOOR_WARM - outdoor) / (OUTDOOR_WARM - OUTDOOR_COLD) * (
        _RIGHT - _LEFT
    )


def _num(value: float) -> str:
    return f"{value:.1f}"


def _line(
    parent: ET.Element, css_class: str, x1: float, y1: float, x2: float, y2: float
) -> None:
    ET.SubElement(
        parent,
        "line",
        {
            "class": css_class,
            "x1": _num(x1),
            "y1": _num(y1),
            "x2": _num(x2),
            "y2": _num(y2),
        },
    )


def _text(
    parent: ET.Element, text: str, x: float, y: float, anchor: str = "start"
) -> None:
    ET.SubElement(
        parent, "text", {"x": _num(x), "y": _num(y), "text-anchor": anchor}
    ).text = text


def _icon(parent: ET.Element, path: str, x: float, y: float, css_class: str) -> None:
    ET.SubElement(
        parent,
        "path",
        {
            "class": css_class,
            "d": path,
            "transform": f"translate({_num(x)} {_num(y)}) scale({_ICON_SIZE / 24})",
        },
    )


def _polyline(
    parent: ET.Element, css_class: str, points: list[tuple[float, float]]
) -> None:
    ET.SubElement(
        parent,
        "polyline",
        {
            "class": css_class,
            "points": " ".join(f"{_num(x)},{_num(y)}" for x, y in points),
        },
    )


def _triangle(
    parent: ET.Element, css_class: str, x: float, y: float, *, up: bool
) -> None:
    tip = -_MARKER_SIZE if up else _MARKER_SIZE
    base = -tip * 0.8
    ET.SubElement(
        parent,
        "polygon",
        {
            "class": css_class,
            "points": " ".join(
                f"{_num(px)},{_num(py)}"
                for px, py in (
                    (x, y + tip),
                    (x + _MARKER_SIZE, y + base),
                    (x - _MARKER_SIZE, y + base),
                )
            ),
        },
    )


def heating_curve_svg(
    curve: HeatingCurve,
    *,
    outdoor: float | None = None,
    calculated_supply: float | None = None,
    actual_supply: float | None = None,
    return_temperature: float | None = None,
) -> bytes:
    """Render the heating curve as an SVG document.

    The x axis runs from warm on the left to cold on the right, as on the pump.
    The curve the pump shows is drawn solid, and the curve including the room
    sensor dashed, when the room sensor moves it. At the outdoor temperature,
    the actual supply and return temperatures are marked next to the
    calculated supply.
    The supply axis starts 10 degrees below the lowest point of the curves.
    """
    with_room_sensor = curve.room_adjustment != 0
    floor = min(
        curve.supply(OUTDOOR_WARM, room_sensor=False),
        curve.supply(OUTDOOR_WARM),
    )
    y_min = max(0, math.floor((floor - 10) / 10) * 10)
    y_max = max(70, math.ceil(curve.max_supply / 10) * 10)
    y_scale = (_BOTTOM - _TOP) / (y_max - y_min)

    def y(value: float) -> float:
        return _BOTTOM - (value - y_min) * y_scale

    def curve_points(room_sensor: bool) -> list[tuple[float, float]]:
        return [
            (_x(t), y(curve.supply(t, room_sensor=room_sensor)))
            for t in range(OUTDOOR_WARM, OUTDOOR_COLD - 1, -1)
        ]

    svg = ET.Element(
        "svg", {"xmlns": _SVG_NAMESPACE, "viewBox": f"0 0 {_WIDTH} {_HEIGHT}"}
    )
    ET.SubElement(svg, "style").text = _STYLE

    for tick in range(y_min + 10, y_max, 10):
        _line(svg, "grid", _LEFT, y(tick), _RIGHT, y(tick))
        _text(svg, str(tick), _LEFT - 6, y(tick) + 4, "end")
    _line(svg, "grid", _LEFT, _TOP, _RIGHT, _TOP)
    _icon(svg, _ICON_SUPPLY, _LEFT - _ICON_SIZE - 4, _TOP - _ICON_SIZE / 2, "icon")

    for tick in range(OUTDOOR_WARM, OUTDOOR_COLD, -10):
        _line(svg, "grid", _x(tick), _TOP, _x(tick), _BOTTOM)
        _text(svg, str(tick), _x(tick), _BOTTOM + 16, "middle")
    _line(svg, "grid", _RIGHT, _TOP, _RIGHT, _BOTTOM)
    _icon(svg, _ICON_OUTDOOR, _RIGHT - _ICON_SIZE / 2, _BOTTOM + 4, "icon")

    _line(svg, "axis", _LEFT, _BOTTOM, _RIGHT, _BOTTOM)
    if y_min:
        # Zigzag on the supply axis, marking that it does not start at zero.
        _line(svg, "axis", _LEFT, _TOP, _LEFT, _BOTTOM - 14)
        _polyline(
            svg,
            "axis-break",
            [
                (_LEFT, _BOTTOM - 14),
                (_LEFT - 4, _BOTTOM - 12),
                (_LEFT + 4, _BOTTOM - 8),
                (_LEFT - 4, _BOTTOM - 4),
                (_LEFT, _BOTTOM - 2),
                (_LEFT, _BOTTOM),
            ],
        )
    else:
        _line(svg, "axis", _LEFT, _TOP, _LEFT, _BOTTOM)

    settings_x, settings_y = _RIGHT - 92, _BOTTOM - 8
    _icon(svg, _ICON_CURVE, settings_x, settings_y - 13, "icon")
    _text(svg, f"{curve.curve:g}", settings_x + _ICON_SIZE + 4, settings_y)
    _icon(svg, _ICON_OFFSET, settings_x + 48, settings_y - 13, "icon")
    _text(svg, f"{curve.offset:+g}", settings_x + 48 + _ICON_SIZE + 4, settings_y)

    for clamp in (curve.min_supply, curve.max_supply):
        if y_min <= clamp <= y_max:
            _line(svg, "clamp", _LEFT, y(clamp), _RIGHT, y(clamp))

    legend_x, legend_y = _LEFT + 10, _TOP + 14

    def legend(
        draw_sample: Callable[[float, float], None], icon: str, icon_class: str
    ) -> None:
        nonlocal legend_y
        draw_sample(legend_x, legend_y)
        _icon(svg, icon, legend_x + 26, legend_y - _ICON_SIZE / 2, icon_class)
        legend_y += 20

    def clamped_y(value: float) -> float:
        return y(min(max(value, y_min), y_max))

    _polyline(svg, "curve", curve_points(room_sensor=False))
    if with_room_sensor:
        _polyline(svg, "effective", curve_points(room_sensor=True))
        legend(
            lambda lx, ly: _polyline(svg, "curve", [(lx, ly), (lx + 20, ly)]),
            _ICON_PUMP_CURVE,
            "icon-curve",
        )
        legend(
            lambda lx, ly: _polyline(svg, "effective", [(lx, ly), (lx + 20, ly)]),
            _ICON_ROOM_SENSOR,
            "icon-effective",
        )

    px = None if outdoor is None else _x(min(max(outdoor, OUTDOOR_COLD), OUTDOOR_WARM))
    py = None if calculated_supply is None else clamped_y(calculated_supply)
    if px is not None and py is not None:
        _polyline(svg, "guide", [(px, _BOTTOM), (px, py), (_LEFT, py)])
    elif px is not None:
        _line(svg, "guide", px, _TOP, px, _BOTTOM)
    elif py is not None:
        _line(svg, "guide", _LEFT, py, _RIGHT, py)

    supply_y = None
    return_y = None
    if px is not None:
        supply_y = None if actual_supply is None else clamped_y(actual_supply)
        return_y = None if return_temperature is None else clamped_y(return_temperature)
    if px is not None and supply_y is not None and return_y is not None:
        _line(svg, "delta", px, supply_y, px, return_y)
    if px is not None and py is not None:
        ET.SubElement(
            svg,
            "circle",
            {"class": "point", "cx": _num(px), "cy": _num(py), "r": "1.5"},
        )
    if px is not None and supply_y is not None:
        _triangle(svg, "supply", px, supply_y, up=True)
        legend(
            lambda lx, ly: _triangle(svg, "supply", lx + 10, ly, up=True),
            _ICON_SUPPLY_TEMPERATURE,
            "icon-supply",
        )
    if px is not None and return_y is not None:
        _triangle(svg, "return", px, return_y, up=False)
        legend(
            lambda lx, ly: _triangle(svg, "return", lx + 10, ly, up=False),
            _ICON_RETURN_TEMPERATURE,
            "icon-return",
        )

    return ET.tostring(svg, encoding="utf-8", xml_declaration=True)
