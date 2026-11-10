"""Procesador de metadatos: lee los archivos pendientes del catálogo y guarda lo extraído.

Este módulo NO depende de Qt. 'process_pending_metadata' es un "trabajo" en el
sentido de 'core/jobs/progress.py': recibe una conexión, avisa del progreso y
obedece a un evento de cancelación, así que se envía tal cual al gestor de
trabajos y se ejecuta en un hilo secundario.

Qué archivos son "pendientes": los de un tipo de medio con extractor registrado
cuya 'scan_version' es menor que la versión de ese extractor. Eso incluye los
recién añadidos (versión 0), los que cambiaron en disco (add_folder los deja en 0)
y todos los de un tipo cuyo extractor ha subido de versión porque ahora lee
campos nuevos. Los tipos sin extractor (de momento vídeo, audio y ebooks) no se
tocan: siguen pendientes hasta que se registre uno.

Cómo trabaja, por lotes de archivos (100 por defecto):
    1. Lee el lote de la tabla (por 'id', sin repetir nunca un archivo).
    2. Se lo entrega al extractor de cada tipo de medio, que lo lee de una vez
       ('extract_batch': con ExifTool, una sola llamada por lote) SIN transacción
       abierta: mientras se espera al disco no se bloquea la escritura al resto de
       la aplicación.
    3. Guarda todo el lote en una transacción corta y hace 'commit'.
    Se puede cancelar: se comprueba entre lote y lote, y lo ya guardado queda
    coherente; la siguiente ejecución continúa donde se quedó.

Qué escribe (y qué no): columnas de 'media_items' que NO estén en
'PROTECTED_COLUMNS' (es decir, metadatos extraídos), la tabla de detalles del
tipo, 'scan_version', 'last_scanned_at' y los errores de la fase 'metadata' en
'scan_errors'. Los extractores nunca escriben datos del usuario; la valoración, la
marca y el color que traiga el XMP del archivo los aplica aparte
'core.userdata.sync.apply_file_user_data' (manda el archivo, salvo que el elemento
esté pendiente de escribir).

Metadatos descriptivos editables (título, pie, ubicación...; ver
'core/userdata/editable_fields.py'): manda el archivo, salvo en las columnas cuyo bit de
'metadata_edit_pending' está puesto (el cambio del usuario aún no está escrito). En los
formatos sin XMP, lo editado está en el '.arca.json' de la carpeta y manda siempre sobre lo
leído. Sin título en el archivo, 'title' vale el nombre del archivo sin extensión.

2.3.0 Metadatos editables: no se pisan los pendientes de escribir; en los formatos sin XMP
      manda el '.arca.json'; un archivo sin título deja el nombre sin extensión (antes se
      conservaba el título anterior).

Qué pasa con cada archivo:
    - Se lee bien      -> se guardan sus datos y se borra cualquier error anterior.
    - Falla (dañado...) -> se anota en 'scan_errors' y se marca como "intentado" con
                          la versión actual, para no reintentarlo en cada ejecución.
                          Se volverá a intentar si el archivo cambia o sube la versión.
    - Formato sin soporte todavía -> se marca como "intentado", sin error (no es un
                          fallo del archivo); se cuenta aparte.
    - Ya no existe     -> se marca 'is_missing = 1'.
    - Su unidad no está conectada -> no se toca (sigue pendiente) y se cuenta aparte.

Prueba rápida (desde la raíz del proyecto):
    python -m core.metadata.processor
"""

__version__ = "2.3.0"
__all__ = [
    "DEFAULT_BATCH_SIZE",
    "SCAN_STAGE_METADATA",
    "MetadataJobResult",
    "process_pending_metadata",
]

# Librerías estándar
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.jobs.progress import JobProgress
from core.metadata.base import (
    PROTECTED_COLUMNS,
    ExtractionResult,
    MetadataError,
    MetadataExtractor,
    UnsupportedFormatError,
)
from core.metadata.registry import ExtractorRegistry, default_registry
from core.userdata.editable_fields import (
    EDITABLE_COLUMNS,
    default_title,
    unless_pending_sql,
)
from core.userdata.policy import uses_xmp
from core.userdata.sync import (
    FolderFileCache,
    apply_file_keywords,
    apply_file_user_data,
    folder_file_edits,
)

# Nombre de la fase para la columna 'stage' de la tabla 'scan_errors'
SCAN_STAGE_METADATA = "metadata"

# Archivos por lote (y por transacción y por llamada a ExifTool)
DEFAULT_BATCH_SIZE = 100

