"""Marcas de los ejes y textos del perfil de elevación.

Funciones puras (sin Qt), para probarlas solas. Formato español, el mismo que la sección
«Track» del inspector ('ui_helpers/inspector/formatting.py'): coma decimal, punto de
miles y «−» para los negativos.

Ejes (marcas «redondas»: múltiplos de 1, 2, 2,5 o 5 por una potencia de 10):
    nice_range(1295, 1774, 4)        -> (1200.0, 1800.0, 200.0)  rango ampliado y paso
    ticks(0, 18396, 2000)            -> [0, 2000, 4000... 18000]
    distance_tick_label(2500, 500)   -> '2,5 km'   (pasos de 500 m o más, en km)
    distance_tick_label(200, 100)    -> '200 m'    (pasos más cortos, en metros)
    altitude_tick_label(1700)        -> '1.700 m'

Textos:
    totals_text(totales)   'Distancia 18,4 km · ↑ 556 m · ↓ 566 m · Mín. 1.295 m · Máx. 1.774 m'
    range_text(tramo)      'Tramo 3,2 km · ↑ 210 m · ↓ 12 m · 1:05:20 · 2,9 km/h · Pendiente media +6,1 %'
    cursor_lines(perfil, i) ['1.639 m', '13,3 km', '+12 %', '14:23']  (la etiqueta del cursor;
                           lo que el punto no tenga, no sale; la hora, la local del equipo)

1.1.0 En los totales, la altitud mínima antes que la máxima (el autor, 15/11/2026).
1.0.0 Primera versión (15/11/2026; docs/MOD_TRACKS.md, paso 5.2).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.helpers.profile_format
"""

__version__ = "1.1.0"
__all__ = [
    "altitude_tick_label",
    "cursor_lines",
    "distance_tick_label",
    "nice_range",
    "nice_step",
    "range_text",
    "signed_percent",
    "ticks",
    "totals_text",
]

# Librerías estándar
import math

# Módulos del proyecto
from core.tracks.profile import ElevationProfileData, RangeStats
from ui_helpers.inspector.formatting import format_distance, format_duration, format_speed

# Separador de los datos de la línea de arriba
_SEPARATOR = "  ·  "

# Pasos «redondos» de los ejes, por cada potencia de 10
_NICE_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)

# A partir de este paso, el eje de distancias va en kilómetros
_KM_STEP_M = 500.0


def _number(value: float, decimals: int) -> str:
    """'1.774', '2,5', '−12' (punto de miles, coma decimal, «−» para los negativos)."""
    text = f"{abs(value):,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    negative = round(value, decimals) < 0
    return f"−{text}" if negative else text


def signed_percent(value: float, decimals: int = 0) -> str:
    """Una pendiente con su signo: '+12 %', '−8 %', '0 %', '+6,1 %'."""
    if round(value, decimals) == 0:
        return f"{_number(0, decimals)} %"
    return f"{'+' if value > 0 else '−'}{_number(abs(value), decimals)} %"


# -----------------------------------------------------------------------------
# Ejes
# -----------------------------------------------------------------------------


def nice_step(span: float, max_ticks: int) -> float:
    """El paso «redondo» más pequeño con el que 'span' cabe en 'max_ticks' marcas o menos."""
    if span <= 0:
        return 1.0
    raw = span / max(1, max_ticks)
    magnitude = 10 ** math.floor(math.log10(raw))
    for nice in _NICE_STEPS:
        if nice * magnitude >= raw * (1 - 1e-9):
            return nice * magnitude
    return 10 * magnitude  # no se llega: el último de la lista ya es 10


def nice_range(low: float, high: float, max_ticks: int) -> tuple[float, float, float]:
    """Rango del eje de altitudes: (desde, hasta, paso), ampliado a múltiplos del paso para
    que la curva no toque los bordes de cualquier manera. Si no hay desnivel (o casi), se
    abre 10 m arriba y abajo."""
    if high - low < 1:
        low, high = low - 10, high + 10
    step = nice_step(high - low, max_ticks)
    return math.floor(low / step) * step, math.ceil(high / step) * step, step


