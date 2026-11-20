"""Comprobación rápida de si los archivos del catálogo siguen en disco.

Este módulo NO depende de Qt. 'check_availability' recibe la conexión como primer
parámetro, así que se envía tal cual a 'CatalogDatabaseManager.execute_async' (se
ejecuta en un hilo secundario; el gestor hace el commit).

Para qué sirve: que la cuadrícula se entere SOLA, con la aplicación abierta, de que
    - se ha desconectado (o conectado) un disco externo o una unidad de red, y
    - se ha borrado (o ha vuelto) un archivo que se está viendo,
sin tener que volver a abrir el catálogo ni reescanear la carpeta.

Qué comprueba (y qué no), para que sea barato aunque el catálogo sea enorme:
    - TODAS las ubicaciones: si existe su carpeta raíz (una consulta al disco por
      ubicación). Si una cambia, se devuelve el estado nuevo de todos sus elementos.
    - Si se pide ('check_folders', con la ventana activa), las CARPETAS del catálogo que
      ya no están en el disco ('folder_tree.find_missing_folders': unas 900 carpetas en
      unos 25 ms con el árbol entero). Sus archivos pasan a ausentes, todos, aunque no se
      vean: lo mismo que haría «Sincronizar» en la carpeta de encima (CAT 6.2b).
    - SOLO los archivos que se le piden (normalmente, las tarjetas visibles: unas
      decenas). Lo que no está a la vista se actualizará al verse o al reescanear.

Qué hace con cada archivo comprobado (de una ubicación conectada):
    - No está y constaba como presente   -> 'is_missing = 1' (ausente).
    - Está y constaba como ausente:
        * igual que antes (tamaño y fecha) -> 'is_missing = 0' (ha vuelto).
        * distinto                         -> 'is_missing = 0' y queda pendiente de
          releer, igual que cuando lo detecta el escáner (metadatos, miniatura y hashes).
Nunca toca los datos del usuario.

Además, dice qué ubicaciones se han conectado o desconectado ('switched_locations') y en
qué carpetas que faltan ha marcado archivos ('missing_folders'), para que el árbol de
«Carpetas» se ponga al día: una ubicación sin archivos no cambia ninguna tarjeta.

Las carpetas no se miran mientras haya una operación con archivos a medias (la tabla
'file_operations'): al renombrar una carpeta desde la aplicación, la de origen deja de
existir un momento antes de que el catálogo lo sepa, y sus archivos no deben quedar como
ausentes. La operación se apunta ANTES de tocar el disco y se borra al terminar.

1.2.0 'check_folders': los archivos de las carpetas que ya no están en el disco, ausentes;
      'AvailabilityCheck.missing_folders' (CAT 6.2b).
1.1.0 'AvailabilityCheck.switched_locations': las ubicaciones que se han conectado o
      desconectado (para poner al día el árbol de «Carpetas»).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.availability
"""

__version__ = "1.2.0"
__all__ = ["AvailabilityCheck", "check_availability"]

# Librerías estándar
import os
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Módulos del proyecto
from core.catalog.folder_tree import FolderNode, fetch_folder_tree
from core.catalog.media_queries import AVAILABLE, MISSING, OFFLINE

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class AvailabilityCheck:
    """Resultado de una comprobación.

    Attributes:
        changes: 'media_items.id' -> disponibilidad nueva (AVAILABLE, MISSING u OFFLINE),
            solo de los elementos cuyo estado ha cambiado.
        rescan_needed: Archivos que han vuelto, pero cambiados: quedan pendientes de
            releer (hay que lanzar la lectura de metadatos).
        switched_locations: 'storage_locations.id' de las que se han conectado o
            desconectado (hay que poner al día el árbol de «Carpetas»).
        missing_folders: (ubicación, carpeta relativa) de las carpetas que ya no están en
            el disco y cuyos archivos se acaban de marcar como ausentes (hay que poner al
            día el árbol). Una que ya estaba marcada no vuelve a salir.
    """

    changes: dict[int, int] = field(default_factory=dict)
    rescan_needed: int = 0
    switched_locations: tuple[int, ...] = ()
    missing_folders: tuple[tuple[int, str], ...] = ()


