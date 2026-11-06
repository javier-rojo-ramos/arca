"""Guardado en la base de datos de lo que entrega el escáner de carpetas.

Este módulo NO depende de Qt: es Python puro. Sus funciones reciben una conexión
sqlite3 como primer parámetro y NO hacen 'commit' (lo hace quien las llama, por
lotes). Las orquesta 'folder_importer.add_folder()'.

Qué hace con cada archivo que entrega el escáner ('ScanCandidate'):

    - NUEVO (no está en 'media_items')          -> se inserta.
    - SIN CAMBIOS (mismo tamaño y misma fecha
      de modificación)                          -> no se toca. Es la comprobación
        barata: no hay que leer el archivo. El hash NO sirve para esto, porque
        obligaría a leer cada archivo en cada reescaneo.
    - CAMBIADO (distinto tamaño o fecha)        -> se actualizan sus datos de
        archivo y se deja "pendiente de procesar": 'scan_version = 0' (la fase de
        metadatos lo volverá a leer), miniatura pendiente y hashes borrados
        (ya no valen).
    - SOLO CAMBIÓ SU SIDECAR .xmp (otro programa,
      p. ej. Lightroom, lo modificó)            -> se anota la fecha nueva del sidecar
        y se deja pendiente de releer los metadatos ('scan_version = 0'). El archivo
        no cambió: su miniatura y sus hashes siguen valiendo. Se cuenta como cambiado.
    - REAPARECIDO (estaba marcado 'is_missing'
      y el archivo sigue igual)                 -> se vuelve a marcar como presente.

Biblioteca ('library'): se guarda al insertar y, en los que ya existían, se corrige si el
candidato trae otra (p. ej. su carpeta se ha declarado de otra biblioteca). Un candidato
SIN biblioteca (None: vídeo en una carpeta automática) nunca borra la que ya tenga: así
no se pierde una clasificación hecha más tarde (pasos 2b y 2c). Una biblioteca corregida
a mano ('library_manual = 1') no se cambia nunca. Se cuenta aparte ('reclassified'),
independientemente de si el archivo cambió o no.

Propietario de las columnas (ver catalog_schema.py): este módulo solo escribe el
BLOQUE A (archivo en disco) y el 'title' inicial de las filas nuevas. NUNCA toca
los datos del usuario (BLOQUE C: valoración, marcas, etiquetas, notas...), así que
un reescaneo no pierde nada. Tampoco modifica los metadatos ya extraídos (BLOQUE B).

Archivos desaparecidos: tras un escaneo COMPLETO, los archivos que estaban en la
base de datos dentro de la carpeta escaneada pero ya no se han visto se marcan
'is_missing = 1' (nunca se borran filas: así no se pierden valoraciones si el
disco estaba desconectado). Para saber cuáles se han visto sin guardar todas las
rutas en memoria, se usa una tabla temporal de SQLite (solo existe en la
conexión, no se guarda en el catálogo).

1.3.0 No se cambia una biblioteca corregida a mano ('library_manual').
1.2.0 Biblioteca de cada elemento ('ScanCandidate.library'): al insertar y al corregirla.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.catalog_writer
"""

