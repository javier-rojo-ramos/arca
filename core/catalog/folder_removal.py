"""Quitar del catálogo una carpeta entera (o una ubicación), como en Lightroom Classic.

Este módulo NO depende de Qt. Las funciones reciben la conexión como primer parámetro
('count_folder_items' para 'CatalogDatabaseManager.execute_async';
'remove_folder_from_catalog' es un trabajo para 'JobManager.start').

Qué se quita (desde el menú de una carpeta de la barra lateral > "Quitar del catálogo..."):
    - TODOS los elementos de la carpeta y de sus subcarpetas (presentes o ausentes), con
      lo mismo que "Eliminar > Eliminar del catálogo" ('media_removal.remove_media_items'
      con 'to_trash=False'): sus filas y en cascada sus detalles y su pertenencia a
      colecciones, sus errores de lectura y sus miniaturas. Antes se escribe en los
      archivos lo pendiente (si quien llama pasa 'write_pending').
    - Lo que dijo el usuario en "¿Qué contiene esta carpeta?" para esa carpeta y las de
      debajo ('folder_libraries') y los errores de lectura que queden bajo ella.
    - Si es la RAÍZ de una ubicación (carpeta ''), también la ubicación
      ('storage_locations'; lo que cuelga de ella se borra en cascada): desaparece del
      árbol y para volver hay que "Añadir carpeta".
    - Ningún archivo del usuario se toca. Por eso se permite también con la ubicación
      desconectada (p. ej. un disco que ya no existe).
    - Las CARPETAS que se han quedado vacías en el disco (sus archivos ya no están: se
      borraron o se movieron fuera de la aplicación) se borran también del disco, como en
      Lightroom Classic (CAT 3.2; reglas en 'empty_folders.py'): lo que sobra (el
      '.arca.json', 'Thumbs.db'...) va a la Papelera y la carpeta se borra con 'os.rmdir'.
      Solo las que se anunciaron en el aviso ('plan_folder_removal'), nunca la raíz de una
      ubicación, y nada con la ubicación desconectada o en una unidad de red.

Si se cancela a mitad, lo ya quitado se queda quitado (se confirma por lotes), pero la
carpeta, su "¿Qué contiene...?" y la ubicación se conservan: aún tienen elementos; y no se
borra ninguna carpeta del disco.

Si después se vuelve a añadir o sincronizar la carpeta, sus archivos vuelven con lo que
ya esté escrito en ellos (valoración, marca, color, palabras clave): no hay lista de
excluidos, igual que en "Eliminar del catálogo".

Uso desde la interfaz:
    plan = plan_folder_removal(conn, location_id, "2024/Viaje")      # para el aviso
    job_manager.start("remove", remove_folder_from_catalog, location_id, "2024/Viaje",
                      write_pending=..., empty_folders=plan.empty_folders, trash=...)

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.folder_removal

1.1.0 Carpetas vacías (CAT 3.2): 'plan_folder_removal' (el recuento y las carpetas que se
      borrarían del disco, para el aviso) y, en 'remove_folder_from_catalog', su borrado
      al terminar ('empty_folders' y 'trash').
1.0.0 Primera versión.
"""

__version__ = "1.1.0"
__all__ = [
    "FolderRemovalPlan",
    "count_folder_items",
    "plan_folder_removal",
    "remove_folder_from_catalog",
]

# Librerías estándar
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.empty_folders import (
    EmptyFolderPlan,
    candidate_folders,
    plan_empty_folders,
    remove_empty_folders,
)
from core.catalog.media_removal import (
    DEFAULT_BATCH_SIZE,
    RemovalResult,
    TrashFunction,
    is_network_path,
    remove_media_items,
)
from core.jobs.progress import JobProgress


