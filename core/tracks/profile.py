"""Perfil de elevación de un track: los números, sin dibujar nada.

Este módulo NO depende de Qt ni de la base de datos. Recibe el recorrido ya leído
('TrackPath', de 'core/tracks/gpx_document.read_gpx_path') y calcula lo que necesita el
widget del perfil (docs/MAPA.md, §4.2 y fase 5): la curva, la pendiente y las estadísticas
del track entero o de un tramo.

Qué calcula 'build_profile', punto a punto. Cada punto conserva su ÍNDICE en el recorrido
(todos los segmentos seguidos), el mismo que usan el mapa y la edición: así el cursor del
perfil y el punto ámbar del mapa hablan del mismo punto.
    - Distancia acumulada desde la salida ('core/tracks/geodesy.haversine_m', en 2D). Entre
      un segmento y el siguiente no se suma nada, como en el catálogo: el segundo empieza
      en la distancia donde acabó el primero.
    - Altitud, tal cual (NaN si el punto no la tiene).
    - Altitud SUAVIZADA, solo para dibujar: la mediana de los puntos del mismo segmento que
      quedan a menos de 'smoothing_m' / 2 por delante o por detrás. Quita los picos sueltos
      del GPS sin aplanar las cuestas. NaN donde falta la altitud.
    - Pendiente (%), para pintarla por colores: lo que sube (+) o baja (-) la altitud
      suavizada entre 'slope_window_m' / 2 por detrás y por delante del punto, dividido por
      la distancia entre esos dos sitios. En los extremos de un segmento la ventana se
      recorta; si queda menos de la mitad (segmentos muy cortos), NaN.
    - Hora (segundos desde 1970, UTC; NaN si no la tiene).

Y los totales ('ElevationProfileData.totals'), con LOS MISMOS NÚMEROS que el catálogo y
el inspector: distancia, desnivel de subida y de bajada, altitud mínima y máxima y
duración (idénticos a los del extractor; el catálogo los guarda redondeados a 0,1 m, y la
duración puede diferir en menos de un microsegundo porque aquí las horas son segundos con
decimales). El desnivel usa el método del umbral del extractor ('gpx_reader',
'ELEVATION_THRESHOLD_M' = 8 m) sobre la altitud SIN suavizar. El cálculo está repetido
aquí ('_climb') porque el del extractor va sumando mientras lee el archivo; si cambia uno,
hay que cambiar el otro. La autoprueba comprueba que dan exactamente lo mismo.

Otras funciones:
    range_stats(data, primero, último)   las estadísticas de un tramo (los dos puntos,
                                         incluidos): las mismas que los totales, más la
                                         velocidad media y la pendiente media. El desnivel
                                         de un tramo se calcula desde su primer punto: dos
                                         tramos seguidos pueden no sumar el del conjunto
                                         (el umbral empieza de cero en cada uno).
    index_at_distance(data, metros)      el punto más cercano a una distancia (el cursor).
    drawing_runs(data, ancho)            los puntos que hay que dibujar, en trozos
                                         continuos (sin saltos de segmento ni huecos sin
                                         altitud) y reducidos a la mínima y la máxima
                                         altitud de cada columna de píxeles: 50 000 puntos
                                         en 1 000 px se dibujan con unos 2 000.

Uso:
    from core.tracks.gpx_document import read_gpx_path
    from core.tracks.profile import build_profile, range_stats

    data = build_profile(read_gpx_path("ruta.gpx"))
    data.totals.distance_m, data.totals.elevation_gain_m
    data.distances[120], data.elevation(120), data.slopes[120]
    tramo = range_stats(data, 120, 800)
    tramo.duration_s, tramo.average_speed_kmh

1.0.0 Primera versión (15/11/2026; docs/MAPA.md, paso 5.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.tracks.profile
"""

__version__ = "1.0.0"
__all__ = [
    "SLOPE_WINDOW_M",
    "SMOOTHING_WINDOW_M",
    "ElevationProfileData",
    "RangeStats",
    "build_profile",
    "drawing_runs",
    "index_at_distance",
    "range_stats",
]