def check_availability(
    conn: sqlite3.Connection, media_ids: Sequence[int] = (), check_folders: bool = False
) -> AvailabilityCheck:
    """Comprueba las ubicaciones, las carpetas (si se pide) y los archivos indicados, y
    anota lo que haya cambiado.

    Args:
        conn: Conexión (la pone el gestor de la base de datos; él hace el commit).
        media_ids: Elementos cuyos archivos hay que comprobar (las tarjetas visibles).
        check_folders: Mirar también qué carpetas ya no están en el disco y marcar sus
            archivos como ausentes (con la ventana activa).

    Returns:
        Lo que ha cambiado (para repintar solo esas tarjetas).
    """
    changes: dict[int, int] = {}

    # 1. Ubicaciones: ¿existe su carpeta raíz?
    locations: dict[int, tuple[Path, bool]] = {}
    switched: list[int] = []
    for location_id, absolute_path, is_online in conn.execute(
        "SELECT id, absolute_path, is_online FROM storage_locations"
    ).fetchall():
        root = Path(absolute_path)
        try:
            online = root.is_dir()
        except OSError:
            online = False
        locations[location_id] = (root, online)
        if online != bool(is_online):
            conn.execute(
                "UPDATE storage_locations SET is_online = ? WHERE id = ?",
                (1 if online else 0, location_id),
            )
            switched.append(location_id)

    # Si una ubicación se conectó o desconectó, cambian TODOS sus elementos
    for location_id in switched:
        online = locations[location_id][1]
        for media_id, is_missing in conn.execute(
            "SELECT id, is_missing FROM media_items WHERE storage_location_id = ?",
            (location_id,),
        ):
            if not online:
                changes[media_id] = OFFLINE
            else:
                changes[media_id] = MISSING if is_missing else AVAILABLE

    # 2. Carpetas que ya no están en el disco: sus archivos, ausentes. Antes que los
    #    archivos pedidos, para que los de esas carpetas no se cuenten dos veces
    missing_folders = _mark_missing_folders(conn, changes) if check_folders else []

    # 3. Archivos pedidos (de ubicaciones conectadas)
    rescan_needed = 0
    ids = [int(media_id) for media_id in media_ids]
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            "SELECT id, storage_location_id, relative_path, is_missing, file_size, "
            f"file_mtime_ns FROM media_items WHERE id IN ({marks})",
            chunk,
        ).fetchall()
        for media_id, location_id, relative_path, is_missing, size, mtime_ns in rows:
            root, online = locations.get(location_id, (None, False))
            if root is None or not online:
                continue  # sin conexión: no se sabe nada de sus archivos
            try:
                info = os.stat(root / relative_path)
            except FileNotFoundError:
                if not is_missing:
                    conn.execute("UPDATE media_items SET is_missing = 1 WHERE id = ?", (media_id,))
                    changes[media_id] = MISSING
                continue
            except OSError:
                continue  # error de acceso puntual: mejor no concluir nada

            if is_missing:
                if (info.st_size, info.st_mtime_ns) == (size, mtime_ns):
                    conn.execute("UPDATE media_items SET is_missing = 0 WHERE id = ?", (media_id,))
                else:
                    # Ha vuelto, pero cambiado: lo mismo que hace el escáner con un
                    # archivo modificado (BLOQUE A + pendiente de releer)
                    conn.execute(
                        """UPDATE media_items SET is_missing = 0,
                                  file_size = ?, file_mtime_ns = ?,
                                  hash_partial = NULL, hash_full = NULL, hash_verified_at = NULL,
                                  thumbnail_status = 0, thumbnail_mtime_ns = NULL,
                                  scan_version = 0
                            WHERE id = ?""",
                        (info.st_size, info.st_mtime_ns, media_id),
                    )
                    rescan_needed += 1
                changes[media_id] = AVAILABLE

    return AvailabilityCheck(changes, rescan_needed, tuple(switched), tuple(missing_folders))


