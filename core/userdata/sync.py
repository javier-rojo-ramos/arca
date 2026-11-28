"""Sincronización de los datos del usuario entre el catálogo y su destino fuera de él.

Este módulo NO depende de Qt. Une la base de datos con los almacenes externos según la
política de cada formato ('policy.py'). CÓMO se escribe en cada uno lo saben los
escritores ('writers.py': el archivo de carpeta y XMP; ahí se añade uno nuevo); aquí se
decide QUÉ hay pendiente y se anota el resultado en el catálogo.

Dos sentidos:

1. CATÁLOGO -> ARCHIVOS: 'write_pending_user_data' es un "trabajo" (ver
   'core/jobs/progress.py'). Recorre los elementos con algún campo pendiente
   ('user_data_pending', un bit por campo: lo que el usuario ha cambiado y aún no está
   escrito) y deja su destino con los valores de la base de datos, SOLO en los campos
   pendientes (si en la aplicación solo se cambió el color, no se toca la valoración
   que otro programa haya puesto en el archivo):
       XMP_EMBEDDED  -> XMP dentro del archivo (ExifTool)
       XMP_SIDECAR   -> sidecar .xmp del RAW (ExifTool; se crea si no existe)
       FOLDER_FILE   -> entrada del archivo en el '.arca.json' de su carpeta
       AUDIO_TAGS    -> partido (el MP3): sus etiquetas, dentro del archivo
                        ('audio_writer.py'); lo demás, a su entrada del '.arca.json'
   Las palabras clave van igual, con su propia marca ('keywords_pending'): se escriben
   EXACTAMENTE las del catálogo (las rutas asignadas; ver 'xmp_writer' y 'folder_file').
   Los metadatos editados (título, pie, ubicación...; 'editable_fields.py') también, con
   su marca por campo ('metadata_edit_pending'): en XMP, su etiqueta y las antiguas que
   el archivo ya tenga; en el '.arca.json', su clave (vaciado = ""). El título igual al
   nombre del archivo se escribe vacío ('file_title').
   Cuando el destino ya tiene esos valores, quita esos bits de pendiente. Lo que no se
   puede escribir (archivo abierto por otro programa, unidad desconectada, sin
   ExifTool...) sigue pendiente y se reintenta la próxima vez: nunca se pierde, porque
   el dato sigue en la base de datos.
   Un archivo con XMP que AÚN NO SE HA LEÍDO NUNCA ('last_scanned_at' vacío) no se
   escribe: lo que trae todavía no está en el catálogo, y escribir lo del catálogo lo
   borraría (las palabras clave van exactas). Lo pendiente espera a la primera lectura.
   Tras modificar un archivo se actualizan su tamaño y su fecha en la base de datos,
   para que el escáner no lo confunda con un cambio externo (ni regenere la miniatura:
   los píxeles no cambian).

2. ARCHIVOS -> CATÁLOGO (al importar o reescanear). Regla: MANDA EL ARCHIVO, campo a
   campo, salvo en los campos pendientes de escribir (su cambio es más nuevo).
       - XMP: 'apply_file_user_data', que llama el procesador de metadatos con lo que el
         extractor ha leído del archivo (y 'apply_file_keywords' para las palabras clave,
         que dejan exactamente las del archivo; en la PRIMERA lectura, si se asignaron
         palabras antes de leerlo, se suman a las suyas). Un campo que el archivo NO trae (etiqueta
         ausente) no toca el catálogo: "no dice nada" no es "sin estrellas". La
         aplicación escribe siempre el 0 explícito (ver 'xmp_writer.py').
       - Archivo de carpeta: 'apply_folder_files', que llama 'add_folder' tras guardar
         cada lote. Ahí el archivo lo escribe solo esta aplicación y omite los valores
         por defecto, así que una entrada sin un campo SÍ significa "valor por defecto".
         Una carpeta SIN archivo '.arca.json' no toca nada (no se sabe nada de ella).
   Nunca se aplica nada leído a medias: si la lectura se canceló o falló (un sidecar
   ilegible), el extractor no entrega datos del usuario y el catálogo no se toca.
       - Metadatos descriptivos editados (título, pie...; 'editable_fields.py') en los
         formatos FOLDER_FILE: lo que guarda el '.arca.json' manda SIEMPRE (el original
         no se toca). Los aplica 'apply_folder_files' al importar y, tras releer el
         archivo, el procesador con 'folder_file_edits'. En los formatos con XMP, los
         escribe el procesador como cualquier metadato extraído (salvo lo pendiente).

1.13.0 El MP3, partido (MUS 6.2b): con el escritor de sus etiquetas ('audio_writer.py',
       en 'default_writers'). 'WriteItem.reread' (un MP3 con su ID3v2 nuevo): solo se
       releen sus metadatos, y cuenta en 'rescan_requested'. 'exiftool_missing', solo si
       falta ExifTool (sin mutagen, al registro). Autoprueba: ida y vuelta de un MP3.
1.12.0 Con las preguntas separadas de 'policy.py' (MUS 6.2a): esperan a su primera
       lectura los formatos cuyo destino lee el extractor ('first_read_extensions'), y
       el '.arca.json' se aplica a los archivos con entrada en él ('has_folder_entry'),
       solo en los datos que guarda ('folder_file_fields'; también 'folder_file_edits').
       Nada cambia: hoy son los de antes (FOLDER_FILE, con todo).
1.11.0 La primera lectura no borra nada del archivo (docs/PENDIENTE.md, GEN 20, paso 1):
       un archivo con XMP que aún no se ha leído nunca no se escribe ('_PENDING_SQL'), y
       en su primera lectura las palabras clave asignadas antes se SUMAN a las del archivo
       ('apply_file_keywords(first_read=True)'). Antes, asignar una palabra a una foto
       sin leer dejaba en el archivo solo esa.
1.10.0 Un archivo, dos destinos ('writers.split_items'): lo que el escritor de un formato
       no sabe guardar va al '.arca.json'; cada parte quita sus marcas por separado y el
       error de un archivo se anota una vez (docs/PENDIENTE.md, GEN 14, paso 2). Hoy no
       se parte ningún formato.
1.9.0 Los dos caminos de escritura ('_write_folder_items' y '_write_xmp_items') pasan a
      'writers.py', como escritores con una interfaz común ('UserDataWriter');
      'write_pending_user_data' reparte los elementos entre ellos y admite 'writers'
      (docs/PENDIENTE.md, GEN 14). Lo que se escribe no cambia.
1.8.0 Campos editables de una tabla de detalles (la actividad de un track): se leen, se
      escriben en el '.arca.json' y se aplican desde él como los demás ('read_sql',
      '_apply_detail_edit').
1.7.0 El GPS editado se escribe también en los formatos con XMP (el escritor ya sabe: ver
      'xmp_writer.py'); fuera el aplazamiento de la 1.6.0.
1.6.0 GPS editado (números): al '.arca.json' ya; en los formatos con XMP queda pendiente
      (el archivo se aplaza, sin error) hasta que el escritor lo sepa escribir.
1.5.0 Escritura de los metadatos editados ('metadata_edit_pending'): XMP o '.arca.json',
      y su marca se quita como la de la valoración. Autoprueba: ida y vuelta de los
      metadatos editados; los textos con tildes se escriben con un archivo de argumentos
      (en Windows, por la línea de órdenes llegaban como «?») y el '.arca.json' oculto se
      sobrescribe con un temporal (con 'write_text' daba PermissionError).
1.4.0 Metadatos descriptivos editados: 'apply_folder_files' los aplica desde el
      '.arca.json' (salvo los pendientes) y 'folder_file_edits' se los da al procesador.
1.3.2 El archivo de carpeta se llama '.arca.json' (comentarios y autoprueba).
1.3.1 Palabras clave comparadas letra a letra al escribir el '.emc.json' y al dar por
      escrito lo pendiente (renombrar solo con mayúsculas o acentos también se escribe).

Prueba rápida (desde la raíz del proyecto; la parte de XMP necesita ExifTool):
    python -m core.userdata.sync
"""

__version__ = "1.13.0"
__all__ = [
    "SCAN_STAGE_USERDATA",
    "FolderFileCache",
    "UserDataWriteResult",
    "apply_file_keywords",
    "apply_file_user_data",
    "apply_folder_files",
    "count_pending_user_data",
    "folder_file_edits",
    "write_pending_user_data",
]

