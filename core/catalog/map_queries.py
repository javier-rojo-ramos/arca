"""Consultas del mapa: qué fotos y qué tracks se ven en él.

Este módulo NO depende de Qt. Sus funciones reciben la conexión como primer parámetro y no
hacen commit: se envían tal cual a 'CatalogDatabaseManager.execute_async'. Diseño en
docs/MAPA.md (§5.1).

El mapa muestra LO MISMO que la cuadrícula: el mismo origen (lo elegido a la izquierda,
un 'GridSource') y el mismo filtro de la barra de filtros. Por eso la condición sale de
'media_queries.source_condition', el único sitio que traduce un origen a SQL, y nunca
pueden discrepar. Lo que cambia es CÓMO se ve cada elemento:

    - lo que tiene coordenadas (fotos y vídeos, sobre todo) es un PUNTO ('MapPoint');
    - un track es una LÍNEA: su contorno ('track_details.overview', ya simplificado por el
      extractor), que aquí se decodifica (en el hilo de la base de datos, no en el de la
      interfaz) ('MapTrackOutline');
    - las fotos y los vídeos sin coordenadas solo se cuentan ('MapItems.unlocated'), para
      que la interfaz pueda decir cuántos no salen en el mapa.

Un track NO es un punto aunque tenga coordenadas: las de 'media_items' son su punto de
salida, y en el mapa se dibuja entero.

Los tipos de aquí son de 'core/' (sin Qt): el controlador del mapa los convierte en los
de la interfaz ('ui_helpers/map/map_types.py': 'MapMarker', 'MapTrack').

1.0.0 Primera versión (docs/MAPA.md, paso 2.2).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.map_queries
"""

__version__ = "1.0.0"
__all__ = ["LOCATABLE_MEDIA_TYPES", "MapItems", "MapPoint", "MapTrackOutline", "fetch_map_items"]

# Librerías estándar
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.grid_source import ALL_ITEMS, GridSource
from core.catalog.media_queries import source_condition
from core.catalog.media_types import MediaType
from core.catalog.smart_rules import RuleSet
from core.tracks.simplify import decode_overview

# Tipos que pueden tener coordenadas propias (las que se escriben en el archivo): los que
# cuentan como «sin ubicación» si no las tienen. Una canción o un libro no se cuentan
LOCATABLE_MEDIA_TYPES: tuple[str, ...] = (MediaType.PHOTO.value, MediaType.VIDEO.value)

_TRACK = MediaType.TRACK.value

# Un segmento: puntos (latitud, longitud)
Segment = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class MapPoint:
    """Un elemento con coordenadas (una foto o un vídeo, casi siempre).

    Attributes:
        media_id: 'media_items.id'.
        latitude: Latitud, en grados.
        longitude: Longitud, en grados.
        media_type: Valor de 'MediaType'.
        has_thumbnail: True si su miniatura está lista ('thumbnail_status' = 1).
        direction: Hacia dónde apunta la cámara (0-360), o None.
    """

    media_id: int
    latitude: float
    longitude: float
    media_type: str
    has_thumbnail: bool
    direction: float | None


@dataclass(frozen=True, slots=True)
class MapTrackOutline:
    """Un track, con su contorno.

    Attributes:
        track_id: 'media_items.id' del GPX.
        name: Su título (el del GPX o, si no tiene, el nombre del archivo).
        segments: Su contorno, por segmentos. Vacío si aún no se ha leído el GPX (o no
            tiene puntos, o el contorno guardado está dañado).
        bounds: Su caja (sur, oeste, norte, este), de 'track_details'; None si no se sabe.
    """

    track_id: int
    name: str
    segments: tuple[Segment, ...]
    bounds: tuple[float, float, float, float] | None


@dataclass(frozen=True, slots=True)
class MapItems:
    """Lo que hay que pintar en el mapa para un origen y un filtro.

    Attributes:
        points: Los elementos con coordenadas (sin los tracks), por id.
        tracks: Los tracks, por id.
        unlocated: Fotos y vídeos del origen que no tienen coordenadas (no salen).
    """

    points: tuple[MapPoint, ...]
    tracks: tuple[MapTrackOutline, ...]
    unlocated: int