__version__ = "1.3.0"
__all__ = [
    "MAX_BATCH_SIZE",
    "BatchResult",
    "count_active_items",
    "mark_missing",
    "record_seen_paths",
    "replace_walk_issues",
    "reset_seen_paths",
    "save_candidates",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Módulos del proyecto
from core.catalog.folder_scanner import SCAN_STAGE_WALK, ScanCandidate, ScanIssue

# Máximo de candidatos por lote. Las versiones antiguas de SQLite solo admiten 999
# parámetros por consulta y la consulta de existentes usa uno por archivo (+1).
MAX_BATCH_SIZE = 900


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Qué ha pasado con los archivos de un lote.

    Attributes:
        new: Filas insertadas.
        changed: Filas actualizadas porque el archivo cambió (tamaño o fecha).
        revived: Filas marcadas de nuevo como presentes (archivo que reapareció).
        unchanged: Filas que no han necesitado ningún cambio (en el archivo).
        reclassified: Filas que ya existían y han cambiado de biblioteca. Se cuentan
            APARTE: una fila puede estar a la vez sin cambios y reclasificada.
    """

    new: int = 0
    changed: int = 0
    revived: int = 0
    unchanged: int = 0
    reclassified: int = 0

    def __add__(self, other: "BatchResult") -> "BatchResult":
        """Suma dos resultados (para acumular los lotes de un escaneo)."""
        return BatchResult(
            self.new + other.new,
            self.changed + other.changed,
            self.revived + other.revived,
            self.unchanged + other.unchanged,
            self.reclassified + other.reclassified,
        )


# -----------------------------------------------------------------------------
# Guardado de candidatos
# -----------------------------------------------------------------------------


def save_candidates(
    conn: sqlite3.Connection, location_id: int, candidates: Sequence[ScanCandidate]
) -> BatchResult:
    """Inserta o actualiza en 'media_items' un lote de candidatos.

    No hace 'commit'. Abre la transacción con 'BEGIN IMMEDIATE' (si no hay una ya
    abierta) para que la consulta de "qué existe ya" y la escritura posterior
    vean lo mismo aunque otra tarea esté escribiendo a la vez.

    Args:
        conn: Conexión sqlite3 (con o sin 'row_factory').
        location_id: Id de la ubicación de almacenamiento ('storage_locations').
        candidates: Lote de candidatos (máximo 'MAX_BATCH_SIZE').

    Returns:
        Cuántos archivos eran nuevos, cambiados, reaparecidos o sin cambios.

    Raises:
        ValueError: Si el lote supera 'MAX_BATCH_SIZE'.
        sqlite3.Error: Si falla la base de datos.
    """
    if not candidates:
        return BatchResult()
    if len(candidates) > MAX_BATCH_SIZE:
        raise ValueError(f"El lote es demasiado grande (máximo {MAX_BATCH_SIZE}).")

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    # 1. Qué archivos del lote ya están en la base de datos (ruta -> datos actuales).
    #    Se accede por posición (no por nombre) para funcionar con cualquier row_factory.
    placeholders = ",".join("?" * len(candidates))
    existing: dict[str, tuple[int, int, int, int, int | None, str | None, int]] = {
        row[0]: (row[1], row[2], row[3], row[4], row[5], row[6], row[7])
        for row in conn.execute(
            "SELECT relative_path, id, file_size, file_mtime_ns, is_missing, sidecar_mtime_ns, "
            "library, library_manual "
            f"FROM media_items WHERE storage_location_id = ? "
            f"AND relative_path IN ({placeholders})",
            (location_id, *(candidate.relative_path for candidate in candidates)),
        )
    }

    # 2. Se clasifica cada candidato
    to_insert: list[tuple] = []
    to_update: list[tuple] = []
    to_revive: list[tuple] = []
    to_reread: list[tuple] = []  # solo cambió el sidecar
    to_reclassify: list[tuple] = []  # cambia de biblioteca (aparte de lo anterior)
    unchanged = 0
    for candidate in candidates:
        found = existing.get(candidate.relative_path)
        if found is None:
            to_insert.append(
                (
                    location_id,
                    candidate.relative_path,
                    candidate.file_name,
                    candidate.file_extension,
                    candidate.media_type,  # StrEnum: SQLite lo recibe como texto
                    candidate.mime_type,
                    candidate.file_size,
                    candidate.file_mtime_ns,
                    candidate.file_created_at,
                    candidate.default_title,
                    candidate.sidecar_mtime_ns,
                    candidate.library,
                )
            )
            continue

        item_id, size, mtime_ns, is_missing, sidecar_mtime_ns, library, library_manual = found
        # Biblioteca: solo se corrige si el candidato trae una, es distinta y no la ha
        # elegido el usuario a mano (None no borra nada)
        if candidate.library is not None and candidate.library != library and not library_manual:
            to_reclassify.append((candidate.library, item_id))
        if size != candidate.file_size or mtime_ns != candidate.file_mtime_ns:
            to_update.append(
                (
                    candidate.file_name,
                    candidate.file_extension,
                    candidate.media_type,
                    candidate.mime_type,
                    candidate.file_size,
                    candidate.file_mtime_ns,
                    candidate.file_created_at,
                    candidate.sidecar_mtime_ns,
                    item_id,
                )
            )
        elif sidecar_mtime_ns != candidate.sidecar_mtime_ns:
            to_reread.append((candidate.sidecar_mtime_ns, item_id))
        elif is_missing:
            to_revive.append((item_id,))
        else:
            unchanged += 1

    # 3. Escritura. Solo columnas del BLOQUE A (y 'title' al insertar).
    conn.executemany(
        """INSERT INTO media_items(storage_location_id, relative_path, file_name,
               file_extension, media_type, mime_type, file_size, file_mtime_ns,
               file_created_at, title, sidecar_mtime_ns, library)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        to_insert,
    )
    # Un archivo cambiado queda "pendiente de procesar": los hashes y la miniatura
    # antiguos ya no valen, y scan_version = 0 hace que la fase de metadatos lo relea.
    conn.executemany(
        """UPDATE media_items SET
               file_name = ?, file_extension = ?, media_type = ?, mime_type = ?,
               file_size = ?, file_mtime_ns = ?, file_created_at = ?, sidecar_mtime_ns = ?,
               hash_partial = NULL, hash_full = NULL, hash_verified_at = NULL,
               is_missing = 0,
               thumbnail_status = 0, thumbnail_mtime_ns = NULL,
               scan_version = 0
           WHERE id = ?""",
        to_update,
    )
    conn.executemany("UPDATE media_items SET is_missing = 0 WHERE id = ?", to_revive)
    # Solo cambió el sidecar: se releen los metadatos, pero la miniatura sigue valiendo
    conn.executemany(
        "UPDATE media_items SET sidecar_mtime_ns = ?, is_missing = 0, scan_version = 0 "
        "WHERE id = ?",
        to_reread,
    )
    conn.executemany("UPDATE media_items SET library = ? WHERE id = ?", to_reclassify)

    return BatchResult(
        new=len(to_insert),
        changed=len(to_update) + len(to_reread),
        revived=len(to_revive),
        unchanged=unchanged,
        reclassified=len(to_reclassify),
    )