# Librerías estándar
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.keywords import media_keyword_paths, same_keywords, set_media_keywords
from core.catalog.media_queries import USER_FIELD_BITS
from core.jobs.progress import JobProgress
from core.metadata.exiftool_runner import ExifToolError, ExifToolRunner
from core.metadata.keyword_tags import FileKeywords
from core.userdata.editable_fields import (
    EDITABLE_COLUMNS,
    applies_sql,
    default_title,
    field_for,
    pending_columns,
    read_sql,
    unless_pending_sql,
)
from core.userdata.folder_file import (
    KEYWORDS_KEY,
    FolderData,
    FolderFileError,
    edited_values_from_entry,
    find_entry_key,
    keywords_from_entry,
    read_folder_file,
    user_values_from_entry,
)
from core.userdata.policy import (
    UserDataDestination,
    destination_for,
    first_read_extensions,
    folder_file_fields,
    has_folder_entry,
)
from core.userdata.writers import USER_COLUMNS as _USER_COLUMNS
from core.userdata.writers import (
    UserDataWriter,
    WriteItem,
    XmpFileWriter,
    default_writers,
    split_items,
)

# Nombre de la fase para la columna 'stage' de la tabla 'scan_errors'
SCAN_STAGE_USERDATA = "userdata"

# Elementos por lote (y por transacción corta)
DEFAULT_BATCH_SIZE = 200

# Caché de archivos de carpeta durante un escaneo: carpeta -> contenido (None = ilegible)
FolderFileCache = dict[Path, FolderData | None]


# =============================================================================
# 1. Catálogo -> archivos
# =============================================================================


@dataclass(frozen=True, slots=True)
class UserDataWriteResult:
    """Resultado del trabajo de escritura.

    Attributes:
        total: Elementos pendientes al empezar.
        written: Destinos modificados (archivos, sidecars o entradas de carpeta).
        already_ok: Elementos cuyo destino ya tenía esos valores (no se tocó nada).
        failed: Elementos que no se pudieron escribir (siguen pendientes).
        skipped_offline: Elementos de unidades desconectadas (siguen pendientes).
        cancelled: True si se interrumpió.
        exiftool_missing: True si había XMP que escribir pero ExifTool no está.
        rescan_requested: Archivos que han quedado pendientes de releer sus metadatos: los
            que habían cambiado fuera de la aplicación (p. ej. en Lightroom) y los MP3 a
            los que se les ha creado el ID3v2 (su tipo de etiqueta es otro).
        failed_messages: Algunos motivos de fallo (para el registro y la interfaz).
    """

    total: int = 0
    written: int = 0
    already_ok: int = 0
    failed: int = 0
    skipped_offline: int = 0
    cancelled: bool = False
    exiftool_missing: bool = False
    rescan_requested: int = 0
    failed_messages: tuple[str, ...] = ()

    @property
    def has_warnings(self) -> bool:
        """True si algo se quedó sin escribir."""
        return bool(self.failed or self.exiftool_missing)

    def status_text(self) -> str:
        """Frase corta para la barra de estado ('' si no hay nada que contar).

        Los guardados normales (unos pocos archivos tras cada clic) no se anuncian: solo
        los fallos y las tandas grandes.
        """
        if self.exiftool_missing:
            return "No se pueden guardar los datos en las fotos: falta ExifTool."
        if self.failed:
            return f"No se pudieron guardar los datos en {self.failed} archivos (se reintentará)."
        if self.written >= 20:
            return f"Datos guardados en {self.written} archivos."
        return ""

    def summary(self) -> str:
        """Resumen en varias líneas (para el registro)."""
        lines = [
            f"Pendientes: {self.total}",
            f"Escritos: {self.written}",
            f"Ya estaban al día: {self.already_ok}",
        ]
        if self.failed:
            lines.append(f"Fallidos (siguen pendientes): {self.failed}")
        if self.skipped_offline:
            lines.append(f"En unidades desconectadas (siguen pendientes): {self.skipped_offline}")
        if self.exiftool_missing:
            lines.append("ExifTool no está disponible: los XMP siguen pendientes.")
        if self.cancelled:
            lines.append("Se canceló antes de terminar.")
        return "\n".join(lines)


# Extensiones cuyo destino lee el extractor (hoy, las de XMP), para la consulta (de una
# lista cerrada, 'policy.py': sin inyección)
_FIRST_READ_EXTENSIONS_SQL = ", ".join(
    f"'{extension}'" for extension in sorted(first_read_extensions())
)

# Elementos con algo pendiente de escribir fuera del catálogo (presentes en disco), salvo
# los archivos cuyo destino lee el extractor y que no se han leído NUNCA
# ('policy.waits_for_first_read'): 'last_scanned_at' solo lo pone la lectura de metadatos
# (también si falla o el formato no se puede leer), así que vacío = lo que trae el archivo
# aún no está en el catálogo. Esperan a su primera lectura, que respeta lo pendiente (y
# suma las palabras clave), y después se escriben como los demás
_PENDING_SQL = (
    "(user_data_pending <> 0 OR keywords_pending <> 0 OR metadata_edit_pending <> 0) "
    "AND is_missing = 0 "
    "AND NOT (last_scanned_at IS NULL "
    f"AND COALESCE(file_extension, '') IN ({_FIRST_READ_EXTENSIONS_SQL}))"
)


def count_pending_user_data(conn: sqlite3.Connection) -> int:
    """Cuántos elementos (presentes) tienen datos del usuario sin escribir fuera del catálogo.

    Cuenta también los metadatos editados (título, pie...) y las palabras clave. No cuenta
    los archivos con XMP que aún no se han leído nunca: esperan a su primera lectura.
    """
    row = conn.execute(f"SELECT COUNT(*) FROM media_items WHERE {_PENDING_SQL}").fetchone()
    return int(row[0])


def write_pending_user_data(
    conn: sqlite3.Connection,
    *,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    runner_factory: Callable[[], ExifToolRunner] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    writers: Mapping[UserDataDestination, UserDataWriter] | None = None,
) -> UserDataWriteResult:
    """Escribe en su destino los datos del usuario pendientes y quita la marca.

    Args:
        conn: Conexión sqlite3 al catálogo.
        progress: Función a la que se avisa tras cada elemento.
        cancel_event: Si se activa, el trabajo se detiene al terminar el lote en curso.
        runner_factory: Crea el lector de ExifTool (por defecto, 'ExifToolRunner()').
            Solo se llama si hay algún XMP que escribir.
        batch_size: Elementos por lote.
        writers: El escritor de cada destino (por defecto, 'writers.default_writers': el
            archivo de carpeta y XMP). Para pruebas o para un escritor de más.

    Returns:
        Un 'UserDataWriteResult' con los recuentos.

    Raises:
        sqlite3.Error: Si falla la base de datos.
    """
    total = count_pending_user_data(conn)
    if total == 0:
        return UserDataWriteResult()
    logger.info(f"Datos del usuario: {total} elementos pendientes de escribir")

    locations = {
        row[0]: Path(row[1]) for row in conn.execute("SELECT id, absolute_path FROM storage_locations")
    }
    online: dict[int, bool] = {}
    if writers is None:
        writers = default_writers(runner_factory)
    # Cada escritor, una vez y en su orden (el de XMP atiende dos destinos)
    ordered_writers = list(dict.fromkeys(writers.values()))
    counts = {"written": 0, "already_ok": 0, "failed": 0, "offline": 0, "rescan": 0}
    messages: list[str] = []
    cancelled = False
    done = 0
    last_id = 0
    _notify(progress, done, total)

    while True:
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        # Las columnas editables van al final (sus nombres salen de una lista cerrada)
        rows = conn.execute(
            f"""SELECT id, storage_location_id, relative_path, file_extension,
                      rating, flag, color_label, user_data_pending,
                      file_size, file_mtime_ns, thumbnail_mtime_ns, sidecar_mtime_ns,
                      keywords_pending, metadata_edit_pending,
                      {", ".join(read_sql(column) for column in EDITABLE_COLUMNS)}
                 FROM media_items
                WHERE {_PENDING_SQL} AND id > ?
                ORDER BY id LIMIT ?""",
            (last_id, batch_size),
        ).fetchall()
        if not rows:
            break
        last_id = rows[-1][0]

        # Elementos del lote cuya unidad está conectada (los demás siguen pendientes)
        items: list[WriteItem] = []
        for row in rows:
            location_id = row[1]
            root = locations.get(location_id)
            if location_id not in online:
                try:
                    online[location_id] = root is not None and root.is_dir()
                except OSError:
                    online[location_id] = False
            if not online[location_id]:
                counts["offline"] += 1
                continue
            items.append(
                WriteItem(
                    media_id=row[0],
                    location_id=location_id,
                    relative_path=row[2],
                    path=root / row[2],
                    destination=destination_for(row[3] or PurePosixPath(row[2]).suffix),
                    values={"rating": row[4], "flag": row[5], "color_label": row[6]},
                    pending=row[7],
                    file_size=row[8],
                    file_mtime_ns=row[9],
                    thumbnail_mtime_ns=row[10],
                    sidecar_mtime_ns=row[11],
                    keywords_pending=bool(row[12]),
                    # Las rutas del catálogo, solo si hay que escribirlas
                    keywords=tuple(media_keyword_paths(conn, row[0])) if row[12] else (),
                    metadata_pending=row[13],
                    metadata=dict(zip(EDITABLE_COLUMNS, row[14:], strict=True)),
                )
            )

        # Lo que el escritor de un formato no sabe guardar va al archivo de carpeta: un
        # archivo puede quedar en dos partes (lo normal: una sola, el propio elemento)
        parts = split_items(items, writers)

        # Escritura (sin transacción abierta: se espera al disco y a ExifTool). Cada
        # escritor recibe las partes de sus destinos y apunta en ellas cómo ha ido
        for writer in ordered_writers:
            group = [part for part in parts if writers[part.destination] is writer]
            if group:
                writer.write(group, cancel_event)

        # Resultado en la base de datos (transacción corta)
        try:
            _save_results(conn, parts)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Recuento por ARCHIVO (sus partes juntas)
        for group in _by_media(parts):
            counts["rescan"] += int(any(part.rescan or part.reread for part in group))
            failed = [part for part in group if not part.ok and not part.deferred]
            if failed:
                counts["failed"] += 1
                if len(messages) < 20:
                    messages.append(f"{group[0].relative_path}: {_failure_text(failed)}")
            elif all(part.ok for part in group):
                counts["written" if any(part.written for part in group) else "already_ok"] += 1
        done += len(rows)
        _notify(progress, min(done, total), total)

    result = UserDataWriteResult(
        total=total,
        written=counts["written"],
        already_ok=counts["already_ok"],
        failed=counts["failed"],
        skipped_offline=counts["offline"],
        cancelled=cancelled,
        # Falta ExifTool (el escritor de XMP). Sin mutagen (el de las canciones), lo suyo
        # también queda pendiente, pero el aviso de la interfaz habla de ExifTool: va al
        # registro (ver 'audio_writer.py')
        exiftool_missing=any(
            writer.unavailable for writer in ordered_writers if writer.name == XmpFileWriter.name
        ),
        rescan_requested=counts["rescan"],
        failed_messages=tuple(messages),
    )
    logger.info(f"Datos del usuario escritos:\n{result.summary()}")
    for message in messages:
        logger.warning(f"No se pudo escribir: {message}")
    return result


