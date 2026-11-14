"""Datos de los tracks seleccionados, para el inspector: distancia, desnivel, duración...

Este módulo NO depende de Qt. Como todas las funciones que tocan la base de datos, recibe
la conexión como primer parámetro y no hace 'commit' (solo lee).

Los datos de cada track los calcula el extractor ('core/metadata/track/extractor.py') al
catalogar el GPX y están en 'track_details' (y la duración, en 'media_items.duration'):
aquí solo se LEEN y, si hay varios tracks, se juntan:

    - Se SUMAN: distancia, desnivel de subida y de bajada, duración, puntos, segmentos y
      puntos de interés (lo que se ha andado entre todos).
    - Altitud: la mínima y la máxima de todos.
    - Actividad y programa: el valor si es el MISMO en todos los que lo tienen; si hay
      varios distintos, 'MIXED'.
    - 'with_duration' y 'with_elevation' dicen cuántos tienen ese dato (una ruta
      planificada no tiene horas; un GPX puede no tener altitud): así se sabe que una suma
      no los incluye a todos.

Solo cuentan los elementos de tipo track con sus datos ya leídos (una fila en
'track_details'); los demás 'id' se ignoran.

Uso (el inspector lo lanza con 'execute_async'):
    stats = fetch_track_stats(conn, [12, 15])
    stats.count, stats.distance_m, stats.elevation_gain_m, stats.duration_s
    stats.average_speed_kmh        # con la distancia de los que tienen duración

1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.4).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.track_stats
"""

__version__ = "1.0.0"
__all__ = ["MIXED", "TrackStats", "fetch_track_stats"]

# Librerías estándar
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

# Módulos del proyecto
from core.catalog.media_types import MediaType

# Valor de un texto cuando los tracks resumidos tienen varios distintos
MIXED = "\x00varios"

# Cuántos 'id' van en cada consulta (SQLite limita los parámetros de una sentencia)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class TrackStats:
    """Los datos de uno o varios tracks, juntos (ver el docstring del archivo).

    Attributes:
        count: Tracks con datos.
        distance_m: Distancia total, en metros (None si ninguno la tiene).
        elevation_gain_m: Desnivel de subida, sumado (None si ninguno tiene altitud).
        elevation_loss_m: Desnivel de bajada, sumado, en positivo.
        elevation_min_m: Altitud mínima de todos.
        elevation_max_m: Altitud máxima de todos.
        duration_s: Duración sumada, en segundos (None si ninguno tiene horas).
        timed_distance_m: Distancia de los que tienen duración (para la velocidad media).
        point_count: Puntos del recorrido, sumados.
        segment_count: Segmentos, sumados.
        waypoint_count: Puntos de interés, sumados.
        planned_routes: Cuántos son rutas planificadas (sin track grabado).
        with_duration: Cuántos tienen duración.
        with_elevation: Cuántos tienen altitud.
        activity_type: Tipo de actividad común, 'MIXED' si hay varios, None si ninguno.
        creator_app: Programa con el que se crearon: igual que 'activity_type'.
    """

    count: int = 0
    distance_m: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    elevation_min_m: float | None = None
    elevation_max_m: float | None = None
    duration_s: float | None = None
    timed_distance_m: float | None = None
    point_count: int = 0
    segment_count: int = 0
    waypoint_count: int = 0
    planned_routes: int = 0
    with_duration: int = 0
    with_elevation: int = 0
    activity_type: str | None = None
    creator_app: str | None = None

    @property
    def average_speed_kmh(self) -> float | None:
        """Velocidad media, en km/h: la distancia de los tracks con duración entre su
        duración (contando las paradas). None si no se puede calcular."""
        if not self.duration_s or self.duration_s <= 0 or self.timed_distance_m is None:
            return None
        return self.timed_distance_m / self.duration_s * 3.6


def _add(total: float | None, value: float | None) -> float | None:
    """Suma que ignora lo que falta (None + None = None)."""
    if value is None:
        return total
    return value if total is None else total + value