# Librerías estándar
import math
from array import array
from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass
from datetime import UTC, datetime

# Módulos del proyecto
from core.metadata.track.gpx_reader import ELEVATION_THRESHOLD_M
from core.tracks.geodesy import haversine_m
from core.tracks.gpx_document import TrackPath

# Ventana de la mediana que suaviza la altitud para dibujarla (metros). Con los relojes y
# móviles, que graban cada 1-10 m, abarca de 3 a 30 puntos: quita un pico suelto y no
# aplana una cuesta.
SMOOTHING_WINDOW_M = 30.0

# Ventana de la pendiente (metros): se mide lo que sube la altitud suavizada a lo largo de
# esta distancia. Más corta, la pendiente sigue mejor los repechos pero tiembla con el
# ruido del GPS (±5 m de altitud en 100 m ya son ±5 %); más larga, se ve más estable.
SLOPE_WINDOW_M = 100.0

_NAN = math.nan


@dataclass(frozen=True, slots=True)
class RangeStats:
    """Estadísticas de un tramo del perfil, o del track entero.

    Los valores que dependen de la altitud o de la hora son None si ningún punto del
    tramo la tiene.

    Attributes:
        first: Índice del primer punto del tramo.
        last: Índice del último punto (incluido).
        distance_m: Distancia recorrida, en metros (sin contar los saltos entre
            segmentos).
        elevation_gain_m: Desnivel acumulado de subida (método del umbral).
        elevation_loss_m: Desnivel acumulado de bajada (positivo).
        elevation_min_m: Altitud mínima.
        elevation_max_m: Altitud máxima.
        duration_s: Segundos entre la primera y la última hora del tramo.
        average_speed_kmh: Distancia entre duración, en km/h (None sin duración).
        average_slope_pct: Diferencia de altitud (suavizada) entre el principio y el
            final, entre la distancia, en %: positiva si el tramo sube en conjunto.
    """

    first: int
    last: int
    distance_m: float
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    elevation_min_m: float | None
    elevation_max_m: float | None
    duration_s: float | None
    average_speed_kmh: float | None
    average_slope_pct: float | None


@dataclass(frozen=True, slots=True)
class ElevationProfileData:
    """El perfil de un recorrido: arrays paralelos, uno por dato, con un valor por punto.

    Attributes:
        distances: Distancia acumulada desde la salida (m). Nunca baja.
        elevations: Altitud (m), tal cual; NaN si el punto no la tiene.
        smoothed: Altitud suavizada, solo para dibujar; NaN donde falta la altitud.
        slopes: Pendiente (%), positiva al subir; NaN si no se puede calcular.
        times: Hora (segundos desde 1970, UTC); NaN si el punto no la tiene.
        segment_starts: Índice del primer punto de cada segmento (el primero, 0).
        totals: Estadísticas del recorrido entero (las del catálogo).
        from_route: True si el recorrido es una ruta planificada (<rte>).
    """

    distances: array
    elevations: array
    smoothed: array
    slopes: array
    times: array
    segment_starts: tuple[int, ...]
    totals: RangeStats
    from_route: bool = False

    @property
    def point_count(self) -> int:
        """Puntos del perfil (los del recorrido)."""
        return len(self.distances)

    @property
    def has_elevation(self) -> bool:
        """True si algún punto tiene altitud."""
        return self.totals.elevation_min_m is not None

    @property
    def has_time(self) -> bool:
        """True si algún punto tiene hora."""
        return self.totals.duration_s is not None

    def segment_of(self, index: int) -> int:
        """Número del segmento al que pertenece el punto 'index'."""
        return bisect_right(self.segment_starts, index) - 1

    def elevation(self, index: int) -> float | None:
        """Altitud del punto 'index', o None si no la tiene."""
        value = self.elevations[index]
        return None if math.isnan(value) else value

    def time(self, index: int) -> datetime | None:
        """Hora (UTC) del punto 'index', o None si no la tiene."""
        value = self.times[index]
        return None if math.isnan(value) else datetime.fromtimestamp(value, UTC)


