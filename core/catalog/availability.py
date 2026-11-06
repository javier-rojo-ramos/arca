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
    - SOLO los archivos que se le piden (normalmente, las tarjetas visibles: unas
      decenas). Lo que no está a la vista se actualizará al verse o al reescanear.

Qué hace con cada archivo comprobado (de una ubicación conectada):
    - No está y constaba como presente   -> 'is_missing = 1' (ausente).
    - Está y constaba como ausente:
        * igual que antes (tamaño y fecha) -> 'is_missing = 0' (ha vuelto).
        * distinto                         -> 'is_missing = 0' y queda pendiente de
          releer, igual que cuando lo detecta el escáner (metadatos, miniatura y hashes).
Nunca toca los datos del usuario.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.availability
"""

__version__ = "1.0.0"
__all__ = ["AvailabilityCheck", "check_availability"]

# Librerías estándar
import os
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Módulos del proyecto
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
    """

    changes: dict[int, int] = field(default_factory=dict)
    rescan_needed: int = 0


def check_availability(
    conn: sqlite3.Connection, media_ids: Sequence[int] = ()
) -> AvailabilityCheck:
    """Comprueba las ubicaciones y los archivos indicados, y anota lo que haya cambiado.

    Args:
        conn: Conexión (la pone el gestor de la base de datos; él hace el commit).
        media_ids: Elementos cuyos archivos hay que comprobar (las tarjetas visibles).

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

    # 2. Archivos pedidos (de ubicaciones conectadas)
    rescan_needed = 0
    ids = [int(media_id) for media_id in media_ids]
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            "SELECT id, storage_location_id, relative_path, is_missing, file_size, "
            f"file_mtime_ns FROM media_items WHERE id IN ({marks})",  # noqa: S608
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

    return AvailabilityCheck(changes, rescan_needed)


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
        assert db.execute("SELECT is_online FROM storage_locations").fetchone()[0] == 0

        # 5. Se vuelve a conectar: cada uno recupera su estado (a.jpg seguía ausente)
        (Path(tmp) / "Fuera").rename(disk)
        result = check_availability(db)
        assert result.changes == {ids["a.jpg"]: MISSING, ids["b.jpg"]: AVAILABLE}, result

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
        db.close()
    print("Autoprueba finalizada correctamente.")
