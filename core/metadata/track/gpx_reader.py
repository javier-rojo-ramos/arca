"""Lector de archivos GPX: resume un track en unos pocos datos (distancia, desnivel, fechas...).

Este módulo NO depende de Qt ni de la base de datos: recibe una ruta y devuelve un
'GpxSummary'. Lo usa el extractor de tracks ('extractor.py'), que decide en qué columnas
del catálogo va cada dato.

Cómo lee el archivo:
    - Con 'defusedxml' (protege de XML malicioso: entidades recursivas, etc.).
    - En STREAMING ('iterparse'): va soltando cada punto en cuanto lo ha sumado, así que
      un track de cientos de miles de puntos no llena la memoria.
    - Admite GPX 1.0 y 1.1 (se ignora el espacio de nombres de las etiquetas).

Qué partes del GPX se usan:
    <trk> / <trkseg> / <trkpt>   el recorrido grabado (lo normal: reloj, móvil, GPS)
    <rte> / <rtept>              una ruta planificada. Solo cuenta si el archivo NO tiene
                                 recorrido grabado (si tiene los dos, se sumaría dos veces)
    <wpt>                        puntos de interés: solo se cuentan
    nombre, descripción, tipo de actividad, autor y fecha de <metadata> y de <trk>

Cómo se calcula:
    - Distancia: suma de las distancias entre puntos consecutivos de un MISMO segmento
      (fórmula del haversine, en 2D, sin la altitud: como Wikiloc, Strava o Garmin). Entre
      un segmento y el siguiente (p. ej. pausa del GPS) no se suma nada.
    - Desnivel acumulado: con un UMBRAL ('ELEVATION_THRESHOLD_M'). La altitud del GPS
      oscila unos metros arriba y abajo; sumar cada oscilación inflaría el desnivel. Solo
      se cuenta una subida (o bajada) cuando la altitud se separa al menos el umbral del
      último punto de referencia.
    - Fechas: la del primer y la del último punto con hora (mínima y máxima, por si el
      archivo no está ordenado). El GPX las guarda en UTC.

1.1.0 Umbral del desnivel: 8 m (antes 5 m), calibrado con tracks reales de Wikiloc.

Prueba rápida (desde la raíz del proyecto):
    python -m core.metadata.track.gpx_reader
"""

__version__ = "1.1.0"
__all__ = [
    "ELEVATION_THRESHOLD_M",
    "GpxError",
    "GpxSummary",
    "parse_gpx_time",
    "read_gpx",
]

# Librerías estándar
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

# Librerías de terceros
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import iterparse

# Radio medio de la Tierra (metros), el habitual para la fórmula del haversine
EARTH_RADIUS_M = 6_371_008.8

# Umbral del desnivel acumulado (metros). Calibrado con tracks reales de Wikiloc
# comparando con el desnivel que muestra Wikiloc (ver 'inspect_cli.py'): con 8 m el
# error total es el menor (una ruta pedía 12 m, otra 3-5 m y otra 8 m; con 5 m una se
# pasaba un 32 %). Ningún umbral único clava todas: el ruido depende del GPS de cada
# track. Con 0 se sumaría cada oscilación del GPS (desniveles muy inflados).
# Si se cambia, hay que subir 'TRACK_EXTRACTOR_VERSION' (extractor.py) para releer.
ELEVATION_THRESHOLD_M = 8.0


class GpxError(Exception):
    """El archivo no es un GPX válido (mensaje corto en español, para 'scan_errors')."""


