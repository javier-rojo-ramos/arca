"""Lector COMPLETO de archivos GPX: todos los puntos, y lo demás sin perder nada.

Este módulo NO depende de Qt ni de la base de datos.

El lector del extractor ('core/metadata/track/gpx_reader.py') RESUME un track (distancia,
desnivel, fechas) y tira los puntos. Este los conserva: es la base del módulo Tracks
(docs/MAPA.md, fases 4 a 7): pintar el recorrido entero en el mapa, el perfil de elevación
y, más adelante, editar y exportar. El del extractor no se toca.

Ofrece dos lecturas:

    read_gpx_path(path) -> TrackPath
        Solo el RECORRIDO, en arrays compactos por segmento (latitud, longitud, altitud y
        hora de cada punto: 32 bytes por punto), y los puntos de interés (waypoints).
        Rápida y ligera: para ver (el mapa y el perfil). Lee en streaming, como el extractor.

    read_gpx_document(path) -> GpxDocument
        El archivo ENTERO, para editarlo: los tracks con sus segmentos y sus puntos, los
        puntos de interés (waypoints) y, tal cual, todo lo que la aplicación no edita
        (<metadata>, extensiones del documento, de los tracks, de los segmentos y de CADA
        punto: pulso, cadencia, temperatura...; las rutas planificadas). Con ello se podrá
        exportar sin perder nada (fase 6). 'document.path()' da el mismo 'TrackPath'.

Las dos leen EL MISMO recorrido que el extractor (lo comprueba la autoprueba):
    - Los puntos sin latitud o longitud válidas se ignoran (se cuentan en
      'skipped_points').
    - El recorrido es el grabado (<trk>). Solo si el archivo no tiene ningún punto grabado
      se usan las rutas planificadas (<rte>), cada una como un track de un segmento
      ('GpxTrack.from_route'); si tiene los dos, las rutas se guardan sin tocar.
    - Los segmentos sin ningún punto válido no cuentan.
Así el ÍNDICE de un punto (su posición contando todos los segmentos seguidos) significa
lo mismo en el contorno del catálogo, en el mapa, en el perfil y en la edición.

Lo que NO se edita se guarda como elementos XML sueltos ('Element'), no como texto: al
exportar se meterán en un único árbol y los espacios de nombres saldrán declarados una
sola vez, con sus prefijos de origen ('GpxDocument.namespaces': gpxtpx, ns3...). No se
conservan los comentarios XML ni el formato exacto (sangrías, orden de los atributos).
(En docs/MAPA.md §7.1 se pensó en guardarlos como texto para ahorrar memoria con tracks
de 100 000 puntos; los del autor tienen de 1 000 a 10 000 y así el exportado es limpio.)

Uso:
    from core.tracks.gpx_document import read_gpx_document, read_gpx_path

    path = read_gpx_path("ruta.gpx")
    path.point_count, len(path.segments)
    path.segments[0].latitudes[0]              # arrays: latitudes, longitudes,
    path.segments[0].elevation(3)              # elevations y times (NaN = sin dato),
    path.segments[0].time(3)                   # o None con 'elevation(i)' / 'time(i)'
    path.locate(120)                           # (segmento, posición) del punto 120

    document = read_gpx_document("ruta.gpx")
    document.tracks[0].name, document.tracks[0].segments[0].points[0].latitude
    document.waypoints[0].name
    document.path()

Errores: 'GpxError' (el del extractor) si no es un GPX o está dañado; 'FileNotFoundError'
y 'OSError' si no se puede leer.

1.1.0 'TrackPath.waypoints': la lectura rápida recoge también los puntos de interés, para
      verlos en el mapa con el track activo (paso 4.3b).
1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.tracks.gpx_document
"""

__version__ = "1.1.0"
__all__ = [
    "GpxDocument",
    "GpxTrack",
    "PathSegment",
    "TrackPath",
    "TrackPoint",
    "TrackSegment",
    "Waypoint",
    "read_gpx_document",
    "read_gpx_path",
]

# Librerías estándar
import math
from array import array
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

# Librerías de terceros
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import iterparse

# Módulos del proyecto
from core.metadata.track.gpx_reader import GpxError, parse_gpx_time

_NAN = math.nan


