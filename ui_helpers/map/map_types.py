"""Datos que entran y salen del mapa: marcadores, tracks, encuadres y lo que hay bajo el ratón.

Este módulo NO depende de Qt: son dataclasses inmutables y enumeraciones. Diseño completo
en docs/MAPA.md (§2).

El componente de mapa ('MapView') no recibe un modelo de Qt ni sabe nada del catálogo:
recibe estos datos, ya preparados, y avisa con ellos. Así los módulos (Catálogo, Imagen,
Tracks) solo conocen esta API y la tecnología del mapa se puede cambiar sin tocarlos.
TODO va por 'media_items.id': nada de filas, rutas ni objetos de la tecnología.

    MapMarker     una foto o un vídeo con coordenadas
    MapTrack      el recorrido de un GPX (su contorno simplificado o su geometría completa)
    MapBounds     un rectángulo geográfico (para encuadrar); 'bounds_of' lo calcula
    MapViewport   lo que se ve: centro, zoom y rectángulo
    MapHit        qué hay en un punto del mapa (para el menú contextual)
    MapMode       qué hace el ratón: hoy solo BROWSE (ver, seleccionar, soltar y mover)
    SelectionMode cómo cambia la selección un clic

Los tipos de la EDICIÓN de tracks (intenciones y parches) se añadirán con la fase 7 de
docs/MAPA.md, cuando se diseñe su detalle.

1.0.0 Primera versión (docs/MAPA.md, paso 1.2).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.map.map_types
"""

__version__ = "1.1.0"
__all__ = [
    "HitKind",
    "MapBounds",
    "MapHit",
    "MapMarker",
    "MapMode",
    "MapTrack",
    "MapViewport",
    "MapWaypoint",
    "SelectionMode",
    "bounds_of",
    "is_valid_position",
]

# Librerías estándar
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

# Un punto del mapa: (latitud, longitud), en grados
Position = tuple[float, float]


def is_valid_position(latitude: object, longitude: object) -> bool:
    """True si son unas coordenadas que se pueden pintar y guardar.

    Números finitos dentro de sus límites, y no 0, 0: el catálogo lo toma por «sin GPS»
    (lo escriben algunas cámaras sin cobertura; ver docs/DECISIONES.md, 11/11/2026).
    """
    for value in (latitude, longitude):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value):
            return False
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return False
    return not (latitude == 0 and longitude == 0)


@dataclass(frozen=True, slots=True)
class MapWaypoint:
    """Un punto de interés de un track (un <wpt> de su GPX): solo para verlo.

    Attributes:
        latitude: Latitud, en grados.
        longitude: Longitud, en grados.
        name: Nombre (puede estar vacío).
        description: Descripción (puede estar vacía).
    """

    latitude: float
    longitude: float
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not is_valid_position(self.latitude, self.longitude):
            raise ValueError(
                f"Coordenadas no válidas en un punto de interés: "
                f"{self.latitude!r}, {self.longitude!r}"
            )


@dataclass(frozen=True, slots=True)
class MapMarker:
    """Una foto o un vídeo con coordenadas.

    Attributes:
        media_id: 'media_items.id'.
        latitude: Latitud, en grados.
        longitude: Longitud, en grados.
        media_type: Valor de 'MediaType' ('photo', 'video'...): el dibujo sin miniatura.
        has_thumbnail: True si tiene miniatura en la caché (el mapa la pide por su id).
        direction: Hacia dónde apunta la cámara, en grados (0-360), o None.
    """

    media_id: int
    latitude: float
    longitude: float
    media_type: str = "photo"
    has_thumbnail: bool = True
    direction: float | None = None

    def __post_init__(self) -> None:
        if not is_valid_position(self.latitude, self.longitude):
            raise ValueError(
                f"Coordenadas no válidas en el elemento {self.media_id}: "
                f"{self.latitude!r}, {self.longitude!r}"
            )


@dataclass(frozen=True, slots=True)
class MapTrack:
    """El recorrido de un track.

    Attributes:
        track_id: 'media_items.id' del GPX (negativo: un track nuevo, aún sin archivo).
        name: Nombre para el usuario (texto emergente).
        segments: Sus segmentos; cada uno, una tupla de (latitud, longitud). Entre dos
            segmentos no se dibuja línea (pausa del GPS).
        detailed: False = contorno simplificado (para ver muchos a la vez); True = la
            geometría completa (la del track activo).
    """

    track_id: int
    name: str
    segments: tuple[tuple[Position, ...], ...]
    detailed: bool = False

    @property
    def point_count(self) -> int:
        """Puntos entre todos los segmentos."""
        return sum(len(segment) for segment in self.segments)

    def bounds(self) -> "MapBounds | None":
        """El rectángulo que lo contiene, o None si no tiene puntos."""
        return bounds_of(point for segment in self.segments for point in segment)


@dataclass(frozen=True, slots=True)
class MapBounds:
    """Un rectángulo geográfico, en grados ('south' <= 'north' y 'west' <= 'east').

    No se contemplan los rectángulos que cruzan el antimeridiano (docs/MAPA.md, §9).
    """

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        if not (self.south <= self.north and self.west <= self.east):
            raise ValueError(f"Rectángulo al revés: {self!r}")

    @property
    def center(self) -> Position:
        """Su punto central (latitud, longitud)."""
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    def contains(self, latitude: float, longitude: float) -> bool:
        """True si el punto está dentro (los bordes cuentan)."""
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east

    def union(self, other: "MapBounds") -> "MapBounds":
        """El menor rectángulo que contiene a los dos."""
        return MapBounds(
            min(self.south, other.south),
            min(self.west, other.west),
            max(self.north, other.north),
            max(self.east, other.east),
        )