# -----------------------------------------------------------------------------
# Detección de archivos desaparecidos
# -----------------------------------------------------------------------------


def reset_seen_paths(conn: sqlite3.Connection) -> None:
    """Prepara (o vacía) la tabla temporal donde se anotan las rutas vistas.

    Llamar una vez al empezar cada escaneo. La tabla es TEMPORAL: solo existe en
    esta conexión y no se guarda en el catálogo. No hace 'commit'.
    """
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS scan_seen_paths "
        "(relative_path TEXT PRIMARY KEY) WITHOUT ROWID;"
    )
    conn.execute("DELETE FROM scan_seen_paths;")


def record_seen_paths(conn: sqlite3.Connection, relative_paths: Iterable[str]) -> None:
    """Anota las rutas que el escaneo ha visto (incluidas las que no han cambiado).

    No hace 'commit'. Requiere haber llamado antes a 'reset_seen_paths'.
    """
    conn.executemany(
        "INSERT OR IGNORE INTO scan_seen_paths(relative_path) VALUES (?)",
        ((path,) for path in relative_paths),
    )


def count_active_items(
    conn: sqlite3.Connection, location_id: int, relative_folder: str
) -> int:
    """Cuenta las filas presentes (no marcadas como desaparecidas) bajo una carpeta."""
    scope_sql, scope_params = _under_prefix("relative_path", relative_folder)
    row = conn.execute(
        "SELECT COUNT(*) FROM media_items "
        f"WHERE storage_location_id = ? AND is_missing = 0 AND {scope_sql}",
        (location_id, *scope_params),
    ).fetchone()
    return int(row[0])