# -----------------------------------------------------------------------------
# El recorrido, compacto (para ver)
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PathSegment:
    """Los puntos de un segmento, en cuatro arrays paralelos (uno por dato).

    Attributes:
        latitudes: Latitud de cada punto (grados).
        longitudes: Longitud de cada punto (grados).
        elevations: Altitud (metros); NaN si el punto no la tiene.
        times: Hora, en segundos desde 1970 en UTC; NaN si el punto no la tiene.
    """

    latitudes: array
    longitudes: array
    elevations: array
    times: array

    def __len__(self) -> int:
        return len(self.latitudes)

    def elevation(self, index: int) -> float | None:
        """Altitud del punto 'index' del segmento, o None si no la tiene."""
        value = self.elevations[index]
        return None if math.isnan(value) else value

    def time(self, index: int) -> datetime | None:
        """Hora (UTC) del punto 'index' del segmento, o None si no la tiene."""
        value = self.times[index]
        return None if math.isnan(value) else datetime.fromtimestamp(value, UTC)


@dataclass(frozen=True, slots=True)
class TrackPath:
    """El recorrido de un GPX: sus segmentos, en orden (ver el docstring del archivo).

    Attributes:
        segments: Los segmentos con al menos un punto.
        from_route: True si sale de una ruta planificada (<rte>), no de un track grabado.
        skipped_points: Puntos ignorados por no tener una latitud y una longitud válidas.
        waypoints: Los puntos de interés del archivo (<wpt>) con coordenadas válidas. No
            son parte del recorrido: no cuentan en 'point_count'.
    """

    segments: tuple[PathSegment, ...] = ()
    from_route: bool = False
    skipped_points: int = 0
    waypoints: "tuple[Waypoint, ...]" = ()

    @property
    def point_count(self) -> int:
        """Puntos del recorrido (entre todos los segmentos)."""
        return sum(len(segment) for segment in self.segments)

    @property
    def has_elevation(self) -> bool:
        """True si algún punto tiene altitud."""
        return any(not math.isnan(v) for segment in self.segments for v in segment.elevations)

    @property
    def has_time(self) -> bool:
        """True si algún punto tiene hora."""
        return any(not math.isnan(v) for segment in self.segments for v in segment.times)

    def locate(self, index: int) -> tuple[int, int]:
        """(segmento, posición dentro de él) del punto 'index' del recorrido.

        Raises:
            IndexError: Si no hay tal punto.
        """
        if index >= 0:
            remaining = index
            for number, segment in enumerate(self.segments):
                if remaining < len(segment):
                    return number, remaining
                remaining -= len(segment)
        raise IndexError(f"El recorrido no tiene el punto {index}.")


class _PathBuilder:
    """Va juntando los puntos de un recorrido en arrays, por segmentos."""

    def __init__(self) -> None:
        self.segments: list[PathSegment] = []
        self.skipped = 0
        self._current: PathSegment | None = None

    def add(self, point: "_RawPoint | None") -> None:
        """Añade un punto al segmento en curso (None = no válido: se cuenta y se ignora)."""
        if point is None:
            self.skipped += 1
            return
        if self._current is None:
            self._current = PathSegment(array("d"), array("d"), array("d"), array("d"))
            self.segments.append(self._current)
        latitude, longitude, elevation, time = point
        self._current.latitudes.append(latitude)
        self._current.longitudes.append(longitude)
        self._current.elevations.append(_NAN if elevation is None else elevation)
        self._current.times.append(_NAN if time is None else time.timestamp())

    def end_segment(self) -> None:
        """Cierra el segmento: el siguiente punto empieza otro."""
        self._current = None

    @property
    def point_count(self) -> int:
        return sum(len(segment) for segment in self.segments)


# -----------------------------------------------------------------------------
# El documento entero (para editar)
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class TrackPoint:
    """Un punto del recorrido.

    Attributes:
        latitude: Latitud (grados).
        longitude: Longitud (grados).
        elevation: Altitud (metros), o None.
        time: Hora (UTC, con zona), o None.
        extra: Los demás hijos del punto en el GPX, tal cual y en su orden (extensiones
            con el pulso o la cadencia, 'hdop', 'sat'...). No se editan: se conservan.
        elevation_estimated: True si la altitud no es del GPX, sino puesta por la
            aplicación con el modelo de elevaciones (al leer, siempre False).
    """

    latitude: float
    longitude: float
    elevation: float | None = None
    time: datetime | None = None
    extra: tuple[Element, ...] = ()
    elevation_estimated: bool = False


@dataclass(slots=True)
class TrackSegment:
    """Un segmento de un track: sus puntos, en orden.

    Attributes:
        points: Los puntos válidos.
        extra: Los demás hijos del <trkseg> (sus extensiones), tal cual.
    """

    points: list[TrackPoint] = field(default_factory=list)
    extra: tuple[Element, ...] = ()