@dataclass(frozen=True, slots=True)
class FolderRemovalPlan:
    """Lo que hay que saber antes de quitar una carpeta (lo calcula 'plan_folder_removal').

    Attributes:
        folder: La carpeta (relativa a la ubicación, con '/'; '' = toda la ubicación).
        count: Elementos del catálogo en ella y en sus subcarpetas.
        empty_folders: Las carpetas que se borrarían del disco porque se han quedado
            vacías; None si no se mira (ubicación desconectada o de red).
    """

    folder: str
    count: int
    empty_folders: EmptyFolderPlan | None = None

    @property
    def deletes_folder(self) -> bool:
        """True si la propia carpeta (con todo lo de dentro) se borra del disco."""
        plan = self.empty_folders
        return bool(self.folder) and plan is not None and self.folder in plan.top_folders

    @property
    def deleted_subfolders(self) -> int:
        """Subcarpetas que se borran del disco sin la carpeta (las de más arriba de cada rama)."""
        if self.empty_folders is None or self.deletes_folder:
            return 0
        return len(self.empty_folders.top_folders)

    @property
    def folder_file_items(self) -> int:
        """Archivos con datos en los '.arca.json' que irían a la Papelera."""
        return 0 if self.empty_folders is None else self.empty_folders.folder_file_items


def _normalize(folder: str) -> str:
    """Carpeta relativa con '/' y sin barras en los extremos ('' = raíz de la ubicación)."""
    return folder.replace("\\", "/").strip("/")


def _items_condition(location_id: int, folder: str) -> tuple[str, list[Any]]:
    """Condición SQL: elementos de esa carpeta y de sus subcarpetas.

    La carpeta se compara por RANGO ('carpeta/' <= ruta < 'carpeta0'), como en el resto del
    catálogo (ver 'catalog_writer._under_prefix'): sin comodines y usando el índice. '0' es
    el carácter siguiente a '/', así que '2024b/...' no cae dentro de '2024'.
    """
    sql = "storage_location_id = ?"
    params: list[Any] = [location_id]
    if folder:
        sql += " AND relative_path >= ? AND relative_path < ?"
        params += [folder + "/", folder + "0"]
    return sql, params


def count_folder_items(conn: sqlite3.Connection, location_id: int, folder: str = "") -> int:
    """Cuenta los elementos de una carpeta y sus subcarpetas (presentes o ausentes).

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        location_id: 'storage_locations.id'.
        folder: Carpeta relativa a la ubicación ('' = toda la ubicación).
    """
    where, params = _items_condition(location_id, _normalize(folder))
    row = conn.execute(f"SELECT COUNT(*) FROM media_items WHERE {where}", params).fetchone()
    return int(row[0])


def plan_folder_removal(
    conn: sqlite3.Connection, location_id: int, folder: str = ""
) -> FolderRemovalPlan:
    """Cuenta los elementos de una carpeta y mira qué carpetas se borrarían del disco.

    Para el aviso de «Quitar del catálogo…». No cambia nada. Lee el disco (poco: ver
    'plan_empty_folders'), así que se llama en segundo plano ('execute_async').

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        location_id: 'storage_locations.id'.
        folder: Carpeta relativa a la ubicación ('' = toda la ubicación).
    """
    folder = _normalize(folder)
    where, params = _items_condition(location_id, folder)
    rows = conn.execute(f"SELECT relative_path FROM media_items WHERE {where}", params)
    paths = [row[0] for row in rows]
    location = conn.execute(
        "SELECT absolute_path, is_online FROM storage_locations WHERE id = ?", (location_id,)
    ).fetchone()
    if location is None or not location[1]:
        return FolderRemovalPlan(folder, len(paths))  # desconectada: el disco no se mira
    root = Path(location[0])
    if not root.is_dir() or is_network_path(root):
        return FolderRemovalPlan(folder, len(paths))  # sin Papelera, o no está
    plan = plan_empty_folders(root, candidate_folders(paths, within=folder))
    for relative_path, reason in plan.kept:
        logger.debug(f"Carpeta que no se borraría del disco: {relative_path}: {reason}")
    return FolderRemovalPlan(folder, len(paths), plan)