def _common(current: str | None, value: str | None) -> str | None:
    """Junta un texto con los vistos hasta ahora: el mismo, o 'MIXED' si ya hay dos."""
    if not value:
        return current
    if current is None or current == value:
        return value
    return MIXED


def fetch_track_stats(conn: sqlite3.Connection, media_ids: Sequence[int]) -> TrackStats:
    """Los datos, juntos, de los tracks que haya entre esos 'id' (ver el docstring del
    archivo). Sin ninguno, un 'TrackStats' vacío ('count' = 0)."""
    ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))  # sin repetidos
    count = planned = with_duration = with_elevation = 0
    points = segments = waypoints = 0
    distance = gain = loss = duration = timed_distance = None
    lowest = highest = None
    activity = creator = None
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT d.distance_m, d.elevation_gain_m, d.elevation_loss_m,
                       d.elevation_min_m, d.elevation_max_m, m.duration,
                       d.point_count, d.segment_count, d.waypoint_count, d.is_planned_route,
                       d.activity_type, d.creator_app
                  FROM media_items AS m
                  JOIN track_details AS d ON d.media_id = m.id
                 WHERE m.media_type = ? AND m.id IN ({marks})""",  # solo se interpolan '?'
            (MediaType.TRACK.value, *chunk),
        )
        for (row_distance, row_gain, row_loss, row_min, row_max, row_duration, row_points,
             row_segments, row_waypoints, row_planned, row_activity, row_creator) in rows:  # fmt: skip
            count += 1
            distance = _add(distance, row_distance)
            gain = _add(gain, row_gain)
            loss = _add(loss, row_loss)
            if row_min is not None:
                lowest = row_min if lowest is None else min(lowest, row_min)
            if row_max is not None:
                highest = row_max if highest is None else max(highest, row_max)
            if row_min is not None or row_max is not None:
                with_elevation += 1
            if row_duration is not None and row_duration > 0:
                with_duration += 1
                duration = _add(duration, row_duration)
                timed_distance = _add(timed_distance, row_distance)
            points += row_points or 0
            segments += row_segments or 0
            waypoints += row_waypoints or 0
            planned += 1 if row_planned else 0
            activity = _common(activity, row_activity)
            creator = _common(creator, row_creator)
    return TrackStats(
        count=count,
        distance_m=distance,
        elevation_gain_m=gain,
        elevation_loss_m=loss,
        elevation_min_m=lowest,
        elevation_max_m=highest,
        duration_s=duration,
        timed_distance_m=timed_distance,
        point_count=points,
        segment_count=segments,
        waypoint_count=waypoints,
        planned_routes=planned,
        with_duration=with_duration,
        with_elevation=with_elevation,
        activity_type=activity,
        creator_app=creator,
    )


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.track_stats
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")

    def add(media_id: int, media_type: str, duration: float | None, details: dict | None) -> None:
        db.execute(
            "INSERT INTO media_items(id, storage_location_id, relative_path, file_name, title, "
            "file_extension, media_type, mime_type, file_size, file_mtime_ns, duration) "
            "VALUES (?, 1, ?, ?, ?, 'x', ?, 'x/x', 1, 1, ?)",
            (media_id, f"f{media_id}", f"f{media_id}", f"f{media_id}", media_type, duration),
        )
        if details is not None:
            columns = ", ".join(details)
            marks = ", ".join("?" * len(details))
            db.execute(
                f"INSERT INTO track_details(media_id, {columns}) VALUES (?, {marks})",
                (media_id, *details.values()),
            )

    # 1: un track completo; 2: otro, con otra actividad; 3: ruta planificada (sin horas ni
    # altitud); 4: track sin datos leídos todavía; 5: una foto
    add(1, "track", 7200.0, {
        "distance_m": 12000.0, "elevation_gain_m": 800.0, "elevation_loss_m": 750.0,
        "elevation_min_m": 1200.0, "elevation_max_m": 2100.0, "point_count": 2500,
        "segment_count": 1, "waypoint_count": 2, "is_planned_route": 0,
        "activity_type": "hiking", "creator_app": "Wikiloc",
    })  # fmt: skip
    add(2, "track", 3600.0, {
        "distance_m": 6000.0, "elevation_gain_m": 100.0, "elevation_loss_m": 300.0,
        "elevation_min_m": 900.0, "elevation_max_m": 1500.0, "point_count": 1000,
        "segment_count": 3, "waypoint_count": 0, "is_planned_route": 0,
        "activity_type": "cycling", "creator_app": "Wikiloc",
    })  # fmt: skip
    add(3, "track", None, {
        "distance_m": 4000.0, "point_count": 40, "segment_count": 1, "waypoint_count": 0,
        "is_planned_route": 1,
    })  # fmt: skip
    add(4, "track", None, None)
    add(5, "photo", None, None)

    # --- Uno solo: sus datos, tal cual
    one = fetch_track_stats(db, [1])
    assert one.count == 1 and one.distance_m == 12000.0
    assert (one.elevation_gain_m, one.elevation_loss_m) == (800.0, 750.0)
    assert (one.elevation_min_m, one.elevation_max_m) == (1200.0, 2100.0)
    assert one.duration_s == 7200.0 and one.average_speed_kmh == 6.0  # 12 km en 2 h
    assert (one.point_count, one.segment_count, one.waypoint_count) == (2500, 1, 2)
    assert (one.activity_type, one.creator_app) == ("hiking", "Wikiloc")
    assert (one.planned_routes, one.with_duration, one.with_elevation) == (0, 1, 1)

    # --- Varios: se suman; altitud mínima y máxima; texto común o «varios»
    both = fetch_track_stats(db, [1, 2, 2, 1])  # los repetidos no cuentan dos veces
    assert both.count == 2 and both.distance_m == 18000.0
    assert (both.elevation_gain_m, both.elevation_loss_m) == (900.0, 1050.0)
    assert (both.elevation_min_m, both.elevation_max_m) == (900.0, 2100.0)
    assert both.duration_s == 10800.0 and both.average_speed_kmh == 6.0  # 18 km en 3 h
    assert (both.point_count, both.segment_count, both.waypoint_count) == (3500, 4, 2)
    assert both.activity_type == MIXED and both.creator_app == "Wikiloc"

    # --- Con una ruta planificada: su distancia cuenta, pero no entra en la velocidad
    mixed = fetch_track_stats(db, [1, 3])
    assert mixed.count == 2 and mixed.distance_m == 16000.0 and mixed.planned_routes == 1
    assert (mixed.with_duration, mixed.with_elevation) == (1, 1)
    assert mixed.duration_s == 7200.0 and mixed.timed_distance_m == 12000.0
    assert mixed.average_speed_kmh == 6.0
    assert mixed.activity_type == "hiking"  # la ruta no tiene: no lo convierte en «varios»
    # Solo la ruta: sin desnivel, sin duración, sin velocidad
    route = fetch_track_stats(db, [3])
    assert route.distance_m == 4000.0 and route.elevation_gain_m is None
    assert route.elevation_min_m is None and route.duration_s is None
    assert route.average_speed_kmh is None and route.activity_type is None

    # --- Lo que no es un track con datos se ignora; sin nada, vacío
    assert fetch_track_stats(db, [1, 4, 5, 999]) == one
    for nothing in ([], [4], [5], [999]):
        empty = fetch_track_stats(db, nothing)
        assert empty == TrackStats() and empty.average_speed_kmh is None, nothing

    # --- Muchos 'id' (más de los que caben en una consulta)
    assert fetch_track_stats(db, [*range(1000, 2500), 1, 2]) == fetch_track_stats(db, [1, 2])

    print("Autoprueba finalizada correctamente.")