@dataclass(slots=True)
class GpxTrack:
    """Un track del archivo (o una ruta planificada tratada como track).

    Attributes:
        name: Nombre (<name>), o None.
        description: Descripción (<desc>), o None.
        activity_type: Tipo de actividad (<type>: 'hiking', 'cycling'...), o None.
        segments: Sus segmentos (también los que hayan quedado sin puntos válidos: el
            recorrido, 'GpxDocument.path', los salta).
        extra: Los demás hijos de la cabecera del track (comentario, enlaces, número,
            extensiones...), tal cual y en su orden. El nombre, la descripción y el tipo
            NO están aquí: van en sus campos.
        from_route: True si en el archivo era una ruta planificada (<rte>).
    """

    name: str | None = None
    description: str | None = None
    activity_type: str | None = None
    segments: list[TrackSegment] = field(default_factory=list)
    extra: tuple[Element, ...] = ()
    from_route: bool = False


@dataclass(slots=True)
class Waypoint:
    """Un punto de interés (<wpt>).

    Attributes:
        latitude: Latitud (grados).
        longitude: Longitud (grados).
        elevation: Altitud (metros), o None.
        time: Hora (UTC), o None.
        name: Nombre (<name>), o None.
        description: Descripción (<desc>), o None.
        symbol: Símbolo (<sym>: 'Flag', 'Summit'...; cada programa usa los suyos), o None.
        extra: Los demás hijos (comentario, enlaces, tipo, extensiones...), tal cual.
    """

    latitude: float
    longitude: float
    elevation: float | None = None
    time: datetime | None = None
    name: str | None = None
    description: str | None = None
    symbol: str | None = None
    extra: tuple[Element, ...] = ()


@dataclass(slots=True)
class GpxDocument:
    """Un archivo GPX entero (ver el docstring del archivo).

    Attributes:
        version: Versión del formato ('1.0', '1.1'), del atributo 'version'.
        creator: Programa o dispositivo que lo creó (atributo 'creator'), o None.
        namespace: Espacio de nombres de las etiquetas GPX ("" si el archivo no lo declara).
        namespaces: Los espacios de nombres declarados, (prefijo, dirección), en su orden
            ("" = el de por defecto). Para exportar con los mismos prefijos.
        root_attributes: Los demás atributos de <gpx> (p. ej. 'xsi:schemaLocation'), con
            el nombre como lo da ElementTree ('{dirección}nombre').
        metadata: <metadata> entero (GPX 1.1), tal cual, o None.
        header: En GPX 1.0, los datos del archivo que van sueltos en <gpx> (name, desc,
            author, time, bounds...), tal cual y en su orden.
        waypoints: Los puntos de interés válidos.
        tracks: Los tracks (o, si el archivo solo tenía rutas con puntos, esas rutas).
        routes: Las rutas planificadas que NO se usan como recorrido (el archivo tiene
            track grabado), tal cual.
        extensions: Los <extensions> del documento, tal cual.
        skipped_points: Puntos del recorrido ignorados por no ser válidos.
        skipped_waypoints: Puntos de interés ignorados por no ser válidos.
    """

    version: str = "1.1"
    creator: str | None = None
    namespace: str = ""
    namespaces: tuple[tuple[str, str], ...] = ()
    root_attributes: dict[str, str] = field(default_factory=dict)
    metadata: Element | None = None
    header: tuple[Element, ...] = ()
    waypoints: list[Waypoint] = field(default_factory=list)
    tracks: list[GpxTrack] = field(default_factory=list)
    routes: tuple[Element, ...] = ()
    extensions: tuple[Element, ...] = ()
    skipped_points: int = 0
    skipped_waypoints: int = 0

    @property
    def from_route(self) -> bool:
        """True si el recorrido sale de rutas planificadas (no había track grabado)."""
        return bool(self.tracks) and all(track.from_route for track in self.tracks)

    @property
    def point_count(self) -> int:
        """Puntos del recorrido (entre todos los tracks y segmentos)."""
        return sum(len(s.points) for track in self.tracks for s in track.segments)

    def path(self) -> TrackPath:
        """El recorrido en arrays compactos: lo mismo que 'read_gpx_path' del archivo
        (mientras no se edite). Los segmentos sin puntos no cuentan."""
        builder = _PathBuilder()
        for track in self.tracks:
            for segment in track.segments:
                for point in segment.points:
                    builder.add((point.latitude, point.longitude, point.elevation, point.time))
                builder.end_segment()
        return TrackPath(
            tuple(builder.segments), self.from_route, self.skipped_points, tuple(self.waypoints)
        )