def _by_media(parts: Iterable[WriteItem]) -> list[list[WriteItem]]:
    """Las partes de cada archivo juntas, en el orden en que aparecen."""
    groups: dict[int, list[WriteItem]] = {}
    for part in parts:
        groups.setdefault(part.media_id, []).append(part)
    return list(groups.values())


def _failure_text(failed: Iterable[WriteItem]) -> str:
    """El motivo de fallo de un archivo (si fallan sus dos partes, los dos, sin repetir)."""
    return "; ".join(dict.fromkeys(part.message for part in failed))


def _save_results(conn: sqlite3.Connection, items: Iterable[WriteItem]) -> None:
    """Guarda en la base de datos el resultado de un lote (sin hacer commit).

    'items' son las PARTES ('split_items'): cada una quita las marcas de sus campos; el
    error de un archivo se anota (o se borra) una vez, mirando todas sus partes.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    items = list(items)
    for item in items:
        if item.db_updates:
            # Nombres de columna de una lista cerrada (los pone este módulo): sin inyección
            assignments = ", ".join(f"{column} = ?" for column in item.db_updates)
            conn.execute(
                f"UPDATE media_items SET {assignments} WHERE id = ?",
                (*item.db_updates.values(), item.media_id),
            )
            if "file_mtime_ns" in item.db_updates and not item.rescan:
                # Solo cambió por nuestra escritura (los píxeles no cambian): la miniatura
                # generada con la fecha anterior sigue valiendo
                conn.execute(
                    "UPDATE media_items SET thumbnail_mtime_ns = ? "
                    "WHERE id = ? AND thumbnail_mtime_ns = ?",
                    (item.db_updates["file_mtime_ns"], item.media_id, item.file_mtime_ns),
                )
        if item.rescan and item.destination is UserDataDestination.XMP_SIDECAR:
            # Solo cambió el sidecar: se releen los metadatos (el RAW sigue igual)
            conn.execute("UPDATE media_items SET scan_version = 0 WHERE id = ?", (item.media_id,))
        elif item.rescan:
            # El archivo cambió fuera de la aplicación: igual que cuando lo detecta el
            # escáner, se releen los metadatos y se regeneran miniatura y hashes
            conn.execute(
                """UPDATE media_items SET scan_version = 0,
                          thumbnail_status = 0, thumbnail_mtime_ns = NULL,
                          hash_partial = NULL, hash_full = NULL, hash_verified_at = NULL
                    WHERE id = ?""",
                (item.media_id,),
            )
        elif item.reread:
            # Se le escribió algo que el catálogo no sabe (un MP3 con su ID3v2 nuevo): solo
            # se releen sus metadatos (la miniatura sigue valiendo)
            conn.execute("UPDATE media_items SET scan_version = 0 WHERE id = ?", (item.media_id,))

        if item.ok:
            # Se quita el bit de cada campo escrito SOLO si su valor sigue siendo el
            # escrito: si el usuario lo cambió mientras tanto, sigue pendiente
            wanted = item.wanted
            for column, value in wanted.items():
                if column not in USER_FIELD_BITS:
                    continue  # las palabras clave y los metadatos van aparte (abajo)
                conn.execute(
                    f"UPDATE media_items SET user_data_pending = user_data_pending & ? "
                    f"WHERE id = ? AND {column} IS ?",
                    (~USER_FIELD_BITS[column] & 7, item.media_id, value),
                )
            # Metadatos editados: igual, comparando con el valor de la BD que se leyó (el
            # título escrito puede ser «sin título» y en la BD, el nombre del archivo)
            for column in pending_columns(item.metadata_pending):
                if column not in wanted:
                    continue  # ese campo es de la otra parte del archivo
                conn.execute(
                    "UPDATE media_items SET metadata_edit_pending = metadata_edit_pending & ~? "
                    f"WHERE id = ? AND {read_sql(column)} IS ?",
                    (field_for(column).bit, item.media_id, item.metadata[column]),
                )
            # Las palabras clave: solo si siguen siendo las escritas (si el usuario las
            # cambió mientras tanto, siguen pendientes)
            if KEYWORDS_KEY in wanted and same_keywords(
                media_keyword_paths(conn, item.media_id), wanted[KEYWORDS_KEY], exact=True
            ):
                conn.execute("UPDATE media_items SET keywords_pending = 0 WHERE id = ?", (item.media_id,))

    # El error de cada archivo, una vez: si falla alguna parte, se anota; si todas han ido
    # bien, se borra el que hubiera; si solo quedó aplazado (falta la herramienta), ni lo uno
    # ni lo otro
    for group in _by_media(items):
        first = group[0]
        failed = [part for part in group if not part.ok and not part.deferred]
        if failed:
            conn.execute(
                """INSERT INTO scan_errors(storage_location_id, relative_path, stage, message)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(storage_location_id, relative_path, stage)
                   DO UPDATE SET message = excluded.message, occurred_at = CURRENT_TIMESTAMP""",
                (first.location_id, first.relative_path, SCAN_STAGE_USERDATA, _failure_text(failed)),
            )
        elif all(part.ok for part in group):
            conn.execute(
                "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ? "
                "AND stage = ?",
                (first.location_id, first.relative_path, SCAN_STAGE_USERDATA),
            )


def _notify(progress: Callable[[JobProgress], None] | None, done: int, total: int) -> None:
    """Avisa del progreso sin que un fallo del aviso detenga el trabajo."""
    if progress is None:
        return
    try:
        progress(JobProgress(done, total))
    except Exception:  # noqa: BLE001 - el aviso es secundario
        logger.exception("Error al notificar el progreso")


# =============================================================================
# 2. Archivos -> catálogo
# =============================================================================


def apply_file_user_data(
    conn: sqlite3.Connection,
    media_id: int,
    user_data: dict[str, Any],
    *,
    expected_state: tuple[int | None, int | None] | None = None,
) -> bool:
    """Aplica a un elemento los datos del usuario leídos de su XMP. Manda el archivo.

    Lo llama el procesador de metadatos, solo para formatos con destino XMP. Campo a
    campo: no toca los campos pendientes de escribir (su cambio es más nuevo que el
    archivo) ni los que el archivo no trae.

    Args:
        conn: Conexión (con la transacción del procesador abierta).
        media_id: Elemento.
        user_data: Lo que el extractor leyó ('rating', 'flag', 'color_label'; None =
            el archivo no dice nada de ese campo). Vacío = no se pudo leer con
            seguridad o el extractor no sabe leer datos del usuario (el de Pillow): no
            se toca nada.
        expected_state: (file_mtime_ns, sidecar_mtime_ns) que tenía el elemento en la
            BD cuando se leyó el archivo. Si han cambiado desde entonces (la aplicación
            acaba de escribir en él), lo leído ya no vale y no se aplica.

    Returns:
        True si se cambió algo en la base de datos.
    """
    if not user_data:
        return False
    row = conn.execute(
        "SELECT rating, flag, color_label, user_data_pending, file_mtime_ns, sidecar_mtime_ns "
        "FROM media_items WHERE id = ?",
        (media_id,),
    ).fetchone()
    if row is None:
        return False
    if expected_state is not None and (row[4], row[5]) != expected_state:
        return False  # el archivo cambió después de leerlo: se releerá

    current = dict(zip(_USER_COLUMNS, row[:3], strict=True))
    pending = row[3]
    updates = {
        column: user_data[column]
        for column in _USER_COLUMNS
        if user_data.get(column) is not None
        and not pending & USER_FIELD_BITS[column]
        and user_data[column] != current[column]
    }
    if not updates:
        return False
    # Nombres de columna de una lista cerrada: sin inyección SQL
    assignments = ", ".join(f"{column} = ?" for column in updates)
    conn.execute(
        f"UPDATE media_items SET {assignments} WHERE id = ?",
        (*updates.values(), media_id),
    )
    return True


def apply_file_keywords(
    conn: sqlite3.Connection,
    media_id: int,
    keywords: FileKeywords | None,
    *,
    expected_state: tuple[int | None, int | None] | None = None,
    first_read: bool = False,
) -> bool:
    """Deja en un elemento las palabras clave leídas de su XMP. Manda el archivo.

    A diferencia de la valoración, aquí una etiqueta ausente SÍ significa "ninguna"
    (Lightroom borra la lista al quitar la última palabra), así que un archivo sin
    palabras deja el elemento sin ninguna. Si las palabras del elemento están PENDIENTES
    de escribir (se cambiaron en la aplicación), no se tocan: su cambio es más nuevo.

    Salvo en la PRIMERA lectura del archivo ('first_read'): si se le asignaron palabras
    antes de leerlo (mientras se leían los metadatos, o con la lectura cancelada), el
    usuario aún no había visto las del archivo y no ha podido quitar ninguna, así que se
    SUMAN a las suyas. La marca de pendiente sigue: la suma se escribe después en el
    archivo, que conserva lo que tenía.

    Args:
        conn: Conexión (con la transacción del procesador abierta).
        media_id: Elemento.
        keywords: Lo que el extractor leyó; None = no se pudo leer con seguridad o el
            extractor no lee palabras clave: no se toca nada.
        expected_state: Como en 'apply_file_user_data': si el archivo cambió después de
            leerlo, lo leído ya no vale y no se aplica.
        first_read: True si es la primera vez que se lee este archivo ('last_scanned_at'
            vacío ANTES de esta lectura: lo mira el procesador).

    Returns:
        True si cambió alguna asignación.
    """
    if keywords is None:
        return False
    row = conn.execute(
        "SELECT file_mtime_ns, sidecar_mtime_ns, keywords_pending FROM media_items WHERE id = ?",
        (media_id,),
    ).fetchone()
    if row is None:
        return False
    pending = bool(row[2])
    if pending and not first_read:
        return False  # sus palabras están pendientes de escribir: su cambio es más nuevo
    if expected_state is not None and (row[0], row[1]) != expected_state:
        return False
    paths = list(keywords.paths)
    if pending:
        # Primera lectura con palabras asignadas antes: las del archivo y las del catálogo
        paths += media_keyword_paths(conn, media_id)
    return set_media_keywords(conn, media_id, paths, keywords.flat)


def apply_folder_files(
    conn: sqlite3.Connection,
    location_root: Path,
    location_id: int,
    relative_paths: Iterable[str],
    cache: FolderFileCache | None = None,
) -> int:
    """Aplica al catálogo los datos de los archivos de carpeta. Manda el archivo.

    Lo llama 'add_folder' tras guardar cada lote (con su transacción abierta). Solo trata
    los archivos con entrada en el '.arca.json' ('policy.has_folder_entry') y, de ellos,
    los datos que guarda esa entrada ('policy.folder_file_fields': en un formato partido,
    lo demás sale del propio archivo) que no están pendientes de escribir. Las carpetas
    sin archivo '.arca.json' no se tocan. Los metadatos editados (título, pie...) solo se
    tocan si la entrada trae su clave.

    Args:
        conn: Conexión (con la transacción del lote abierta).
        location_root: Carpeta raíz de la ubicación.
        location_id: Id de la ubicación.
        relative_paths: Rutas relativas de los archivos del lote.
        cache: Archivos de carpeta ya leídos en este escaneo (se reutiliza entre lotes).

    Returns:
        Cuántos elementos se han cambiado en la base de datos.
    """
    if cache is None:
        cache = {}
    changed = 0
    for relative_path in relative_paths:
        if not has_folder_entry(relative_path):
            continue
        fields = folder_file_fields(relative_path)  # lo que guarda su entrada (None, todo)
        posix = PurePosixPath(relative_path)
        data = _folder_data(location_root / posix.parent, cache)
        if data is None or not data.exists:
            continue  # ilegible o sin archivo: no se sabe nada, no se toca nada

        key = find_entry_key(data.items, posix.name)
        entry = data.items.get(key) if key else None
        values = user_values_from_entry(entry)
        row = conn.execute(
            "SELECT id, rating, flag, color_label, user_data_pending, keywords_pending "
            "FROM media_items WHERE storage_location_id = ? AND relative_path = ?",
            (location_id, relative_path),
        ).fetchone()
        if row is None:
            continue
        # Palabras clave: las de la entrada (sin la clave = ninguna), salvo si están
        # pendientes de escribir
        keywords_changed = (
            not row[5]
            and _in_folder_file(fields, KEYWORDS_KEY)
            and set_media_keywords(conn, row[0], keywords_from_entry(entry))
        )
        current = dict(zip(_USER_COLUMNS, row[1:4], strict=True))
        updates = {
            column: values[column]
            for column in _USER_COLUMNS
            if _in_folder_file(fields, column)
            and not row[4] & USER_FIELD_BITS[column]
            and values[column] != current[column]
        }
        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(
                f"UPDATE media_items SET {assignments} WHERE id = ?",
                (*updates.values(), row[0]),
            )
        # Metadatos editados: solo los que la entrada trae (sin la clave, manda lo que
        # lea el extractor) y guarda, salvo los pendientes de escribir
        edits = {
            column: value
            for column, value in edited_values_from_entry(entry).items()
            if _in_folder_file(fields, column)
        }
        edits_changed = _apply_edited_values(conn, row[0], posix.name, edits)
        if updates or keywords_changed or edits_changed:
            changed += 1
    return changed


def folder_file_edits(
    location_root: Path, relative_path: str, cache: FolderFileCache
) -> dict[str, str | None] | None:
    """Metadatos editados que guarda el '.arca.json' para un archivo con entrada en él
    ('policy.has_folder_entry'): solo los campos que guarda esa entrada
    ('policy.folder_file_fields').

    Lo usa el procesador de metadatos: lo editado en la aplicación que vive en el archivo
    de carpeta (el original no se toca) manda SIEMPRE sobre lo que lea el extractor.

    Args:
        location_root: Carpeta raíz de la ubicación.
        relative_path: Ruta relativa del archivo (con '/').
        cache: Archivos de carpeta ya leídos (se reutiliza entre archivos).

    Returns:
        Columna -> valor (None = vaciado a propósito) de los campos editados; vacío si
        no hay archivo de carpeta o el archivo no tiene entrada. None si el archivo de
        carpeta está dañado: no se sabe qué se editó.
    """
    posix = PurePosixPath(relative_path)
    data = _folder_data(location_root / posix.parent, cache)
    if data is None:
        return None
    if not data.exists:
        return {}
    key = find_entry_key(data.items, posix.name)
    edits = edited_values_from_entry(data.items.get(key) if key else None)
    fields = folder_file_fields(relative_path)
    return {column: value for column, value in edits.items() if _in_folder_file(fields, column)}


def _in_folder_file(fields: frozenset[str] | None, name: str) -> bool:
    """True si la entrada del '.arca.json' guarda ese dato ('fields', lo que da
    'policy.folder_file_fields': None, todos)."""
    return fields is None or name in fields


def _folder_data(folder: Path, cache: FolderFileCache) -> FolderData | None:
    """El archivo de carpeta de 'folder', leído una vez por escaneo (None = ilegible)."""
    if folder not in cache:
        try:
            cache[folder] = read_folder_file(folder)
        except FolderFileError as error:
            # No se sabe qué hay: mejor no tocar nada que poner valores por defecto
            logger.warning(f"No se aplican los datos de la carpeta {folder}: {error}")
            cache[folder] = None
    return cache[folder]


def _apply_edited_values(
    conn: sqlite3.Connection, media_id: int, file_name: str, edits: dict[str, str | float | None]
) -> bool:
    """Pone en un elemento los metadatos editados del archivo de carpeta.

    No toca los campos pendientes de escribir (su cambio es más nuevo). Un título vaciado
    vuelve al nombre del archivo sin extensión.

    Returns:
        True si cambió algo.
    """
    if not edits:
        return False
    # Los campos de una tabla de detalles (la actividad de un track), aparte
    changed = False
    for column in [column for column in edits if field_for(column).table]:
        changed |= _apply_detail_edit(conn, media_id, column, edits[column])
    values = {
        column: default_title(file_name) if column == "title" and value is None else value
        for column, value in edits.items()
        if not field_for(column).table
    }
    if not values:
        return changed
    # Nombres de columna de la lista cerrada de 'editable_fields.py': sin inyección SQL.
    # Cada columna conserva su valor si su bit está pendiente; solo se cuenta como cambio
    # si alguna columna no pendiente tenía otro valor.
    assignments = ", ".join(unless_pending_sql(column) for column in values)
    changed_condition = " OR ".join(
        f"(NOT metadata_edit_pending & {field_for(column).bit} AND {column} IS NOT ?)"
        for column in values
    )
    cursor = conn.execute(
        f"UPDATE media_items SET {assignments} WHERE id = ? AND ({changed_condition})",
        (*values.values(), media_id, *values.values()),
    )
    return changed or cursor.rowcount > 0


def _apply_detail_edit(
    conn: sqlite3.Connection, media_id: int, column: str, value: str | float | None
) -> bool:
    """Pone en la tabla de detalles de un elemento un metadato editado del archivo de
    carpeta, si el campo se aplica a su tipo de archivo y no está pendiente de escribir.

    Returns:
        True si cambió algo.
    """
    spec = field_for(column)
    only, types = applies_sql(column)
    applies = conn.execute(
        f"SELECT 1 FROM media_items WHERE id = ?{only} AND NOT metadata_edit_pending & ?",
        (media_id, *types, spec.bit),
    ).fetchone()
    if applies is None:
        return False  # no es de ese tipo de archivo, o el cambio del usuario es más nuevo
    # Nombres de tabla y de columna de la lista cerrada de 'editable_fields.py'
    conn.execute(f"INSERT OR IGNORE INTO {spec.table} (media_id) VALUES (?)", (media_id,))
    cursor = conn.execute(
        f"UPDATE {spec.table} SET {column} = ? WHERE media_id = ? AND {column} IS NOT ?",
        (value, media_id, value),
    )
    return cursor.rowcount > 0


if __name__ == "__main__":
    # Autoprueba de ida y vuelta: catálogo -> archivos -> catálogo NUEVO (como si se
    # hubiera borrado el catálogo y se reconstruyera reescaneando las carpetas).
    # Trabaja en una carpeta temporal; la parte de XMP necesita ExifTool.
    # Ejecutar desde la raíz del proyecto:  python -m core.userdata.sync
    import subprocess
    import sys
    import tempfile

    from PIL import Image

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.folder_importer import add_folder
    from core.catalog.media_queries import update_metadata_fields, update_user_field
    from core.metadata.image.extractor import ImageExtractor
    from core.metadata.processor import process_pending_metadata
    from core.metadata.registry import ExtractorRegistry
    from core.userdata.folder_file import BACKUP_FILE_NAME, FOLDER_FILE_NAME
    from core.userdata.xmp_writer import XMP_READ_TAGS

    try:
        runner = ExifToolRunner()
        runner.version()
    except ExifToolError as error:
        print(f"Sin ExifTool no se puede probar la escritura en XMP: {error}")
        sys.exit(0)
    registry = ExtractorRegistry()
    registry.register(ImageExtractor(runner))

    def new_catalog() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        configure_connection(conn)
        apply_migrations(conn)
        return conn

    def user_values(conn: sqlite3.Connection) -> dict[str, tuple]:
        return {
            row[0]: (row[1], row[2], row[3])
            for row in conn.execute(
                "SELECT relative_path, rating, flag, color_label FROM media_items"
            )
        }

    def ids(conn: sqlite3.Connection) -> dict[str, int]:
        return dict(conn.execute("SELECT relative_path, id FROM media_items"))

    def pending(conn: sqlite3.Connection) -> int:
        return count_pending_user_data(conn)

    def edited(conn: sqlite3.Connection, path: str) -> tuple:
        """Título, pie, creador y ciudad de un elemento."""
        return tuple(conn.execute(
            "SELECT title, description, creator, city FROM media_items WHERE relative_path = ?",
            (path,),
        ).fetchone())  # fmt: skip

    def exiftool_args(path: Path, *args: str) -> None:
        """Otro programa escribe en un archivo. Con un archivo de argumentos UTF-8: en
        Windows, por la línea de órdenes las tildes llegan como «?» (docs/TRAMPAS.md)."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write("\n".join([*args, str(path)]) + "\n")
        try:
            subprocess.run(
                [*runner.command, "-overwrite_original", "-charset", "utf8",
                 "-charset", "filename=utf8", "-@", f.name],
                capture_output=True, check=True,
            )  # fmt: skip
        finally:
            Path(f.name).unlink(missing_ok=True)

    def overwrite(path: Path, content: str) -> None:
        """Sobrescribe un archivo aunque esté oculto (en Windows, 'write_text' no puede)."""
        temp = path.with_name(path.name + ".prueba")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)

    def tags_of(path: Path) -> dict[str, Any]:
        return runner.read([path], tags=(*XMP_READ_TAGS, "-CurrentIPTCDigest"))[path].tags

    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "Biblioteca"
        (library / "sub").mkdir(parents=True)
        Image.new("RGB", (40, 30), "red").save(library / "foto.jpg", quality=90)
        # Como si lo hubiera guardado Lightroom: IPTC antiguo y su resumen al día
        exiftool_args(library / "foto.jpg", "-IPTC:ObjectName=Viejo", "-IPTC:City=Málaga")
        exiftool_args(library / "foto.jpg", "-Photoshop:IPTCDigest=new")
        Image.new("RGB", (40, 30), "blue").save(library / "dibujo.png")
        Image.new("RGB", (40, 30), "green").save(library / "raw.nef", format="TIFF")  # "RAW"
        (library / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
        (library / "sub" / "peli.mkv").write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)

        # --- 1. Catálogo original: el usuario valora, marca y colorea ---------------
        original = new_catalog()
        add_folder(original, library)
        process_pending_metadata(original, registry=registry)
        original.execute(
            "UPDATE media_items SET thumbnail_status = 1, thumbnail_mtime_ns = file_mtime_ns"
        )
        original.commit()
        by_path = ids(original)
        wanted = {
            "foto.jpg": (3, -1, "red"),
            "dibujo.png": (5, 1, "blue"),
            "raw.nef": (2, 1, "green"),
            "clip.mp4": (4, 0, "purple"),
            "sub/peli.mkv": (1, -1, None),
        }
        for path, (rating, flag, color) in wanted.items():
            update_user_field(original, [by_path[path]], "rating", rating)
            update_user_field(original, [by_path[path]], "flag", flag)
            update_user_field(original, [by_path[path]], "color_label", color)
        original.commit()
        assert pending(original) == 5

        # --- 2. Escritura: cada uno a su destino --------------------------------------
        size_before = (library / "foto.jpg").stat().st_size
        result = write_pending_user_data(original)
        print(result.summary())
        assert (result.written, result.failed, pending(original)) == (5, 0, 0)
        assert (library / "raw.xmp").is_file()  # sidecar del RAW (convención de Adobe)
        assert (library / FOLDER_FILE_NAME).is_file()  # vídeo de la carpeta raíz
        assert (library / "sub" / FOLDER_FILE_NAME).is_file()  # y el de la subcarpeta
        # El JPEG cambió, pero el catálogo ya conoce su tamaño y fecha nuevos, y su
        # miniatura sigue valiendo
        row = original.execute(
            "SELECT file_size, file_mtime_ns, thumbnail_mtime_ns FROM media_items "
            "WHERE relative_path = 'foto.jpg'"
        ).fetchone()
        stat = (library / "foto.jpg").stat()
        assert row == (stat.st_size, stat.st_mtime_ns, stat.st_mtime_ns) and stat.st_size != size_before
        rescan = add_folder(original, library)
        assert rescan.changed_items == 0, rescan.summary()  # nada parece "cambiado fuera"
        print("Escritura: cada dato en su destino, sin falsos cambios al reescanear")

        # Repetir no toca nada
        again = write_pending_user_data(original)
        assert again.total == 0

        # --- 2b. Metadatos editados: XMP con sus antiguas, sidecar y '.arca.json' --------
        city = "Villanueva de la Cañada del Río Grande"  # más larga que el IPTC (32 bytes)
        edits = {
            "foto.jpg": {"title": "Atardecer en León", "description": "Línea 1\nLínea 2 →",
                         "city": city},
            "raw.nef": {"creator": "Javier Rojo"},
            "clip.mp4": {"title": "Vídeo editado", "description": None},
            "dibujo.png": {"title": "Temporal"},
        }  # fmt: skip
        for path, values in edits.items():
            update_metadata_fields(original, [by_path[path]], values)
        original.commit()
        assert pending(original) == 4
        result = write_pending_user_data(original)
        assert (result.written, result.failed, pending(original)) == (4, 0, 0), result
        tags = tags_of(library / "foto.jpg")
        assert tags["XMP-dc:Title"] == tags["IPTC:ObjectName"] == "Atardecer en León", tags
        assert tags["XMP-dc:Description"] == "Línea 1\nLínea 2 →", tags
        assert tags["XMP-photoshop:City"] == city and city.startswith(tags["IPTC:City"]), tags
        digest = next(v for k, v in tags.items() if k.endswith("CurrentIPTCDigest"))
        assert tags["Photoshop:IPTCDigest"] == digest  # resumen IPTC al día
        assert tags_of(library / "raw.xmp")["XMP-dc:Creator"] == "Javier Rojo"
        entry = read_folder_file(library).items["clip.mp4"]
        assert entry["title"] == "Vídeo editado" and entry["description"] == "", entry
        # Vaciar el título: en el archivo desaparece; en el catálogo, el nombre del archivo
        update_metadata_fields(original, [by_path["dibujo.png"]], {"title": "  "})
        original.commit()
        assert write_pending_user_data(original).written == 1
        assert "XMP-dc:Title" not in tags_of(library / "dibujo.png")
        assert edited(original, "dibujo.png")[0] == "dibujo" and pending(original) == 0
        assert add_folder(original, library).changed_items == 0  # sin falsos cambios
        print("Metadatos editados: al XMP (con IPTC y resumen), al sidecar y al .arca.json")

        # --- 2c. GPS editado: la foto, que no tenía GPS, al EXIF (como Lightroom); el RAW,
        #     a su sidecar; el vídeo, al '.arca.json' -------------------------------------
        gps_edits = {
            "foto.jpg": {"latitude": 43.4623, "longitude": -3.81, "altitude": -2.5,
                         "gps_direction": 90.0},
            "raw.nef": {"latitude": 41.3874, "longitude": 2.1686},
            "clip.mp4": {"latitude": 41.3874, "longitude": 2.1686, "altitude": -12.5},
        }  # fmt: skip
        for path, values in gps_edits.items():
            update_metadata_fields(original, [by_path[path]], values)
        original.commit()
        gps_pass = write_pending_user_data(original)
        assert (gps_pass.written, gps_pass.failed, pending(original)) == (3, 0, 0), gps_pass.summary()
        tags = tags_of(library / "foto.jpg")
        assert (tags["GPS:GPSLatitudeRef"], tags["GPS:GPSLongitudeRef"], tags["GPS:GPSAltitudeRef"]) == (
            "N", "W", 1
        ), tags
        assert "XMP-exif:GPSLatitude" not in tags  # sin GPS antes: solo el EXIF
        assert tags_of(library / "raw.xmp")["XMP-exif:GPSLatitude"] == 41.3874
        entry = read_folder_file(library).items["clip.mp4"]
        assert (entry["latitude"], entry["longitude"], entry["altitude"]) == (41.3874, 2.1686, -12.5)
        assert add_folder(original, library).changed_items == 0  # sin falsos cambios
        print("GPS editado: al EXIF de la foto, al sidecar del RAW y al .arca.json del vídeo")

        # --- 3. Catálogo NUEVO a partir de las carpetas -------------------------------
        rebuilt = new_catalog()
        imported = add_folder(rebuilt, library)
        assert imported.user_data_applied == 2, imported.summary()  # vídeos (.arca.json)
        process_pending_metadata(rebuilt, registry=registry)  # fotos (XMP y sidecar)
        assert user_values(rebuilt) == wanted, user_values(rebuilt)
        assert pending(rebuilt) == 0
        assert edited(rebuilt, "foto.jpg") == ("Atardecer en León", "Línea 1\nLínea 2 →", None, city)
        assert edited(rebuilt, "raw.nef") == ("raw", None, "Javier Rojo", None)
        assert edited(rebuilt, "clip.mp4") == ("Vídeo editado", None, None, None)
        assert edited(rebuilt, "dibujo.png")[0] == "dibujo"
        clip_gps = rebuilt.execute(
            "SELECT latitude, longitude, altitude FROM media_items WHERE relative_path = 'clip.mp4'"
        ).fetchone()
        assert tuple(clip_gps) == (41.3874, 2.1686, -12.5), tuple(clip_gps)  # del .arca.json
        photo_gps = rebuilt.execute(
            "SELECT relative_path, latitude, longitude, altitude, gps_direction FROM media_items "
            "WHERE relative_path IN ('foto.jpg', 'raw.nef') ORDER BY relative_path"
        ).fetchall()
        assert [(p, round(a, 6), round(b, 6), c, d) for p, a, b, c, d in photo_gps] == [
            ("foto.jpg", 43.4623, -3.81, -2.5, 90.0), ("raw.nef", 41.3874, 2.1686, None, None)
        ], photo_gps  # del EXIF de la foto y del sidecar del RAW
        print("Catálogo reconstruido: valoraciones, marcas, colores y metadatos editados recuperados")

        # --- 4. Un cambio pendiente NO se pisa al releer el archivo -------------------
        ids_rebuilt = ids(rebuilt)
        update_user_field(rebuilt, [ids_rebuilt["foto.jpg"]], "rating", 5)
        update_user_field(rebuilt, [ids_rebuilt["clip.mp4"]], "rating", 1)
        rebuilt.execute("UPDATE media_items SET scan_version = 0")  # fuerza la relectura
        rebuilt.commit()
        process_pending_metadata(rebuilt, registry=registry)
        add_folder(rebuilt, library)
        values = user_values(rebuilt)
        assert values["foto.jpg"][0] == 5 and values["clip.mp4"][0] == 1, values
        write_pending_user_data(rebuilt)
        assert pending(rebuilt) == 0
        print("Cambio pendiente protegido frente a la relectura, y escrito después")

        # --- 5. Otro programa cambia los archivos: al reescanear, manda el archivo ----
        command = runner.command
        subprocess.run([*command, "-overwrite_original", "-XMP-xmp:Rating=1",
                        str(library / "foto.jpg")], capture_output=True, check=True)  # fmt: skip
        subprocess.run([*command, "-overwrite_original", "-XMP-xmp:Rating=4",
                        str(library / "raw.xmp")], capture_output=True, check=True)  # fmt: skip
        changed = add_folder(rebuilt, library)
        assert changed.changed_items == 2, changed.summary()  # JPEG + sidecar del RAW
        process_pending_metadata(rebuilt, registry=registry)
        values = user_values(rebuilt)
        assert values["foto.jpg"][0] == 1 and values["raw.nef"][0] == 4, values
        print("Cambios hechos fuera (JPEG y sidecar): el catálogo los recoge")

        # --- 5b. Cambio externo Y cambio en la aplicación a la vez: gana la aplicación,
        #     pero el archivo se relee (por si trae otros datos nuevos, como un título)
        exiftool_args(library / "foto.jpg", "-XMP-dc:Title=Nuevo título")
        update_user_field(rebuilt, [ids_rebuilt["foto.jpg"]], "rating", 2)
        rebuilt.execute("UPDATE media_items SET thumbnail_status = 1 WHERE relative_path = 'foto.jpg'")
        rebuilt.commit()
        both = write_pending_user_data(rebuilt)
        assert both.rescan_requested == 1 and both.written == 1, both
        row = rebuilt.execute(
            "SELECT scan_version, thumbnail_status, file_mtime_ns FROM media_items "
            "WHERE relative_path = 'foto.jpg'"
        ).fetchone()
        assert row[0] == 0 and row[1] == 0 and row[2] == (library / "foto.jpg").stat().st_mtime_ns
        process_pending_metadata(rebuilt, registry=registry)
        title = rebuilt.execute(
            "SELECT title, rating FROM media_items WHERE relative_path = 'foto.jpg'"
        ).fetchone()
        assert tuple(title) == ("Nuevo título", 2), title
        assert write_pending_user_data(rebuilt).total == 0  # sin bucles de relectura
        assert add_folder(rebuilt, library).changed_items == 0
        print("Cambio externo + cambio en la app: gana la app y se relee el resto")

        # --- 6. Sin ExifTool: los XMP siguen pendientes; el archivo de carpeta sí se escribe
        update_user_field(rebuilt, [ids_rebuilt["dibujo.png"]], "rating", 2)
        update_user_field(rebuilt, [ids_rebuilt["sub/peli.mkv"]], "rating", 5)
        rebuilt.commit()

        def no_exiftool() -> ExifToolRunner:
            raise ExifToolError("no instalado")

        partial = write_pending_user_data(rebuilt, runner_factory=no_exiftool)
        assert partial.exiftool_missing and partial.has_warnings and partial.failed == 0
        assert pending(rebuilt) == 1  # solo el PNG
        assert "falta ExifTool" in partial.status_text()
        print("Sin ExifTool: el PNG sigue pendiente, el vídeo se escribe")

        # --- 7. Archivo de carpeta dañado: no se reescribe a ciegas ------------------
        overwrite(library / "sub" / FOLDER_FILE_NAME, "{roto")
        overwrite(library / "sub" / BACKUP_FILE_NAME, "{roto")
        update_user_field(rebuilt, [ids_rebuilt["sub/peli.mkv"]], "rating", 3)
        rebuilt.commit()
        broken = write_pending_user_data(rebuilt)
        assert broken.failed == 1 and (library / "sub" / FOLDER_FILE_NAME).read_text() == "{roto"
        error = rebuilt.execute(
            "SELECT message FROM scan_errors WHERE stage = ?", (SCAN_STAGE_USERDATA,)
        ).fetchone()
        assert error is not None and "dañado" in error[0], error
        # Y al reescanear tampoco se aplican valores por defecto a sus archivos
        add_folder(rebuilt, library)
        assert user_values(rebuilt)["sub/peli.mkv"][0] == 3
        print("Archivo de carpeta dañado: ni se reescribe ni se aplican valores por defecto")

        original.close()
        rebuilt.close()

    # --- 8. Casos límite encontrados en la revisión -----------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp)
        # a) RAW cuya cámara guardó 3 estrellas DENTRO del RAW, sin sidecar
        Image.new("RGB", (40, 30), "green").save(library / "camara.nef", format="TIFF")
        subprocess.run([*runner.command, "-overwrite_original", "-XMP-xmp:Rating=3",
                        str(library / "camara.nef")], capture_output=True, check=True)  # fmt: skip
        # b) JPEG al que otro programa pondrá 4 estrellas sin que la app se entere aún
        Image.new("RGB", (40, 30), "red").save(library / "lr.jpg", quality=90)

        catalog = new_catalog()
        add_folder(catalog, library)
        process_pending_metadata(catalog, registry=registry)
        assert user_values(catalog)["camara.nef"][0] == 3  # sin sidecar: vale lo de la cámara
        by_path = ids(catalog)

        # a) Quitar las estrellas aquí crea el sidecar con Rating = 0: al reconstruir, 0
        update_user_field(catalog, [by_path["camara.nef"]], "rating", 0)
        # b) Lightroom pone 4 estrellas y aquí SOLO se cambia el color
        subprocess.run([*runner.command, "-overwrite_original", "-XMP-xmp:Rating=4",
                        str(library / "lr.jpg")], capture_output=True, check=True)  # fmt: skip
        update_user_field(catalog, [by_path["lr.jpg"]], "color_label", "red")
        catalog.commit()
        write_pending_user_data(catalog)
        assert (library / "camara.xmp").is_file()
        process_pending_metadata(catalog, registry=registry)  # relee el JPEG (cambió fuera)
        values = user_values(catalog)
        assert values["lr.jpg"] == (4, 0, "red"), values  # la valoración de Lightroom sigue
        again = new_catalog()
        add_folder(again, library)
        process_pending_metadata(again, registry=registry)
        assert user_values(again) == {"camara.nef": (0, 0, None), "lr.jpg": (4, 0, "red")}
        print("RAW con valoración de cámara y JPEG tocado en Lightroom: nada se pierde")

        # c) Relectura cancelada después de leer el RAW pero antes que su sidecar: el
        #    elemento no se guarda (sigue pendiente de leer) y sus datos no cambian
        update_user_field(again, [ids(again)["camara.nef"]], "rating", 5)
        again.commit()
        write_pending_user_data(again)
        again.execute("UPDATE media_items SET scan_version = 0")
        again.commit()

        class CancelAfterFirstFile(ExifToolRunner):
            """Lector que se "cancela" tras leer el primer archivo del lote."""

            def read(self, paths, *, tags=(), cancel_event=None):
                return super().read(list(paths)[:1], tags=tags, cancel_event=cancel_event)

        cancelling = ExtractorRegistry()
        cancelling.register(ImageExtractor(CancelAfterFirstFile()))
        process_pending_metadata(again, registry=cancelling)
        row = again.execute(
            "SELECT rating, scan_version FROM media_items WHERE relative_path = 'camara.nef'"
        ).fetchone()
        assert tuple(row) == (5, 0), row
        print("Lectura a medias (sidecar sin leer): no se aplica nada y se releerá")
        catalog.close()
        again.close()

    # --- 9. Un archivo, dos destinos: un escritor que solo sabe guardar el título y la
    #        valoración (como unas etiquetas de audio); lo demás va al '.arca.json'
    class _PartialWriter(UserDataWriter):
        """Escritor de mentira: apunta lo que le piden y no toca ningún archivo."""

        name = "parcial"

        def __init__(self) -> None:
            super().__init__()
            self.seen: list[dict[str, Any]] = []
            self.fail = False

        def fields_for(self, item: WriteItem) -> frozenset[str] | None:
            return frozenset({"title", "rating"})

        def write(self, items: list[WriteItem], cancel_event: threading.Event | None = None) -> None:
            for item in items:
                self.seen.append(dict(item.wanted))
                item.ok, item.written = not self.fail, not self.fail
                item.message = "no se pudo" if self.fail else ""

    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "Partido"
        library.mkdir()
        Image.new("RGB", (40, 30), "red").save(library / "foto.jpg", quality=90)
        split = new_catalog()
        add_folder(split, library)
        process_pending_metadata(split, registry=registry)
        (photo,) = ids(split).values()
        partial_writer = _PartialWriter()
        custom = {**default_writers(), UserDataDestination.XMP_EMBEDDED: partial_writer}

        def marks() -> tuple:
            return tuple(split.execute(
                "SELECT user_data_pending, metadata_edit_pending FROM media_items"
            ).fetchone())  # fmt: skip

        def errors() -> list:
            return split.execute("SELECT message FROM scan_errors WHERE stage = ?", (SCAN_STAGE_USERDATA,)).fetchall()

        update_user_field(split, [photo], "rating", 4)
        update_user_field(split, [photo], "color_label", "blue")
        update_metadata_fields(split, [photo], {"title": "Partido", "city": "Jaca"})
        split.commit()
        size_before = (library / "foto.jpg").stat().st_size
        result = write_pending_user_data(split, writers=custom)
        # El escritor del formato recibe SOLO lo suyo; el resto está en el '.arca.json'
        assert partial_writer.seen == [{"rating": 4, "title": "Partido"}], partial_writer.seen
        entry = read_folder_file(library).items["foto.jpg"]
        assert entry["color_label"] == "blue" and entry["city"] == "Jaca", entry
        assert "rating" not in entry and "title" not in entry, entry
        assert (result.total, result.written, result.failed) == (1, 1, 0) and marks() == (0, 0)
        assert (library / "foto.jpg").stat().st_size == size_before  # nadie tocó el original
        print("Un archivo, dos destinos: cada campo a su escritor y todas las marcas quitadas")

        # Si falla una parte, solo sus campos siguen pendientes; el error se anota una vez
        partial_writer.fail = True
        update_user_field(split, [photo], "rating", 2)
        update_user_field(split, [photo], "color_label", "red")
        split.commit()
        result = write_pending_user_data(split, writers=custom)
        assert (result.written, result.failed) == (0, 1) and result.failed_messages
        assert marks() == (USER_FIELD_BITS["rating"], 0), marks()  # el color sí se guardó
        assert read_folder_file(library).items["foto.jpg"]["color_label"] == "red"
        assert errors() == [("no se pudo",)], errors()
        # Al ir bien, se quita la marca y el error
        partial_writer.fail = False
        result = write_pending_user_data(split, writers=custom)
        assert (result.written, result.failed) == (1, 0) and marks() == (0, 0) and errors() == []
        # Con los escritores de siempre, una foto NO se parte: todo al XMP, nada al '.arca.json'
        update_user_field(split, [photo], "color_label", "green")
        update_metadata_fields(split, [photo], {"city": "Canfranc"})
        split.commit()
        write_pending_user_data(split)
        assert read_folder_file(library).items["foto.jpg"]["color_label"] == "red"  # el de antes
        assert tags_of(library / "foto.jpg")["XMP-photoshop:City"] == "Canfranc" and marks() == (0, 0)
        print("Si falla una parte, solo esa sigue pendiente; las fotos siguen yendo enteras al XMP")
        split.close()

    # --- 10. Primera lectura: lo que se asigna ANTES de leer un archivo no borra lo que
    #     trae (GEN 20, paso 1). Antes, una palabra asignada a una foto sin leer dejaba en
    #     el archivo solo esa ----------------------------------------------------------------
    from core.catalog.keywords import assign_keyword, ensure_keyword_path, remove_keyword

    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "Nuevas"
        library.mkdir()
        Image.new("RGB", (40, 30), "red").save(library / "playa.jpg", quality=90)
        # Como si viniera de Lightroom: una palabra con su ruta, otra suelta y 2 estrellas
        exiftool_args(
            library / "playa.jpg",
            "-XMP-lr:HierarchicalSubject=Lugares|Playa",
            "-XMP-dc:Subject=Lugares", "-XMP-dc:Subject=Playa", "-XMP-dc:Subject=Sol",
            "-XMP-xmp:Rating=2",
        )  # fmt: skip
        (library / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
        fresh = new_catalog()
        add_folder(fresh, library)
        by_path = ids(fresh)
        photo, clip = by_path["playa.jpg"], by_path["clip.mp4"]

        # Antes de leer nada (mientras se leen los metadatos, o con la lectura cancelada)
        assign_keyword(fresh, [photo], ensure_keyword_path(fresh, ("Nueva",)))
        update_user_field(fresh, [photo], "rating", 4)
        update_user_field(fresh, [clip], "rating", 3)
        fresh.commit()

        # a) La foto, sin leer, no se escribe; el vídeo sí (sus datos son del '.arca.json',
        #    que ya se aplicó al añadir la carpeta)
        mtime_before = (library / "playa.jpg").stat().st_mtime_ns
        assert pending(fresh) == 1
        result = write_pending_user_data(fresh)
        assert (result.total, result.written) == (1, 1), result.summary()
        assert (library / "playa.jpg").stat().st_mtime_ns == mtime_before  # sin tocar
        assert read_folder_file(library).items["clip.mp4"]["rating"] == 3

        # b) Primera lectura: las palabras se SUMAN; la valoración puesta aquí manda
        process_pending_metadata(fresh, registry=registry)
        paths = media_keyword_paths(fresh, photo)
        assert paths == [("Lugares", "Playa"), ("Nueva",), ("Sol",)], paths
        assert user_values(fresh)["playa.jpg"][0] == 4
        assert pending(fresh) == 1  # ya leída: ahora sí se escribe
        assert write_pending_user_data(fresh).written == 1
        tags = tags_of(library / "playa.jpg")
        assert {"Lugares", "Playa", "Sol", "Nueva"} <= set(tags["XMP-dc:Subject"]), tags
        assert tags["XMP-xmp:Rating"] == 4, tags

        # c) En las lecturas siguientes vuelve a mandar lo pendiente: quitar «Sol» aquí y
        #    releer el archivo (que aún la tiene) no la recupera
        (sol,) = fresh.execute("SELECT id FROM keywords WHERE name = 'Sol'").fetchone()
        remove_keyword(fresh, [photo], sol)
        fresh.execute("UPDATE media_items SET scan_version = 0")  # fuerza la relectura
        fresh.commit()
        process_pending_metadata(fresh, registry=registry)
        assert ("Sol",) not in media_keyword_paths(fresh, photo)
        write_pending_user_data(fresh)
        assert "Sol" not in tags_of(library / "playa.jpg")["XMP-dc:Subject"]
        print("Primera lectura: nada se escribe antes; las palabras asignadas se suman a las del archivo")
        fresh.close()

    # --- 11. Un MP3 (MUS 6.2b), el primer formato partido: sus etiquetas, dentro del
    #     archivo; la valoración, la marca, el color, las palabras clave y lo demás, en el
    #     '.arca.json'; y de vuelta en un catálogo nuevo ----------------------------------
    from mutagen.id3 import ID3, TALB, TIT2, TPE1

    from core.audio.tag_reader import read_audio
    from core.metadata.audio.extractor import AudioExtractor

    audio_registry = ExtractorRegistry()
    audio_registry.register(AudioExtractor())
    silence = b"\xff\xfb\x90\x00" + bytes(413)  # una trama de MP3 (MPEG-1 Layer III)

    def audio_row(conn: sqlite3.Connection, media_id: int) -> tuple:
        """Los campos de una canción que van a sus etiquetas (y la ciudad, que no)."""
        return tuple(conn.execute(
            "SELECT m.title, m.creator, m.description, m.city, a.album, a.track_number, "
            "a.track_total, a.genre FROM media_items AS m "
            "JOIN audio_details AS a ON a.media_id = m.id WHERE m.id = ?",
            (media_id,),
        ).fetchone())  # fmt: skip

    with tempfile.TemporaryDirectory() as tmp:
        library = Path(tmp) / "Musica"
        library.mkdir()
        song = library / "01 - Vino Tinto.mp3"
        song.write_bytes(silence * 20)
        id3 = ID3()
        id3.add(TIT2(encoding=1, text=["Vino tinto"]))
        id3.add(TPE1(encoding=1, text=["Estopa"]))
        id3.add(TALB(encoding=1, text=["Destrangis"]))
        id3.save(song, v2_version=3, v1=0)
        bare = library / "02 - Sin etiquetas.mp3"
        bare.write_bytes(silence * 20)
        catalog = new_catalog()
        add_folder(catalog, library)
        by_path = ids(catalog)
        song_id, bare_id = by_path[song.name], by_path[bare.name]

        # a) Sin leer, no se escribe (espera a su primera lectura, como las fotos); al
        #    leerlo, lo pendiente no se pisa
        update_user_field(catalog, [song_id], "rating", 2)
        update_metadata_fields(catalog, [song_id], {"album": "Destrangis (reedición)"})
        catalog.commit()
        mtime_before = song.stat().st_mtime_ns
        assert pending(catalog) == 0 and write_pending_user_data(catalog).total == 0
        assert song.stat().st_mtime_ns == mtime_before
        process_pending_metadata(catalog, registry=audio_registry)
        assert audio_row(catalog, song_id)[4] == "Destrangis (reedición)"

        # b) Escritura: las etiquetas, al MP3; lo demás, al '.arca.json'. Al MP3 sin
        #    etiquetas se le crea el ID3v2 (la preferida) y se relee
        update_metadata_fields(catalog, [song_id], {
            "title": "Vino Tinto", "creator": "Estopa; Rosendo", "description": "Primer disco",
            "track_number": 3, "track_total": 12, "genre": "Rock", "city": "Barcelona",
        })  # fmt: skip
        update_user_field(catalog, [song_id], "flag", 1)
        update_user_field(catalog, [song_id], "color_label", "red")
        assign_keyword(catalog, [song_id], ensure_keyword_path(catalog, ("Rumba",)))
        update_metadata_fields(catalog, [bare_id], {"album": "Nuevo"})
        catalog.commit()
        result = write_pending_user_data(catalog)
        assert (result.total, result.written, result.failed) == (2, 2, 0), result.summary()
        assert result.rescan_requested == 1 and pending(catalog) == 0, result.summary()
        tags = read_audio(song).tags
        assert (tags.title, tags.artist, tags.album) == (
            "Vino Tinto", "Estopa; Rosendo", "Destrangis (reedición)"
        ), tags  # fmt: skip
        assert (tags.track_number, tags.track_total, tags.genre, tags.comment) == (
            3, 12, "Rock", "Primer disco"
        ), tags  # fmt: skip
        entry = read_folder_file(library).items[song.name]
        assert (entry["rating"], entry["flag"], entry["color_label"]) == (2, 1, "red"), entry
        assert entry["keywords"] == [["Rumba"]] and entry["city"] == "Barcelona", entry
        # Lo de las etiquetas, solo en el archivo (un dato, un sitio)
        assert not {"title", "creator", "description", "album", "track_number", "genre"} & set(
            entry
        ), entry
        assert (read_audio(bare).tag_type, read_audio(bare).tags.album) == ("ID3v2.3", "Nuevo")
        # El catálogo relee el que tiene etiqueta nueva y no ve falsos cambios en ninguno
        process_pending_metadata(catalog, registry=audio_registry)
        assert catalog.execute(
            "SELECT tag_type FROM audio_details WHERE media_id = ?", (bare_id,)
        ).fetchone()[0] == "ID3v2.3"
        assert add_folder(catalog, library).changed_items == 0

        # c) Catálogo NUEVO: las etiquetas salen del archivo y lo demás, del '.arca.json'
        rebuilt = new_catalog()
        add_folder(rebuilt, library)
        process_pending_metadata(rebuilt, registry=audio_registry)
        new_id = ids(rebuilt)[song.name]
        assert audio_row(rebuilt, new_id) == (
            "Vino Tinto", "Estopa; Rosendo", "Primer disco", "Barcelona",
            "Destrangis (reedición)", 3, 12, "Rock",
        ), audio_row(rebuilt, new_id)  # fmt: skip
        assert user_values(rebuilt)[song.name] == (2, 1, "red")
        assert media_keyword_paths(rebuilt, new_id) == [("Rumba",)]
        assert pending(rebuilt) == 0
        print("MP3: sus etiquetas en el archivo y lo demás en el .arca.json, de ida y vuelta")
        catalog.close()
        rebuilt.close()

    print("Autoprueba finalizada correctamente.")