def fetch_map_items(
    conn: sqlite3.Connection,
    source: GridSource = ALL_ITEMS,
    filters: Sequence[RuleSet] = (),
) -> MapItems:
    """Las fotos con coordenadas y los tracks de un origen, con el filtro aplicado.

    Incluye lo que no está disponible (ausente o en un disco desconectado), como la
    cuadrícula: sus coordenadas están en el catálogo.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        source: Lo elegido a la izquierda (por defecto, todo el catálogo).
        filters: El filtro de la barra de filtros ('GridFilter.rule_sets()').

    Raises:
        ValueError: Si el origen no se conoce o una regla del filtro no es válida.
    """
    where_sql, where_params = source_condition(source, filters)

    # Coordenadas imposibles no hay (las impiden los CHECK); 0, 0 tampoco debería haber
    # (la lectura las toma por «sin GPS»), pero el mapa las rechazaría: fuera
    points = tuple(
        MapPoint(int(media_id), float(lat), float(lon), media_type, status == 1, direction)
        for media_id, lat, lon, media_type, status, direction in conn.execute(
            f"""SELECT m.id, m.latitude, m.longitude, m.media_type, m.thumbnail_status,
                       m.gps_direction
                  FROM media_items AS m
                 WHERE ({where_sql})
                   AND m.media_type <> ?
                   AND m.latitude IS NOT NULL AND m.longitude IS NOT NULL
                   AND NOT (m.latitude = 0 AND m.longitude = 0)
              ORDER BY m.id""",
            (*where_params, _TRACK),
        )
    )

    tracks = tuple(
        MapTrackOutline(
            int(track_id),
            name,
            _segments(int(track_id), overview),
            (south, west, north, east) if None not in (south, west, north, east) else None,
        )
        for track_id, name, overview, south, west, north, east in conn.execute(
            f"""SELECT m.id, m.title, d.overview,
                       d.min_latitude, d.min_longitude, d.max_latitude, d.max_longitude
                  FROM media_items AS m
             LEFT JOIN track_details AS d ON d.media_id = m.id
                 WHERE ({where_sql}) AND m.media_type = ?
              ORDER BY m.id""",
            (*where_params, _TRACK),
        )
    )

    placeholders = ", ".join("?" * len(LOCATABLE_MEDIA_TYPES))
    unlocated = conn.execute(
        f"""SELECT COUNT(*) FROM media_items AS m
             WHERE ({where_sql})
               AND m.media_type IN ({placeholders})
               AND (m.latitude IS NULL OR m.longitude IS NULL
                    OR (m.latitude = 0 AND m.longitude = 0))""",
        (*where_params, *LOCATABLE_MEDIA_TYPES),
    ).fetchone()[0]

    return MapItems(points, tracks, int(unlocated))


def _segments(track_id: int, overview: str | None) -> tuple[Segment, ...]:
    """El contorno guardado, decodificado. Si está dañado, ninguno (y se anota)."""
    try:
        return decode_overview(overview)
    except ValueError:
        logger.warning(f"El contorno guardado del track {track_id} está dañado: no se dibuja.")
        return ()