# -----------------------------------------------------------------------------
# Lectura de las piezas
# -----------------------------------------------------------------------------

# (latitud, longitud, altitud, hora) de un punto válido
_RawPoint = tuple[float, float, float | None, datetime | None]


def _local_name(tag: str) -> str:
    """Nombre de una etiqueta sin el espacio de nombres ('{http://...}trkpt' -> 'trkpt')."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(element: Element) -> str | None:
    """Texto de un elemento sin espacios en los extremos; None si queda vacío."""
    value = (element.text or "").strip()
    return value or None


def _coordinates(element: Element) -> tuple[float, float] | None:
    """(latitud, longitud) de un punto, o None si faltan o son imposibles (como hace el
    extractor: ese punto se ignora)."""
    try:
        latitude = float(element.get("lat", ""))
        longitude = float(element.get("lon", ""))
    except ValueError:
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None  # también deja fuera NaN e infinito
    return latitude, longitude


def _elevation(text: str | None) -> float | None:
    """La altitud de un <ele>, o None si no es un número finito."""
    if text is None:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _read_point(element: Element, *, keep_extra: bool) -> tuple[_RawPoint, tuple[Element, ...]] | None:
    """Lee un punto (<trkpt>, <rtept> o <wpt>): sus cuatro datos y, si se piden, los demás
    hijos tal cual. None si no es válido.

    De <ele> y <time> vale el PRIMERO (como en el extractor); uno repetido o ilegible se
    queda en 'extra' para no perderlo.
    """
    coordinates = _coordinates(element)
    if coordinates is None:
        return None
    elevation: float | None = None
    time: datetime | None = None
    seen_elevation = seen_time = False
    extra: list[Element] = []
    for child in element:
        name = _local_name(child.tag)
        if name == "ele" and not seen_elevation:
            seen_elevation = True
            elevation = _elevation(_text(child))
            if elevation is not None or _text(child) is None:
                continue  # leída (o vacía): no hace falta conservarla
        elif name == "time" and not seen_time:
            seen_time = True
            time = parse_gpx_time(_text(child))
            if time is not None or _text(child) is None:
                continue
        if keep_extra:
            extra.append(child)
    return (coordinates[0], coordinates[1], elevation, time), tuple(extra)


def _split_named(element: Element, names: tuple[str, ...]) -> tuple[dict[str, str | None], list[Element]]:
    """Separa de los hijos de 'element' los textos con esos nombres (el primero de cada
    uno) y devuelve además el resto de hijos, en su orden."""
    values: dict[str, str | None] = dict.fromkeys(names)
    seen: set[str] = set()
    rest: list[Element] = []
    for child in element:
        name = _local_name(child.tag)
        if name in values and name not in seen:
            seen.add(name)
            values[name] = _text(child)
        else:
            rest.append(child)
    return values, rest


def _read_track(element: Element, document: GpxDocument) -> GpxTrack:
    """Un <trk> ya completo: su cabecera y sus segmentos."""
    values, rest = _split_named(element, ("name", "desc", "type"))
    track = GpxTrack(values["name"], values["desc"], values["type"])
    header: list[Element] = []
    for child in rest:
        if _local_name(child.tag) != "trkseg":
            header.append(child)
            continue
        segment = TrackSegment()
        extra: list[Element] = []
        for item in child:
            if _local_name(item.tag) != "trkpt":
                extra.append(item)
                continue
            point = _read_point(item, keep_extra=True)
            if point is None:
                document.skipped_points += 1
            else:
                segment.points.append(TrackPoint(*point[0], extra=point[1]))
        segment.extra = tuple(extra)
        track.segments.append(segment)
    track.extra = tuple(header)
    return track


def _read_route(element: Element) -> tuple[GpxTrack, int]:
    """Una <rte> como track de un segmento, y cuántos de sus puntos no valían."""
    values, rest = _split_named(element, ("name", "desc", "type"))
    track = GpxTrack(values["name"], values["desc"], values["type"], from_route=True)
    segment = TrackSegment()
    header: list[Element] = []
    skipped = 0
    for child in rest:
        if _local_name(child.tag) != "rtept":
            header.append(child)
            continue
        point = _read_point(child, keep_extra=True)
        if point is None:
            skipped += 1
        else:
            segment.points.append(TrackPoint(*point[0], extra=point[1]))
    track.segments.append(segment)
    track.extra = tuple(header)
    return track, skipped


def _read_waypoint(element: Element) -> Waypoint | None:
    """Un <wpt>, o None si sus coordenadas no valen."""
    point = _read_point(element, keep_extra=True)
    if point is None:
        return None
    (latitude, longitude, elevation, time), children = point
    values: dict[str, str | None] = dict.fromkeys(("name", "desc", "sym"))
    seen: set[str] = set()
    extra: list[Element] = []
    for child in children:
        name = _local_name(child.tag)
        if name in values and name not in seen:
            seen.add(name)
            values[name] = _text(child)
        else:
            extra.append(child)
    return Waypoint(
        latitude, longitude, elevation, time,
        values["name"], values["desc"], values["sym"], tuple(extra),
    )  # fmt: skip


# -----------------------------------------------------------------------------
# Lectura de un archivo
# -----------------------------------------------------------------------------


def read_gpx_path(path: str | Path) -> TrackPath:
    """Lee solo el recorrido de un GPX (ver el docstring del archivo).

    Raises:
        FileNotFoundError: Si el archivo no existe.
        GpxError: Si no es un GPX o está dañado.
        OSError: Si no se puede leer.
    """
    track = _PathBuilder()
    route = _PathBuilder()
    waypoints: list[Waypoint] = []
    depth = 0
    try:
        for event, element in iterparse(str(path), events=("start", "end")):
            if event == "start":
                if depth == 0 and _local_name(element.tag) != "gpx":
                    raise GpxError("No es un archivo GPX (falta la etiqueta <gpx>).")
                depth += 1
                continue
            depth -= 1
            name = _local_name(element.tag)
            if name in ("trkpt", "rtept"):
                point = _read_point(element, keep_extra=False)
                (track if name == "trkpt" else route).add(point[0] if point else None)
                element.clear()  # libera la memoria del punto ya leído
            elif name in ("trkseg", "trk"):
                track.end_segment()
                element.clear()
            elif name == "rte":
                route.end_segment()
                element.clear()
            elif name == "wpt":
                waypoint = _read_waypoint(element)
                if waypoint is not None:
                    # Solo lo que se enseña: sin los demás hijos (se va a soltar el elemento)
                    waypoint.extra = ()
                    waypoints.append(waypoint)
                element.clear()
    except (ParseError, DefusedXmlException) as error:
        raise GpxError(f"El GPX está dañado o no es XML válido ({error}).") from error

    # El grabado si tiene puntos; si no, la ruta planificada (como el extractor)
    from_route = track.point_count == 0 and route.point_count > 0
    chosen = route if from_route else track
    return TrackPath(tuple(chosen.segments), from_route, chosen.skipped, tuple(waypoints))


def read_gpx_document(path: str | Path) -> GpxDocument:
    """Lee un GPX entero, para editarlo (ver el docstring del archivo).

    Raises:
        FileNotFoundError: Si el archivo no existe.
        GpxError: Si no es un GPX o está dañado.
        OSError: Si no se puede leer.
    """
    namespaces: list[tuple[str, str]] = []
    try:
        parser = iterparse(str(path), events=("start", "start-ns"))
        checked = False
        for event, item in parser:
            if event == "start-ns":
                if item not in namespaces:
                    namespaces.append(item)  # (prefijo, dirección)
            elif not checked:
                checked = True
                if _local_name(item.tag) != "gpx":
                    raise GpxError("No es un archivo GPX (falta la etiqueta <gpx>).")
        root: Element | None = parser.root
    except (ParseError, DefusedXmlException) as error:
        raise GpxError(f"El GPX está dañado o no es XML válido ({error}).") from error
    if root is None:
        raise GpxError("No es un archivo GPX (está vacío).")

    tag = root.tag if isinstance(root.tag, str) else ""
    attributes = dict(root.attrib)
    document = GpxDocument(
        version=attributes.pop("version", "1.1").strip() or "1.1",
        creator=(attributes.pop("creator", "") or "").strip() or None,
        namespace=tag[1:].split("}", 1)[0] if tag.startswith("{") else "",
        namespaces=tuple(namespaces),
        root_attributes=attributes,
    )

    header: list[Element] = []
    extensions: list[Element] = []
    routes: list[Element] = []
    for child in root:
        name = _local_name(child.tag)
        if name == "metadata" and document.metadata is None:
            document.metadata = child
        elif name == "wpt":
            waypoint = _read_waypoint(child)
            if waypoint is None:
                document.skipped_waypoints += 1
            else:
                document.waypoints.append(waypoint)
        elif name == "trk":
            document.tracks.append(_read_track(child, document))
        elif name == "rte":
            routes.append(child)
        elif name == "extensions":
            extensions.append(child)
        else:
            header.append(child)  # GPX 1.0: name, desc, author, time, bounds...
    document.header = tuple(header)
    document.extensions = tuple(extensions)

    # Sin ningún punto grabado, el recorrido son las rutas planificadas (como el
    # extractor); si no, las rutas se guardan tal cual
    if document.point_count == 0:
        converted = [_read_route(route) for route in routes]
        if any(track.segments[0].points for track, _skipped in converted):
            # Los tracks vacíos que hubiera se sueltan: el recorrido son las rutas
            document.tracks = [track for track, _skipped in converted]
            document.skipped_points = sum(skipped for _track, skipped in converted)
            routes = []
    document.routes = tuple(routes)
    return document


if __name__ == "__main__":
    # Autoprueba con archivos GPX inventados en una carpeta temporal (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m core.tracks.gpx_document
    import tempfile

    from core.metadata.track.gpx_reader import read_gpx

    TPX = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
    GPX = "http://www.topografix.com/GPX/1/1"

    GPX11 = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- un comentario: no se conserva -->
<gpx version="1.1" creator="Garmin Connect" xmlns="{GPX}" xmlns:gpxtpx="{TPX}"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{GPX} http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>Archivo de prueba</name>
    <author><name>Javier</name></author>
    <time>2024-05-01T07:00:00Z</time>
  </metadata>
  <wpt lat="43.0" lon="-3.0"><ele>95.5</ele><name>Fuente</name><cmt>agua</cmt>
       <desc>Fuente del camino</desc><sym>Drinking Water</sym><type>POI</type></wpt>
  <wpt lat="43.02" lon="-3.01"><name>Cumbre</name></wpt>
  <wpt lat="91" lon="0"><name>Imposible</name></wpt>
  <trk>
    <name>Ruta del Cares</name>
    <cmt>comentario</cmt>
    <desc>Poncebos - Caín</desc>
    <type>hiking</type>
    <extensions><color>red</color></extensions>
    <trkseg>
      <trkpt lat="43.0000" lon="-3.0000"><ele>100</ele><time>2024-05-01T08:00:00Z</time>
        <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>120</gpxtpx:hr>
        </gpxtpx:TrackPointExtension></extensions></trkpt>
      <trkpt lat="43.0010" lon="-3.0000"><ele>102</ele><time>2024-05-01T08:01:00Z</time><sat>9</sat></trkpt>
      <trkpt lat="43.0020" lon="-3.0000"><ele>alto</ele><time>ayer</time></trkpt>
      <trkpt lat="43.0030" lon="-3.0000"><time>2024-05-01T08:03:00Z</time></trkpt>
    </trkseg>
    <trkseg>
      <trkpt lat="abc" lon="0"/>
    </trkseg>
    <trkseg>
      <trkpt lat="43.0100" lon="-3.0000"><ele>104</ele><time>2024-05-01T09:00:00Z</time></trkpt>
      <trkpt lat="43.0110" lon="-3.0000"><ele>90</ele><time>2024-05-01T09:01:30.500Z</time></trkpt>
      <trkpt lat="999" lon="0"><ele>5</ele></trkpt>
      <extensions><nota>del segmento</nota></extensions>
    </trkseg>
  </trk>
  <trk><name>Segundo</name><trkseg>
      <trkpt lat="43.02" lon="-3.0"/><trkpt lat="43.03" lon="-3.0"/>
  </trkseg></trk>
  <rte><name>Plan que no se usa</name><rtept lat="1" lon="1"/></rte>
  <extensions><app>dato del documento</app></extensions>
</gpx>"""

    GPX10_ROUTE = """<?xml version="1.0"?>
<gpx version="1.0" creator="Wikiloc">
  <name>Ruta planificada</name>
  <author>Alguien</author>
  <trk><name>Vacío</name><trkseg/></trk>
  <rte>
    <name>Plan</name>
    <number>1</number>
    <rtept lat="40.0" lon="-3.0"><name>Salida</name></rtept>
    <rtept lat="x" lon="y"/>
    <rtept lat="40.0" lon="-2.99"><ele>650</ele></rtept>
  </rte>
  <rte><name>Otro plan</name><rtept lat="40.1" lon="-3.0"/></rte>
</gpx>"""

    def _same_as_summary(file: Path, track_path: TrackPath) -> None:
        """El recorrido leído aquí es el del extractor: mismos puntos, por segmentos."""
        summary = read_gpx(file, collect_points=True)
        assert track_path.point_count == summary.point_count, (file.name, track_path.point_count)
        assert len(track_path.segments) == summary.segment_count == len(summary.path_points)
        assert track_path.from_route == summary.uses_route
        for segment, flat in zip(track_path.segments, summary.path_points, strict=True):
            assert list(segment.latitudes) == list(flat[0::2])
            assert list(segment.longitudes) == list(flat[1::2])

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # --- 1. GPX 1.1: el recorrido compacto
        cares = base / "cares.gpx"
        cares.write_text(GPX11, encoding="utf-8")
        way = read_gpx_path(cares)
        # 4 + 2 + 2 puntos: el segmento sin puntos válidos no cuenta; dos puntos ignorados
        assert [len(segment) for segment in way.segments] == [4, 2, 2] and way.point_count == 8
        assert way.skipped_points == 2 and not way.from_route
        assert way.has_elevation and way.has_time
        first = way.segments[0]
        assert list(first.latitudes) == [43.0, 43.001, 43.002, 43.003]
        assert first.elevation(0) == 100.0 and first.elevation(2) is None  # «alto» no vale
        assert first.elevation(3) is None and first.time(2) is None        # «ayer» tampoco
        assert first.time(0) == datetime(2024, 5, 1, 8, 0, tzinfo=UTC)
        assert way.segments[1].time(1) == datetime(2024, 5, 1, 9, 1, 30, 500000, tzinfo=UTC)
        assert not math.isnan(way.segments[1].elevations[0]) and math.isnan(way.segments[2].times[0])
        # El índice de un punto, contando los segmentos seguidos
        assert way.locate(0) == (0, 0) and way.locate(3) == (0, 3) and way.locate(4) == (1, 0)
        assert way.locate(7) == (2, 1)
        # Los puntos de interés válidos, con lo que se enseña de ellos
        assert [(w.name, w.latitude, w.longitude) for w in way.waypoints] == [
            ("Fuente", 43.0, -3.0), ("Cumbre", 43.02, -3.01)]  # fmt: skip
        assert (way.waypoints[0].description, way.waypoints[0].symbol) == (
            "Fuente del camino", "Drinking Water")  # fmt: skip
        assert way.waypoints[0].elevation == 95.5 and way.waypoints[0].extra == ()
        for bad_index in (8, -1):
            try:
                way.locate(bad_index)
                raise AssertionError("debía fallar")
            except IndexError:
                pass
        _same_as_summary(cares, way)

        # --- 2. GPX 1.1: el documento entero
        doc = read_gpx_document(cares)
        assert (doc.version, doc.creator, doc.namespace) == ("1.1", "Garmin Connect", GPX)
        assert ("", GPX) in doc.namespaces and ("gpxtpx", TPX) in doc.namespaces
        assert list(doc.root_attributes) == ["{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"]
        assert doc.metadata is not None and _local_name(doc.metadata.tag) == "metadata"
        assert [_local_name(child.tag) for child in doc.metadata] == ["name", "author", "time"]
        assert doc.header == () and len(doc.extensions) == 1
        assert _text(doc.extensions[0][0]) == "dato del documento"
        # La ruta no se usa (hay track grabado): se guarda tal cual
        assert len(doc.routes) == 1 and not doc.from_route
        assert (doc.skipped_points, doc.skipped_waypoints) == (2, 1)

        # Puntos de interés: lo editable, en sus campos; lo demás, tal cual
        assert [w.name for w in doc.waypoints] == ["Fuente", "Cumbre"]
        fountain = doc.waypoints[0]
        assert (fountain.latitude, fountain.longitude, fountain.elevation) == (43.0, -3.0, 95.5)
        assert (fountain.description, fountain.symbol) == ("Fuente del camino", "Drinking Water")
        assert [_local_name(e.tag) for e in fountain.extra] == ["cmt", "type"]
        assert doc.waypoints[1].symbol is None and doc.waypoints[1].extra == ()

        # Tracks: cabecera, segmentos (también el que se quedó sin puntos) y puntos
        assert [t.name for t in doc.tracks] == ["Ruta del Cares", "Segundo"]
        cares_track = doc.tracks[0]
        assert (cares_track.description, cares_track.activity_type) == ("Poncebos - Caín", "hiking")
        assert [_local_name(e.tag) for e in cares_track.extra] == ["cmt", "extensions"]
        assert [len(s.points) for s in cares_track.segments] == [4, 0, 2]
        assert [_local_name(e.tag) for e in cares_track.segments[2].extra] == ["extensions"]
        point = cares_track.segments[0].points[0]
        assert (point.latitude, point.longitude, point.elevation) == (43.0, -3.0, 100.0)
        assert point.time == datetime(2024, 5, 1, 8, 0, tzinfo=UTC) and not point.elevation_estimated
        # Las extensiones de cada punto se conservan, con su espacio de nombres
        assert len(point.extra) == 1 and _local_name(point.extra[0].tag) == "extensions"
        heart = point.extra[0][0][0]
        assert heart.tag == f"{{{TPX}}}hr" and heart.text == "120"
        assert [_local_name(e.tag) for e in cares_track.segments[0].points[1].extra] == ["sat"]
        # Una altitud o una hora ilegibles no se pierden: se quedan con lo demás
        odd = cares_track.segments[0].points[2]
        assert odd.elevation is None and odd.time is None
        assert [(_local_name(e.tag), e.text) for e in odd.extra] == [("ele", "alto"), ("time", "ayer")]
        assert cares_track.segments[0].points[3].extra == ()

        # El recorrido del documento es el mismo que el de la lectura rápida
        from_doc = doc.path()
        assert doc.point_count == 8 and from_doc.skipped_points == 2
        assert [w.name for w in from_doc.waypoints] == ["Fuente", "Cumbre"]
        assert [len(segment) for segment in from_doc.segments] == [4, 2, 2]
        for a, b in zip(from_doc.segments, way.segments, strict=True):
            assert list(a.latitudes) == list(b.latitudes) and list(a.longitudes) == list(b.longitudes)
            assert [a.elevation(i) for i in range(len(a))] == [b.elevation(i) for i in range(len(b))]
            assert [a.time(i) for i in range(len(a))] == [b.time(i) for i in range(len(b))]

        # --- 3. GPX 1.0 solo con rutas: son el recorrido, cada una un track de un segmento
        plan = base / "plan.gpx"
        plan.write_text(GPX10_ROUTE, encoding="utf-8")
        way = read_gpx_path(plan)
        assert way.from_route and [len(s) for s in way.segments] == [2, 1] and way.skipped_points == 1
        assert way.has_elevation and not way.has_time
        _same_as_summary(plan, way)
        doc = read_gpx_document(plan)
        assert (doc.version, doc.creator, doc.namespace, doc.namespaces) == ("1.0", "Wikiloc", "", ())
        assert doc.metadata is None and [_local_name(e.tag) for e in doc.header] == ["name", "author"]
        assert doc.from_route and doc.routes == () and doc.skipped_points == 1
        assert [(t.name, t.from_route, len(t.segments)) for t in doc.tracks] == [
            ("Plan", True, 1), ("Otro plan", True, 1)]  # fmt: skip
        assert [_local_name(e.tag) for e in doc.tracks[0].extra] == ["number"]
        start = doc.tracks[0].segments[0].points[0]
        assert [(_local_name(e.tag), e.text) for e in start.extra] == [("name", "Salida")]
        assert doc.tracks[0].segments[0].points[1].elevation == 650.0
        assert [len(s) for s in doc.path().segments] == [2, 1] and doc.path().from_route

        # --- 4. Vacío o sin puntos válidos: un recorrido sin segmentos
        empty = base / "vacio.gpx"
        empty.write_text('<gpx version="1.1" creator="x"><trk><trkseg/></trk></gpx>', encoding="utf-8")
        way = read_gpx_path(empty)
        assert way.segments == () and way.point_count == 0 and not way.has_elevation
        assert way.waypoints == ()
        doc = read_gpx_document(empty)
        assert doc.point_count == 0 and len(doc.tracks) == 1 and not doc.from_route
        assert doc.path().segments == ()
        _same_as_summary(empty, way)

        # --- 5. Errores: no es GPX, XML roto, XML peligroso y archivo inexistente
        (base / "otro.gpx").write_text("<kml></kml>", encoding="utf-8")
        (base / "roto.gpx").write_text("<gpx><trk><trkseg>", encoding="utf-8")
        (base / "bomba.gpx").write_text(
            '<!DOCTYPE gpx [<!ENTITY a "aaaa">]><gpx><name>&a;</name></gpx>', encoding="utf-8"
        )
        for reader in (read_gpx_path, read_gpx_document):
            for bad in ("otro.gpx", "roto.gpx", "bomba.gpx"):
                try:
                    reader(base / bad)
                except GpxError:
                    pass
                else:
                    raise AssertionError(f"{bad} debería rechazarse con {reader.__name__}")
            try:
                reader(base / "no_existe.gpx")
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("debería lanzar FileNotFoundError")

    print("Autoprueba finalizada correctamente.")
