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
    - Las carpetas apuntadas en el catálogo (tabla 'folders', CAT 5) dentro de ella, o ella
      misma, que ya no están en el disco, con las de dentro y con las precauciones de
      'folder_tree.find_missing_folders' (que el sistema diga que no existen; nada con la
      raíz de la ubicación vacía). Sin esto, una carpeta borrada fuera de la aplicación
      seguiría en el árbol de «Carpetas», con 0 (CAT 6.2c). Las carpetas vacías que siguen
      en el disco se quedan (CAT 5).
    - NUNCA se toca ningún archivo del disco del usuario.

'count_missing' cuenta las dos cosas (para la pregunta); 'count_missing_items', solo los
archivos (el resumen de sincronizar, que ya pone al día las carpetas).

1.1.0 También las carpetas que ya no están en el disco: 'count_missing' ('MissingCount') y
      'RemovedItems.folders' (CAT 6.2c).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.missing_items
"""

__version__ = "1.1.0"
__all__ = [
    "MissingCount",
    "RemovedItems",
    "count_missing",
    "count_missing_items",
    "remove_missing_items",
]

# Librerías estándar
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.catalog_folders import folders_under, remove_folders
from core.catalog.folder_tree import build_folder_tree, find_missing_folders

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class RemovedItems:
    """Resultado de 'remove_missing_items'.

    Attributes:
        count: Elementos quitados del catálogo.
        thumbnails_deleted: Archivos de miniatura borrados de la caché.
        folders: Carpetas quitadas porque ya no están en el disco (las de más arriba: una
            con sus subcarpetas cuenta como una).
    """

    count: int = 0
    thumbnails_deleted: int = 0
    folders: int = 0


@dataclass(frozen=True, slots=True)
class MissingCount:
    """Lo que quitaría 'remove_missing_items' (lo cuenta 'count_missing').

    Attributes:
        items: Archivos ausentes.
        folders: Carpetas que ya no están en el disco (las de más arriba).
        folder_missing: Es la propia carpeta pedida la que ya no está (o una de encima).
    """

    items: int = 0
    folders: int = 0
    folder_missing: bool = False


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
    row = conn.execute(f"SELECT COUNT(*) FROM media_items WHERE {where}", params).fetchone()
    return int(row[0])


def count_missing(
    conn: sqlite3.Connection, location_id: int, relative_folder: str = ""
) -> MissingCount:
    """Cuenta lo que quitaría 'remove_missing_items': archivos ausentes y carpetas que ya no
    están en el disco (mira el disco: en segundo plano).

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        location_id: 'storage_locations.id'.
        relative_folder: Carpeta relativa a la ubicación ('' = toda la ubicación).
    """
    folders = _missing_folders(conn, location_id, relative_folder)
    scope = _normalize(relative_folder)
    return MissingCount(
        items=count_missing_items(conn, location_id, relative_folder),
        folders=len(folders),
        folder_missing=bool(scope) and folders == [scope],
    )


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
        Cuántos elementos, miniaturas y carpetas se han quitado.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    where, params = _missing_condition(location_id, relative_folder)
    rows = conn.execute(
        f"SELECT id, media_type, relative_path FROM media_items WHERE {where}",
        params,
    ).fetchall()
    missing_folders = _missing_folders(conn, location_id, relative_folder)
    if not rows and not missing_folders:
        return RemovedItems()

    # 1. Filas (y en cascada, sus detalles) y sus errores de lectura
    ids = [row[0] for row in rows]
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM media_items WHERE id IN ({marks})", chunk)
    conn.executemany(
        "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ?",
        ((location_id, row[2]) for row in rows),
    )

    # 2. Las carpetas que ya no están en el disco, con las de dentro (sin esto seguirían en
    #    el árbol, con 0; CAT 6.2c)
    for missing_folder in missing_folders:
        remove_folders(conn, location_id, missing_folder)

    # 3. Miniaturas de la caché
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
        f"Quitados del catálogo {len(rows)} archivos ausentes y {len(missing_folders)} carpetas "
        f"que ya no están (ubicación {location_id}, carpeta '{relative_folder}'); miniaturas "
        f"borradas: {thumbnails_deleted}"
    )
    return RemovedItems(
        count=len(rows), thumbnails_deleted=thumbnails_deleted, folders=len(missing_folders)
    )


def _normalize(folder: str) -> str:
    """Carpeta relativa con '/' y sin barras en los extremos ('' = la ubicación)."""
    return folder.replace("\\", "/").strip("/")


def _missing_folders(
    conn: sqlite3.Connection, location_id: int, relative_folder: str
) -> list[str]:
    """Las carpetas apuntadas ('folders') dentro de 'relative_folder', o ella, que ya no
    están en el disco: las de más arriba (las de dentro se quitan con ellas).

    Solo con la ubicación conectada y con las precauciones de 'find_missing_folders'. Si
    falta la propia carpeta (o una de encima), es ella la única.
    """
    location = conn.execute(
        "SELECT absolute_path, is_online FROM storage_locations WHERE id = ?", (location_id,)
    ).fetchone()
    if location is None or not location[1]:
        return []
    scope = _normalize(relative_folder)
    paths = folders_under(conn, location_id, scope)
    if not paths:
        return []
    # El árbol lleva también las de encima de 'scope' (se mira de arriba abajo)
    missing = find_missing_folders(location[0], build_folder_tree({}, paths))
    if scope and any(scope == path or scope.startswith(f"{path}/") for path in missing):
        return [scope]
    return sorted(missing)


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

    # Las carpetas que ya no están en el disco (CAT 6.2c), con carpetas de verdad
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        disk = Path(tmp) / "Disco"
        (disk / "Sigue" / "Vacía").mkdir(parents=True)  # vacía en el disco: se queda
        db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Disco', ?)", (str(disk),))
        loc = db.execute("SELECT id FROM storage_locations WHERE name = 'Disco'").fetchone()[0]
        for folder in ("Viejas", "Viejas/2020", "Sigue", "Sigue/Vacía", "Sigue/Borrada"):
            db.execute(
                "INSERT INTO folders(storage_location_id, relative_path) VALUES (?, ?)", (loc, folder)
            )
        add(loc, "Viejas/2020/x.jpg", 1)

        def listed() -> set[str]:
            rows = db.execute("SELECT relative_path FROM folders WHERE storage_location_id = ?", (loc,))
            return {row[0] for row in rows}

        assert count_missing(db, loc) == MissingCount(1, 2, False)  # Viejas y Sigue/Borrada
        assert count_missing(db, loc, "Viejas/2020") == MissingCount(1, 1, True)  # falta la de encima
        assert count_missing(db, loc, "Sigue") == MissingCount(0, 1, False)
        assert count_missing(db, loc, "Sigue/Vacía") == MissingCount()  # está (vacía): se queda
        assert remove_missing_items(db, loc, "Sigue") == RemovedItems(0, 0, 1)
        assert listed() == {"Viejas", "Viejas/2020", "Sigue", "Sigue/Vacía"}
        assert remove_missing_items(db, loc) == RemovedItems(1, 0, 1)  # Viejas, con 2020
        assert listed() == {"Sigue", "Sigue/Vacía"}
        assert remove_missing_items(db, loc) == RemovedItems()
        # Con la raíz vacía (un disco desmontado): no se quita ninguna carpeta
        db.execute("INSERT INTO folders(storage_location_id, relative_path) VALUES (?, 'Otra')", (loc,))
        (disk / "Sigue" / "Vacía").rmdir()
        (disk / "Sigue").rmdir()
        assert count_missing(db, loc) == MissingCount() and remove_missing_items(db, loc) == RemovedItems()
        # Desconectada: tampoco
        db.execute("UPDATE storage_locations SET is_online = 0 WHERE id = ?", (loc,))
        assert count_missing(db, loc) == MissingCount()
        db.commit()
    print("Autoprueba finalizada correctamente.")