def _mark_missing_folders(
    conn: sqlite3.Connection, changes: dict[int, int]
) -> list[tuple[int, str]]:
    """Marca como ausentes los archivos de las carpetas que ya no están en el disco.

    Solo en las ubicaciones conectadas y con las precauciones de 'find_missing_folders'
    (que el sistema diga que no existe; nada con la raíz vacía). Nada mientras haya una
    operación con archivos a medias (ver la cabecera). Apunta en 'changes' los archivos
    marcados.

    Returns:
        Las carpetas (ubicación, ruta relativa) con algún archivo recién marcado.
    """
    if conn.execute("SELECT 1 FROM file_operations LIMIT 1").fetchone() is not None:
        return []
    found: list[tuple[int, str]] = []
    for location in fetch_folder_tree(conn):
        if not location.is_online:
            continue
        for folder in _topmost_missing(location.root):
            # Lo de dentro, por RANGO ('carpeta/' <= ruta < 'carpeta0'), como el resto del
            # catálogo: sin comodines y usando el índice
            marked = conn.execute(
                """UPDATE media_items SET is_missing = 1
                    WHERE storage_location_id = ? AND is_missing = 0
                      AND relative_path >= ? AND relative_path < ?
                RETURNING id""",
                (location.location_id, f"{folder}/", f"{folder}0"),
            ).fetchall()
            if marked:
                changes.update((int(media_id), MISSING) for (media_id,) in marked)
                found.append((location.location_id, folder))
    return found