# Resultado de procesar un archivo
_OK = "ok"
_FAILED = "failed"
_UNSUPPORTED = "unsupported"
_MISSING = "missing"
_OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class MetadataJobResult:
    """Resultado de una ejecución de 'process_pending_metadata'.

    Attributes:
        total: Archivos pendientes al empezar.
        processed: Archivos leídos con éxito.
        failed: Archivos que no se pudieron leer (están en 'scan_errors').
        unsupported: Archivos de un formato que aún no se sabe leer.
        missing: Archivos que ya no existen en disco (marcados 'is_missing').
        skipped_offline: Archivos sin tocar porque su unidad no está conectada.
        cancelled: True si el trabajo se interrumpió antes de terminar.
        unsupported_extensions: Extensiones de los archivos 'unsupported'.
    """

    total: int
    processed: int
    failed: int
    unsupported: int
    missing: int
    skipped_offline: int
    cancelled: bool
    unsupported_extensions: Counter[str]

    @property
    def has_warnings(self) -> bool:
        """True si algo merece la atención del usuario (errores, cancelación...)."""
        return bool(
            self.failed
            or self.unsupported
            or self.missing
            or self.skipped_offline
            or self.cancelled
        )

    def status_text(self) -> str:
        """Frase corta para la barra de estado ('' si no había nada pendiente)."""
        if self.total == 0:
            return ""
        text = f"Metadatos leídos: {self.processed} de {self.total} archivos"
        if self.failed:
            text += f", {self.failed} con errores"
        if self.unsupported:
            text += f", {self.unsupported} de formato sin soporte"
        if self.cancelled:
            text += " (cancelado)"
        return text

    def summary(self) -> str:
        """Resumen en varias líneas, para el registro o para un cuadro de diálogo."""
        lines = [f"Archivos leídos: {self.processed} de {self.total}"]
        if self.failed:
            lines.append(f"Con errores: {self.failed} (ver la lista de errores)")
        if self.unsupported:
            top = ", ".join(
                f"{ext} ({count})"
                for ext, count in self.unsupported_extensions.most_common(5)
            )
            lines.append(f"Formato sin soporte todavía: {self.unsupported} [{top}]")
        if self.missing:
            lines.append(f"Ya no están en disco: {self.missing}")
        if self.skipped_offline:
            lines.append(f"Sin comprobar (unidad desconectada): {self.skipped_offline}")
        if self.cancelled:
            lines.append("El proceso se canceló antes de terminar.")
        return "\n".join(lines)


@dataclass(slots=True)
class _Outcome:
    """Lo ocurrido con un archivo, a la espera de guardarlo en la base de datos."""

    kind: str
    media_id: int
    location_id: int
    relative_path: str
    extractor: MetadataExtractor
    extension: str
    result: ExtractionResult | None = None
    message: str = ""
    # (file_mtime_ns, sidecar_mtime_ns) en la BD al leer el archivo: si cambian antes de
    # guardar (la aplicación acaba de escribir en él), sus datos del usuario no se aplican
    state: tuple[int | None, int | None] | None = None
    # Solo en los formatos con '.arca.json' (sin XMP): los metadatos editados que guarda
    # para este archivo (columna -> valor; vacío = ninguno). None = el '.arca.json' está
    # dañado y no se sabe qué se editó (o el formato usa XMP: no se mira)
    folder_edits: dict[str, str | None] | None = None