def bounds_of(points: Iterable[Position]) -> MapBounds | None:
    """El menor rectángulo que contiene unos puntos (latitud, longitud); None si no hay."""
    south = west = math.inf
    north = east = -math.inf
    for latitude, longitude in points:
        south, north = min(south, latitude), max(north, latitude)
        west, east = min(west, longitude), max(east, longitude)
    if south == math.inf:
        return None
    return MapBounds(south, west, north, east)


@dataclass(frozen=True, slots=True)
class MapViewport:
    """Lo que se ve en el mapa.

    Attributes:
        latitude: Latitud del centro.
        longitude: Longitud del centro.
        zoom: Nivel de zoom (puede tener decimales mientras se anima).
        bounds: Rectángulo visible.
    """

    latitude: float
    longitude: float
    zoom: float
    bounds: MapBounds


class SelectionMode(Enum):
    """Cómo cambia la selección un clic en el mapa."""

    REPLACE = "replace"  # clic: solo eso queda seleccionado (lista vacía = nada)
    TOGGLE = "toggle"  # Ctrl + clic: se añade o se quita


class MapMode(Enum):
    """Qué hace el ratón en el mapa. Los modos de edición de tracks llegarán con la fase 7."""

    BROWSE = "browse"  # ver, seleccionar, soltar tarjetas y mover marcadores


class HitKind(Enum):
    """Qué hay bajo el ratón."""

    EMPTY = "empty"  # solo mapa
    MARKER = "marker"  # una foto
    CLUSTER = "cluster"  # un grupo de fotos
    TRACK = "track"  # la línea de un track


@dataclass(frozen=True, slots=True)
class MapHit:
    """Qué hay en un punto del mapa (lo que acompaña al menú contextual).

    Attributes:
        kind: Qué es.
        latitude: Latitud del punto pulsado.
        longitude: Longitud del punto pulsado.
        media_ids: MARKER: su id; CLUSTER: los de sus fotos. Vacío en lo demás.
        track_id: TRACK: su id.
        point_index: TRACK: índice (entre todos sus segmentos) del punto más cercano.
    """

    kind: HitKind
    latitude: float
    longitude: float
    media_ids: tuple[int, ...] = ()
    track_id: int | None = None
    point_index: int | None = None


if __name__ == "__main__":
    # Autoprueba (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.map.map_types

    # 1. Coordenadas válidas: límites incluidos; fuera, no finitas, textos y 0, 0, no
    for latitude, longitude in ((42.65, 0.03), (-90, 180), (90, -180), (0, 10), (10, 0), (-33.9, 151)):
        assert is_valid_position(latitude, longitude), (latitude, longitude)
    for latitude, longitude in (
        (0, 0), (0.0, -0.0), (90.1, 0), (10, 180.5), (math.nan, 1), (1, math.inf),
        ("42", 1), (None, None), (True, 1),
    ):  # fmt: skip
        assert not is_valid_position(latitude, longitude), (latitude, longitude)

    # 2. Marcadores: inmutables, comparables y con las coordenadas comprobadas al crearlos
    marker = MapMarker(7, 42.65, 0.03)
    assert marker == MapMarker(7, 42.65, 0.03, "photo", True, None)
    assert marker != MapMarker(7, 42.65, 0.03, media_type="video")
    assert len({marker, MapMarker(7, 42.65, 0.03)}) == 1
    for latitude, longitude in ((0, 0), (95, 0), (math.nan, 0)):
        try:
            MapMarker(1, latitude, longitude)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debería rechazarse: {latitude}, {longitude}")

    # 3. Rectángulos
    assert bounds_of([]) is None
    assert bounds_of([(42.0, -1.0)]) == MapBounds(42.0, -1.0, 42.0, -1.0)
    box = bounds_of([(42.0, -1.0), (43.5, 0.5), (41.0, 0.0)])
    assert box == MapBounds(south=41.0, west=-1.0, north=43.5, east=0.5)
    assert box.center == (42.25, -0.25)
    assert box.contains(41.0, -1.0) and box.contains(42.0, 0.0) and not box.contains(44.0, 0.0)
    assert box.union(MapBounds(40.0, 0.0, 42.0, 2.0)) == MapBounds(40.0, -1.0, 43.5, 2.0)
    try:
        MapBounds(43.0, 0.0, 42.0, 1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("un rectángulo al revés debe rechazarse")

    # 4. Tracks: puntos y rectángulo entre todos los segmentos
    track = MapTrack(12, "Ordesa", (((42.6, 0.0), (42.7, 0.1)), ((42.5, 0.2),)), detailed=True)
    assert track.point_count == 3
    assert track.bounds() == MapBounds(42.5, 0.0, 42.7, 0.2)
    assert MapTrack(-1, "Nuevo", ()).bounds() is None and MapTrack(-1, "Nuevo", ()).point_count == 0

    # 5. Lo demás: valores estables (se guardan o viajan a la página)
    assert {mode.value for mode in SelectionMode} == {"replace", "toggle"}
    assert MapMode("browse") is MapMode.BROWSE
    hit = MapHit(HitKind.CLUSTER, 42.0, 0.0, media_ids=(1, 2, 3))
    assert hit.track_id is None and hit.media_ids == (1, 2, 3)
    view = MapViewport(42.0, 0.0, 12.0, box)
    assert view.bounds is box

    print("Autoprueba finalizada correctamente.")
