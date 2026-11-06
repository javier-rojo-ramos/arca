"""Quitar del catálogo los archivos ausentes (los que ya no están en el disco).

Este módulo NO depende de Qt. Sus funciones reciben la conexión como primer parámetro,
así que se envían tal cual a 'CatalogDatabaseManager.execute_async' (el gestor hace el
commit).

Por qué hace falta: al añadir o sincronizar una carpeta, los archivos que ya no están NO
se borran del catálogo, solo se marcan como ausentes ('is_missing = 1'). Un archivo
"desaparecido" puede haberse movido o renombrado, y un fallo puntual (unidad de red que
no responde) no debe vaciar el catálogo. Quitarlos es una decisión del usuario, como en
Lightroom: lo pregunta la aplicación tras sincronizar una carpeta, o se pide desde el
menú contextual de la carpeta.

Qué se quita (y qué no):
    - Solo elementos marcados como ausentes, dentro de la carpeta indicada (y sus
      subcarpetas), y solo si su ubicación está CONECTADA: con el disco desconectado no
      se sabe si los archivos siguen ahí.
    - Sus filas de 'media_items'; las tablas de detalles ('photo_details',
      'track_details'...) se borran solas (ON DELETE CASCADE).
    - Sus errores de lectura en 'scan_errors'.
    - Sus miniaturas de la caché (si se indica la carpeta del catálogo o se puede deducir).
    - NUNCA se toca ningún archivo del disco del usuario.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.missing_items
"""

__version__ = "1.0.0"
__all__ = ["RemovedItems", "count_missing_items", "remove_missing_items"]

# Librerías estándar
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class RemovedItems:
    """Resultado de 'remove_missing_items'.

    Attributes:
        count: Elementos quitados del catálogo.
        thumbnails_deleted: Archivos de miniatura borrados de la caché.
    """

    count: int = 0
    thumbnails_deleted: int = 0


def _missing_condition(location_id: int, relative_folder: str) -> tuple[str, list[Any]]:
    """Condición SQL: ausentes de esa carpeta (y subcarpetas), con la ubicación conectada.

    La carpeta se compara por RANGO ('carpeta/' <= ruta < 'carpeta0'), como en el resto del
    catálogo (ver 'catalog_writer._under_prefix'): sin comodines y usando el índice.
    """
    sql = (
        "is_missing = 1 AND storage_location_id = ? "
        "AND EXISTS (SELECT 1 FROM storage_locations l "
        "            WHERE l.id = media_items.storage_location_id AND l.is_online = 1)"
    )
    params: list[Any] = [location_id]
    folder = relative_folder.strip("/")
    if folder:
        sql += " AND relative_path >= ? AND relative_path < ?"
        params += [folder + "/", folder + "0"]
    return sql, params


def count_missing_items(
    conn: sqlite3.Connection, location_id: int, relative_folder: str = ""
) -> int:
    """Cuenta los ausentes de una carpeta (y sus subcarpetas) que se pueden quitar.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        location_id: 'storage_locations.id'.
        relative_folder: Carpeta relativa a la ubicación ('' = toda la ubicación).

    Returns:
        Número de elementos ausentes. 0 si la ubicación está desconectada.
    """
    where, params = _missing_condition(location_id, relative_folder)
    row = conn.execute(f"SELECT COUNT(*) FROM media_items WHERE {where}", params).fetchone()  # noqa: S608
    return int(row[0])