def remove_folder_from_catalog(
    conn: sqlite3.Connection,
    location_id: int,
    folder: str = "",
    *,
    write_pending: Callable[[sqlite3.Connection], Any] | None = None,
    empty_folders: EmptyFolderPlan | None = None,
    trash: TrashFunction | None = None,
    catalog_dir: str | Path | None = None,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> RemovalResult:
    """Quita del catálogo una carpeta, todo lo que contiene y, si es la raíz, su ubicación.

    Es un trabajo para 'JobManager.start' (progreso y cancelación); hace 'commit' por
    lote. Ver la cabecera del módulo para las reglas.

    Args:
        conn: Conexión sqlite3 propia del trabajo.
        location_id: 'storage_locations.id'.
        folder: Carpeta relativa a la ubicación ('' = toda la ubicación, que también se
            quita).
        write_pending: Función que escribe antes en los archivos los datos del usuario
            pendientes (recibe la conexión). None = no se escribe nada.
        empty_folders: Las carpetas vacías anunciadas en el aviso ('plan_folder_removal'):
            al terminar, se borran del disco (cada una se vuelve a mirar antes). None = no
            se toca el disco.
        trash: Función que envía un archivo a la Papelera (para lo que sobra en esas
            carpetas). Sin ella, tampoco se toca el disco.
        catalog_dir: Carpeta del catálogo (para borrar las miniaturas). None = se deduce
            del archivo de la base de datos (en memoria: no se tocan).
        progress: Función a la que se avisa del avance.
        cancel_event: Si se activa, se termina el lote en curso y se para.
        batch_size: Elementos por lote.

    Returns:
        El resultado de 'remove_media_items' (cuántos se quitaron, avisos, cancelación).
    """
    folder = _normalize(folder)
    where, params = _items_condition(location_id, folder)
    ids = [row[0] for row in conn.execute(f"SELECT id FROM media_items WHERE {where}", params)]

    # 1. Los elementos, como "Eliminar del catálogo" (por lotes, con commit y miniaturas)
    result = remove_media_items(
        conn,
        ids,
        to_trash=False,
        catalog_dir=catalog_dir,
        write_pending=write_pending,
        progress=progress,
        cancel_event=cancel_event,
        batch_size=batch_size,
    )
    if result.cancelled:
        logger.info(f"Quitar carpeta del catálogo cancelado (ubicación {location_id}, '{folder}')")
        return result

    # 2. La carpeta en sí: solo si ya no le queda nada (un elemento añadido mientras tanto
    # por otro hilo la mantiene, con su "¿Qué contiene...?")
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE;")
    try:
        remaining = conn.execute(
            f"SELECT COUNT(*) FROM media_items WHERE {where}",
            params,
        ).fetchone()[0]
        if remaining:
            logger.warning(f"La carpeta '{folder}' aún tiene {remaining} elementos: se conserva")
        elif not folder:
            # La ubicación entera: 'folder_libraries' y 'scan_errors' se borran en cascada
            conn.execute("DELETE FROM storage_locations WHERE id = ?", (location_id,))
        else:
            under = (location_id, folder, folder + "/", folder + "0")
            conn.execute(
                "DELETE FROM folder_libraries WHERE storage_location_id = ? "
                "AND (folder = ? OR (folder >= ? AND folder < ?))",
                under,
            )
            conn.execute(
                "DELETE FROM scan_errors WHERE storage_location_id = ? "
                "AND (relative_path = ? OR (relative_path >= ? AND relative_path < ?))",
                under,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    logger.info(
        f"Carpeta quitada del catálogo (ubicación {location_id}, '{folder or '<raíz>'}'): "
        f"{result.removed} elementos"
    )

    # 3. Las carpetas que se han quedado vacías en el disco (solo si la carpeta salió entera
    # del catálogo: si le quedaba algo, sigue siendo del catálogo)
    if empty_folders is not None and empty_folders.folders and trash is not None:
        if remaining:
            return result
        outcome = remove_empty_folders(empty_folders, trash, cancel_event=cancel_event)
        result.folders_deleted.extend(outcome.removed)
        result.folders_kept.extend(outcome.kept)
        result.cancelled = result.cancelled or outcome.cancelled
    return result


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria (sin caché de miniaturas).
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.folder_removal
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Fotos', '/f')")
    db.execute(
        "INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('Ext', '/e', 0)"
    )

    def add(location: int, path: str, missing: int = 0) -> int:
        cursor = db.execute(
            """INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
                   mime_type, file_size, file_mtime_ns, title, is_missing)
               VALUES (?, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x', ?)""",
            (location, path, path.rsplit("/", 1)[-1], missing),
        )
        return int(cursor.lastrowid)

    def paths(location: int) -> set[str]:
        sql = "SELECT relative_path FROM media_items WHERE storage_location_id = ?"
        return {row[0] for row in db.execute(sql, (location,))}

    gone = add(1, "2024/a.jpg")
    add(1, "2024/sub/b.jpg")
    add(1, "2024/ausente.jpg", missing=1)  # también se quita (no solo los ausentes)
    add(1, "2024b/fuera.jpg")  # '2024b' NO está dentro de '2024'
    add(1, "suelta.jpg")
    add(2, "2024/desconectada.jpg")
    db.execute("INSERT INTO photo_details(media_id, iso) VALUES (?, 100)", (gone,))
    db.executemany(
        "INSERT INTO folder_libraries(storage_location_id, folder, content) VALUES (?, ?, 'auto')",
        [(1, ""), (1, "2024"), (1, "2024/sub"), (1, "2024b"), (2, "")],
    )
    db.executemany(
        "INSERT INTO scan_errors(storage_location_id, relative_path, stage, message) "
        "VALUES (1, ?, 'metadata', 'x')",
        [("2024/roto.jpg",), ("2024b/roto.jpg",)],  # errores de archivos sin fila
    )
    db.commit()

    # 1. Contar
    assert count_folder_items(db, 1, "2024") == 3
    assert count_folder_items(db, 1, "\\2024\\") == 3  # barras de Windows y de los extremos
    assert count_folder_items(db, 1) == 5
    assert count_folder_items(db, 2) == 1
    print("1. Contar los elementos de una carpeta y sus subcarpetas")

    # 2. Una subcarpeta: sus elementos, su "¿Qué contiene...?" y sus errores; nada más
    steps: list[JobProgress] = []
    result = remove_folder_from_catalog(db, 1, "2024", progress=steps.append)
    assert result.removed == 3 and not result.cancelled, result
    assert steps and steps[-1].done == 3, steps
    assert paths(1) == {"2024b/fuera.jpg", "suelta.jpg"}, paths(1)
    assert db.execute("SELECT COUNT(*) FROM photo_details").fetchone()[0] == 0  # en cascada
    libraries = {row[0] for row in db.execute("SELECT folder FROM folder_libraries WHERE storage_location_id = 1")}
    assert libraries == {"", "2024b"}, libraries
    errors = {row[0] for row in db.execute("SELECT relative_path FROM scan_errors")}
    assert errors == {"2024b/roto.jpg"}, errors
    assert db.execute("SELECT COUNT(*) FROM storage_locations").fetchone()[0] == 2
    print("2. Subcarpeta quitada (con lo de debajo); la ubicación se queda")

    # 3. Lo pendiente se escribe antes de quitar
    written: list[bool] = []
    remove_folder_from_catalog(db, 1, "2024b", write_pending=lambda _conn: written.append(True))
    assert written == [True]
    assert paths(1) == {"suelta.jpg"}, paths(1)
    print("3. Se escribe lo pendiente antes de quitar")

    # 4. Cancelado a mitad (lotes de 1): lo quitado, quitado; la ubicación se conserva
    add(1, "otra.jpg")
    cancel = threading.Event()
    cancel.set()
    result = remove_folder_from_catalog(db, 1, "", cancel_event=cancel, batch_size=1)
    assert result.cancelled and result.removed == 1, result
    assert len(paths(1)) == 1, paths(1)
    assert db.execute("SELECT COUNT(*) FROM storage_locations WHERE id = 1").fetchone()[0] == 1
    print("4. Cancelar no borra la ubicación mientras le queden elementos")

    # 5. Una ubicación desconectada, entera: desaparece con todo lo suyo
    result = remove_folder_from_catalog(db, 2, "")
    assert result.removed == 1, result
    assert paths(2) == set()
    assert db.execute("SELECT COUNT(*) FROM storage_locations WHERE id = 2").fetchone()[0] == 0
    sql = "SELECT COUNT(*) FROM folder_libraries WHERE storage_location_id = 2"
    assert db.execute(sql).fetchone()[0] == 0  # en cascada
    print("5. Ubicación (desconectada) quitada entera")

    # 6. Carpetas vacías en el disco (CAT 3.2), con carpetas de verdad en una temporal
    import tempfile

    from core.userdata.folder_file import FolderData, write_folder_file

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Fotos"
        bin_dir = Path(tmp) / "papelera"
        bin_dir.mkdir()
        trashed: list[str] = []

        def fake_trash(path: Path) -> None:
            path.replace(bin_dir / f"{len(trashed)}_{path.name}")
            trashed.append(path.relative_to(root).as_posix())

        cursor = db.execute(
            "INSERT INTO storage_locations(name, absolute_path) VALUES ('Fotos', ?)", (str(root),)
        )
        location = int(cursor.lastrowid)
        # Viaje: sus archivos ya no están (ausentes); queda su .arca.json con un vídeo
        (root / "Viaje/sub").mkdir(parents=True)
        items = {"a.mp4": {"rating": 4}}
        assert write_folder_file(FolderData(directory=root / "Viaje", items=items))
        add(location, "Viaje/a.mp4", missing=1)
        add(location, "Viaje/sub/b.jpg", missing=1)
        # Otra: su foto sigue en el disco, pero su subcarpeta se ha quedado vacía
        (root / "Otra/vacia").mkdir(parents=True)
        (root / "Otra/foto.jpg").write_bytes(b"x")
        add(location, "Otra/foto.jpg")
        add(location, "Otra/vacia/c.jpg", missing=1)
        db.commit()

        plan = plan_folder_removal(db, location, "Viaje")
        assert plan.count == 2 and plan.deletes_folder and plan.folder_file_items == 1, plan
        other = plan_folder_removal(db, location, "Otra")
        assert not other.deletes_folder and other.deleted_subfolders == 1, other
        whole = plan_folder_removal(db, location, "")
        assert not whole.deletes_folder and whole.deleted_subfolders == 2, whole  # la raíz, no
        print("6a. Plan: «Viaje» entera, de «Otra» una subcarpeta; nunca la raíz")

        # Sin la papelera no se toca el disco
        empty = other.empty_folders
        result = remove_folder_from_catalog(db, location, "Otra", empty_folders=empty)
        assert result.removed == 2 and result.folders_deleted == [], result
        assert (root / "Otra/vacia").is_dir()
        # Con ella, la carpeta vacía se borra del disco (y lo que sobra, a la papelera)
        result = remove_folder_from_catalog(
            db, location, "Viaje", empty_folders=plan.empty_folders, trash=fake_trash
        )
        assert result.removed == 2 and result.folders_deleted == ["Viaje/sub", "Viaje"], result
        assert not (root / "Viaje").exists() and trashed == ["Viaje/.arca.json"], trashed
        assert "carpetas eliminadas del disco: 2" in result.status_text(), result.status_text()
        assert not result.has_warnings
        print("6b. Quitada: «Viaje» borrada del disco; sin papelera, nada")

        # Si la carpeta sigue teniendo algo en el catálogo (cancelado), el disco no se toca
        (root / "Tarde").mkdir()
        add(location, "Tarde/1.jpg", missing=1)
        add(location, "Tarde/2.jpg", missing=1)
        db.commit()
        late = plan_folder_removal(db, location, "Tarde")
        assert late.deletes_folder
        cancel = threading.Event()
        cancel.set()
        result = remove_folder_from_catalog(
            db, location, "Tarde", empty_folders=late.empty_folders, trash=fake_trash,
            cancel_event=cancel, batch_size=1,
        )  # fmt: skip
        assert result.cancelled and result.folders_deleted == [] and (root / "Tarde").is_dir()
        print("6c. Cancelado con elementos aún en el catálogo: la carpeta se queda en el disco")

        # Desconectada o inexistente: no se mira el disco
        db.execute("UPDATE storage_locations SET is_online = 0 WHERE id = ?", (location,))
        assert plan_folder_removal(db, location, "Tarde").empty_folders is None
        db.execute(
            "UPDATE storage_locations SET is_online = 1, absolute_path = ? WHERE id = ?",
            (str(root / "no_existe"), location),
        )
        assert plan_folder_removal(db, location, "Tarde").empty_folders is None
        print("6d. Ubicación desconectada o que no existe: el disco no se mira")

    db.close()
    print("Autoprueba finalizada correctamente.")