# -----------------------------------------------------------------------------
# Construcción del perfil
# -----------------------------------------------------------------------------


def build_profile(
    path: TrackPath,
    *,
    threshold_m: float = ELEVATION_THRESHOLD_M,
    smoothing_m: float = SMOOTHING_WINDOW_M,
    slope_window_m: float = SLOPE_WINDOW_M,
) -> ElevationProfileData:
    """Calcula el perfil de un recorrido (ver el docstring del archivo).

    Args:
        path: El recorrido, leído con 'read_gpx_path'.
        threshold_m: Umbral del desnivel acumulado (el del catálogo, salvo para probar).
        smoothing_m: Ventana de la mediana que suaviza la altitud para dibujar.
        slope_window_m: Ventana de la pendiente.

    Returns:
        El perfil. Un recorrido sin puntos da un perfil vacío (sin puntos ni totales).
    """
    distances = array("d")
    elevations = array("d")
    times = array("d")
    starts: list[int] = []
    total = 0.0
    for segment in path.segments:
        starts.append(len(distances))
        latitudes, longitudes = segment.latitudes, segment.longitudes
        for i in range(len(segment)):
            # Se suma en el mismo orden que el extractor: la distancia final es idéntica
            if i:
                total += haversine_m(
                    latitudes[i - 1], longitudes[i - 1], latitudes[i], longitudes[i]
                )
            distances.append(total)
        elevations.extend(segment.elevations)
        times.extend(segment.times)

    count = len(distances)
    smoothed = array("d", [_NAN]) * count
    slopes = array("d", [_NAN]) * count
    bounds = [*starts, count]
    for number in range(len(starts)):
        start, end = bounds[number], bounds[number + 1]
        _smooth_segment(distances, elevations, smoothed, start, end, smoothing_m / 2)
        _slope_segment(distances, smoothed, slopes, start, end, slope_window_m / 2)

    segment_starts = tuple(starts)
    if count:
        totals = _stats(
            distances, elevations, smoothed, times, segment_starts, 0, count - 1, threshold_m
        )
    else:
        totals = RangeStats(0, -1, 0.0, None, None, None, None, None, None, None)
    return ElevationProfileData(
        distances, elevations, smoothed, slopes, times, segment_starts, totals, path.from_route
    )


def _smooth_segment(
    distances: array, elevations: array, out: array, start: int, end: int, half: float
) -> None:
    """Mediana móvil de la altitud de un segmento (puntos 'start' a 'end' - 1), por
    distancia: la ventana de cada punto va de 'half' metros por detrás a 'half' por delante.

    La ventana se mantiene ORDENADA al avanzar (entra un valor por delante, sale otro por
    detrás): así, aunque un track parado mucho rato junte miles de puntos en el mismo
    sitio, no hay que ordenar cada ventana desde cero.
    """
    window: list[float] = []
    lo = hi = start
    for i in range(start, end):
        here = distances[i]
        while hi < end and distances[hi] <= here + half:
            value = elevations[hi]
            if not math.isnan(value):
                insort(window, value)
            hi += 1
        while distances[lo] < here - half:
            value = elevations[lo]
            if not math.isnan(value):
                del window[bisect_left(window, value)]
            lo += 1
        if math.isnan(elevations[i]) or not window:
            continue  # sin altitud: sin curva (se queda NaN)
        middle = len(window) // 2
        out[i] = window[middle] if len(window) % 2 else (window[middle - 1] + window[middle]) / 2