def _topmost_missing(node: FolderNode) -> list[str]:
    """Las carpetas marcadas como que faltan (las de más arriba: no se mira por dentro)."""
    if node.is_missing:
        return [node.relative_path]
    return [path for child in node.children for path in _topmost_missing(child)]


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria y carpetas temporales.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.availability
    import tempfile

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    with tempfile.TemporaryDirectory() as tmp:
        disk = Path(tmp) / "Disco"
        disk.mkdir()
        for name in ("a.jpg", "b.jpg"):
            (disk / name).write_bytes(b"x" * 10)

        db = sqlite3.connect(":memory:")
        configure_connection(db)
        apply_migrations(db)
        db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('D', ?)", (str(disk),))
        for name in ("a.jpg", "b.jpg"):
            info = (disk / name).stat()
            db.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       media_type, mime_type, file_size, file_mtime_ns, title, rating,
                       scan_version, thumbnail_status)
                   VALUES (1, ?, ?, 'photo', 'image/jpeg', ?, ?, ?, 4, 6, 1)""",
                (name, name, info.st_size, info.st_mtime_ns, name),
            )
        ids = dict(db.execute("SELECT relative_path, id FROM media_items"))

        # 1. Todo en su sitio: nada cambia
        assert check_availability(db, list(ids.values())) == AvailabilityCheck()

        # 2. Se borra un archivo visible: pasa a ausente (sin tocar su valoración)
        (disk / "a.jpg").unlink()
        result = check_availability(db, [ids["a.jpg"]])
        assert result.changes == {ids["a.jpg"]: MISSING}, result
        assert db.execute("SELECT is_missing, rating FROM media_items WHERE id = ?",
                          (ids["a.jpg"],)).fetchone() == (1, 4)  # fmt: skip
        assert check_availability(db, [ids["a.jpg"]]).changes == {}  # ya constaba

        # 3. Un archivo que no se pide no se comprueba (solo los visibles)
        (disk / "b.jpg").unlink()
        assert check_availability(db, [ids["a.jpg"]]).changes == {}

        # 4. Se desconecta el disco: todos sus elementos, sin conexión
        disk.rename(Path(tmp) / "Fuera")
        result = check_availability(db, [ids["b.jpg"]])
        assert result.changes == {ids["a.jpg"]: OFFLINE, ids["b.jpg"]: OFFLINE}, result
        assert result.switched_locations == (1,), result
        assert db.execute("SELECT is_online FROM storage_locations").fetchone()[0] == 0
        assert check_availability(db).switched_locations == ()  # ya constaba

        # 5. Se vuelve a conectar: cada uno recupera su estado (a.jpg seguía ausente)
        (Path(tmp) / "Fuera").rename(disk)
        result = check_availability(db)
        assert result.changes == {ids["a.jpg"]: MISSING, ids["b.jpg"]: AVAILABLE}, result
        assert result.switched_locations == (1,), result

        # 5b. Una ubicación sin archivos también avisa (el árbol la muestra atenuada)
        empty = Path(tmp) / "Vacio"
        empty.mkdir()
        db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('V', ?)", (str(empty),))
        empty_id = db.execute("SELECT id FROM storage_locations WHERE name = 'V'").fetchone()[0]
        empty.rmdir()
        result = check_availability(db)
        assert result.changes == {} and result.switched_locations == (empty_id,), result

        # 6. Vuelve un archivo ausente, pero distinto: presente y pendiente de releer
        (disk / "a.jpg").write_bytes(b"y" * 20)
        result = check_availability(db, [ids["a.jpg"], ids["b.jpg"]])
        assert result.changes == {ids["a.jpg"]: AVAILABLE, ids["b.jpg"]: MISSING}, result
        assert result.rescan_needed == 1
        row = db.execute(
            "SELECT is_missing, file_size, scan_version, thumbnail_status, rating "
            "FROM media_items WHERE id = ?", (ids["a.jpg"],)
        ).fetchone()
        assert row == (0, 20, 0, 0, 4), row

        # 7. Carpetas que ya no están en el disco (CAT 6.2b): sus archivos, ausentes
        for folder, name in (("Sub", "c.jpg"), ("Sub/Deep", "d.jpg"), ("Otra", "e.jpg")):
            (disk / folder).mkdir(parents=True, exist_ok=True)
            (disk / folder / name).write_bytes(b"z")
            db.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       media_type, mime_type, file_size, file_mtime_ns, title)
                   VALUES (1, ?, ?, 'photo', 'image/jpeg', 1, 0, ?)""",
                (f"{folder}/{name}", name, name),
            )
        ids = dict(db.execute("SELECT relative_path, id FROM media_items"))
        assert check_availability(db, (), True).missing_folders == ()  # todo en su sitio
        import shutil

        shutil.rmtree(disk / "Sub")
        assert check_availability(db, ()).changes == {}  # sin pedirlo, no se mira
        # Con una operación con archivos a medias, tampoco (renombrar una carpeta)
        db.execute(
            """INSERT INTO file_operations(batch_id, kind, source_location_id, source_path,
                   target_location_id, target_path) VALUES (1, 'folder', 1, 'Sub', 1, 'Sub2')"""
        )
        assert check_availability(db, (), True) == AvailabilityCheck()
        db.execute("DELETE FROM file_operations")
        result = check_availability(db, [ids["Otra/e.jpg"], ids["Sub/c.jpg"]], True)
        assert result.changes == {ids["Sub/c.jpg"]: MISSING, ids["Sub/Deep/d.jpg"]: MISSING}, result
        assert result.missing_folders == ((1, "Sub"),), result
        assert db.execute("SELECT is_missing FROM media_items WHERE id = ?",
                          (ids["Otra/e.jpg"],)).fetchone() == (0,)  # fmt: skip
        assert check_availability(db, (), True) == AvailabilityCheck()  # ya constaban
        # Con la ubicación vacía (un disco desmontado que deja su carpeta): nada
        shutil.rmtree(disk)
        disk.mkdir()
        db.execute("UPDATE media_items SET is_missing = 0")
        assert check_availability(db, (), True).changes == {}
        db.close()
    print("Autoprueba finalizada correctamente.")