def remove_missing_items(
    conn: sqlite3.Connection,
    location_id: int,
    relative_folder: str = "",
    *,
    catalog_dir: str | Path | None = None,
) -> RemovedItems:
    """Quita del catálogo los ausentes de una carpeta (y sus subcarpetas).

    No hace 'commit' (lo hace el gestor asíncrono). Las miniaturas se borran DESPUÉS de
    borrar las filas: si algo fallara antes, no se pierde ninguna miniatura de un
    elemento que sigue en el catálogo.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        location_id: 'storage_locations.id'.
        relative_folder: Carpeta relativa a la ubicación ('' = toda la ubicación).
        catalog_dir: Carpeta del catálogo (para borrar sus miniaturas). Si es None, se
            deduce del archivo de la base de datos; si tampoco se puede (base de datos en
            memoria), las miniaturas no se tocan.

    Returns:
        Cuántos elementos y miniaturas se han quitado.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    where, params = _missing_condition(location_id, relative_folder)
    rows = conn.execute(
        f"SELECT id, media_type, relative_path FROM media_items WHERE {where}",  # noqa: S608
        params,
    ).fetchall()
    if not rows:
        return RemovedItems()

    # 1. Filas (y en cascada, sus detalles) y sus errores de lectura
    ids = [row[0] for row in rows]
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM media_items WHERE id IN ({marks})", chunk)  # noqa: S608
    conn.executemany(
        "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ?",
        ((location_id, row[2]) for row in rows),
    )

    # 2. Miniaturas de la caché
    thumbnails_deleted = 0
    folder = Path(catalog_dir) if catalog_dir is not None else _catalog_directory(conn)
    if folder is not None:
        # Importación diferida: solo hace falta aquí (y arrastra Pillow)
        from core.thumbnails.cache import ThumbnailCache

        cache = ThumbnailCache(folder)
        for media_id, media_type, _path in rows:
            try:
                thumbnails_deleted += len(cache.delete(media_type, media_id))
            except ValueError:
                continue  # tipo de medio desconocido: no tiene carpeta en la caché

    logger.info(
        f"Quitados del catálogo {len(rows)} archivos ausentes (ubicación {location_id}, "
        f"carpeta '{relative_folder}'); miniaturas borradas: {thumbnails_deleted}"
    )
    return RemovedItems(count=len(rows), thumbnails_deleted=thumbnails_deleted)


def _catalog_directory(conn: sqlite3.Connection) -> Path | None:
    """Carpeta del catálogo (la que contiene el .db), o None si la base está en memoria."""
    for _sequence, schema_name, file_path in conn.execute("PRAGMA database_list;"):
        if schema_name == "main" and file_path:
            return Path(file_path).parent
    return None


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria (sin caché de miniaturas).
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.missing_items
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Fotos', '/f')")
    db.execute("INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('Ext', '/e', 0)")

    def add(location: int, path: str, missing: int) -> int:
        cursor = db.execute(
            """INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
                   mime_type, file_size, file_mtime_ns, title, is_missing, rating)
               VALUES (?, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x', ?, 4)""",
            (location, path, path.rsplit("/", 1)[-1], missing),
        )
        return int(cursor.lastrowid)

    kept = add(1, "2024/presente.jpg", 0)
    gone = add(1, "2024/borrada.jpg", 1)
    add(1, "2024/sub/otra_borrada.jpg", 1)
    add(1, "2024b/fuera.jpg", 1)  # '2024b' NO está dentro de '2024'
    add(2, "2024/desconectada.jpg", 1)  # disco desconectado: no se toca
    db.execute("INSERT INTO photo_details(media_id, iso) VALUES (?, 100)", (gone,))
    db.execute(
        "INSERT INTO scan_errors(storage_location_id, relative_path, stage, message) "
        "VALUES (1, '2024/borrada.jpg', 'metadata', 'x')"
    )
    db.commit()

    assert count_missing_items(db, 1, "2024") == 2
    assert count_missing_items(db, 1) == 3
    assert count_missing_items(db, 2) == 0  # desconectada: no se puede decidir

    result = remove_missing_items(db, 1, "2024")
    db.commit()
    assert result == RemovedItems(count=2, thumbnails_deleted=0), result
    paths = {row[0] for row in db.execute("SELECT relative_path FROM media_items")}
    assert paths == {"2024/presente.jpg", "2024b/fuera.jpg", "2024/desconectada.jpg"}, paths
    assert db.execute("SELECT COUNT(*) FROM photo_details").fetchone()[0] == 0  # en cascada
    assert db.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0] == 0
    assert db.execute("SELECT rating FROM media_items WHERE id = ?", (kept,)).fetchone()[0] == 4

    assert remove_missing_items(db, 1, "2024") == RemovedItems()  # nada más que quitar
    assert remove_missing_items(db, 2) == RemovedItems()  # desconectada
    print("Autoprueba finalizada correctamente.")