def _slope_segment(
    distances: array, smoothed: array, out: array, start: int, end: int, half: float
) -> None:
    """Pendiente (%) de cada punto de un segmento con altitud: la de la altitud suavizada
    entre 'half' metros por detrás y 'half' por delante (interpolando entre puntos)."""
    marks = [i for i in range(start, end) if not math.isnan(smoothed[i])]
    if len(marks) < 2:
        return
    ds = [distances[i] for i in marks]
    zs = [smoothed[i] for i in marks]
    last = len(marks) - 1
    minimum_span = half  # la mitad de la ventana: menos, y la pendiente sería poco fiable
    left = right = 0
    for k, i in enumerate(marks):
        low_target, high_target = ds[k] - half, ds[k] + half
        # Por detrás: el primer punto a 'half' metros o más cerca
        while ds[left] < low_target:
            left += 1
        if left == 0:
            low_d, low_z = ds[0], zs[0]  # la ventana se recorta al principio del segmento
        else:
            low_d, low_z = low_target, _interpolate(ds, zs, left - 1, left, low_target)
        # Por delante: el primer punto más allá de 'half' metros
        while right <= last and ds[right] <= high_target:
            right += 1
        if right > last:
            high_d, high_z = ds[last], zs[last]  # recortada al final del segmento
        else:
            high_d, high_z = high_target, _interpolate(ds, zs, right - 1, right, high_target)
        span = high_d - low_d
        if span >= minimum_span:
            out[i] = (high_z - low_z) / span * 100.0


def _interpolate(ds: list[float], zs: list[float], a: int, b: int, target: float) -> float:
    """Altitud en la distancia 'target', entre los puntos 'a' y 'b' (ds[a] < target <= ds[b])."""
    return zs[a] + (zs[b] - zs[a]) * (target - ds[a]) / (ds[b] - ds[a])


# -----------------------------------------------------------------------------
# Estadísticas
# -----------------------------------------------------------------------------


def range_stats(data: ElevationProfileData, first: int, last: int) -> RangeStats:
    """Estadísticas del tramo entre los puntos 'first' y 'last' (los dos incluidos; da
    igual el orden).

    Raises:
        IndexError: Si alguno de los dos puntos no existe.
    """
    if first > last:
        first, last = last, first
    if first < 0 or last >= data.point_count:
        raise IndexError(f"El perfil no tiene el tramo {first}-{last}.")
    return _stats(
        data.distances, data.elevations, data.smoothed, data.times, data.segment_starts,
        first, last, ELEVATION_THRESHOLD_M,
    )  # fmt: skip


def _stats(
    distances: array,
    elevations: array,
    smoothed: array,
    times: array,
    segment_starts: tuple[int, ...],
    first: int,
    last: int,
    threshold_m: float,
) -> RangeStats:
    """Estadísticas de los puntos 'first' a 'last' (incluidos; first <= last)."""
    distance = distances[last] - distances[first]
    gain, loss, lowest, highest = _climb(elevations, segment_starts, first, last, threshold_m)

    # Duración: de la primera a la última hora (mínima y máxima, como el extractor)
    finite_times = [t for t in times[first : last + 1] if not math.isnan(t)]
    duration = max(finite_times) - min(finite_times) if finite_times else None
    speed = distance / duration * 3.6 if duration else None

    # Pendiente media: con la altitud suavizada del primer y el último punto que la tienen
    # (la de un solo punto del GPS puede estar unos metros desviada)
    slope = None
    marks = [i for i in range(first, last + 1) if not math.isnan(smoothed[i])]
    if len(marks) >= 2:
        span = distances[marks[-1]] - distances[marks[0]]
        if span > 0:
            slope = (smoothed[marks[-1]] - smoothed[marks[0]]) / span * 100.0

    return RangeStats(first, last, distance, gain, loss, lowest, highest, duration, speed, slope)