def process_pending_metadata(
    conn: sqlite3.Connection,
    *,
    registry: ExtractorRegistry | None = None,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> MetadataJobResult:
    """Extrae y guarda los metadatos de todos los archivos pendientes del catálogo.

    Args:
        conn: Conexión sqlite3 al catálogo (con o sin 'row_factory').
        registry: Extractores disponibles (por defecto, 'default_registry()').
        progress: Función a la que se avisa tras cada archivo (conviene envolverla
            con 'core.jobs.progress.throttled' si llega a la interfaz).
        cancel_event: Si se activa desde otro hilo, el trabajo se detiene en cuanto
            termina el archivo en curso.
        batch_size: Archivos por lote y por transacción.

    Returns:
        Un 'MetadataJobResult' con los recuentos.

    Raises:
        ValueError: Si un extractor devuelve columnas que no puede escribir (un
            error de programación: se deshace el lote en curso y se aborta).
        sqlite3.Error: Si falla la base de datos.
    """
    if registry is None:
        registry = default_registry()
    extractors = list(registry)
    if not extractors:
        return MetadataJobResult(0, 0, 0, 0, 0, 0, False, Counter())

    # "Pendiente" = tipo con extractor y versión guardada menor que la del extractor
    pending_sql = " OR ".join(
        "(media_type = ? AND scan_version < ?)" for _ in extractors
    )
    pending_params: list[object] = []
    for extractor in extractors:
        pending_params += [extractor.media_type.value, extractor.version]

    total = conn.execute(
        f"SELECT COUNT(*) FROM media_items WHERE is_missing = 0 AND ({pending_sql})",
        pending_params,
    ).fetchone()[0]
    logger.info(f"Metadatos: {total} archivos pendientes")

    locations = {
        row[0]: Path(row[1])
        for row in conn.execute("SELECT id, absolute_path FROM storage_locations")
    }
    table_columns: dict[
        str, frozenset[str]
    ] = {}  # columnas de cada tabla (se leen una vez)

    counts: Counter[str] = Counter()
    unsupported_extensions: Counter[str] = Counter()
    cancelled = False
    done = 0
    last_id = (
        0  # paginación por 'id': un archivo nunca se vuelve a pedir en esta ejecución
    )

    _notify(progress, done, total)

    while not cancelled:
        rows = conn.execute(
            "SELECT id, storage_location_id, relative_path, media_type, file_extension, "
            "file_mtime_ns, sidecar_mtime_ns "
            f"FROM media_items WHERE id > ? AND is_missing = 0 AND ({pending_sql}) "
            "ORDER BY id LIMIT ?",
            (last_id, *pending_params, batch_size),
        ).fetchall()
        if not rows:
            break
        last_id = rows[-1][0]

        # La cancelación se comprueba entre lote y lote (y dentro del lote, si el
        # extractor la respeta)
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break

        # 1. Se leen los archivos del lote (aquí no hay ninguna transacción abierta)
        outcomes, batch_cancelled = _extract_rows(
            rows, registry, locations, cancel_event
        )
        cancelled = cancelled or batch_cancelled
        for outcome in outcomes:
            counts[outcome.kind] += 1
            if outcome.kind == _UNSUPPORTED:
                unsupported_extensions[outcome.extension or "(sin extensión)"] += 1
            done += 1
            _notify(progress, done, total)

        # 2. Se guarda lo leído en una transacción corta (también si se canceló a medias)
        try:
            _write_outcomes(conn, outcomes, table_columns)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    result = MetadataJobResult(
        total=total,
        processed=counts[_OK],
        failed=counts[_FAILED],
        unsupported=counts[_UNSUPPORTED],
        missing=counts[_MISSING],
        skipped_offline=counts[_OFFLINE],
        cancelled=cancelled,
        unsupported_extensions=unsupported_extensions,
    )
    logger.info(f"Metadatos procesados:\n{result.summary()}")
    return result


# -----------------------------------------------------------------------------
# Lectura de un archivo
# -----------------------------------------------------------------------------


def _extract_rows(
    rows: list[sqlite3.Row | tuple],
    registry: ExtractorRegistry,
    locations: dict[int, Path],
    cancel_event: threading.Event | None,
) -> tuple[list[_Outcome], bool]:
    """Lee los metadatos de un lote de filas y devuelve lo ocurrido con cada archivo.

    Las filas se agrupan por tipo de medio: cada extractor recibe de una vez todos sus
    archivos del lote. Un archivo problemático no aborta el trabajo: su fallo se
    convierte en un resultado 'failed' con su mensaje. Solo un fallo general del
    extractor (p. ej. ExifTool no se puede ejecutar) se propaga y aborta el trabajo.

    Returns:
        Los resultados de los archivos tratados y si el lote se cortó por cancelación.
    """
    outcomes: list[_Outcome] = []
    cancelled = False
    online_locations: dict[int, bool] = {}
    # Archivos de carpeta leídos en este lote (se leen aquí, sin transacción abierta)
    folder_files: FolderFileCache = {}

    groups: dict[str, list[sqlite3.Row | tuple]] = {}
    for row in rows:
        groups.setdefault(row[3], []).append(row)

    for media_type, group in groups.items():
        extractor = registry.get(media_type)
        assert extractor is not None  # la consulta solo pide tipos con extractor

        pending_rows: list[sqlite3.Row | tuple] = []
        paths: list[Path] = []
        for row in group:
            media_id, location_id, relative_path, _media_type, extension = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4] or "",
            )

            # ¿Está conectada la unidad? Se comprueba una vez por ubicación y lote.
            if location_id not in online_locations:
                root = locations.get(location_id)
                try:
                    online_locations[location_id] = root is not None and root.is_dir()
                except OSError:
                    online_locations[location_id] = False
            if not online_locations[location_id]:
                outcomes.append(
                    _Outcome(
                        _OFFLINE,
                        media_id,
                        location_id,
                        relative_path,
                        extractor,
                        extension,
                    )
                )
                continue

            pending_rows.append(row)
            paths.append(locations[location_id] / relative_path)

        if not paths:
            continue

        results = extractor.extract_batch(paths, cancel_event)
        for row, path, result in zip(pending_rows, paths, results, strict=True):
            if result is None:  # no se llegó a leer por haberse cancelado
                cancelled = True
                continue
            outcome = _to_outcome(row, extractor, path, result)
            # Formatos sin XMP: lo editado en la aplicación está en su '.arca.json'
            if outcome.kind == _OK and not uses_xmp(outcome.extension):
                outcome.folder_edits = folder_file_edits(
                    locations[outcome.location_id], outcome.relative_path, folder_files
                )
            outcomes.append(outcome)

    return outcomes, cancelled


def _to_outcome(
    row: sqlite3.Row | tuple,
    extractor: MetadataExtractor,
    path: Path,
    result: ExtractionResult | Exception,
) -> _Outcome:
    """Convierte el resultado de un extractor para un archivo en lo que hay que guardar."""
    media_id, location_id, relative_path, extension = (
        row[0],
        row[1],
        row[2],
        row[4] or "",
    )

    def outcome(kind: str, **extra: object) -> _Outcome:
        return _Outcome(
            kind,
            media_id,
            location_id,
            relative_path,
            extractor,
            extension,
            state=(row[5], row[6]) if len(row) > 6 else None,
            **extra,
        )

    if isinstance(result, ExtractionResult):
        return outcome(_OK, result=result)
    if isinstance(result, FileNotFoundError):
        return outcome(_MISSING)
    if isinstance(result, UnsupportedFormatError):
        return outcome(_UNSUPPORTED, message=str(result))
    if isinstance(result, MetadataError):
        return outcome(_FAILED, message=str(result))
    if isinstance(result, OSError):
        return outcome(
            _FAILED, message=f"No se pudo leer el archivo ({result.strerror or result})"
        )
    # Cualquier otra excepción es inesperada: se registra con su traza
    logger.opt(exception=result).warning(f"Error inesperado leyendo: {path}")
    return outcome(
        _FAILED, message=f"Error inesperado ({type(result).__name__}: {result})"
    )