if __name__ == "__main__":
    # Autoprueba con un catálogo en memoria (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.map_queries
    import time

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_source import collection_source, folder_source, library_source
    from core.catalog.media_queries import count_grid_items, fetch_grid_rows
    from core.catalog.smart_rules import Rule
    from core.tracks.simplify import encode_overview

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(id, name, absolute_path) VALUES (1, 'Fotos', '/f')")

    def add(media_id: int, path: str, media_type: str, lat: float | None, lon: float | None, **extra: object) -> None:
        columns = {
            "id": media_id, "storage_location_id": 1, "relative_path": path,
            "file_name": path.rsplit("/", 1)[-1], "media_type": media_type, "mime_type": "x/y",
            "file_size": 1, "file_mtime_ns": 0, "title": path.rsplit("/", 1)[-1].split(".")[0],
            "latitude": lat, "longitude": lon, "library": "tracks" if media_type == _TRACK else "image",
            **extra,
        }  # fmt: skip
        db.execute(
            f"INSERT INTO media_items({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            tuple(columns.values()),
        )

    # Fotos y vídeos con y sin GPS, una canción, un ausente y tres tracks
    add(1, "Viaje/a.jpg", "photo", 42.6, 0.03, rating=4, thumbnail_status=1, gps_direction=90.0)
    add(2, "Viaje/b.jpg", "photo", 42.7, 0.10, rating=1)
    add(3, "Viaje/c.jpg", "photo", None, None, rating=5)
    add(4, "Viaje/d.mov", "video", 42.65, 0.05, rating=3, is_missing=1)
    add(5, "Casa/e.jpg", "photo", 40.4, -3.7, rating=2)
    add(6, "Casa/f.jpg", "photo", 0.0, 0.0)  # 0, 0: «sin GPS»
    add(7, "Musica/g.mp3", "audio", None, None)
    add(10, "Viaje/ruta.gpx", _TRACK, 42.6, 0.0)
    add(11, "Viaje/sin_leer.gpx", _TRACK, None, None)
    add(12, "Viaje/danada.gpx", _TRACK, 42.6, 0.0)
    outline = encode_overview([[42.6, 0.0, 42.65, 0.05, 42.7, 0.1], [42.8, 0.3, 42.81, 0.31]])
    db.execute(
        "INSERT INTO track_details(media_id, overview, min_latitude, max_latitude, "
        "min_longitude, max_longitude) VALUES (10, ?, 42.6, 42.81, 0.0, 0.31)",
        (outline,),
    )
    db.execute("INSERT INTO track_details(media_id, overview) VALUES (12, 'esto no es un contorno')")

    # 1. Todo el catálogo: los puntos (sin los tracks ni el 0, 0), los tres tracks y cuántas
    #    fotos y vídeos no tienen coordenadas (la foto 3 y la del 0, 0; la canción no cuenta)
    items = fetch_map_items(db)
    assert [p.media_id for p in items.points] == [1, 2, 4, 5], items.points
    first = items.points[0]
    assert (first.latitude, first.longitude, first.media_type) == (42.6, 0.03, "photo")
    assert first.has_thumbnail and first.direction == 90.0
    assert not items.points[1].has_thumbnail and items.points[1].direction is None
    assert items.points[2].media_type == "video"  # ausente, pero con coordenadas: sale
    assert [t.track_id for t in items.tracks] == [10, 11, 12]
    route, unread, broken = items.tracks
    assert route.name == "ruta" and route.bounds == (42.6, 0.0, 42.81, 0.31)
    assert route.segments == (((42.6, 0.0), (42.65, 0.05), (42.7, 0.1)), ((42.8, 0.3), (42.81, 0.31)))
    assert unread.segments == () and unread.bounds is None  # aún sin leer: sin contorno
    assert broken.segments == ()  # contorno dañado: no se dibuja (y se anota)
    assert items.unlocated == 2

    # 2. Mismo origen que la cuadrícula: una carpeta, una biblioteca, una colección
    viaje = folder_source(1, "Viaje")
    assert [p.media_id for p in fetch_map_items(db, viaje).points] == [1, 2, 4]
    assert [t.track_id for t in fetch_map_items(db, viaje).tracks] == [10, 11, 12]
    assert fetch_map_items(db, viaje).unlocated == 1
    image = fetch_map_items(db, library_source("image"))
    assert image.tracks == () and [p.media_id for p in image.points] == [1, 2, 4, 5]
    db.execute("INSERT INTO collections(id, kind, name) VALUES (1, 'static', 'Ruta y fotos')")
    db.executemany(
        "INSERT INTO collection_items(collection_id, media_id) VALUES (1, ?)", ((1,), (3,), (10,))
    )
    trip = fetch_map_items(db, collection_source(1))
    assert ([p.media_id for p in trip.points], [t.track_id for t in trip.tracks], trip.unlocated) == (
        [1], [10], 1,
    )  # fmt: skip

    # 3. Con el filtro de la barra de filtros: lo mismo que la cuadrícula filtrada
    rated = (RuleSet(rules=(Rule("rating", "gte", 3),)),)
    filtered = fetch_map_items(db, ALL_ITEMS, rated)
    assert [p.media_id for p in filtered.points] == [1, 4] and filtered.tracks == ()
    assert filtered.unlocated == 1  # la foto 3 (5 estrellas, sin GPS)
    grid_ids = {row["id"] for row in fetch_grid_rows(db, source=ALL_ITEMS, filters=rated)}
    assert {p.media_id for p in filtered.points} | {3} == grid_ids
    # Y sin filtro, todo lo de la cuadrícula está en el mapa o contado aparte
    every = count_grid_items(db, [ALL_ITEMS])[ALL_ITEMS]
    assert len(items.points) + len(items.tracks) + items.unlocated + 1 == every  # +1: la canción

    # 4. Un origen o una regla que no valen: ValueError (como la cuadrícula)
    for bad in ((GridSource(kind="nope"), ()), (ALL_ITEMS, (RuleSet(rules=(Rule("no_existe", "eq", 1),)),))):
        try:
            fetch_map_items(db, *bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debería rechazarse: {bad}")

    # 5. Rendimiento: 20 000 fotos con coordenadas
    db.executemany(
        "INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type, "
        "mime_type, file_size, file_mtime_ns, title, latitude, longitude, library) "
        "VALUES (1, ?, ?, 'photo', 'image/jpeg', 1, 0, ?, ?, ?, 'image')",
        (
            (f"Masivo/{i}.jpg", f"{i}.jpg", str(i), 36 + (i % 700) / 100, -8 + (i % 1100) / 100)
            for i in range(20_000)
        ),
    )
    started = time.perf_counter()
    many = fetch_map_items(db)
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"{len(many.points)} puntos y {len(many.tracks)} tracks en {elapsed_ms:.0f} ms")
    assert len(many.points) == 20_004

    db.close()
    print("Autoprueba finalizada correctamente.")