def _climb(
    elevations: array, segment_starts: tuple[int, ...], first: int, last: int, threshold_m: float
) -> tuple[float | None, float | None, float | None, float | None]:
    """Desnivel de subida y de bajada, altitud mínima y máxima de los puntos 'first' a
    'last': (None, None, None, None) si ninguno tiene altitud.

    El MISMO método que 'gpx_reader._Accumulator.add_point' (ver la cabecera): una subida
    o una bajada solo cuenta cuando la altitud se separa al menos el umbral del último
    punto de referencia; la referencia empieza de cero en cada segmento.
    """
    gain = loss = 0.0
    lowest = highest = None
    reference: float | None = None
    next_start_at = bisect_right(segment_starts, first)
    next_start = segment_starts[next_start_at] if next_start_at < len(segment_starts) else -1
    for i in range(first, last + 1):
        if i == next_start:  # empieza otro segmento: no se une al anterior
            reference = None
            next_start_at += 1
            next_start = segment_starts[next_start_at] if next_start_at < len(segment_starts) else -1
        value = elevations[i]
        if math.isnan(value):
            continue
        lowest = value if lowest is None else min(lowest, value)
        highest = value if highest is None else max(highest, value)
        if reference is None:
            reference = value
        elif value - reference >= threshold_m:
            gain += value - reference
            reference = value
        elif reference - value >= threshold_m:
            loss += reference - value
            reference = value
    if lowest is None:
        return None, None, None, None
    return gain, loss, lowest, highest


# -----------------------------------------------------------------------------
# Para el widget: el cursor y el dibujo
# -----------------------------------------------------------------------------


def index_at_distance(data: ElevationProfileData, distance_m: float) -> int:
    """El punto más cercano a una distancia desde la salida (fuera del recorrido, el
    primero o el último). Si varios están a la misma distancia (una parada, un salto de
    segmento), el primero de ellos.

    Raises:
        IndexError: Si el perfil no tiene puntos.
    """
    distances = data.distances
    if not distances:
        raise IndexError("El perfil no tiene puntos.")
    after = bisect_left(distances, distance_m)
    if after == 0:
        return 0
    if after == len(distances):
        return len(distances) - 1
    before = bisect_left(distances, distances[after - 1])  # el primero a esa distancia
    if distance_m - distances[after - 1] <= distances[after] - distance_m:
        return before
    return after


def drawing_runs(
    data: ElevationProfileData, width_px: int, first: int = 0, last: int | None = None
) -> list[list[int]]:
    """Los puntos que hay que dibujar entre 'first' y 'last' (por defecto, todos) para un
    perfil de 'width_px' píxeles de ancho.

    Returns:
        Trozos CONTINUOS de índices: un trozo se corta en cada salto de segmento y en cada
        punto sin altitud. Dentro de un trozo, de cada columna de píxeles solo quedan el
        punto más bajo y el más alto (en su orden), y siempre el primero y el último del
        trozo: el dibujo es el mismo con muchos menos puntos.
    """
    if last is None:
        last = data.point_count - 1
    if first > last or width_px <= 0:
        return []
    distances, smoothed = data.distances, data.smoothed
    span = distances[last] - distances[first]
    scale = width_px / span if span > 0 else 0.0
    origin = distances[first]

    runs: list[list[int]] = []
    for start, end in _continuous_pieces(data, first, last):
        run = [start]  # el primero del trozo, siempre
        column = -1
        low = high = start  # el punto más bajo y el más alto de la columna en curso
        for i in range(start, end + 1):
            here = min(int((distances[i] - origin) * scale), width_px - 1)
            if here != column:
                if column >= 0:
                    _add_in_order(run, low, high)
                column, low, high = here, i, i
                continue
            if smoothed[i] < smoothed[low]:
                low = i
            if smoothed[i] > smoothed[high]:
                high = i
        _add_in_order(run, low, high)
        if run[-1] != end:
            run.append(end)  # y el último
        runs.append(run)
    return runs


def _continuous_pieces(data: ElevationProfileData, first: int, last: int) -> list[tuple[int, int]]:
    """Los trozos (primero, último) de 'first' a 'last' que se dibujan con una sola línea:
    puntos seguidos con altitud y del mismo segmento."""
    pieces: list[tuple[int, int]] = []
    starts = set(data.segment_starts)
    piece_start: int | None = None
    for i in range(first, last + 1):
        has_value = not math.isnan(data.smoothed[i])
        if piece_start is not None and (not has_value or i in starts):
            pieces.append((piece_start, i - 1))
            piece_start = None
        if has_value and piece_start is None:
            piece_start = i
    if piece_start is not None:
        pieces.append((piece_start, last))
    return pieces