def mark_missing(
    conn: sqlite3.Connection,
    location_id: int,
    relative_folder: str,
    unreadable_paths: Iterable[str],
) -> int:
    """Marca 'is_missing = 1' los archivos de la carpeta que el escaneo no ha visto.

    SOLO debe llamarse tras un escaneo completo y fiable (ver 'add_folder'). No
    hace 'commit'. Nunca se marca nada fuera de 'relative_folder', ni nada que
    esté en (o debajo de) una ruta que no se pudo leer: si una carpeta no se pudo
    abrir, sus archivos no se han visto pero tampoco han desaparecido.

    Args:
        conn: Conexión sqlite3.
        location_id: Id de la ubicación de almacenamiento.
        relative_folder: Carpeta escaneada, relativa a la ubicación ('' = toda).
        unreadable_paths: Rutas relativas que dieron error de lectura al escanear.

    Returns:
        Número de filas marcadas como desaparecidas.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS scan_unreadable_paths "
        "(path TEXT PRIMARY KEY) WITHOUT ROWID;"
    )
    conn.execute("DELETE FROM scan_unreadable_paths;")
    conn.executemany(
        "INSERT OR IGNORE INTO scan_unreadable_paths(path) VALUES (?)",
        ((path,) for path in unreadable_paths),
    )

    scope_sql, scope_params = _under_prefix("relative_path", relative_folder)
    cursor = conn.execute(
        f"""UPDATE media_items SET is_missing = 1
            WHERE storage_location_id = ? AND is_missing = 0 AND {scope_sql}
              -- no se ha visto en este escaneo...
              AND NOT EXISTS (SELECT 1 FROM scan_seen_paths seen
                              WHERE seen.relative_path = media_items.relative_path)
              -- ...y no está en una ruta ilegible (ni debajo de una carpeta ilegible)
              AND NOT EXISTS (SELECT 1 FROM scan_unreadable_paths bad
                              WHERE media_items.relative_path = bad.path
                                 OR (media_items.relative_path >= bad.path || '/'
                                     AND media_items.relative_path < bad.path || '0'))""",
        (location_id, *scope_params),
    )
    return cursor.rowcount


# -----------------------------------------------------------------------------
# Errores de lectura
# -----------------------------------------------------------------------------


def replace_walk_issues(
    conn: sqlite3.Connection,
    location_id: int,
    relative_folder: str,
    issues: Iterable[ScanIssue],
    *,
    clear_previous: bool,
) -> None:
    """Guarda en 'scan_errors' los problemas de lectura del recorrido.

    No hace 'commit'.

    Args:
        conn: Conexión sqlite3.
        location_id: Id de la ubicación de almacenamiento.
        relative_folder: Carpeta escaneada, relativa a la ubicación ('' = toda).
        issues: Problemas encontrados en este escaneo.
        clear_previous: Si es True, antes se borran los errores de recorrido
            anteriores de esa carpeta: así un problema ya resuelto desaparece de
            la lista. Debe ser False si el escaneo se canceló (no se vio todo).
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    if clear_previous:
        scope_sql, scope_params = _under_prefix("relative_path", relative_folder)
        conn.execute(
            "DELETE FROM scan_errors "
            f"WHERE storage_location_id = ? AND stage = ? AND {scope_sql}",
            (location_id, SCAN_STAGE_WALK, *scope_params),
        )

    # Una fila por archivo y fase: si el problema se repite, se actualiza la existente
    conn.executemany(
        """INSERT INTO scan_errors(storage_location_id, relative_path, stage, message)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(storage_location_id, relative_path, stage)
           DO UPDATE SET message = excluded.message, occurred_at = CURRENT_TIMESTAMP""",
        (
            (location_id, issue.relative_path, issue.stage, issue.message)
            for issue in issues
        ),
    )


# -----------------------------------------------------------------------------
# Utilidades internas
# -----------------------------------------------------------------------------


