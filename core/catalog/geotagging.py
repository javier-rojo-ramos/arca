"""Ubicar fotos: poner, mover o quitar sus coordenadas recordando las de antes (para deshacer).

Este módulo NO depende de Qt. Sus funciones reciben la conexión como primer parámetro y no
hacen commit: se envían por la cola de cambios del inspector ('request_edit'). Diseño en
docs/MAPA.md (§5.1 y pasos 3.2 a 3.4).

Cada cambio pasa por 'media_queries.update_metadata_fields', el mismo camino que la edición
del GPS en el inspector: las mismas comprobaciones, los bits de pendiente y, después, la
escritura en los archivos con la regla del GPS. Lo único que se añade es que, ANTES de
cambiar, se leen las coordenadas que tenían: con ellas, 'restore_media_positions' deshace el
cambio (y devuelve a su vez las de antes de deshacer, por si un día se quiere rehacer).

Solo cambian la latitud y la longitud: la altitud y la dirección no se tocan (D7).

    cambio = set_media_position(conn, [12, 13], 42.65, 0.03)      # ubicar o mover
    cambio = set_media_position(conn, [12], None, None)           # quitar la ubicación
    restore_media_positions(conn, cambio.previous)                 # deshacer

1.0.0 Primera versión (docs/MAPA.md, pasos 3.3 y 3.4).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.geotagging
"""

__version__ = "1.0.0"
__all__ = ["Position", "PositionChange", "restore_media_positions", "set_media_position"]

# Librerías estándar
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Módulos del proyecto
from core.catalog.media_queries import update_metadata_fields

# Coordenadas (latitud, longitud), o None si no tiene
Position = tuple[float, float] | None

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class PositionChange:
    """Lo que hizo un cambio de coordenadas.

    Attributes:
        previous: 'media_items.id' -> coordenadas que tenía ANTES (None = sin ubicación).
            Es lo que hay que poner para deshacerlo.
        count: Elementos modificados (lo que la cola del inspector cuenta como cambiados:
            se escriben en los archivos).
    """

    previous: dict[int, Position]
    count: int


def _positions(conn: sqlite3.Connection, media_ids: Sequence[int]) -> dict[int, Position]:
    """Coordenadas actuales de esos elementos (los que no existen no salen)."""
    result: dict[int, Position] = {}
    ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        for media_id, latitude, longitude in conn.execute(
            f"SELECT id, latitude, longitude FROM media_items WHERE id IN ({marks})", chunk
        ):
            located = latitude is not None and longitude is not None
            result[media_id] = (latitude, longitude) if located else None
    return result


def set_media_position(
    conn: sqlite3.Connection,
    media_ids: Sequence[int],
    latitude: float | None,
    longitude: float | None,
) -> PositionChange:
    """Pone las mismas coordenadas a unos elementos (None, None = quitarles la ubicación),
    recordando las que tenían.

    Raises:
        ValueError: Si las coordenadas no son válidas (fuera de sus límites, solo una de las
            dos...); no se modifica nada.
    """
    previous = _positions(conn, media_ids)
    if not previous:
        return PositionChange({}, 0)
    count = update_metadata_fields(
        conn, list(previous), {"latitude": latitude, "longitude": longitude}
    )
    return PositionChange(previous, count)


def restore_media_positions(
    conn: sqlite3.Connection, positions: Mapping[int, Position]
) -> PositionChange:
    """Vuelve a poner a cada elemento sus coordenadas (las de 'PositionChange.previous'):
    deshace un cambio. Los que tienen las mismas se cambian juntos.

    Returns:
        Las coordenadas de antes de deshacer (para rehacer) y cuántos se han modificado.
    """
    current = _positions(conn, list(positions))
    groups: dict[Position, list[int]] = {}
    for media_id, position in positions.items():
        if media_id in current:  # si se ha borrado del catálogo, no hay nada que poner
            groups.setdefault(position, []).append(media_id)
    count = 0
    for position, ids in groups.items():
        latitude, longitude = position if position is not None else (None, None)
        count += update_metadata_fields(conn, ids, {"latitude": latitude, "longitude": longitude})
    return PositionChange(current, count)


if __name__ == "__main__":
    # Autoprueba con un catálogo en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.geotagging
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(id, name, absolute_path) VALUES (1, 'F', '/f')")
    for media_id, lat, lon, alt in ((1, 42.6, 0.03, 1200.0), (2, None, None, None), (3, 40.4, -3.7, None)):
        db.execute(
            "INSERT INTO media_items(id, storage_location_id, relative_path, file_name, media_type, "
            "mime_type, file_size, file_mtime_ns, title, latitude, longitude, altitude) "
            "VALUES (?, 1, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x', ?, ?, ?)",
            (media_id, f"{media_id}.jpg", f"{media_id}.jpg", lat, lon, alt),
        )

    def stored() -> list[tuple]:
        return db.execute(
            "SELECT id, latitude, longitude, altitude, metadata_edit_pending FROM media_items ORDER BY id"
        ).fetchall()

    original = stored()

    # 1. Ubicar 1 y 2 en un punto (y un id que no existe): recuerda las de antes
    change = set_media_position(db, [1, 2, 99], 41.5, 2.0)
    assert change.previous == {1: (42.6, 0.03), 2: None} and change.count == 2, change
    assert stored()[:2] == [(1, 41.5, 2.0, 1200.0, 1536), (2, 41.5, 2.0, None, 1536)]  # altitud igual
    assert stored()[2] == original[2]  # la 3, sin tocar

    # 2. Deshacer: cada una vuelve a lo suyo (la 2, sin ubicación); devuelve lo de antes de deshacer
    undone = restore_media_positions(db, change.previous)
    assert [row[:4] for row in stored()] == [row[:4] for row in original]
    assert undone.previous == {1: (41.5, 2.0), 2: (41.5, 2.0)} and undone.count == 2
    # Queda pendiente de escribir: el archivo tiene que volver a lo de antes
    assert [row[4] for row in stored()[:2]] == [1536, 1536]

    # 3. Quitar la ubicación y deshacerlo
    removed = set_media_position(db, [3], None, None)
    assert stored()[2][1:3] == (None, None) and removed.previous == {3: (40.4, -3.7)}
    restore_media_positions(db, removed.previous)
    assert stored()[2][1:3] == (40.4, -3.7)

    # 4. Lo que no vale no cambia nada; un elemento borrado no se «resucita» al deshacer
    for bad in ((95.0, 0.0), (42.0, None)):
        try:
            set_media_position(db, [1], *bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debería rechazarse: {bad}")
    assert stored()[0][1:3] == (42.6, 0.03)
    assert set_media_position(db, [99], 1.0, 1.0) == PositionChange({}, 0)
    db.execute("DELETE FROM media_items WHERE id = 2")
    assert restore_media_positions(db, {2: (1.0, 1.0), 1: (42.6, 0.03)}).count == 1

    db.close()
    print("Autoprueba finalizada correctamente.")