def _add_in_order(run: list[int], low: int, high: int) -> None:
    """Añade a un trozo el punto más bajo y el más alto de una columna, en su orden y sin
    repetir el último añadido."""
    for index in sorted({low, high}):
        if run[-1] != index:
            run.append(index)


if __name__ == "__main__":
    # Autoprueba con archivos GPX inventados en una carpeta temporal (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m core.tracks.profile
    import tempfile
    import time
    from pathlib import Path

    from core.metadata.track.gpx_reader import read_gpx
    from core.tracks.gpx_document import PathSegment, read_gpx_path

    def gpx_file(folder: Path, name: str, body: str) -> Path:
        file = folder / name
        file.write_text(
            f'<?xml version="1.0"?><gpx version="1.1" creator="prueba" '
            f'xmlns="http://www.topografix.com/GPX/1/1">{body}</gpx>',
            encoding="utf-8",
        )
        return file

    def points(rows: list[tuple[float, float, float | None, str | None]]) -> str:
        text = []
        for lat, lon, ele, hour in rows:
            inner = (f"<ele>{ele}</ele>" if ele is not None else "") + (
                f"<time>2024-05-01T{hour}Z</time>" if hour else ""
            )
            text.append(f'<trkpt lat="{lat}" lon="{lon}">{inner}</trkpt>')
        return "".join(text)

    def same_as_catalog(file: Path) -> ElevationProfileData:
        """Los totales del perfil son, EXACTAMENTE, los del extractor."""
        summary = read_gpx(file)
        data = build_profile(read_gpx_path(file))
        totals = data.totals
        assert data.point_count == summary.point_count, file.name
        assert len(data.segment_starts) == summary.segment_count, file.name
        # (sin puntos, el extractor no da distancia; el perfil, 0)
        assert totals.distance_m == (summary.distance_m or 0.0), (file.name, totals.distance_m)
        assert totals.elevation_gain_m == summary.elevation_gain_m, file.name
        assert totals.elevation_loss_m == summary.elevation_loss_m, file.name
        assert totals.elevation_min_m == summary.elevation_min_m, file.name
        assert totals.elevation_max_m == summary.elevation_max_m, file.name
        # La duración, al microsegundo: el lector completo guarda las horas como segundos
        # con decimales y, con milisegundos en el GPX, la resta difiere en la 8.ª cifra
        if summary.duration_s is None:
            assert totals.duration_s is None, file.name
        else:
            assert totals.duration_s is not None, file.name
            assert abs(totals.duration_s - summary.duration_s) < 1e-3, file.name
        return data

    with tempfile.TemporaryDirectory() as folder_name:
        folder = Path(folder_name)

        # --- Un track con tres segmentos, ruido, puntos sin altitud ni hora y uno no válido
        # Cada 0,0001° de latitud son unos 11 m. Primer segmento: sube 1,5 m por punto, con
        # un saliente de 5 m cada tres puntos (por debajo del umbral) y un pico suelto de
        # 40 m; el suavizado debe quitar los dos.
        first_rows = []
        for k in range(60):
            ele = 1000 + k * 1.5 + (5 if k % 3 == 0 else 0)
            if k == 30:
                ele += 40  # pico suelto del GPS
            hour = f"08:{k // 6:02d}:{(k % 6) * 10:02d}"
            first_rows.append((42.6 + k * 0.0001, 0.0, ele, hour))
        first_rows[10] = (first_rows[10][0], 0.0, None, first_rows[10][3])  # sin altitud
        first_rows[11] = (first_rows[11][0], 0.0, first_rows[11][2], None)  # sin hora
        second_rows = [(42.62 + k * 0.0001, 0.0, 1200 - k * 3, f"09:{k:02d}:00") for k in range(20)]
        second_rows[-1] = (*second_rows[-1][:3], "09:19:00.517")  # con milisegundos
        third_rows = [(42.63, 0.0, None, None), (42.6301, 0.0, None, None)]  # sin altitud
        body = (
            "<trk><trkseg>" + points(first_rows) + "</trkseg>"
            '<trkseg><trkpt lat="abc" lon="0"/></trkseg>'  # segmento sin puntos válidos
            "<trkseg>" + points(second_rows) + '<trkpt lat="999" lon="0"/></trkseg></trk>'
            "<trk><trkseg>" + points(third_rows) + "</trkseg></trk>"
        )
        data = same_as_catalog(gpx_file(folder, "tres.gpx", body))
        assert data.segment_starts == (0, 60, 80) and data.point_count == 82
        assert data.has_elevation and data.has_time
        # Entre segmentos no se suma: el segundo empieza donde acabó el primero
        assert data.distances[60] == data.distances[59] and data.distances[0] == 0
        assert all(data.distances[i] <= data.distances[i + 1] for i in range(81))
        assert data.segment_of(0) == 0 and data.segment_of(59) == 0 and data.segment_of(60) == 1
        assert data.segment_of(81) == 2
        # Lo que no tiene altitud se queda sin curva y sin pendiente; la hora, igual
        assert data.elevation(10) is None and math.isnan(data.smoothed[10])
        assert math.isnan(data.slopes[10]) and data.time(11) is None
        assert data.time(0) == datetime(2024, 5, 1, 8, 0, tzinfo=UTC)
        assert all(math.isnan(data.smoothed[i]) for i in (80, 81))
        # El suavizado quita el pico de 40 m (la mediana se queda con los vecinos)...
        assert data.elevations[30] - data.smoothed[30] > 30
        # ...pero los números salen de la altitud sin suavizar
        assert data.totals.elevation_max_m == max(r[2] for r in first_rows + second_rows if r[2])
        # La pendiente: el primer segmento sube unos 1,5 m cada 11 m (≈ 13,5 %), el segundo
        # baja 3 m cada 11 m (≈ -27 %)
        assert 10 < data.slopes[45] < 17, data.slopes[45]
        assert -30 < data.slopes[70] < -24, data.slopes[70]

        # --- Estadísticas de un tramo
        whole = range_stats(data, 81, 0)  # da igual el orden
        assert whole == data.totals
        climb = range_stats(data, 0, 59)
        assert climb.distance_m == data.distances[59]
        assert climb.elevation_gain_m and climb.elevation_gain_m > 50 and climb.elevation_loss_m is not None
        assert climb.duration_s == 9 * 60 + 50 and climb.average_speed_kmh
        assert abs(climb.average_speed_kmh - climb.distance_m / climb.duration_s * 3.6) < 1e-9
        assert climb.average_slope_pct and 10 < climb.average_slope_pct < 17
        # Baja 57 m de 3 en 3: el umbral cuenta 6 bajadas de 9 m; los 3 m del final, no
        down = range_stats(data, 60, 79)
        assert down.elevation_gain_m == 0 and down.elevation_loss_m == 54
        assert down.average_slope_pct and down.average_slope_pct < -20
        # Un tramo que cruza el salto de segmento no suma la distancia del salto (1,5 km)
        across = range_stats(data, 50, 65)
        expected = (data.distances[59] - data.distances[50]) + (data.distances[65] - data.distances[60])
        assert abs(across.distance_m - expected) < 1e-6 and across.distance_m < 200
        # Un solo punto: distancia 0, sin velocidad ni pendiente
        single = range_stats(data, 5, 5)
        assert single.distance_m == 0 and single.duration_s == 0 and single.average_speed_kmh is None
        assert single.average_slope_pct is None
        # Sin altitud ni hora (el tercer segmento)
        empty = range_stats(data, 80, 81)
        assert empty.elevation_gain_m is None and empty.elevation_min_m is None
        assert empty.duration_s is None and empty.average_slope_pct is None
        for wrong in ((-1, 3), (0, 82)):
            try:
                range_stats(data, *wrong)
            except IndexError:
                pass
            else:
                raise AssertionError(wrong)

        # --- El cursor: el punto más cercano a una distancia
        assert index_at_distance(data, -50) == 0
        assert index_at_distance(data, 1e9) == 81
        assert index_at_distance(data, data.distances[20]) == 20
        middle = (data.distances[20] + data.distances[21]) / 2
        assert index_at_distance(data, middle - 0.1) == 20
        assert index_at_distance(data, middle + 0.1) == 21
        # En el salto de segmento hay dos puntos a la misma distancia: el primero
        assert index_at_distance(data, data.distances[60]) == 59

        # --- Lo que se dibuja: trozos continuos
        runs = drawing_runs(data, 2000)  # sobra ancho: no se quita ningún punto
        assert [run[0] for run in runs] == [0, 11, 60], runs
        assert runs[0] == list(range(10)) and runs[1] == list(range(11, 60))
        assert runs[2] == list(range(60, 80))
        assert drawing_runs(data, 0) == [] and drawing_runs(data, 100, 50, 40) == []
        assert drawing_runs(data, 100, 80, 81) == []  # sin altitud, nada que dibujar

        # --- Otros casos que también deben coincidir con el catálogo
        same_as_catalog(gpx_file(folder, "vacio.gpx", "<trk><trkseg/></trk>"))
        flat = same_as_catalog(gpx_file(folder, "sin_altitud.gpx",
            "<trk><trkseg>" + points([(40.0, -3.0, None, None), (40.001, -3.0, None, None)])
            + "</trkseg></trk>"))  # fmt: skip
        assert not flat.has_elevation and not flat.has_time and flat.totals.elevation_gain_m is None
        assert drawing_runs(flat, 100) == []
        route = same_as_catalog(gpx_file(folder, "ruta.gpx",
            '<rte><rtept lat="40.0" lon="-3.0"><ele>600</ele></rtept>'
            '<rtept lat="40.0" lon="-2.99"><ele>650</ele></rtept></rte>'))  # fmt: skip
        assert route.from_route and route.totals.elevation_gain_m == 50

    # --- Un perfil vacío
    nothing = build_profile(TrackPath())
    assert nothing.point_count == 0 and nothing.totals.distance_m == 0 and not nothing.has_elevation
    assert drawing_runs(nothing, 100) == []
    try:
        index_at_distance(nothing, 0)
    except IndexError:
        pass
    else:
        raise AssertionError("perfil vacío")

    # --- Un track largo (50 000 puntos, cada 3 m), con una parada de 2 000 puntos en el
    # mismo sitio: rápido, y reducido a como mucho unos dos puntos por columna
    def synthetic(count: int) -> TrackPath:
        lats, lons, eles, times_ = array("d"), array("d"), array("d"), array("d")
        lat = 42.0
        for k in range(count):
            if not 20_000 <= k < 22_000:  # parado
                lat += 0.000027
            lats.append(lat)
            lons.append(0.0)
            eles.append(1000 + 300 * math.sin(k / 3000) + (k * 7919 % 11) - 5)
            times_.append(1_700_000_000 + k)
        return TrackPath((PathSegment(lats, lons, eles, times_),))

    started = time.perf_counter()
    long_data = build_profile(synthetic(50_000))
    built = time.perf_counter() - started
    started = time.perf_counter()
    long_runs = drawing_runs(long_data, 1000)
    reduced = time.perf_counter() - started
    drawn = sum(len(run) for run in long_runs)
    assert len(long_runs) == 1 and long_runs[0][0] == 0 and long_runs[0][-1] == 49_999
    assert drawn <= 2 * 1000 + 2, drawn
    assert long_runs[0] == sorted(long_runs[0])
    # La mediana con miles de puntos parados en el mismo sitio no se atasca
    assert not math.isnan(long_data.smoothed[21_000])
    print(f"50 000 puntos: perfil en {built:.2f} s; {drawn} puntos que dibujar en {reduced * 1000:.0f} ms")
    assert built < 5, built

    print("Autoprueba finalizada correctamente.")
