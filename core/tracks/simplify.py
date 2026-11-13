"""Simplificar un recorrido y guardarlo como texto compacto (el contorno de un track).

Este módulo NO depende de Qt ni de la base de datos. Diseño en docs/MAPA.md (§5.3 y §8).

Para pintar muchos tracks a la vez en el mapa no se abren sus GPX: cada uno guarda en el
catálogo un CONTORNO ('track_details.overview'), su recorrido simplificado. Lo calcula el
extractor de tracks al leer el GPX:

    overview = encode_overview(simplify_track(segmentos))      # al leer el GPX
    segmentos = decode_overview(overview)                       # al pintarlo

Cómo se simplifica ('simplify_track'):
    1. Se quitan los puntos a menos de la tolerancia del último que se ha quedado (los
       relojes graban cada pocos metros: es lo que más reduce y lo más rápido).
    2. Douglas-Peucker: entre dos puntos que se quedan, se conserva el más alejado de la
       recta que los une si se separa más que la tolerancia, y se repite a cada lado.
       Así se conservan las curvas y se quitan los tramos casi rectos.
    3. Si aun así quedan más de 'max_points' entre todos los segmentos, se repite con el
       doble de tolerancia (sobre lo ya simplificado: es mucho más rápido).
    El primer y el último punto de cada segmento se quedan siempre. Las distancias se
    miden en metros sobre una proyección local (plana alrededor del segmento): para un
    track el error es despreciable. No se contemplan los tracks que cruzan el
    antimeridiano.

Formato del texto ('encode_overview'): cada segmento, una POLILÍNEA CODIFICADA (el formato
de Google Maps: cada número es la diferencia con el anterior, en caracteres del 63 al
126), con precisión 5 (unos 1,1 m); los segmentos, separados por saltos de línea. Unos
1 000 puntos ocupan unos 5 KB.

Los segmentos llegan como listas PLANAS [lat, lon, lat, lon...] (o 'array.array("d")',
que es como los guarda el lector de GPX: 16 bytes por punto).

1.0.0 Primera versión (docs/MAPA.md, paso 2.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.tracks.simplify
"""

__version__ = "1.0.0"
__all__ = [
    "OVERVIEW_MAX_POINTS",
    "OVERVIEW_TOLERANCE_M",
    "decode_overview",
    "decode_polyline",
    "encode_overview",
    "encode_polyline",
    "simplify_segment",
    "simplify_track",
]

# Librerías estándar
import math
from collections.abc import Iterable, Sequence

# Módulos del proyecto
from core.tracks.geodesy import EARTH_RADIUS_M

# Contorno de un track: tolerancia de partida y tope de puntos entre todos sus segmentos
# (docs/MAPA.md, §5.3). Si cambian, hay que subir TRACK_EXTRACTOR_VERSION para recalcularlo
OVERVIEW_TOLERANCE_M = 15.0
OVERVIEW_MAX_POINTS = 1000

# Veces que se dobla la tolerancia como mucho (15 m × 2^12 ≈ 61 km: de sobra)
_MAX_ROUNDS = 12
# Metros por grado de latitud
_METERS_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180
# Separador de segmentos en el texto (la polilínea solo usa los caracteres 63 a 126)
_SEGMENT_SEPARATOR = "\n"
_PRECISION = 5

FlatPoints = Sequence[float]


# -----------------------------------------------------------------------------
# Simplificar
# -----------------------------------------------------------------------------


