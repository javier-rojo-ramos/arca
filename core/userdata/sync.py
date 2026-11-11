"""Sincronización de los datos del usuario entre el catálogo y su destino fuera de él.

Este módulo NO depende de Qt. Une la base de datos con los dos almacenes externos
('xmp_writer.py' y 'folder_file.py') según la política de cada formato ('policy.py').

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
   Tras modificar un archivo se actualizan su tamaño y su fecha en la base de datos,
   para que el escáner no lo confunda con un cambio externo (ni regenere la miniatura:
   los píxeles no cambian).

2. ARCHIVOS -> CATÁLOGO (al importar o reescanear). Regla: MANDA EL ARCHIVO, campo a
   campo, salvo en los campos pendientes de escribir (su cambio es más nuevo).
       - XMP: 'apply_file_user_data', que llama el procesador de metadatos con lo que el
         extractor ha leído del archivo (y 'apply_file_keywords' para las palabras clave,
         que dejan exactamente las del archivo). Un campo que el archivo NO trae (etiqueta
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

__version__ = "1.5.0"
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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.keywords import media_keyword_paths, same_keywords, set_media_keywords
from core.catalog.media_queries import USER_FIELD_BITS
from core.jobs.progress import JobProgress
from core.metadata.exiftool_runner import ExifToolError, ExifToolRunner, find_sidecars
from core.metadata.keyword_tags import FileKeywords
from core.userdata.editable_fields import (
    EDITABLE_COLUMNS,
    default_title,
    field_for,
    file_title,
    pending_columns,
    unless_pending_sql,
)
from core.userdata.folder_file import (
    KEYWORDS_KEY,
    FolderData,
    FolderFileError,
    edited_values_from_entry,
    find_entry_key,
    keywords_from_entry,
    merge_entry,
    read_folder_file,
    user_values_from_entry,
    write_folder_file,
)
from core.userdata.policy import (
    UserDataDestination,
    destination_for,
    sidecar_path_for_writing,
)
from core.userdata.xmp_writer import XmpUserDataWriter, XmpWriteRequest

# Nombre de la fase para la columna 'stage' de la tabla 'scan_errors'
SCAN_STAGE_USERDATA = "userdata"

# Elementos por lote (y por transacción corta)
DEFAULT_BATCH_SIZE = 200

# Columnas de los datos del usuario que se sincronizan (mismo orden en todo el módulo)
_USER_COLUMNS: tuple[str, ...] = ("rating", "flag", "color_label")

# Caché de archivos de carpeta durante un escaneo: carpeta -> contenido (None = ilegible)
FolderFileCache = dict[Path, FolderData | None]

# Valor de un metadato que la entrada del archivo de carpeta no trae (no editado): distinto
# de None (vaciado a propósito), para decidir si hay que escribir la entrada
_NOT_EDITED = object()


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
        rescan_requested: Archivos que habían cambiado fuera de la aplicación (p. ej. en
            Lightroom) y han quedado pendientes de releer sus metadatos.
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


@dataclass(slots=True)
class _Item:
    """Un elemento pendiente, con lo necesario para escribirlo y actualizar la BD."""

    media_id: int
    location_id: int
    relative_path: str
    path: Path
    destination: UserDataDestination
    values: dict[str, Any]  # los tres valores de la BD
    pending: int  # bits de 'user_data_pending' (qué campos hay que escribir)
    file_size: int
    file_mtime_ns: int
    thumbnail_mtime_ns: int | None
    sidecar_mtime_ns: int | None
    keywords_pending: bool = False  # 'keywords_pending' (hay que escribir las palabras)
    keywords: tuple[tuple[str, ...], ...] = ()  # las palabras del catálogo (rutas)
    metadata_pending: int = 0  # bits de 'metadata_edit_pending' (metadatos editados)
    metadata: dict[str, Any] = field(default_factory=dict)  # sus valores en la BD
    # Resultado
    ok: bool = False
    written: bool = False
    deferred: bool = False  # no se intentó (falta ExifTool): no es un fallo del archivo
    message: str = ""
    db_updates: dict[str, Any] = field(default_factory=dict)  # columnas a actualizar tras escribir
    rescan: bool = False  # el archivo cambió fuera de la aplicación: releer sus metadatos

    @property
    def wanted(self) -> dict[str, Any]:
        """Solo los campos pendientes, con su valor de la BD (lo que hay que escribir)."""
        wanted: dict[str, Any] = {
            column: self.values[column]
            for column in _USER_COLUMNS
            if self.pending & USER_FIELD_BITS[column]
        }
        if self.keywords_pending:
            wanted[KEYWORDS_KEY] = self.keywords
        # Metadatos editados: el título igual al nombre del archivo es «sin título»
        for column in pending_columns(self.metadata_pending):
            value = self.metadata[column]
            wanted[column] = file_title(value, self.path.name) if column == "title" else value
        return wanted


# Elementos con algo pendiente de escribir fuera del catálogo (presentes en disco)
_PENDING_SQL = (
    "(user_data_pending <> 0 OR keywords_pending <> 0 OR metadata_edit_pending <> 0) "
    "AND is_missing = 0"
)


def count_pending_user_data(conn: sqlite3.Connection) -> int:
    """Cuántos elementos (presentes) tienen datos del usuario sin escribir fuera del catálogo.

    Cuenta también los metadatos editados (título, pie...) y las palabras clave.
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
) -> UserDataWriteResult:
    """Escribe en su destino los datos del usuario pendientes y quita la marca.

    Args:
        conn: Conexión sqlite3 al catálogo.
        progress: Función a la que se avisa tras cada elemento.
        cancel_event: Si se activa, el trabajo se detiene al terminar el lote en curso.
        runner_factory: Crea el lector de ExifTool (por defecto, 'ExifToolRunner()').
            Solo se llama si hay algún XMP que escribir.
        batch_size: Elementos por lote.

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
    writer_holder: dict[str, XmpUserDataWriter | None] = {}  # se crea al primer XMP
    counts = {"written": 0, "already_ok": 0, "failed": 0, "offline": 0, "rescan": 0}
    messages: list[str] = []
    exiftool_missing = False
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
                      keywords_pending, metadata_edit_pending, {", ".join(EDITABLE_COLUMNS)}
                 FROM media_items
                WHERE {_PENDING_SQL} AND id > ?
                ORDER BY id LIMIT ?""",
            (last_id, batch_size),
        ).fetchall()
        if not rows:
            break
        last_id = rows[-1][0]

        # Elementos del lote cuya unidad está conectada (los demás siguen pendientes)
        items: list[_Item] = []
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
                _Item(
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

        # Escritura (sin transacción abierta: se espera al disco y a ExifTool)
        folder_items = [i for i in items if i.destination is UserDataDestination.FOLDER_FILE]
        xmp_items = [i for i in items if i.destination is not UserDataDestination.FOLDER_FILE]
        _write_folder_items(folder_items)
        if xmp_items:
            writer = _get_writer(writer_holder, runner_factory)
            if writer is None:
                exiftool_missing = True
                for item in xmp_items:
                    item.deferred = True
            else:
                try:
                    _write_xmp_items(writer, xmp_items, cancel_event)
                except ExifToolError as error:
                    # Fallo general de ExifTool: el resto del lote queda pendiente
                    exiftool_missing = True
                    logger.error(f"ExifTool no puede escribir: {error}")
                    for item in xmp_items:
                        if not item.ok:
                            item.deferred = True

        # Resultado en la base de datos (transacción corta)
        try:
            _save_results(conn, items)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        for item in items:
            counts["rescan"] += int(item.rescan)
            if item.ok:
                counts["written" if item.written else "already_ok"] += 1
            elif not item.deferred:
                counts["failed"] += 1
                if len(messages) < 20:
                    messages.append(f"{item.relative_path}: {item.message}")
        done += len(rows)
        _notify(progress, min(done, total), total)

    result = UserDataWriteResult(
        total=total,
        written=counts["written"],
        already_ok=counts["already_ok"],
        failed=counts["failed"],
        skipped_offline=counts["offline"],
        cancelled=cancelled,
        exiftool_missing=exiftool_missing,
        rescan_requested=counts["rescan"],
        failed_messages=tuple(messages),
    )
    logger.info(f"Datos del usuario escritos:\n{result.summary()}")
    for message in messages:
        logger.warning(f"No se pudo escribir: {message}")
    return result


def _get_writer(
    holder: dict[str, XmpUserDataWriter | None],
    runner_factory: Callable[[], ExifToolRunner] | None,
) -> XmpUserDataWriter | None:
    """Crea (una vez por trabajo) el escritor de XMP. None si ExifTool no está disponible."""
    if "writer" not in holder:
        try:
            runner = runner_factory() if runner_factory else ExifToolRunner()
            runner.version()  # comprueba que se puede ejecutar de verdad
            holder["writer"] = XmpUserDataWriter(runner)
        except ExifToolError as error:
            logger.warning(f"ExifTool no disponible: no se escriben XMP ({error})")
            holder["writer"] = None
    return holder["writer"]


def _write_folder_items(items: list[_Item]) -> None:
    """Escribe en el archivo de carpeta los elementos de destino FOLDER_FILE.

    Una lectura y, como mucho, una escritura por carpeta. Si el archivo de una carpeta
    no se puede leer (dañado, sin permisos), NO se reescribe: sus elementos fallan y
    siguen pendientes (reescribirlo a ciegas podría borrar datos de otros archivos).
    """
    by_folder: dict[Path, list[_Item]] = {}
    for item in items:
        by_folder.setdefault(item.path.parent, []).append(item)

    for folder, group in by_folder.items():
        try:
            data = read_folder_file(folder)
        except FolderFileError as error:
            for item in group:
                item.message = str(error)
            continue

        changed = False
        for item in group:
            key = find_entry_key(data.items, item.path.name)
            old_entry = data.items.get(key) if key else None
            # Se parte de lo que ya tiene y se cambian solo los campos pendientes
            wanted = item.wanted
            old_values: dict[str, Any] = user_values_from_entry(old_entry)
            if KEYWORDS_KEY in wanted:
                old_values[KEYWORDS_KEY] = keywords_from_entry(old_entry)
            # Metadatos editados: sin la clave NO es lo mismo que vaciado (""): la clave
            # dice que se editó, y entonces manda sobre lo que traiga el archivo
            old_edits = edited_values_from_entry(old_entry)
            for column in EDITABLE_COLUMNS:
                if column in wanted:
                    old_values[column] = old_edits.get(column, _NOT_EDITED)
            new_values = {**old_values, **wanted}
            if _same_values(new_values, old_values):
                continue  # ya lo tenía: no hace falta escribir por él
            new_entry = merge_entry(old_entry, new_values)
            if key is not None and key != item.path.name:
                del data.items[key]  # la entrada pasa a llevar el nombre exacto del archivo
            if new_entry is None:
                data.items.pop(item.path.name, None)
            else:
                data.items[item.path.name] = new_entry
            item.written = True
            changed = True

        try:
            if changed:
                write_folder_file(data)
        except FolderFileError as error:
            for item in group:
                item.written = False
                item.message = str(error)
            continue
        for item in group:
            item.ok = True


def _same_values(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """True si dos juegos de valores del usuario son iguales (las palabras clave, sin
    orden pero letra a letra: un cambio solo de mayúsculas también se escribe)."""
    if first.keys() != second.keys():
        return False
    for key, value in first.items():
        if key == KEYWORDS_KEY:
            if not same_keywords(value, second[key], exact=True):
                return False
        elif value != second[key]:
            return False
    return True


def _write_xmp_items(
    writer: XmpUserDataWriter, items: list[_Item], cancel_event: threading.Event | None
) -> None:
    """Escribe los elementos de destino XMP (incrustado o sidecar) y prepara la BD.

    Raises:
        ExifToolError: Si ExifTool no se puede ejecutar (fallo general).
    """
    requests: list[XmpWriteRequest] = []
    targets: list[_Item] = []
    before: dict[int, os.stat_result | None] = {}  # estado del destino antes de escribir
    for item in items:
        try:
            original = item.path.stat()
        except FileNotFoundError:
            item.message = "El archivo no existe (se marcará al reescanear la carpeta)"
            continue
        except OSError as error:
            item.message = f"No se puede acceder al archivo ({error.strerror or error})"
            continue

        if item.destination is UserDataDestination.XMP_SIDECAR:
            target = sidecar_path_for_writing(item.path)
            try:
                before[item.media_id] = target.stat()
            except OSError:
                before[item.media_id] = None  # el sidecar aún no existe
            # Si el sidecar cambió fuera de la aplicación y aún no se ha leído, habrá
            # que releer los metadatos del RAW (p. ej. un título puesto en Lightroom)
            sidecar_before = before[item.media_id]
            if sidecar_before is not None and sidecar_before.st_mtime_ns != item.sidecar_mtime_ns:
                item.rescan = True
        else:
            target = item.path
            before[item.media_id] = original
            # ¿Cambió el archivo fuera de la aplicación desde el último escaneo?
            if (original.st_size, original.st_mtime_ns) != (item.file_size, item.file_mtime_ns):
                item.rescan = True

        requests.append(XmpWriteRequest(target, item.wanted))
        targets.append(item)

    if not requests:
        return
    outcomes = writer.write(requests, cancel_event)
    for item in targets[len(outcomes) :]:
        item.deferred = True  # cancelado antes de llegar a él: sigue pendiente, sin error
    for item, outcome in zip(targets, outcomes, strict=False):
        item.ok = outcome.ok
        item.written = outcome.written
        item.message = outcome.message
        if not (outcome.written or item.rescan):
            continue  # el destino no ha cambiado: nada que anotar

        # Estado del destino que se anota en la base de datos: el de después de escribir
        # o, si no se escribió, el que tenía (cambiado fuera de la aplicación)
        state = before[item.media_id]
        if outcome.written:
            try:
                state = outcome.request.path.stat()
            except OSError:
                state = None  # se escribió y comprobó; se corregirá en el próximo escaneo
        if state is None:
            continue

        # Se anota SIEMPRE el estado actual: así la próxima pasada no vuelve a ver un
        # "cambio externo" en el mismo archivo (si la escritura sigue fallando, no se
        # entra en un bucle de relecturas)
        if item.destination is UserDataDestination.XMP_SIDECAR:
            # Misma regla que el escáner: si hay dos sidecars, la fecha más reciente
            item.db_updates = {
                "sidecar_mtime_ns": _sidecars_mtime(item.path) or state.st_mtime_ns,
                "has_xmp_sidecar": 1,
            }
        else:
            item.db_updates = {"file_size": state.st_size, "file_mtime_ns": state.st_mtime_ns}


def _sidecars_mtime(path: Path) -> int | None:
    """Fecha más reciente de los sidecars de un archivo (la misma que anota el escáner)."""
    mtimes = []
    for sidecar in find_sidecars(path):
        try:
            mtimes.append(sidecar.stat().st_mtime_ns)
        except OSError:
            continue
    return max(mtimes) if mtimes else None


def _save_results(conn: sqlite3.Connection, items: Iterable[_Item]) -> None:
    """Guarda en la base de datos el resultado de un lote (sin hacer commit)."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

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

        if item.ok:
            # Se quita el bit de cada campo escrito SOLO si su valor sigue siendo el
            # escrito: si el usuario lo cambió mientras tanto, sigue pendiente
            for column, value in item.wanted.items():
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
                conn.execute(
                    "UPDATE media_items SET metadata_edit_pending = metadata_edit_pending & ~? "
                    f"WHERE id = ? AND {column} IS ?",
                    (field_for(column).bit, item.media_id, item.metadata[column]),
                )
            # Las palabras clave: solo si siguen siendo las escritas (si el usuario las
            # cambió mientras tanto, siguen pendientes)
            if KEYWORDS_KEY in item.wanted and same_keywords(
                media_keyword_paths(conn, item.media_id), item.wanted[KEYWORDS_KEY], exact=True
            ):
                conn.execute("UPDATE media_items SET keywords_pending = 0 WHERE id = ?", (item.media_id,))
            conn.execute(
                "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ? "
                "AND stage = ?",
                (item.location_id, item.relative_path, SCAN_STAGE_USERDATA),
            )
        elif not item.deferred:
            conn.execute(
                """INSERT INTO scan_errors(storage_location_id, relative_path, stage, message)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(storage_location_id, relative_path, stage)
                   DO UPDATE SET message = excluded.message, occurred_at = CURRENT_TIMESTAMP""",
                (item.location_id, item.relative_path, SCAN_STAGE_USERDATA, item.message),
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
) -> bool:
    """Deja en un elemento las palabras clave leídas de su XMP. Manda el archivo.

    A diferencia de la valoración, aquí una etiqueta ausente SÍ significa "ninguna"
    (Lightroom borra la lista al quitar la última palabra), así que un archivo sin
    palabras deja el elemento sin ninguna. Si las palabras del elemento están PENDIENTES
    de escribir (se cambiaron en la aplicación), no se tocan: su cambio es más nuevo.

    Args:
        conn: Conexión (con la transacción del procesador abierta).
        media_id: Elemento.
        keywords: Lo que el extractor leyó; None = no se pudo leer con seguridad o el
            extractor no lee palabras clave: no se toca nada.
        expected_state: Como en 'apply_file_user_data': si el archivo cambió después de
            leerlo, lo leído ya no vale y no se aplica.

    Returns:
        True si cambió alguna asignación.
    """
    if keywords is None:
        return False
    row = conn.execute(
        "SELECT file_mtime_ns, sidecar_mtime_ns, keywords_pending FROM media_items WHERE id = ?",
        (media_id,),
    ).fetchone()
    if row is None or row[2]:
        return False  # no existe, o sus palabras están pendientes de escribir
    if expected_state is not None and (row[0], row[1]) != expected_state:
        return False
    return set_media_keywords(conn, media_id, keywords.paths, keywords.flat)


def apply_folder_files(
    conn: sqlite3.Connection,
    location_root: Path,
    location_id: int,
    relative_paths: Iterable[str],
    cache: FolderFileCache | None = None,
) -> int:
    """Aplica al catálogo los datos de los archivos de carpeta. Manda el archivo.

    Lo llama 'add_folder' tras guardar cada lote (con su transacción abierta). Solo trata
    los archivos cuyo destino es FOLDER_FILE y, de ellos, los campos que no están
    pendientes de escribir. Las carpetas sin archivo '.arca.json' no se tocan. Los
    metadatos editados (título, pie...) solo se tocan si la entrada trae su clave.

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
        if destination_for(relative_path) is not UserDataDestination.FOLDER_FILE:
            continue
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
        keywords_changed = not row[5] and set_media_keywords(
            conn, row[0], keywords_from_entry(entry)
        )
        current = dict(zip(_USER_COLUMNS, row[1:4], strict=True))
        updates = {
            column: values[column]
            for column in _USER_COLUMNS
            if not row[4] & USER_FIELD_BITS[column] and values[column] != current[column]
        }
        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(
                f"UPDATE media_items SET {assignments} WHERE id = ?",
                (*updates.values(), row[0]),
            )
        # Metadatos editados: solo los que la entrada trae (sin la clave, manda lo que
        # lea el extractor), salvo los pendientes de escribir
        edits_changed = _apply_edited_values(
            conn, row[0], posix.name, edited_values_from_entry(entry)
        )
        if updates or keywords_changed or edits_changed:
            changed += 1
    return changed


def folder_file_edits(
    location_root: Path, relative_path: str, cache: FolderFileCache
) -> dict[str, str | None] | None:
    """Metadatos editados que guarda el '.arca.json' para un archivo FOLDER_FILE.

    Lo usa el procesador de metadatos: en estos formatos lo editado en la aplicación vive
    solo en el archivo de carpeta (el original no se toca), así que manda SIEMPRE sobre
    lo que lea el extractor.

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
    return edited_values_from_entry(data.items.get(key) if key else None)


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
    conn: sqlite3.Connection, media_id: int, file_name: str, edits: dict[str, str | None]
) -> bool:
    """Pone en un elemento los metadatos editados del archivo de carpeta.

    No toca los campos pendientes de escribir (su cambio es más nuevo). Un título vaciado
    vuelve al nombre del archivo sin extensión.

    Returns:
        True si cambió algo.
    """
    if not edits:
        return False
    values = {
        column: default_title(file_name) if column == "title" and value is None else value
        for column, value in edits.items()
    }
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

    print("Autoprueba finalizada correctamente.")