# -----------------------------------------------------------------------------
# Escritura en la base de datos
# -----------------------------------------------------------------------------


def _write_outcomes(
    conn: sqlite3.Connection,
    outcomes: list[_Outcome],
    table_columns: dict[str, frozenset[str]],
) -> None:
    """Guarda en la base de datos lo ocurrido con un lote de archivos (sin hacer commit)."""
    if not any(outcome.kind != _OFFLINE for outcome in outcomes):
        return  # nada que escribir (lote vacío o solo unidades desconectadas)

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    for outcome in outcomes:
        if outcome.kind == _OK:
            _write_success(conn, outcome, table_columns)
        elif outcome.kind == _FAILED:
            _mark_attempted(conn, outcome)
            conn.execute(
                """INSERT INTO scan_errors(storage_location_id, relative_path, stage, message)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(storage_location_id, relative_path, stage)
                   DO UPDATE SET message = excluded.message, occurred_at = CURRENT_TIMESTAMP""",
                (
                    outcome.location_id,
                    outcome.relative_path,
                    SCAN_STAGE_METADATA,
                    outcome.message,
                ),
            )
        elif outcome.kind == _UNSUPPORTED:
            _mark_attempted(conn, outcome)
            _clear_error(conn, outcome)
        elif outcome.kind == _MISSING:
            conn.execute(
                "UPDATE media_items SET is_missing = 1 WHERE id = ?",
                (outcome.media_id,),
            )


def _columns_of(
    conn: sqlite3.Connection, table: str, cache: dict[str, frozenset[str]]
) -> frozenset[str]:
    """Columnas de una tabla (se consultan una sola vez por ejecución)."""
    if table not in cache:
        cache[table] = frozenset(
            row[1] for row in conn.execute(f"PRAGMA table_info({table})")
        )
    return cache[table]


def _write_success(
    conn: sqlite3.Connection,
    outcome: _Outcome,
    table_columns: dict[str, frozenset[str]],
) -> None:
    """Guarda los datos de un archivo leído: columnas comunes, detalles y versión."""
    result = outcome.result
    assert result is not None
    extractor = outcome.extractor
    extractor_name = type(extractor).__name__

    # Nunca se escriben las columnas del archivo, del usuario ni de control interno
    forbidden = set(result.common) & PROTECTED_COLUMNS
    if forbidden:
        raise ValueError(
            f"{extractor_name} devolvió columnas que no puede escribir: {sorted(forbidden)}"
        )
    unknown = set(result.common) - _columns_of(conn, "media_items", table_columns)
    if unknown:
        raise ValueError(
            f"{extractor_name} devolvió columnas que no existen en 'media_items': "
            f"{sorted(unknown)} (¿falta la migración?)"
        )

    values = dict(result.common)
    # Metadatos editados en la aplicación, en los formatos sin XMP: viven en el '.arca.json'
    # (el original no se toca) y mandan SIEMPRE sobre lo leído del archivo
    if not uses_xmp(outcome.extension):
        if outcome.folder_edits is None:
            # '.arca.json' dañado: no se sabe qué se editó; mejor no tocar esas columnas
            for column in EDITABLE_COLUMNS:
                values.pop(column, None)
        else:
            values.update(outcome.folder_edits)
    # El título es NOT NULL: sin título, el nombre del archivo sin extensión
    if "title" in values and values["title"] is None:
        values["title"] = default_title(PurePosixPath(outcome.relative_path).name)
    # Los nombres de columna salen de listas cerradas (las de arriba y la de los campos
    # editables): no hay inyección SQL. Un campo editado pendiente de escribir en el
    # archivo no se pisa (se comprueba en la misma sentencia: 'unless_pending_sql')
    assignments = [
        unless_pending_sql(column) if column in EDITABLE_COLUMNS else f"{column} = ?"
        for column in values
    ]
    assignments += ["scan_version = ?", "last_scanned_at = CURRENT_TIMESTAMP"]
    conn.execute(
        f"UPDATE media_items SET {', '.join(assignments)} WHERE id = ?",
        (*values.values(), extractor.version, outcome.media_id),
    )

    # Valoración, marca y color del archivo: MANDA EL ARCHIVO, salvo que el elemento esté
    # pendiente de escribir (el cambio del usuario es más nuevo). Solo en los formatos
    # cuyos datos viven en XMP: los demás los toma 'add_folder' de su archivo de carpeta
    if uses_xmp(outcome.extension):
        apply_file_user_data(
            conn, outcome.media_id, result.user_data, expected_state=outcome.state
        )
        # Palabras clave (solo las imágenes las leen): las del archivo, exactamente
        apply_file_keywords(
            conn, outcome.media_id, result.user_data.get("keywords"), expected_state=outcome.state
        )

    # Tabla de detalles del tipo (1:1): se crea la fila o se actualiza la existente
    if result.details and extractor.details_table:
        table = extractor.details_table
        allowed = _columns_of(conn, table, table_columns) - {"media_id"}
        if not allowed:
            raise ValueError(f"La tabla '{table}' no existe: ¿falta una migración?")
        unknown = set(result.details) - allowed
        if unknown:
            raise ValueError(
                f"{extractor_name} devolvió columnas que no existen en '{table}': "
                f"{sorted(unknown)} (¿falta la migración?)"
            )

        columns = list(result.details)
        conn.execute(
            f"INSERT INTO {table} (media_id, {', '.join(columns)}) "
            f"VALUES (?, {', '.join('?' * len(columns))}) "
            f"ON CONFLICT(media_id) DO UPDATE SET "
            f"{', '.join(f'{column} = excluded.{column}' for column in columns)}",
            (outcome.media_id, *result.details.values()),
        )

    _clear_error(conn, outcome)