def _under_prefix(column: str, prefix: str) -> tuple[str, tuple[str, ...]]:
    """Condición SQL "la ruta es la carpeta 'prefix' o está debajo de ella".

    Se usa una comparación por rango ('prefix/' <= ruta < 'prefix0', porque '0' es
    el carácter que sigue a '/') en lugar de LIKE: LIKE no distingue mayúsculas
    de minúsculas y trata '%' y '_' como comodines, algo muy frecuente en nombres
    de carpetas. El rango además aprovecha el índice del UNIQUE de 'media_items'.
    Una carpeta 'ab' NO queda dentro de 'a'.

    Args:
        column: Nombre de la columna con la ruta relativa.
        prefix: Carpeta relativa a la ubicación; '' significa "toda la ubicación".

    Returns:
        Fragmento SQL y sus parámetros.
    """
    if not prefix:
        return "1 = 1", ()
    return (
        f"({column} = ? OR ({column} >= ? AND {column} < ?))",
        (prefix, prefix + "/", prefix + "0"),
    )


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria (no toca el disco).
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.catalog_writer
    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.media_types import MediaType

    def make_candidate(
        relative_path: str, size: int = 10, mtime: int = 1, sidecar: int | None = None
    ) -> ScanCandidate:
        """Crea un candidato falso (solo importan los campos que guarda la BD)."""
        name = relative_path.rsplit("/", 1)[-1]
        return ScanCandidate(
            path=Path("/ubicacion") / relative_path,
            relative_path=relative_path,
            file_name=name,
            file_extension="jpg",
            media_type=MediaType.PHOTO,
            mime_type="image/jpeg",
            file_size=size,
            file_mtime_ns=mtime,
            file_created_at=None,
            sidecar_mtime_ns=sidecar,
        )

    def state(path: str) -> tuple:
        """Devuelve (is_missing, scan_version, rating, hash_partial) de una fila."""
        return connection.execute(
            "SELECT is_missing, scan_version, rating, hash_partial FROM media_items "
            "WHERE relative_path = ?",
            (path,),
        ).fetchone()

    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    apply_migrations(connection)
    connection.execute(
        "INSERT INTO storage_locations(name, absolute_path) VALUES ('Prueba', '/ubicacion')"
    )
    connection.commit()

    # 1. Archivos nuevos
    batch = [make_candidate(p) for p in ("a/1.jpg", "a/2.jpg", "ab/3.jpg", "b/4.jpg")]
    result = save_candidates(connection, 1, batch)
    connection.commit()
    print("Primer guardado:", result)
    assert result == BatchResult(new=4)
    title = connection.execute(
        "SELECT title FROM media_items WHERE relative_path = 'a/1.jpg'"
    ).fetchone()[0]
    assert title == "1"  # nombre sin extensión

    # 2. Mismo lote otra vez: nada cambia (comprobación por tamaño + fecha)
    result = save_candidates(connection, 1, batch)
    connection.commit()
    assert result == BatchResult(unchanged=4)

    # 3. Un archivo cambia: se invalida lo derivado, pero se conserva lo del usuario
    connection.execute(
        "UPDATE media_items SET rating = 4, hash_partial = 'abc', scan_version = 5, "
        "thumbnail_status = 1 WHERE relative_path = 'a/1.jpg'"
    )
    connection.commit()
    result = save_candidates(connection, 1, [make_candidate("a/1.jpg", size=99, mtime=2)])
    connection.commit()
    assert result == BatchResult(changed=1)
    # is_missing=0, scan_version=0 (a reprocesar), rating=4 (intacto), hash borrado
    assert state("a/1.jpg") == (0, 0, 4, None)
    thumb = connection.execute(
        "SELECT thumbnail_status FROM media_items WHERE relative_path = 'a/1.jpg'"
    ).fetchone()[0]
    assert thumb == 0
    print("Archivo cambiado: reprocesable y con la valoración intacta")

    # 4. Desaparecidos: solo dentro de la carpeta escaneada ('a'), y 'ab' NO cuenta
    reset_seen_paths(connection)
    record_seen_paths(connection, ["a/1.jpg"])  # 'a/2.jpg' no se ha visto
    missing = mark_missing(connection, 1, "a", unreadable_paths=[])
    connection.commit()
    print("Marcados como desaparecidos:", missing)
    assert missing == 1
    assert state("a/2.jpg")[0] == 1
    assert state("ab/3.jpg")[0] == 0 and state("b/4.jpg")[0] == 0  # fuera de 'a'

    # 5. Reaparece sin cambios: se marca de nuevo como presente
    result = save_candidates(connection, 1, [make_candidate("a/2.jpg")])
    connection.commit()
    assert result == BatchResult(revived=1) and state("a/2.jpg")[0] == 0

    # 6. Carpeta ilegible: lo que hay debajo NO se marca como desaparecido
    save_candidates(connection, 1, [make_candidate("c/sub/5.jpg"), make_candidate("c/6.jpg")])
    reset_seen_paths(connection)
    missing = mark_missing(connection, 1, "", unreadable_paths=["c/sub"])
    connection.commit()
    assert state("c/sub/5.jpg")[0] == 0  # protegido por estar bajo 'c/sub'
    assert state("c/6.jpg")[0] == 1  # no visto y legible: sí desaparece
    print("Carpeta ilegible protegida; marcados en total esta vez:", missing)

    # 7. Recuento de presentes bajo una carpeta. En el paso 6 no se anotó ninguna
    #    ruta como vista, así que todo quedó desaparecido salvo lo protegido.
    assert count_active_items(connection, 1, "c") == 1  # solo c/sub/5.jpg
    assert count_active_items(connection, 1, "c/sub") == 1
    assert count_active_items(connection, 1, "a") == 0
    assert count_active_items(connection, 1, "") == 1

    # 8. Errores de recorrido: se reemplazan los anteriores de la carpeta
    old = ScanIssue("a/x", SCAN_STAGE_WALK, "viejo")
    new = ScanIssue("a/y", SCAN_STAGE_WALK, "nuevo")
    replace_walk_issues(connection, 1, "a", [old], clear_previous=True)
    replace_walk_issues(connection, 1, "a", [new], clear_previous=True)  # 'old' ya no ocurre
    replace_walk_issues(connection, 1, "a", [new], clear_previous=True)  # repetir no duplica
    connection.commit()
    errors = connection.execute("SELECT relative_path, message FROM scan_errors").fetchall()
    assert errors == [("a/y", "nuevo")]

    # 9. Solo cambia el sidecar .xmp (otro programa lo editó): se releen los metadatos,
    #    pero la miniatura y el hash siguen valiendo
    save_candidates(connection, 1, [make_candidate("r/raw.nef", sidecar=None)])
    connection.execute(
        "UPDATE media_items SET scan_version = 5, thumbnail_status = 1, hash_partial = 'h' "
        "WHERE relative_path = 'r/raw.nef'"
    )
    result = save_candidates(connection, 1, [make_candidate("r/raw.nef", sidecar=777)])
    connection.commit()
    assert result == BatchResult(changed=1)
    row = connection.execute(
        "SELECT scan_version, thumbnail_status, hash_partial, sidecar_mtime_ns "
        "FROM media_items WHERE relative_path = 'r/raw.nef'"
    ).fetchone()
    assert tuple(row) == (0, 1, "h", 777), row
    assert save_candidates(connection, 1, [make_candidate("r/raw.nef", sidecar=777)]) == (
        BatchResult(unchanged=1)
    )
    print("Sidecar modificado fuera: metadatos a releer, miniatura intacta")

    # 10. Biblioteca: se guarda al insertar, se corrige si cambia y None nunca la borra
    from dataclasses import replace

    lib = replace(make_candidate("l/clip.mp4"), library="image")
    assert save_candidates(connection, 1, [lib]) == BatchResult(new=1)
    assert connection.execute(
        "SELECT library FROM media_items WHERE relative_path = 'l/clip.mp4'"
    ).fetchone() == ("image",)
    moved = replace(lib, library="video")  # su carpeta se declara de películas
    assert save_candidates(connection, 1, [moved]) == BatchResult(unchanged=1, reclassified=1)
    unknown = replace(lib, library=None)  # carpeta automática: no sabe qué es
    assert save_candidates(connection, 1, [unknown]) == BatchResult(unchanged=1)
    assert connection.execute(
        "SELECT library FROM media_items WHERE relative_path = 'l/clip.mp4'"
    ).fetchone() == ("video",)
    # ...y la elegida a mano no la cambia ningún reescaneo
    connection.execute(
        "UPDATE media_items SET library = 'image', library_manual = 1 "
        "WHERE relative_path = 'l/clip.mp4'"
    )
    assert save_candidates(connection, 1, [moved]) == BatchResult(unchanged=1)
    connection.commit()
    print("Biblioteca: guardada, corregida, nunca borrada sin motivo y respetada si es manual")

    # 11. Un lote demasiado grande se rechaza
    try:
        save_candidates(connection, 1, [make_candidate(f"z/{i}.jpg") for i in range(MAX_BATCH_SIZE + 1)])
    except ValueError:
        print("Lote demasiado grande rechazado")
    else:
        raise AssertionError("Debería rechazar lotes de más de MAX_BATCH_SIZE")

    connection.close()
    print("Autoprueba finalizada correctamente.")