def simplify_segment(flat: FlatPoints, tolerance_m: float) -> list[float]:
    """Simplifica un segmento [lat, lon, lat, lon...] con una tolerancia en metros.

    Returns:
        El segmento simplificado, también plano. Conserva siempre el primer y el último
        punto (un segmento de 0, 1 o 2 puntos vuelve igual).
    """
    count = len(flat) // 2
    if count <= 2 or tolerance_m <= 0:
        return list(flat[: count * 2])

    # Proyección local en metros: x hacia el este, y hacia el norte
    latitude0 = math.radians(sum(flat[0::2][:count]) / count)
    kx = _METERS_PER_DEGREE * math.cos(latitude0)
    xs = [flat[2 * i + 1] * kx for i in range(count)]
    ys = [flat[2 * i] * _METERS_PER_DEGREE for i in range(count)]

    # 1. Distancia radial: fuera los puntos a menos de la tolerancia del último que se queda
    tolerance2 = tolerance_m * tolerance_m
    kept = [0]
    for i in range(1, count - 1):
        last = kept[-1]
        if (xs[i] - xs[last]) ** 2 + (ys[i] - ys[last]) ** 2 >= tolerance2:
            kept.append(i)
    kept.append(count - 1)

    # 2. Douglas-Peucker, sin recursión (con una pila): vale para cientos de miles de puntos
    marks = [False] * len(kept)
    marks[0] = marks[-1] = True
    stack = [(0, len(kept) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        a, b = kept[first], kept[last]
        ax, ay = xs[a], ys[a]
        dx, dy = xs[b] - ax, ys[b] - ay
        length2 = dx * dx + dy * dy
        worst, worst_at = -1.0, -1
        for position in range(first + 1, last):
            p = kept[position]
            px, py = xs[p] - ax, ys[p] - ay
            if length2 == 0:
                # Los extremos coinciden (un recorrido circular): distancia a ese punto
                distance2 = px * px + py * py
            else:
                # Distancia al TRAMO (no a la recta entera)
                t = max(0.0, min(1.0, (px * dx + py * dy) / length2))
                ex, ey = px - t * dx, py - t * dy
                distance2 = ex * ex + ey * ey
            if distance2 > worst:
                worst, worst_at = distance2, position
        if worst > tolerance2:
            marks[worst_at] = True
            stack.append((first, worst_at))
            stack.append((worst_at, last))

    result: list[float] = []
    for position, keep in enumerate(marks):
        if keep:
            i = kept[position]
            result.append(flat[2 * i])
            result.append(flat[2 * i + 1])
    return result


def simplify_track(
    segments: Iterable[FlatPoints],
    *,
    tolerance_m: float = OVERVIEW_TOLERANCE_M,
    max_points: int = OVERVIEW_MAX_POINTS,
) -> list[list[float]]:
    """Simplifica todos los segmentos de un track hasta que, entre todos, no pasen de
    'max_points' (doblando la tolerancia si hace falta). Los segmentos de menos de dos
    puntos se quitan (no se pueden dibujar).

    Si hay tantos segmentos que ni con la mayor tolerancia se baja del tope (cada uno
    conserva sus dos extremos), se devuelve lo más simplificado que se ha conseguido.
    """
    current = [list(segment) for segment in segments if len(segment) >= 4]
    tolerance = tolerance_m
    for _ in range(_MAX_ROUNDS):
        current = [simplify_segment(segment, tolerance) for segment in current]
        if sum(len(segment) for segment in current) // 2 <= max_points:
            break
        tolerance *= 2
    return current


# -----------------------------------------------------------------------------
# Polilínea codificada (el formato de Google)
# -----------------------------------------------------------------------------


def _encode_number(value: int, out: list[str]) -> None:
    value = ~(value << 1) if value < 0 else value << 1
    while value >= 0x20:
        out.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    out.append(chr(value + 63))


def encode_polyline(flat: FlatPoints, precision: int = _PRECISION) -> str:
    """Un segmento [lat, lon, lat, lon...] como polilínea codificada."""
    factor = 10**precision
    out: list[str] = []
    previous_lat = previous_lon = 0
    for i in range(0, len(flat) - 1, 2):
        lat = round(flat[i] * factor)
        lon = round(flat[i + 1] * factor)
        _encode_number(lat - previous_lat, out)
        _encode_number(lon - previous_lon, out)
        previous_lat, previous_lon = lat, lon
    return "".join(out)


def decode_polyline(text: str, precision: int = _PRECISION) -> list[float]:
    """Una polilínea codificada como lista plana [lat, lon, lat, lon...].

    Raises:
        ValueError: Si el texto no es una polilínea válida.
    """
    factor = 10**precision
    values: list[int] = []
    number = shift = 0
    for char in text:
        code = ord(char) - 63
        if not 0 <= code < 64:
            raise ValueError(f"Carácter no válido en una polilínea: {char!r}")
        number |= (code & 0x1F) << shift
        shift += 5
        if code < 0x20:
            values.append(~(number >> 1) if number & 1 else number >> 1)
            number = shift = 0
    if shift or len(values) % 2:
        raise ValueError("Polilínea incompleta")
    flat: list[float] = []
    lat = lon = 0
    for i in range(0, len(values), 2):
        lat += values[i]
        lon += values[i + 1]
        flat.append(lat / factor)
        flat.append(lon / factor)
    return flat


def encode_overview(segments: Iterable[FlatPoints]) -> str | None:
    """Los segmentos (ya simplificados) como texto para 'track_details.overview'.
    Solo cuentan los de al menos dos puntos (uno suelto no se puede dibujar); None si no
    queda ninguno."""
    lines = [encode_polyline(segment) for segment in segments if len(segment) >= 4]
    return _SEGMENT_SEPARATOR.join(lines) if lines else None


def decode_overview(text: str | None) -> tuple[tuple[tuple[float, float], ...], ...]:
    """El texto de 'track_details.overview' como segmentos de (latitud, longitud): la forma
    que espera el mapa ('MapTrack.segments'). Vacío si no hay nada.

    Raises:
        ValueError: Si el texto está dañado.
    """
    if not text:
        return ()
    segments = []
    for line in text.split(_SEGMENT_SEPARATOR):
        flat = decode_polyline(line)
        segments.append(tuple((flat[i], flat[i + 1]) for i in range(0, len(flat), 2)))
    return tuple(segment for segment in segments if segment)


if __name__ == "__main__":
    # Autoprueba (sin Qt ni base de datos).
    # Ejecutar desde la raíz del proyecto:  python -m core.tracks.simplify
    import random
    import time
    from array import array

    def wander(count: int, seed: int, start: tuple[float, float] = (42.65, -0.05)) -> list[float]:
        """Un recorrido inventado: pasos de unos 8 m con giros suaves, como un reloj GPS."""
        walker = random.Random(seed)
        latitude, longitude, heading = start[0], start[1], walker.uniform(0, 6)
        flat: list[float] = []
        for _ in range(count):
            flat += (latitude, longitude)
            heading += walker.uniform(-0.25, 0.25)
            latitude += 0.00007 * math.cos(heading)
            longitude += 0.0001 * math.sin(heading)
        return flat

    def max_deviation_m(original: list[float], simplified: list[float]) -> float:
        """Lo más que se separa un punto original (uno de cada 20) del recorrido
        simplificado: su distancia al tramo más cercano, en la proyección local."""
        kx = _METERS_PER_DEGREE * math.cos(math.radians(original[0]))
        ky = _METERS_PER_DEGREE
        pieces = [
            (simplified[i + 1] * kx, simplified[i] * ky, simplified[i + 3] * kx, simplified[i + 2] * ky)
            for i in range(0, len(simplified) - 2, 2)
        ]
        worst = 0.0
        for i in range(0, len(original), 40):
            px, py = original[i + 1] * kx, original[i] * ky
            nearest = math.inf
            for ax, ay, bx, by in pieces:
                dx, dy = bx - ax, by - ay
                length2 = dx * dx + dy * dy or 1e-12
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
                nearest = min(nearest, math.hypot(px - ax - t * dx, py - ay - t * dy))
            worst = max(worst, nearest)
        return worst

    # 1. Casos pequeños: 0, 1 y 2 puntos vuelven igual; una recta se queda en sus extremos
    assert simplify_segment([], 15) == [] and simplify_segment([42.0, 0.0], 15) == [42.0, 0.0]
    assert simplify_segment([42.0, 0.0, 42.1, 0.1], 15) == [42.0, 0.0, 42.1, 0.1]
    line = [v for k in range(101) for v in (42.0 + k * 0.001, 0.0)]  # 11 km hacia el norte
    assert simplify_segment(line, 15) == [42.0, 0.0, 42.1, 0.0]
    # Una esquina se conserva; un recorrido circular (vuelve al principio) también se dibuja
    corner = [42.0, 0.0, 42.0005, 0.0, 42.001, 0.0, 42.001, 0.0007, 42.001, 0.0014]
    assert simplify_segment(corner, 15) == [42.0, 0.0, 42.001, 0.0, 42.001, 0.0014]
    loop = [v for k in range(41) for v in (42 + 0.01 * math.sin(k * math.pi / 20),
                                           0.01 * (1 - math.cos(k * math.pi / 20)))]  # fmt: skip
    simplified_loop = simplify_segment(loop, 15)
    assert len(simplified_loop) // 2 > 10 and simplified_loop[:2] == loop[:2]

    # 2. Un track realista de 10 000 puntos: se reduce mucho y no se separa del original
    #    más de la tolerancia (con margen por la medida aproximada)
    track = wander(10_000, 5)
    started = time.perf_counter()
    simplified = simplify_segment(track, 15)
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"10 000 puntos -> {len(simplified) // 2} con 15 m, en {elapsed_ms:.0f} ms")
    assert len(simplified) // 2 < 2500 and simplified[:2] == track[:2] and simplified[-2:] == track[-2:]
    deviation = max_deviation_m(track, simplified)
    print(f"Lo más que se separa del original: {deviation:.1f} m")
    assert deviation <= 15.5, deviation  # la tolerancia (y medio metro por la proyección)

    # 3. El tope de puntos: con 100 000 puntos en dos segmentos, quedan 1 000 o menos;
    #    también si los segmentos llegan como 'array("d")' (como los da el lector de GPX)
    long_track = wander(100_000, 6)
    segments = [array("d", long_track[:120_000]), array("d", long_track[120_400:])]
    started = time.perf_counter()
    overview = simplify_track(segments)
    elapsed_ms = (time.perf_counter() - started) * 1000
    total = sum(len(s) for s in overview) // 2
    print(f"100 000 puntos en 2 segmentos -> {total} puntos, en {elapsed_ms:.0f} ms")
    assert len(overview) == 2 and total <= OVERVIEW_MAX_POINTS
    assert overview[0][:2] == list(segments[0][:2]) and overview[1][-2:] == list(segments[1][-2:])
    # Los segmentos vacíos se quitan; uno de un solo punto, también (no se puede dibujar)
    assert simplify_track([[], [42.0, 0.0], line]) == [[42.0, 0.0, 42.1, 0.0]]
    # Demasiados segmentos para el tope: lo más simplificado posible (sus extremos)
    many = [[42.0 + k * 0.01, 0.0, 42.0 + k * 0.01, 0.005, 42.0 + k * 0.01, 0.01] for k in range(600)]
    assert sum(len(s) for s in simplify_track(many)) // 2 == 1200

    # 4. Polilínea: el ejemplo de la documentación de Google y la ida y vuelta
    google = [38.5, -120.2, 40.7, -120.95, 43.252, -126.453]
    assert encode_polyline(google) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == google
    assert encode_polyline([]) == "" and decode_polyline("") == []
    again = decode_polyline(encode_polyline(simplified))
    assert len(again) == len(simplified)
    assert max(abs(a - b) for a, b in zip(again, simplified, strict=True)) <= 0.5e-5 + 1e-12
    for bad in ("_p~iF~ps|", " ", "ñ", "_p~iF"):
        try:
            decode_polyline(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debería rechazarse: {bad!r}")

    # 5. El contorno como texto: segmentos por líneas, ida y vuelta, y su tamaño
    text = encode_overview(overview)
    assert text is not None and text.count("\n") == 1
    assert all(32 < ord(char) < 127 or char == "\n" for char in text)
    decoded = decode_overview(text)
    assert [len(s) for s in decoded] == [len(s) // 2 for s in overview]
    assert decoded[0][0] == (round(overview[0][0], 5), round(overview[0][1], 5))
    print(f"Contorno de {total} puntos: {len(text)} caracteres")
    assert len(text) < 12_000
    assert encode_overview([]) is None and encode_overview([[42.0, 0.0]]) is None
    assert decode_overview(None) == () and decode_overview("") == ()
    try:
        decode_overview("_p~iF\n???")
    except ValueError:
        pass
    else:
        raise AssertionError("un contorno dañado debe rechazarse")

    print("Autoprueba finalizada correctamente.")