@dataclass(frozen=True, slots=True)
class GpxSummary:
    """Resumen de un archivo GPX.

    Todos los campos pueden ser None (o 0 en los recuentos) si el archivo no trae ese dato.

    Attributes:
        name: Nombre del track (o, si no tiene, el del archivo GPX o el de la ruta).
        description: Descripción del track (o la del archivo GPX).
        author: Autor que figura en el GPX.
        activity_type: Tipo de actividad del track ('hiking', 'cycling'...), tal cual.
        creator_app: Programa o dispositivo que creó el archivo (atributo 'creator').
        metadata_time: Fecha del archivo GPX (<metadata><time>), en UTC.
        start_time: Hora del primer punto (UTC, con zona).
        end_time: Hora del último punto (UTC, con zona).
        distance_m: Distancia total en metros.
        elevation_gain_m: Desnivel acumulado de subida, en metros.
        elevation_loss_m: Desnivel acumulado de bajada, en metros (positivo).
        elevation_min_m: Altitud mínima.
        elevation_max_m: Altitud máxima.
        start_point: (latitud, longitud, altitud o None) del primer punto.
        end_point: (latitud, longitud, altitud o None) del último punto.
        bounds: (lat. mínima, lat. máxima, lon. mínima, lon. máxima) del recorrido.
        point_count: Puntos del recorrido usados.
        segment_count: Segmentos (o rutas) con al menos un punto.
        track_count: Elementos <trk> del archivo.
        route_count: Elementos <rte> del archivo.
        waypoint_count: Puntos de interés (<wpt>).
        uses_route: True si el recorrido sale de <rte> (no había track grabado).
    """

    name: str | None = None
    description: str | None = None
    author: str | None = None
    activity_type: str | None = None
    creator_app: str | None = None
    metadata_time: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    elevation_min_m: float | None = None
    elevation_max_m: float | None = None
    start_point: tuple[float, float, float | None] | None = None
    end_point: tuple[float, float, float | None] | None = None
    bounds: tuple[float, float, float, float] | None = None
    point_count: int = 0
    segment_count: int = 0
    track_count: int = 0
    route_count: int = 0
    waypoint_count: int = 0
    uses_route: bool = False

    @property
    def duration_s(self) -> float | None:
        """Segundos entre el primer y el último punto con hora (None si no hay horas)."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------


def parse_gpx_time(text: str | None) -> datetime | None:
    """Convierte una fecha GPX ('2024-05-01T08:12:33Z') en un datetime UTC (con zona).

    Admite fracciones de segundo y desfases ('+02:00'). Una fecha sin zona se considera
    UTC, que es lo que manda el estándar GPX. Devuelve None si el texto no es una fecha.
    """
    if not text:
        return None
    value = text.strip()
    try:
        parsed = datetime.fromisoformat(value)  # Python 3.11+ entiende la 'Z' final
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos (grados), sobre una esfera."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _local_name(tag: str) -> str:
    """Nombre de una etiqueta sin el espacio de nombres ('{http://...}trkpt' -> 'trkpt')."""
    return tag.rsplit("}", 1)[-1]


def _child_text(element: Element, name: str) -> str | None:
    """Texto (sin espacios en los extremos) del primer hijo con ese nombre, o None."""
    for child in element:
        if _local_name(child.tag) == name:
            value = (child.text or "").strip()
            return value or None
    return None


def _clean(text: str | None) -> str | None:
    """Texto sin espacios en los extremos; None si queda vacío."""
    if text is None:
        return None
    value = text.strip()
    return value or None


class _Accumulator:
    """Va sumando los puntos de un recorrido (track o ruta) sin guardarlos en memoria."""

    def __init__(self, threshold_m: float) -> None:
        self.threshold_m = threshold_m
        self.points = 0
        self.segments = 0
        self.distance_m = 0.0
        self.gain_m = 0.0
        self.loss_m = 0.0
        self.ele_min: float | None = None
        self.ele_max: float | None = None
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.first_point: tuple[float, float, float | None] | None = None
        self.last_point: tuple[float, float, float | None] | None = None
        self.min_lat = self.min_lon = math.inf
        self.max_lat = self.max_lon = -math.inf
        # Estado del segmento en curso
        self._previous: tuple[float, float] | None = None
        self._ele_reference: float | None = None
        self._segment_has_points = False

    def add_point(self, lat: float, lon: float, ele: float | None, time: datetime | None) -> None:
        """Suma un punto al segmento en curso."""
        self.points += 1
        if not self._segment_has_points:
            self._segment_has_points = True
            self.segments += 1

        # Distancia desde el punto anterior del MISMO segmento
        if self._previous is not None:
            self.distance_m += _haversine_m(*self._previous, lat, lon)
        self._previous = (lat, lon)

        # Desnivel con umbral (ver la cabecera del módulo)
        if ele is not None:
            self.ele_min = ele if self.ele_min is None else min(self.ele_min, ele)
            self.ele_max = ele if self.ele_max is None else max(self.ele_max, ele)
            if self._ele_reference is None:
                self._ele_reference = ele
            elif ele - self._ele_reference >= self.threshold_m:
                self.gain_m += ele - self._ele_reference
                self._ele_reference = ele
            elif self._ele_reference - ele >= self.threshold_m:
                self.loss_m += self._ele_reference - ele
                self._ele_reference = ele

        # Fechas: mínima y máxima (por si los puntos no vienen ordenados)
        if time is not None:
            if self.start_time is None or time < self.start_time:
                self.start_time = time
            if self.end_time is None or time > self.end_time:
                self.end_time = time

        # Caja geográfica y extremos del recorrido
        self.min_lat, self.max_lat = min(self.min_lat, lat), max(self.max_lat, lat)
        self.min_lon, self.max_lon = min(self.min_lon, lon), max(self.max_lon, lon)
        if self.first_point is None:
            self.first_point = (lat, lon, ele)
        self.last_point = (lat, lon, ele)

    def end_segment(self) -> None:
        """Cierra el segmento: el siguiente punto no se une a este (ni en distancia ni en desnivel)."""
        self._previous = None
        self._ele_reference = None
        self._segment_has_points = False


# -----------------------------------------------------------------------------
# Lectura
# -----------------------------------------------------------------------------


def read_gpx(path: str | Path, *, threshold_m: float = ELEVATION_THRESHOLD_M) -> GpxSummary:
    """Lee un archivo GPX y devuelve su resumen.

    Args:
        path: Ruta del archivo.
        threshold_m: Umbral del desnivel acumulado (ver la cabecera del módulo).

    Returns:
        El resumen del archivo.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        GpxError: Si no es un GPX o está dañado.
        OSError: Si no se puede leer (permisos...).
    """
    track = _Accumulator(threshold_m)
    route = _Accumulator(threshold_m)

    # Textos que se buscan (se queda el primero que aparece de cada uno)
    texts: dict[str, str | None] = {
        "track_name": None, "track_desc": None, "track_type": None,
        "file_name": None, "file_desc": None, "file_time": None,
        "author": None, "route_name": None,
    }  # fmt: skip
    creator_app: str | None = None
    track_count = route_count = waypoint_count = 0

    stack: list[str] = []  # nombres (sin espacio de nombres) de las etiquetas abiertas
    try:
        for event, element in iterparse(str(path), events=("start", "end")):
            name = _local_name(element.tag)

            if event == "start":
                if not stack and name != "gpx":
                    raise GpxError("No es un archivo GPX (falta la etiqueta <gpx>).")
                if not stack:
                    creator_app = _clean(element.get("creator"))
                stack.append(name)
                continue

            # --- event == "end": la etiqueta ya está completa (con sus hijos) ---
            parent = stack[-2] if len(stack) >= 2 else ""

            if name in ("trkpt", "rtept"):
                point = _read_point(element)
                if point is not None:
                    (track if name == "trkpt" else route).add_point(*point)
                element.clear()  # libera la memoria del punto ya sumado
            elif name == "trkseg":
                track.end_segment()
                element.clear()  # suelta también los puntos (ya vacíos) del segmento
            elif name == "trk":
                track_count += 1
                track.end_segment()
            elif name == "rte":
                route_count += 1
                route.end_segment()
            elif name == "wpt":
                waypoint_count += 1
                element.clear()
            else:
                _collect_text(name, parent, stack, element, texts)

            stack.pop()
    except (ParseError, DefusedXmlException) as error:
        raise GpxError(f"El GPX está dañado o no es XML válido ({error}).") from error

    # Un GPX sin puntos es válido: simplemente no tiene recorrido (se devuelve sin datos)

    # Recorrido: el grabado si lo hay; si no, la ruta planificada
    uses_route = track.points == 0 and route.points > 0
    path_data = route if uses_route else track
    has_points = path_data.points > 0

    return GpxSummary(
        name=texts["track_name"] or texts["file_name"] or texts["route_name"],
        description=texts["track_desc"] or texts["file_desc"],
        author=texts["author"],
        activity_type=texts["track_type"],
        creator_app=creator_app,
        metadata_time=parse_gpx_time(texts["file_time"]),
        start_time=path_data.start_time,
        end_time=path_data.end_time,
        distance_m=path_data.distance_m if has_points else None,
        elevation_gain_m=path_data.gain_m if path_data.ele_min is not None else None,
        elevation_loss_m=path_data.loss_m if path_data.ele_min is not None else None,
        elevation_min_m=path_data.ele_min,
        elevation_max_m=path_data.ele_max,
        start_point=path_data.first_point,
        end_point=path_data.last_point,
        bounds=(
            (path_data.min_lat, path_data.max_lat, path_data.min_lon, path_data.max_lon)
            if has_points
            else None
        ),
        point_count=path_data.points,
        segment_count=path_data.segments,
        track_count=track_count,
        route_count=route_count,
        waypoint_count=waypoint_count,
        uses_route=uses_route,
    )


def _read_point(element: Element) -> tuple[float, float, float | None, datetime | None] | None:
    """Lee un <trkpt>/<rtept>: (latitud, longitud, altitud, hora), o None si no es válido."""
    try:
        lat = float(element.get("lat", ""))
        lon = float(element.get("lon", ""))
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None  # coordenadas imposibles: el punto se ignora

    ele: float | None = None
    ele_text = _child_text(element, "ele")
    if ele_text is not None:
        try:
            ele = float(ele_text)
        except ValueError:
            ele = None
        if ele is not None and not math.isfinite(ele):
            ele = None

    return lat, lon, ele, parse_gpx_time(_child_text(element, "time"))


def _collect_text(
    name: str,
    parent: str,
    stack: list[str],
    element: Element,
    texts: dict[str, str | None],
) -> None:
    """Guarda los textos que interesan (nombre, descripción, autor...) según dónde están.

    Solo se queda el PRIMERO de cada uno (p. ej. el nombre del primer track). El nombre de
    un punto (<wpt><name>) no cuenta: se mira la etiqueta padre.
    """

    def keep(key: str, value: str | None) -> None:
        if texts[key] is None and value:
            texts[key] = value

    value = _clean(element.text)
    # Dentro de <metadata> (GPX 1.1) o directamente en <gpx> (GPX 1.0)
    file_level = parent in ("metadata", "gpx")

    if name == "name":
        if parent == "trk":
            keep("track_name", value)
        elif parent == "rte":
            keep("route_name", value)
        elif file_level:
            keep("file_name", value)
        elif parent == "author" and len(stack) >= 3 and stack[-3] == "metadata":
            keep("author", value)  # GPX 1.1: <metadata><author><name>
    elif name == "desc":
        if parent == "trk":
            keep("track_desc", value)
        elif file_level:
            keep("file_desc", value)
    elif name == "type" and parent == "trk":
        keep("track_type", value)
    elif name == "time" and file_level:
        keep("file_time", value)
    elif name == "author" and parent == "gpx":
        keep("author", value)  # GPX 1.0: <gpx><author>texto</author>


if __name__ == "__main__":
    # Autoprueba con archivos GPX inventados en una carpeta temporal.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.track.gpx_reader
    import tempfile

    GPX11 = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Garmin Connect" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>Archivo de prueba</name>
    <author><name>Javier</name></author>
    <time>2024-05-01T07:00:00Z</time>
  </metadata>
  <wpt lat="43.0" lon="-3.0"><name>Fuente</name></wpt>
  <trk>
    <name>Ruta del Cares</name>
    <desc>Poncebos - Caín</desc>
    <type>hiking</type>
    <trkseg>
      <trkpt lat="43.0000" lon="-3.0000"><ele>100</ele><time>2024-05-01T08:00:00Z</time></trkpt>
      <trkpt lat="43.0010" lon="-3.0000"><ele>102</ele><time>2024-05-01T08:01:00Z</time></trkpt>
      <trkpt lat="43.0020" lon="-3.0000"><ele>110</ele><time>2024-05-01T08:02:00Z</time></trkpt>
      <trkpt lat="43.0030" lon="-3.0000"><ele>104</ele><time>2024-05-01T08:03:00Z</time></trkpt>
    </trkseg>
    <trkseg>
      <trkpt lat="43.0100" lon="-3.0000"><ele>104</ele><time>2024-05-01T09:00:00Z</time></trkpt>
      <trkpt lat="43.0110" lon="-3.0000"><ele>90</ele><time>2024-05-01T09:01:30.500Z</time></trkpt>
      <trkpt lat="999" lon="0"><ele>5</ele></trkpt>
    </trkseg>
  </trk>
</gpx>"""

    # Ruta planificada sin track grabado, en GPX 1.0 y sin horas ni altitudes
    GPX10_ROUTE = """<?xml version="1.0"?>
<gpx version="1.0" creator="Wikiloc">
  <name>Ruta planificada</name>
  <author>Alguien</author>
  <rte>
    <name>Plan</name>
    <rtept lat="40.0" lon="-3.0"/>
    <rtept lat="40.0" lon="-2.99"/>
  </rte>
</gpx>"""

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # 1. GPX 1.1 completo: dos segmentos, un punto inválido y un punto de interés
        (base / "cares.gpx").write_text(GPX11, encoding="utf-8")
        s = read_gpx(base / "cares.gpx", threshold_m=5)
        print(s)
        assert s.name == "Ruta del Cares" and s.description == "Poncebos - Caín"
        assert s.author == "Javier" and s.activity_type == "hiking"
        assert s.creator_app == "Garmin Connect"
        assert (s.track_count, s.route_count, s.waypoint_count) == (1, 0, 1)
        assert (s.point_count, s.segment_count) == (6, 2)  # el punto 999 se ignora
        # 3 tramos de 0,001° (≈111 m) en el primer segmento + 1 en el segundo; NO se une
        # el final del primero con el principio del segundo (≈778 m)
        assert 440 < s.distance_m < 450, s.distance_m
        # Umbral de 5 m: 100 -> 102 (no cuenta) -> 110 (+10) -> 104 (-6);
        # segundo segmento: 104 -> 90 (-14)
        assert s.elevation_gain_m == 10 and s.elevation_loss_m == 20, (s.elevation_gain_m, s.elevation_loss_m)
        assert (s.elevation_min_m, s.elevation_max_m) == (90, 110)
        assert s.start_time == datetime(2024, 5, 1, 8, 0, tzinfo=UTC)
        assert s.end_time == datetime(2024, 5, 1, 9, 1, 30, 500000, tzinfo=UTC)
        assert s.duration_s == 3690.5
        assert s.start_point == (43.0, -3.0, 100.0) and s.end_point == (43.011, -3.0, 90.0)
        assert s.bounds == (43.0, 43.011, -3.0, -3.0)
        assert s.metadata_time == datetime(2024, 5, 1, 7, 0, tzinfo=UTC)

        # 2. El umbral cambia el resultado: con 0 se suma cada oscilación (también los
        #    6 m de bajada que el umbral de 5 m ya contaba); con 10 m, esa bajada no cuenta
        raw = read_gpx(base / "cares.gpx", threshold_m=0)
        assert (raw.elevation_gain_m, raw.elevation_loss_m) == (10, 20)
        strict = read_gpx(base / "cares.gpx", threshold_m=10)
        assert (strict.elevation_gain_m, strict.elevation_loss_m) == (10, 14)

        # 3. Ruta planificada (GPX 1.0): se usa porque no hay track grabado
        (base / "plan.gpx").write_text(GPX10_ROUTE, encoding="utf-8")
        r = read_gpx(base / "plan.gpx")
        assert r.uses_route and r.point_count == 2 and r.route_count == 1
        assert r.name == "Ruta planificada" and r.author == "Alguien"  # nivel de archivo
        assert r.start_time is None and r.duration_s is None
        assert r.elevation_gain_m is None and r.elevation_min_m is None
        assert 850 < r.distance_m < 860, r.distance_m  # 0,01° de longitud a 40° N ≈ 852 m

        # 4. GPX vacío: válido, sin datos
        (base / "vacio.gpx").write_text('<gpx version="1.1" creator="x"></gpx>', encoding="utf-8")
        e = read_gpx(base / "vacio.gpx")
        assert e.point_count == 0 and e.distance_m is None and e.bounds is None

        # 5. Errores: no es GPX, XML roto y archivo inexistente
        (base / "otro.gpx").write_text("<kml></kml>", encoding="utf-8")
        (base / "roto.gpx").write_text("<gpx><trk><trkseg>", encoding="utf-8")
        for bad in ("otro.gpx", "roto.gpx"):
            try:
                read_gpx(base / bad)
            except GpxError as error:
                print(f"{bad}: {error}")
            else:
                raise AssertionError(f"{bad} debería rechazarse")
        try:
            read_gpx(base / "no_existe.gpx")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("debería lanzar FileNotFoundError")

        # 6. Fechas sueltas
        assert parse_gpx_time("2024-05-01T08:00:00+02:00") == datetime(2024, 5, 1, 6, 0, tzinfo=UTC)
        assert parse_gpx_time("2024-05-01T08:00:00") == datetime(2024, 5, 1, 8, 0, tzinfo=UTC)
        assert parse_gpx_time("ayer") is None and parse_gpx_time(None) is None

    print("Autoprueba finalizada correctamente.")