def _mark_attempted(conn: sqlite3.Connection, outcome: _Outcome) -> None:
    """Marca el archivo como procesado con la versión actual (aunque no se haya podido leer)."""
    conn.execute(
        "UPDATE media_items SET scan_version = ?, last_scanned_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (outcome.extractor.version, outcome.media_id),
    )


def _clear_error(conn: sqlite3.Connection, outcome: _Outcome) -> None:
    """Borra el error de metadatos anterior de un archivo (si lo había)."""
    conn.execute(
        "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ? AND stage = ?",
        (outcome.location_id, outcome.relative_path, SCAN_STAGE_METADATA),
    )


def _notify(
    progress: Callable[[JobProgress], None] | None, done: int, total: int
) -> None:
    """Avisa del progreso. Un fallo en el aviso no debe interrumpir el trabajo."""
    if progress is None:
        return
    try:
        progress(JobProgress(done, total))
    except Exception:  # noqa: BLE001 - el aviso es opcional
        logger.exception("Error en la función de progreso de los metadatos.")


if __name__ == "__main__":
    # Autoprueba con un catálogo REAL, imágenes reales y add_folder: de punta a punta.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.processor
    import os
    import tempfile
    from contextlib import closing

    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational

    from core.catalog.catalog_builder import CatalogBuilder
    from core.catalog.catalog_schema import configure_connection
    from core.catalog.folder_importer import add_folder
    from core.metadata.image.pillow_extractor import ImageMetadataExtractor

    def make_jpeg(path: Path, camera: str | None = None, size=(40, 30)) -> None:
        """Crea un JPEG pequeño, con cámara y GPS si se indica."""
        path.parent.mkdir(parents=True, exist_ok=True)
        exif = Image.Exif()
        if camera:
            exif[0x010F] = "Canon"
            exif[0x0110] = camera
            exif[0x8769] = {0x9003: "2026:09:12 14:48:51", 0x8827: 800}
            exif[0x8825] = {
                1: "N",
                2: (IFDRational(40), IFDRational(30), IFDRational(0)),
                3: "W",
                4: (IFDRational(3), IFDRational(0), IFDRational(0)),
            }
        extra = {"exif": exif} if camera else {}  # Pillow no admite exif=None
        Image.new("RGB", size, "gray").save(path, **extra)

    def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list:
        return conn.execute(sql, params).fetchall()

    # La primera parte de la autoprueba es del extractor de Pillow: se le da un registro EXPLÍCITO.
    # Con el registro por defecto, si hay un ExifTool instalado se usaría el extractor de ExifTool y
    # los recuentos serían otros ('default_registry()' decide según lo que haya en el equipo).
    pillow_registry = ExtractorRegistry()
    pillow_registry.register(ImageMetadataExtractor())

    first_version = (
        ImageMetadataExtractor.version
    )  # la versión con la que se lee la primera vez
    next_version = first_version + 1

    class VersionTwoExtractor(ImageMetadataExtractor):
        """El extractor de imágenes tras "aprender" campos nuevos (versión subida)."""

        version = next_version

    class GreedyExtractor(ImageMetadataExtractor):
        """Extractor mal programado: intenta escribir la valoración del usuario."""

        version = 99

        def extract(self, path):
            result = super().extract(path)
            result.common["rating"] = 5
            return result

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        library = base / "Fotos"
        make_jpeg(library / "buena.jpg", camera="Canon EOS R5")
        make_jpeg(library / "sub" / "otra.jpg", camera="Canon EOS R6")
        Image.new("RGB", (64, 32), "red").save(library / "sin_exif.png")
        (library / "rota.jpg").write_bytes(b"no soy una imagen" * 20)
        (library / "iphone.heic").write_bytes(b"x" * 50)
        make_jpeg(library / "desaparece.jpg")
        (library / "video.mp4").write_bytes(b"x" * 50)  # sin extractor todavía

        db_path = CatalogBuilder(base / "Cat").build()
        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)
            add_folder(conn, library)
            (
                library / "desaparece.jpg"
            ).unlink()  # se borra DESPUÉS de añadir la carpeta

            # Los extractores solo pueden rellenar columnas que existen de verdad
            columns = {row[1] for row in conn.execute("PRAGMA table_info(media_items)")}
            assert PROTECTED_COLUMNS <= columns, PROTECTED_COLUMNS - columns

            # 1. Primera ejecución
            conn.execute(
                "UPDATE media_items SET rating = 4 WHERE relative_path = 'buena.jpg'"
            )
            conn.commit()
            seen: list[JobProgress] = []
            result = process_pending_metadata(
                conn, registry=pillow_registry, progress=seen.append, batch_size=2
            )
            print(result.summary())
            assert (result.total, result.processed, result.failed) == (6, 3, 1)
            assert (result.unsupported, result.missing) == (1, 1)
            assert seen[0] == JobProgress(0, 6) and seen[-1] == JobProgress(6, 6)

            good = rows(
                conn,
                "SELECT width, height, latitude, longitude, content_created_at, scan_version, "
                "rating, title FROM media_items WHERE relative_path = 'buena.jpg'",
            )[0]
            assert tuple(good)[:2] == (40, 30) and abs(good[2] - 40.5) < 1e-9
            assert abs(good[3] + 3.0) < 1e-9 and good[4] == "2026-09-12 14:48:51"
            assert tuple(good)[5:] == (
                first_version,
                4,
                "buena",
            )  # valoración intacta, título sin tocar
            det = rows(
                conn,
                "SELECT camera_make, camera_model, iso FROM photo_details "
                "JOIN media_items ON id = media_id WHERE relative_path = 'buena.jpg'",
            )
            assert tuple(det[0]) == ("Canon", "Canon EOS R5", 800)
            png = rows(
                conn,
                "SELECT width, height, content_date_source FROM media_items "
                "WHERE relative_path = 'sin_exif.png'",
            )
            assert tuple(png[0]) == (64, 32, "file_mtime")
            errors = rows(conn, "SELECT relative_path, stage FROM scan_errors")
            assert [tuple(e) for e in errors] == [("rota.jpg", "metadata")]
            state = {
                r[0]: (r[1], r[2])
                for r in rows(
                    conn,
                    "SELECT relative_path, scan_version, is_missing FROM media_items",
                )
            }
            assert state["rota.jpg"] == (first_version, 0) and state["iphone.heic"] == (
                first_version,
                0,
            )  # intentados
            assert state["desaparece.jpg"] == (0, 1)  # desaparecido
            assert state["video.mp4"] == (0, 0)  # sin extractor: intacto
            print(
                "Primera ejecución: datos, errores, desaparecidos y tipos sin extractor correctos"
            )

            # 2. Segunda ejecución: no hay nada pendiente
            again = process_pending_metadata(conn, registry=pillow_registry)
            assert (again.total, again.processed) == (0, 0)
            assert again.status_text() == "" and not again.has_warnings
            assert (
                "3 de 6" in result.status_text()
                and "1 con errores" in result.status_text()
            )

            # 3. El extractor sube de versión: se vuelve a leer todo lo de su tipo
            registry_v2 = ExtractorRegistry()
            registry_v2.register(VersionTwoExtractor())
            result = process_pending_metadata(conn, registry=registry_v2)
            assert (
                result.total,
                result.processed,
                result.failed,
                result.unsupported,
            ) == (5, 3, 1, 1)
            assert rows(conn, "SELECT COUNT(*) FROM scan_errors") == [
                (1,)
            ]  # sin duplicar el error
            assert rows(
                conn, "SELECT rating FROM media_items WHERE relative_path = 'buena.jpg'"
            ) == [(4,)]
            print(
                "Subida de versión del extractor: reprocesado sin duplicar errores ni tocar datos del usuario"
            )

            # 4. Un archivo que cambia en disco vuelve a procesarse (add_folder lo deja en versión 0)
            make_jpeg(library / "buena.jpg", camera="Canon EOS R5", size=(80, 60))
            os.utime(library / "buena.jpg", ns=(9_000_000_000, 9_000_000_000))
            add_folder(conn, library)
            result = process_pending_metadata(conn, registry=registry_v2)
            assert (result.total, result.processed) == (1, 1)
            assert rows(
                conn, "SELECT width FROM media_items WHERE relative_path = 'buena.jpg'"
            ) == [(80,)]

            # 5. Cancelación a mitad, y la siguiente ejecución termina lo que faltaba
            for index in range(30):
                make_jpeg(library / "lote" / f"f{index:02d}.jpg", camera="Canon EOS R5")
            add_folder(conn, library)
            event = threading.Event()
            calls = {"n": 0}

            def cancel_after_ten(_progress: JobProgress) -> None:
                calls["n"] += 1
                if calls["n"] == 10:
                    event.set()

            result = process_pending_metadata(
                conn,
                registry=registry_v2,
                progress=cancel_after_ten,
                cancel_event=event,
                batch_size=7,
            )
            assert result.cancelled and 0 < result.processed < 30
            partial = rows(
                conn,
                f"SELECT COUNT(*) FROM media_items WHERE scan_version = {next_version} "
                "AND relative_path LIKE 'lote/%'",
            )[0][0]
            assert (
                partial == result.processed
            )  # lo leído antes de cancelar quedó guardado
            result = process_pending_metadata(conn, registry=registry_v2)
            assert not result.cancelled and result.processed + partial == 30
            print(
                "Cancelación: lo leído se conserva y la siguiente ejecución completa el resto"
            )

            # 6. Unidad desconectada: no se marca nada como desaparecido y sigue pendiente
            make_jpeg(library / "nueva.jpg", camera="Canon EOS R5")
            add_folder(conn, library)
            library.rename(base / "Fotos_desconectada")
            offline = process_pending_metadata(conn, registry=registry_v2)
            assert (
                offline.skipped_offline == 1
                and offline.missing == 0
                and offline.has_warnings
            )
            (base / "Fotos_desconectada").rename(library)
            assert process_pending_metadata(conn, registry=registry_v2).processed == 1
            print(
                "Unidad desconectada: sin falsos desaparecidos, y se recupera al volver"
            )

            # 7. Un extractor que intenta escribir datos del usuario es un error de programación
            greedy = ExtractorRegistry()
            greedy.register(GreedyExtractor())
            try:
                process_pending_metadata(conn, registry=greedy)
            except ValueError as error:
                print("Extractor mal programado:", error)
            else:
                raise AssertionError("Debería rechazar columnas del usuario")
            assert rows(
                conn, "SELECT COUNT(*) FROM media_items WHERE scan_version = 99"
            ) == [(0,)]
            assert rows(conn, "SELECT COUNT(*) FROM media_items WHERE rating = 5") == [
                (0,)
            ]

            # 8. Registro vacío: no hace nada
            assert (
                process_pending_metadata(conn, registry=ExtractorRegistry()).total == 0
            )

    # ---------- Con el extractor de ExifTool (ExifTool SIMULADO, datos reales de un JPEG) ----------
    import json
    import sys

    from core.metadata.exiftool_runner import ExifToolRunner
    from core.metadata.image._fixtures import REAL_JPEG_TAGS
    from core.metadata.image.extractor import ImageExtractor
    from core.metadata.image.fields import IMAGE_FIELDS_VERSION

    FAKE_EXIFTOOL = r"""
import json, os, sys
args = sys.argv[1:]
if "-ver" in args:
    print("13.59"); sys.exit(0)
files = open(args[args.index("-@") + 1], encoding="utf-8").read().splitlines()
if any("explota" in f for f in files):
    sys.stderr.write("caída"); sys.exit(1)
tags = json.load(open(os.environ["FAKE_TAGS"], encoding="utf-8"))
out = []
for f in files:
    if f.endswith(".xmp"):
        out.append({"SourceFile": f, "XMP-photoshop:City": "Bilbao"})
    elif "corrupta" in f:
        out.append({"SourceFile": f, "ExifTool:Error": "File format error"})
    else:
        out.append({"SourceFile": f, **tags})
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
"""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "fake_exiftool.py").write_text(FAKE_EXIFTOOL, encoding="utf-8")
        (base / "tags.json").write_text(json.dumps(REAL_JPEG_TAGS), encoding="utf-8")
        os.environ["FAKE_TAGS"] = str(base / "tags.json")
        runner = ExifToolRunner(
            command=[sys.executable, str(base / "fake_exiftool.py")]
        )
        exiftool_registry = ExtractorRegistry()
        exiftool_registry.register(ImageExtractor(runner))

        library = base / "Fotos"
        library.mkdir()
        for name in (
            "a.jpg",
            "b.dng",
            "c.heic",
            "d.nef",
            "corrupta.jpg",
            "explota.jpg",
        ):
            (library / name).write_bytes(b"x")
        (library / "b.xmp").write_text("<x/>")  # sidecar de b.dng

        db_path = CatalogBuilder(base / "Cat").build()
        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)
            add_folder(conn, library)
            result = process_pending_metadata(conn, registry=exiftool_registry)
            print(result.summary())
            # a, b, c, d se leen; 'corrupta' falla en ExifTool; 'explota' hace caer ExifTool y se aísla
            assert (result.total, result.processed, result.failed) == (6, 4, 2)
            errors = {
                r[0]: r[1]
                for r in rows(conn, "SELECT relative_path, message FROM scan_errors")
            }
            assert (
                set(errors) == {"corrupta.jpg", "explota.jpg"}
                and "File format error" in errors["corrupta.jpg"]
            )

            row = rows(
                conn,
                "SELECT m.city, m.sublocation, m.width, m.has_xmp_sidecar, m.scan_version, d.camera_model, "
                "d.iso, d.flash_fired, d.exposure_program FROM media_items m "
                "JOIN photo_details d ON d.media_id = m.id WHERE m.relative_path = ?",
                ("a.jpg",),
            )[0]
            assert tuple(row) == (
                "Castro Urdiales",
                "Paseo",
                4032,
                0,
                IMAGE_FIELDS_VERSION,
                "iPhone 17 Pro",
                1000,
                0,
                2,
            )
            with_sidecar = rows(
                conn,
                "SELECT city, has_xmp_sidecar FROM media_items WHERE relative_path = 'b.dng'",
            )
            assert tuple(with_sidecar[0]) == (
                "Bilbao",
                1,
            )  # el sidecar manda sobre el XMP incrustado
            assert rows(conn, "SELECT COUNT(*) FROM photo_details") == [(4,)]
            print(
                "ExifTool: lote leído, sidecar aplicado, archivo problemático aislado y datos en la base"
            )

            # Una segunda ejecución no tiene nada pendiente (los dos fallos quedan como "intentados")
            assert process_pending_metadata(conn, registry=exiftool_registry).total == 0

            # Metadatos editados (formato con XMP): al releer, lo pendiente de escribir no
            # se pisa y lo demás lo manda el archivo
            from core.catalog.media_queries import update_metadata_fields

            a_id = rows(conn, "SELECT id FROM media_items WHERE relative_path = 'a.jpg'")[0][0]

            def edited_a() -> tuple:
                return tuple(rows(
                    conn, "SELECT title, city, sublocation FROM media_items WHERE id = ?", (a_id,)
                )[0])  # fmt: skip

            update_metadata_fields(conn, [a_id], {"title": "Atardecer", "city": "Soria"})
            conn.execute(
                "UPDATE media_items SET sublocation = 'Otro', scan_version = 0 WHERE id = ?",
                (a_id,),
            )
            conn.commit()
            assert process_pending_metadata(conn, registry=exiftool_registry).processed == 1
            assert edited_a() == ("Atardecer", "Soria", "Paseo"), edited_a()
            # Ya escrito (sin pendiente): manda el archivo, que no trae título -> el nombre
            conn.execute(
                "UPDATE media_items SET metadata_edit_pending = 0, scan_version = 0 WHERE id = ?",
                (a_id,),
            )
            conn.commit()
            process_pending_metadata(conn, registry=exiftool_registry)
            assert edited_a() == ("a", "Castro Urdiales", "Paseo"), edited_a()
            print("Metadatos editados (XMP): lo pendiente no se pisa; sin título, el nombre")

    # ---------- Formato sin XMP (GPX): lo editado en su '.arca.json' manda siempre ----------
    from core.metadata.track.extractor import TrackExtractor
    from core.userdata.folder_file import (
        FOLDER_FILE_NAME,
        FolderData,
        write_folder_file,
    )

    GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Prueba" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Ruta del archivo</name>
    <desc>Descripción del archivo</desc>
    <trkseg>
      <trkpt lat="43.1" lon="-4.8"><ele>500</ele><time>2024-07-15T06:30:00Z</time></trkpt>
      <trkpt lat="43.2" lon="-4.8"><ele>900</ele><time>2024-07-15T10:30:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>"""
    track_registry = ExtractorRegistry()
    track_registry.register(TrackExtractor())

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        routes = base / "Rutas"
        routes.mkdir()
        for name in ("editada.gpx", "sin_editar.gpx"):
            (routes / name).write_text(GPX, encoding="utf-8")
        folder_data = FolderData(routes)
        folder_data.items["editada.gpx"] = {"title": "Ruta editada", "description": "", "rating": 3}
        write_folder_file(folder_data)

        db_path = CatalogBuilder(base / "Cat").build()
        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)

            def route(name: str) -> tuple:
                return tuple(rows(
                    conn, "SELECT title, description, rating FROM media_items "
                    "WHERE relative_path = ?", (name,),
                )[0])  # fmt: skip

            # Al importar ('apply_folder_files'), antes de leer el GPX
            add_folder(conn, routes)
            assert route("editada.gpx") == ("Ruta editada", None, 3), route("editada.gpx")
            assert route("sin_editar.gpx") == ("sin_editar", None, 0)
            # Tras leerlo: lo editado manda; lo que no se editó sale del archivo
            assert process_pending_metadata(conn, registry=track_registry).processed == 2
            assert route("editada.gpx") == ("Ruta editada", None, 3), route("editada.gpx")
            assert route("sin_editar.gpx") == ("Ruta del archivo", "Descripción del archivo", 0)
            # Un cambio pendiente de escribir manda sobre el '.arca.json' (es más nuevo), al
            # releer y al volver a añadir la carpeta
            ids = dict(rows(conn, "SELECT relative_path, id FROM media_items"))
            update_metadata_fields(conn, [ids["editada.gpx"]], {"title": "Pendiente"})
            conn.execute("UPDATE media_items SET scan_version = 0")
            conn.commit()
            process_pending_metadata(conn, registry=track_registry)
            add_folder(conn, routes)
            assert route("editada.gpx") == ("Pendiente", None, 3), route("editada.gpx")
            # '.arca.json' dañado (y sin copia): no se sabe qué se editó y esas columnas no
            # se tocan, ni siquiera las de un archivo sin editar
            broken = routes / "roto.tmp"
            broken.write_text("{ esto no es json", encoding="utf-8")
            os.replace(broken, routes / FOLDER_FILE_NAME)  # el .arca.json está oculto
            conn.execute("UPDATE media_items SET metadata_edit_pending = 0, scan_version = 0")
            conn.execute("UPDATE media_items SET title = 'Otro' WHERE id = ?",
                         (ids["sin_editar.gpx"],))  # fmt: skip
            conn.commit()
            assert process_pending_metadata(conn, registry=track_registry).processed == 2
            assert route("editada.gpx")[0] == "Pendiente" and route("sin_editar.gpx")[0] == "Otro"
            print("Metadatos editados (.arca.json): mandan siempre, salvo lo pendiente")

    print("Autoprueba finalizada correctamente.")