def ticks(low: float, high: float, step: float) -> list[float]:
    """Los múltiplos de 'step' entre 'low' y 'high' (los dos incluidos)."""
    if step <= 0 or high < low:
        return []
    first = math.ceil(low / step - 1e-9)
    last = math.floor(high / step + 1e-9)
    return [round(k * step, 6) for k in range(first, last + 1)]


def _decimals_for(value: float) -> int:
    """Decimales que hacen falta para escribir 'value' sin perder nada (hasta 3)."""
    for decimals in range(4):
        if abs(round(value, decimals) - value) < 1e-9:
            return decimals
    return 3


def distance_tick_label(meters: float, step: float) -> str:
    """Una marca del eje de distancias: en km si el paso es de 500 m o más ('2 km',
    '2,5 km'); si no, en metros ('200 m', '1.200 m')."""
    if step >= _KM_STEP_M:
        return f"{_number(meters / 1000, _decimals_for(step / 1000))} km"
    return f"{_number(meters, 0)} m"


def altitude_tick_label(meters: float) -> str:
    """Una marca del eje de altitudes: '1.700 m'."""
    return f"{_number(meters, 0)} m"


# -----------------------------------------------------------------------------
# Textos
# -----------------------------------------------------------------------------


def _elevation_parts(stats: RangeStats) -> list[str]:
    parts = []
    if stats.elevation_gain_m is not None and stats.elevation_loss_m is not None:
        parts.append(f"↑ {_number(stats.elevation_gain_m, 0)} m")
        parts.append(f"↓ {_number(stats.elevation_loss_m, 0)} m")
    return parts


def totals_text(stats: RangeStats) -> str:
    """La línea de arriba con los datos del track entero: distancia, subida, bajada y
    altitud mínima y máxima (en ese orden, decidido por el autor el 15/11/2026)."""
    parts = [f"Distancia {format_distance(stats.distance_m)}", *_elevation_parts(stats)]
    if stats.elevation_max_m is not None and stats.elevation_min_m is not None:
        parts.append(f"Mín. {_number(stats.elevation_min_m, 0)} m")
        parts.append(f"Máx. {_number(stats.elevation_max_m, 0)} m")
    return _SEPARATOR.join(parts)


def range_text(stats: RangeStats) -> str:
    """La línea de arriba con los datos del tramo elegido."""
    parts = [f"Tramo {format_distance(stats.distance_m)}", *_elevation_parts(stats)]
    if stats.duration_s:
        parts.append(format_duration(stats.duration_s))
    if stats.average_speed_kmh is not None:
        parts.append(format_speed(stats.average_speed_kmh))
    if stats.average_slope_pct is not None:
        parts.append(f"Pendiente media {signed_percent(stats.average_slope_pct, 1)}")
    return _SEPARATOR.join(parts)


def cursor_lines(data: ElevationProfileData, index: int) -> list[str]:
    """Las líneas de la etiqueta del cursor: altitud, distancia, pendiente y hora (lo que
    el punto no tenga, no sale). La hora es la local del equipo."""
    lines = []
    elevation = data.elevation(index)
    if elevation is not None:
        lines.append(f"{_number(elevation, 0)} m")
    lines.append(format_distance(data.distances[index]))
    slope = data.slopes[index]
    if not math.isnan(slope):
        lines.append(signed_percent(slope))
    moment = data.time(index)
    if moment is not None:
        lines.append(moment.astimezone().strftime("%H:%M"))
    return lines


if __name__ == "__main__":
    # Autoprueba (sin Qt). Ejecutar desde la raíz:  python -m ui_helpers.helpers.profile_format
    from array import array
    from datetime import UTC, datetime

    from core.tracks.gpx_document import PathSegment, TrackPath
    from core.tracks.profile import build_profile, range_stats

    # Números
    assert _number(1774.443, 0) == "1.774" and _number(2.5, 1) == "2,5"
    assert _number(-12.4, 0) == "−12" and _number(-0.2, 0) == "0"
    assert _number(1234567.891, 2) == "1.234.567,89"
    assert signed_percent(12.4) == "+12 %" and signed_percent(-7.6) == "−8 %"
    assert signed_percent(0.3) == "0 %" and signed_percent(6.14, 1) == "+6,1 %"

    # Pasos y rangos «redondos»
    assert nice_step(479, 4) == 200 and nice_step(100, 4) == 25 and nice_step(18396, 9) == 2500
    assert nice_step(10, 10) == 1 and nice_step(0.35, 4) == 0.1 and nice_step(0, 5) == 1
    assert nice_range(1295.4, 1774.4, 4) == (1200.0, 1800.0, 200.0)
    assert nice_range(1500, 1500, 4) == (1490.0, 1510.0, 5.0)  # sin desnivel: ±10 m
    low, high, step = nice_range(-12, 35, 5)
    assert low <= -12 and high >= 35 and step == 10
    assert ticks(0, 18396, 2000) == [k * 2000.0 for k in range(10)]
    assert ticks(1200, 1800, 200) == [1200.0, 1400.0, 1600.0, 1800.0]
    assert ticks(0.0, 0.7, 0.1) == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]  # sin errores de coma flotante
    assert ticks(5, 4, 1) == [] and ticks(0, 10, 0) == []

    # Marcas de los ejes
    assert distance_tick_label(0, 2000) == "0 km" and distance_tick_label(4000, 2000) == "4 km"
    assert distance_tick_label(2500, 2500) == "2,5 km" and distance_tick_label(500, 500) == "0,5 km"
    assert distance_tick_label(200, 100) == "200 m" and distance_tick_label(1200, 200) == "1.200 m"
    assert altitude_tick_label(1700) == "1.700 m" and altitude_tick_label(-50) == "−50 m"

    # Textos, con un perfil inventado: 21 puntos cada 11 m que suben 1,5 m, con hora. Sube
    # 30 m, pero el umbral de 8 m los cuenta de 9 en 9: 27 m (como el catálogo)
    lats = array("d", [42.6 + k * 0.0001 for k in range(21)])
    eles = array("d", [1000 + k * 1.5 for k in range(21)])
    times = array("d", [datetime(2024, 5, 1, 8, k, tzinfo=UTC).timestamp() for k in range(21)])
    data = build_profile(TrackPath((PathSegment(lats, array("d", [0.0] * 21), eles, times),)))
    totals = totals_text(data.totals)
    assert totals == "Distancia 222 m  ·  ↑ 27 m  ·  ↓ 0 m  ·  Mín. 1.000 m  ·  Máx. 1.030 m", totals
    section = range_text(range_stats(data, 0, 20))
    assert section.startswith("Tramo 222 m  ·  ↑ 27 m  ·  ↓ 0 m  ·  20:00  ·  0,7 km/h"), section
    # (13,5 % de pendiente real; la media usa la altitud suavizada de los extremos, donde
    # la mediana junta dos puntos: 28,5 m en 222 m)
    assert section.endswith("Pendiente media +12,8 %"), section
    lines = cursor_lines(data, 10)
    expected_hour = datetime(2024, 5, 1, 8, 10, tzinfo=UTC).astimezone().strftime("%H:%M")
    assert lines == ["1.015 m", "111 m", "+13 %", expected_hour], lines
    # Sin altitud ni hora: solo la distancia
    bare = build_profile(TrackPath((PathSegment(lats, array("d", [0.0] * 21),
                                                array("d", [math.nan] * 21), array("d", [math.nan] * 21)),)))  # fmt: skip
    assert cursor_lines(bare, 3) == ["33 m"]
    assert totals_text(bare.totals) == "Distancia 222 m"
    assert range_text(range_stats(bare, 0, 20)) == "Tramo 222 m"

    print("Autoprueba finalizada correctamente.")
