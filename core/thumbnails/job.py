"""Trabajo en segundo plano: genera las miniaturas pendientes del catálogo.

Este módulo NO depende de Qt. 'generate_pending_thumbnails' es un "trabajo" en el
sentido de 'core/jobs/progress.py': recibe una conexión, avisa del progreso y obedece
a un evento de cancelación, así que se envía tal cual a 'JobManager.start' y se ejecuta
en un hilo secundario. Se lanza DESPUÉS del trabajo de metadatos:

    add_folder  ->  process_pending_metadata  ->  generate_pending_thumbnails

Qué archivos son "pendientes" (de un tipo de medio con origen de miniaturas registrado):
    - thumbnail_status = 0                     nunca generada, o marcada para regenerar
    - thumbnail_version < la actual            el motor ha cambiado (THUMBNAIL_VERSION)
    - thumbnail_mtime_ns != file_mtime_ns      el archivo cambió desde que se generó

'add_folder' ya deja en 0 los archivos modificados; la tercera condición es un cinturón
de seguridad por si 'file_mtime_ns' cambiara por otra vía.

REGENERAR A DEMANDA es lo mismo que generar: 'invalidate_thumbnails' marca archivos como
pendientes (thumbnail_status = 0) y se lanza este mismo trabajo. Así hay un solo camino de
código, con su barra de progreso, su botón Cancelar y su reanudación tras un cierre. La
regeneración solo toca las columnas de estado de miniatura (BLOQUE D) y 'scan_errors'; los
metadatos y los datos del usuario no se tocan. Si lo que ha cambiado es el ORIGINAL, lo
correcto es volver a "añadir" su carpeta (reescaneo): 'add_folder' detecta el cambio y deja
pendientes a la vez los metadatos y la miniatura.

Cómo trabaja, por lotes (48 archivos por defecto):
    1. Lee el lote de la tabla (por 'id', sin repetir nunca un archivo).
    2. Genera las miniaturas de todo el lote en un grupo de hilos, SIN transacción abierta:
       decodificar y reducir imágenes es lo que más tarda y Pillow libera el GIL, así que
       varios hilos aprovechan varios núcleos. Solo este hilo escribe en la base de datos.
    3. Guarda el resultado del lote en una transacción corta y hace 'commit'.
    Se puede cancelar: lo ya guardado queda coherente y la siguiente ejecución continúa.

Qué pasa con cada archivo:
    - Se genera bien        -> status 1, y se anotan versión, origen y 'mtime' del archivo.
    - Falla (dañado...)      -> status 2 y un error en 'scan_errors' (fase 'thumbnail'). No se
                               reintenta hasta que el archivo cambie, suba la versión o se
                               pida regenerar (p. ej. "Regenerar miniaturas con error").
    - Sin origen (p. ej. HEIC sin pillow-heif) -> igual que un fallo, con un mensaje que
                               explica cómo arreglarlo; se cuenta aparte.
    - Ya no existe           -> 'is_missing = 1'.
    - Su unidad no está conectada -> no se toca (sigue pendiente) y se cuenta aparte.
    - La caché no se puede escribir (disco lleno...) -> el trabajo se ABORTA sin marcar nada
                               como fallido: no es culpa de los archivos.

Prueba rápida (desde la raíz del proyecto):
    python -m core.thumbnails.job
"""

__version__ = "1.0.0"
__all__ = [
    "DEFAULT_BATCH_SIZE",
    "SCAN_STAGE_THUMBNAIL",
    "ThumbnailJobResult",
    "catalog_directory_of",
    "generate_pending_thumbnails",
    "invalidate_thumbnails",
]

# Librerías estándar
import os
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.jobs.progress import JobProgress
from core.thumbnails.cache import ThumbnailCache, ThumbnailStorageError
from core.thumbnails.generator import THUMBNAIL_VERSION, ThumbnailResult, generate_thumbnails
from core.thumbnails.registry import SourceRegistry, default_registry
from core.thumbnails.sizes import DEFAULT_SIZES, ThumbnailSize
from core.thumbnails.sources.base import (
    ThumbnailError,
    ThumbnailRequest,
    UnsupportedSourceError,
)

# Nombre de la fase para la columna 'stage' de la tabla 'scan_errors'
SCAN_STAGE_THUMBNAIL = "thumbnail"

# Archivos por lote (y por transacción). Con 4 hilos, un lote de ~12 archivos por hilo deja
# poco tiempo muerto al final de cada lote.
DEFAULT_BATCH_SIZE = 48

# SQLite admite pocos parámetros por consulta en versiones antiguas
_MAX_SQL_PARAMETERS = 900

# Resultado de procesar un archivo
_OK = "ok"
_FAILED = "failed"
_UNSUPPORTED = "unsupported"
_MISSING = "missing"
_OFFLINE = "offline"
_SKIPPED = "skipped"  # no se llegó a procesar por haberse cancelado: sigue pendiente


@dataclass(frozen=True, slots=True)
class ThumbnailJobResult:
    """Resultado de una ejecución de 'generate_pending_thumbnails'.

    Attributes:
        total: Archivos pendientes al empezar.
        generated: Archivos cuyas miniaturas se han generado bien.
        failed: Archivos que no se pudieron procesar (están en 'scan_errors').
        unsupported: Archivos para los que no hay origen (falta una librería o ExifTool).
        missing: Archivos que ya no existen en disco (marcados 'is_missing').
        skipped_offline: Archivos sin tocar porque su unidad no está conectada.
        cancelled: True si el trabajo se interrumpió antes de terminar.
        generated_ids: 'id' de los archivos generados (para que la interfaz refresque esas tarjetas).
        unsupported_extensions: Extensiones de los archivos 'unsupported'.
    """

    total: int
    generated: int
    failed: int
    unsupported: int
    missing: int
    skipped_offline: int
    cancelled: bool
    generated_ids: tuple[int, ...]
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
        text = f"Miniaturas generadas: {self.generated} de {self.total} archivos"
        if self.failed:
            text += f", {self.failed} con errores"
        if self.unsupported:
            text += f", {self.unsupported} sin soporte"
        if self.cancelled:
            text += " (cancelado)"
        return text

    def summary(self) -> str:
        """Resumen en varias líneas, para el registro o para un cuadro de diálogo."""
        lines = [f"Miniaturas generadas: {self.generated} de {self.total}"]
        if self.failed:
            lines.append(f"Con errores: {self.failed} (ver la lista de errores)")
        if self.unsupported:
            top = ", ".join(
                f"{ext} ({count})" for ext, count in self.unsupported_extensions.most_common(5)
            )
            lines.append(
                f"Sin origen de miniaturas: {self.unsupported} [{top}] "
                "(falta pillow-heif o ExifTool; al instalarlo, usa 'Regenerar miniaturas con error')"
            )
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
    file_mtime_ns: int
    extension: str
    result: ThumbnailResult | None = None
    message: str = ""


# -----------------------------------------------------------------------------
# Trabajo principal
# -----------------------------------------------------------------------------


def generate_pending_thumbnails(
    conn: sqlite3.Connection,
    *,
    registry: SourceRegistry | None = None,
    sizes: Iterable[ThumbnailSize] = DEFAULT_SIZES,
    version: int = THUMBNAIL_VERSION,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int | None = None,
) -> ThumbnailJobResult:
    """Genera las miniaturas de todos los archivos pendientes del catálogo.

    Args:
        conn: Conexión sqlite3 al catálogo (con o sin 'row_factory'). La caché de miniaturas
            se busca junto al archivo de la base de datos ('<catálogo>/cache').
        registry: Orígenes de miniaturas (por defecto, 'default_registry()').
        sizes: Tamaños a generar (por defecto, todos).
        version: Versión del motor que se anotará (por defecto, 'THUMBNAIL_VERSION').
        progress: Función a la que se avisa tras cada archivo (conviene envolverla con
            'core.jobs.progress.throttled' si llega a la interfaz).
        cancel_event: Si se activa desde otro hilo, el trabajo se detiene en cuanto
            termina el archivo en curso de cada hilo.
        batch_size: Archivos por lote y por transacción.
        max_workers: Hilos de generación (por defecto, hasta 4 según los núcleos).

    Returns:
        Un 'ThumbnailJobResult' con los recuentos.

    Raises:
        ValueError: Si el catálogo no está en un archivo.
        ThumbnailStorageError: Si no se puede escribir en la caché (lo ya guardado se conserva).
        sqlite3.Error: Si falla la base de datos.
    """
    sizes = tuple(sizes)
    if registry is None:
        registry = default_registry()

    # Solo los tipos de medio con algún origen registrado: los demás siguen como están
    media_types = sorted({source.media_type.value for source in registry})
    if not media_types:
        return ThumbnailJobResult(0, 0, 0, 0, 0, 0, False, (), Counter())

    catalog_dir = catalog_directory_of(conn)
    if catalog_dir is None:
        raise ValueError("El catálogo no está en un archivo: no hay dónde guardar la caché.")
    cache = ThumbnailCache(catalog_dir)

    pending_sql = (
        f"is_missing = 0 AND media_type IN ({','.join('?' * len(media_types))}) "
        "AND (thumbnail_status = 0 OR thumbnail_version < ? "
        "OR thumbnail_mtime_ns IS NOT file_mtime_ns)"
    )
    pending_params: list[object] = [*media_types, version]

    total = conn.execute(
        f"SELECT COUNT(*) FROM media_items WHERE {pending_sql}", pending_params
    ).fetchone()[0]
    logger.info(f"Miniaturas: {total} archivos pendientes")

    locations = {
        row[0]: Path(row[1])
        for row in conn.execute("SELECT id, absolute_path FROM storage_locations")
    }
    workers = max(1, max_workers or min(4, os.cpu_count() or 2))

    counts: Counter[str] = Counter()
    unsupported_extensions: Counter[str] = Counter()
    generated_ids: list[int] = []
    cancelled = False
    done = 0
    last_id = 0  # paginación por 'id': un archivo nunca se vuelve a pedir en esta ejecución
    _notify(progress, done, total)

    while not cancelled:
        rows = conn.execute(
            "SELECT id, storage_location_id, relative_path, media_type, file_extension, "
            f"file_mtime_ns FROM media_items WHERE id > ? AND {pending_sql} "
            "ORDER BY id LIMIT ?",
            (last_id, *pending_params, batch_size),
        ).fetchall()
        if not rows:
            break
        last_id = rows[-1][0]

        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break

        # 1. Se generan las miniaturas del lote (aquí no hay ninguna transacción abierta)
        fatal: ThumbnailStorageError | None = None
        outcomes: list[_Outcome] = []
        try:
            for outcome in _process_rows(
                rows, locations, cache, registry, sizes, workers, cancel_event
            ):
                if outcome.kind == _SKIPPED:
                    cancelled = True  # sigue pendiente: no se cuenta ni se guarda
                    continue
                outcomes.append(outcome)
                counts[outcome.kind] += 1
                if outcome.kind == _UNSUPPORTED:
                    unsupported_extensions[outcome.extension or "(sin extensión)"] += 1
                if outcome.kind == _OK:
                    generated_ids.append(outcome.media_id)
                done += 1
                _notify(progress, done, total)
        except ThumbnailStorageError as error:
            fatal = error  # se guarda lo que sí se hizo y después se aborta

        # 2. Se guarda lo ocurrido en una transacción corta (también si se canceló a medias)
        try:
            _write_outcomes(conn, outcomes, version)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if fatal is not None:
            logger.error(f"Miniaturas: se aborta el trabajo. {fatal}")
            raise fatal

    result = ThumbnailJobResult(
        total=total,
        generated=counts[_OK],
        failed=counts[_FAILED],
        unsupported=counts[_UNSUPPORTED],
        missing=counts[_MISSING],
        skipped_offline=counts[_OFFLINE],
        cancelled=cancelled,
        generated_ids=tuple(generated_ids),
        unsupported_extensions=unsupported_extensions,
    )
    logger.info(f"Miniaturas procesadas:\n{result.summary()}")
    return result


# -----------------------------------------------------------------------------
# Regeneración a demanda
# -----------------------------------------------------------------------------


def invalidate_thumbnails(
    conn: sqlite3.Connection,
    media_ids: Iterable[int] | None = None,
    *,
    only_errors: bool = False,
) -> int:
    """Marca miniaturas como pendientes para que 'generate_pending_thumbnails' las regenere.

    Es el paso previo de la "regeneración a demanda": después hay que lanzar el trabajo de
    miniaturas. No borra ningún archivo de la caché (la generación sobrescribe lo que haya y
    sustituye todos los tamaños), así que mientras tanto se sigue viendo la miniatura antigua.
    No hace 'commit' (lo hace el gestor asíncrono). No toca los archivos desaparecidos.

    Args:
        conn: Conexión sqlite3.
        media_ids: 'id' de los archivos a regenerar. None = todos los del catálogo.
        only_errors: Si es True, solo los que están marcados con error (thumbnail_status = 2).

    Returns:
        Número de archivos marcados como pendientes.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    condition = "is_missing = 0" + (" AND thumbnail_status = 2" if only_errors else "")
    if media_ids is None:
        cursor = conn.execute(f"UPDATE media_items SET thumbnail_status = 0 WHERE {condition}")
        return cursor.rowcount

    ids = list(dict.fromkeys(media_ids))  # sin repetidos y en el mismo orden
    changed = 0
    for start in range(0, len(ids), _MAX_SQL_PARAMETERS):
        chunk = ids[start : start + _MAX_SQL_PARAMETERS]
        cursor = conn.execute(
            f"UPDATE media_items SET thumbnail_status = 0 "
            f"WHERE {condition} AND id IN ({','.join('?' * len(chunk))})",
            chunk,
        )
        changed += cursor.rowcount
    return changed


# -----------------------------------------------------------------------------
# Pasos internos
# -----------------------------------------------------------------------------


def catalog_directory_of(conn: sqlite3.Connection) -> Path | None:
    """Devuelve la carpeta del catálogo (la que contiene el .db), o None si es una base en memoria.

    'PRAGMA database_list' indica el archivo de cada base de datos de la conexión.
    """
    for _sequence, schema_name, file_path in conn.execute("PRAGMA database_list;"):
        if schema_name == "main" and file_path:
            return Path(file_path).parent
    return None


def _process_rows(
    rows: list[sqlite3.Row | tuple],
    locations: dict[int, Path],
    cache: ThumbnailCache,
    registry: SourceRegistry,
    sizes: tuple[ThumbnailSize, ...],
    workers: int,
    cancel_event: threading.Event | None,
) -> Iterator[_Outcome]:
    """Genera las miniaturas de un lote y va entregando el resultado de cada archivo.

    Los resultados llegan en el orden en que terminan (no en el de las filas). Si algún hilo
    encuentra un fallo de la caché, los demás paran en cuanto pueden y el error se lanza al
    final, DESPUÉS de haber entregado lo que sí se hizo.
    """
    stop_event = threading.Event()  # fallo general de la caché: que los demás hilos paren
    online: dict[int, bool] = {}
    outcomes: list[_Outcome] = []
    to_process: list[tuple[_Outcome, ThumbnailRequest]] = []

    for row in rows:
        media_id, location_id, relative_path, media_type, extension, mtime_ns = (
            row[0], row[1], row[2], row[3], row[4] or "", row[5],
        )  # fmt: skip

        def outcome(kind: str, **extra: object) -> _Outcome:
            return _Outcome(
                kind, media_id, location_id, relative_path, mtime_ns, extension, **extra  # noqa: B023
            )

        # ¿Está conectada la unidad? Se comprueba una vez por ubicación y lote.
        if location_id not in online:
            root = locations.get(location_id)
            try:
                online[location_id] = root is not None and root.is_dir()
            except OSError:
                online[location_id] = False
        if not online[location_id]:
            outcomes.append(outcome(_OFFLINE))
            continue

        request = ThumbnailRequest(
            media_id, MediaType(media_type), locations[location_id] / relative_path
        )
        to_process.append((outcome(_OK), request))

    yield from outcomes

    def work(item: tuple[_Outcome, ThumbnailRequest]) -> _Outcome:
        base, request = item
        if stop_event.is_set() or (cancel_event is not None and cancel_event.is_set()):
            base.kind = _SKIPPED
            return base
        try:
            base.result = generate_thumbnails(request, cache, registry, sizes)
            base.kind = _OK
        except FileNotFoundError:
            base.kind = _MISSING
        except UnsupportedSourceError as error:
            base.kind, base.message = _UNSUPPORTED, str(error)
        except ThumbnailError as error:
            base.kind, base.message = _FAILED, str(error)
        except ThumbnailStorageError:
            stop_event.set()
            raise
        except Exception as error:  # noqa: BLE001 - un archivo malo no debe parar a los demás
            logger.opt(exception=True).warning(f"Error inesperado generando: {request.path}")
            base.kind = _FAILED
            base.message = f"Error inesperado ({type(error).__name__}: {error})"
        return base

    fatal: ThumbnailStorageError | None = None
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thumbnails") as pool:
        futures = [pool.submit(work, item) for item in to_process]
        for future in as_completed(futures):
            try:
                yield future.result()
            except ThumbnailStorageError as error:
                fatal = fatal or error
    if fatal is not None:
        raise fatal


def _write_outcomes(conn: sqlite3.Connection, outcomes: list[_Outcome], version: int) -> None:
    """Guarda en la base de datos lo ocurrido con un lote de archivos (sin hacer commit)."""
    if not any(outcome.kind != _OFFLINE for outcome in outcomes):
        return  # nada que escribir (lote vacío o solo unidades desconectadas)

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    for outcome in outcomes:
        if outcome.kind == _OK:
            assert outcome.result is not None
            conn.execute(
                "UPDATE media_items SET thumbnail_status = 1, thumbnail_mtime_ns = ?, "
                "thumbnail_version = ?, thumbnail_source = ? WHERE id = ?",
                (outcome.file_mtime_ns, version, outcome.result.source_name, outcome.media_id),
            )
            _clear_error(conn, outcome)
        elif outcome.kind in (_FAILED, _UNSUPPORTED):
            # Se marca "intentado" con la versión actual: no se reintenta hasta que el archivo
            # cambie, suba la versión o se pida regenerar
            conn.execute(
                "UPDATE media_items SET thumbnail_status = 2, thumbnail_mtime_ns = ?, "
                "thumbnail_version = ?, thumbnail_source = NULL WHERE id = ?",
                (outcome.file_mtime_ns, version, outcome.media_id),
            )
            conn.execute(
                """INSERT INTO scan_errors(storage_location_id, relative_path, stage, message)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(storage_location_id, relative_path, stage)
                   DO UPDATE SET message = excluded.message, occurred_at = CURRENT_TIMESTAMP""",
                (
                    outcome.location_id,
                    outcome.relative_path,
                    SCAN_STAGE_THUMBNAIL,
                    outcome.message,
                ),
            )
        elif outcome.kind == _MISSING:
            conn.execute(
                "UPDATE media_items SET is_missing = 1 WHERE id = ?", (outcome.media_id,)
            )


def _clear_error(conn: sqlite3.Connection, outcome: _Outcome) -> None:
    """Borra el error de miniatura anterior de un archivo (si lo había)."""
    conn.execute(
        "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ? AND stage = ?",
        (outcome.location_id, outcome.relative_path, SCAN_STAGE_THUMBNAIL),
    )


def _notify(progress: Callable[[JobProgress], None] | None, done: int, total: int) -> None:
    """Avisa del progreso. Un fallo en el aviso no debe interrumpir el trabajo."""
    if progress is None:
        return
    try:
        progress(JobProgress(done, total))
    except Exception:  # noqa: BLE001 - el aviso es opcional
        logger.exception("Error en la función de progreso de las miniaturas.")


if __name__ == "__main__":
    # Autoprueba de punta a punta con un catálogo REAL en una carpeta temporal, imágenes reales,
    # 'add_folder', un ExifTool SIMULADO para el RAW y un HEIC simulado.
    # Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.job
    import base64
    import json
    import shutil
    import sys
    import tempfile
    from contextlib import closing

    from PIL import Image

    from core.catalog.catalog_builder import CatalogBuilder
    from core.catalog.catalog_schema import configure_connection
    from core.catalog.folder_importer import add_folder
    from core.metadata.exiftool_runner import ExifToolRunner
    from core.thumbnails import _testing
    from core.thumbnails.sizes import ALL_SIZES
    from core.thumbnails.sources import heif_source
    from core.thumbnails.sources.pillow_source import PillowSource
    from core.thumbnails.sources.raw_preview_source import RawPreviewSource

    # Guardián: si cambian los tamaños, la calidad o el formato SIN subir THUMBNAIL_VERSION, las
    # miniaturas ya generadas no se regenerarían. Al cambiarlos, sube la versión en 'generator.py'
    # y actualiza estos valores.
    assert (
        THUMBNAIL_VERSION,
        tuple((size.max_side, size.quality) for size in ALL_SIZES),
        ThumbnailCache.FILE_EXTENSION,
    ) == (2, ((160, 80), (480, 85), (1200, 85), (2560, 88)), "jpg"), (
        "Han cambiado los tamaños, la calidad o el formato de las miniaturas: sube "
        "THUMBNAIL_VERSION en generator.py y actualiza esta comprobación."
    )

    def db_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list:
        return conn.execute(sql, params).fetchall()

    def state(conn: sqlite3.Connection, path: str) -> tuple:
        """(thumbnail_status, thumbnail_version, thumbnail_source, is_missing) de un archivo."""
        return tuple(
            conn.execute(
                "SELECT thumbnail_status, thumbnail_version, thumbnail_source, is_missing "
                "FROM media_items WHERE relative_path = ?",
                (path,),
            ).fetchone()
        )

    def media_id(conn: sqlite3.Connection, path: str) -> int:
        return conn.execute("SELECT id FROM media_items WHERE relative_path = ?", (path,)).fetchone()[0]

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        library = base / "Fotos"
        library.mkdir()

        # ---- Archivos de prueba ----
        (library / "a.jpg").write_bytes(_testing.jpeg_bytes((3000, 2000), orientation=6))
        Image.new("RGB", (800, 600), (30, 90, 200)).save(library / "b.png")
        (library / "rota.jpg").write_bytes(b"esto no es una imagen" * 30)
        (library / "iphone.heic").write_bytes(_testing.jpeg_bytes((900, 600)))  # JPEG disfrazado
        (library / "raw.dng").write_bytes(b"x")
        (library / "peli.mp4").write_bytes(b"x" * 20)  # vídeo: aún sin origen de miniaturas

        fake = base / "fake_exiftool.py"
        fake.write_text(_testing.FAKE_EXIFTOOL, encoding="utf-8")
        os.environ["FAKE_EXIFTOOL_DATA"] = str(base / "exiftool_data.json")
        preview = "base64:" + base64.b64encode(_testing.jpeg_bytes((1024, 683))).decode()
        (base / "exiftool_data.json").write_text(
            json.dumps({"raw.dng": {"IFD0:Orientation": 1, "SubIFD1:PreviewImage": preview}}),
            encoding="utf-8",
        )
        registry = SourceRegistry()
        registry.register(PillowSource())
        registry.register(heif_source.HeifSource())
        registry.register(RawPreviewSource(ExifToolRunner(command=[sys.executable, str(fake)])))

        real_support = heif_source.heif_support_available
        heif_source.heif_support_available = lambda: False  # al principio, pillow-heif "no instalada"

        db_path = CatalogBuilder(base / "Catalogo").build()
        cache = ThumbnailCache(base / "Catalogo")
        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)
            add_folder(conn, library)

            # ---- 1. Primera ejecución ----
            seen: list[JobProgress] = []
            result = generate_pending_thumbnails(
                conn, registry=registry, progress=seen.append, batch_size=2, max_workers=3
            )
            print(result.summary())
            assert (result.total, result.generated, result.failed, result.unsupported) == (5, 3, 1, 1)
            assert len(result.generated_ids) == 3 and result.has_warnings
            assert seen[0] == JobProgress(0, 5) and seen[-1] == JobProgress(5, 5)
            assert state(conn, "a.jpg") == (1, THUMBNAIL_VERSION, "pillow", 0)
            assert state(conn, "raw.dng") == (1, THUMBNAIL_VERSION, "raw_preview:PreviewImage", 0)
            assert state(conn, "rota.jpg") == (2, THUMBNAIL_VERSION, None, 0)
            assert state(conn, "iphone.heic") == (2, THUMBNAIL_VERSION, None, 0)
            assert state(conn, "peli.mp4") == (0, 0, None, 0)  # sin origen: no se toca
            same = db_rows(conn, "SELECT COUNT(*) FROM media_items WHERE thumbnail_mtime_ns = file_mtime_ns AND thumbnail_status > 0")
            assert same == [(5,)]  # 3 generadas + 2 marcadas con error, todas con el mtime anotado
            errors = {r[0]: r[1] for r in db_rows(conn, "SELECT relative_path, stage FROM scan_errors")}
            assert errors == {"rota.jpg": "thumbnail", "iphone.heic": "thumbnail"}
            message = db_rows(conn, "SELECT message FROM scan_errors WHERE relative_path = 'iphone.heic'")[0][0]
            assert "pillow-heif" in message
            a_id, dng_id = media_id(conn, "a.jpg"), media_id(conn, "raw.dng")
            assert [s.max_side for s in cache.existing("photo", a_id)] == [160, 480, 1200, 2560]
            assert [s.max_side for s in cache.existing("photo", dng_id)] == [160, 480, 1200, 2560]  # los dos grandes, a 1024 px
            print("1. Primera ejecución: 3 generadas, 1 con error, 1 sin soporte; el vídeo, intacto")

            # ---- 2. Segunda ejecución: nada pendiente ----
            again = generate_pending_thumbnails(conn, registry=registry)
            assert again.total == 0 and again.status_text() == "" and not again.has_warnings

            # ---- 3. Un archivo cambia en disco: add_folder lo marca y se regenera ----
            Image.new("RGB", (300, 200), (200, 30, 30)).save(library / "b.png")
            os.utime(library / "b.png", ns=(9_000_000_000, 9_000_000_000))
            b_id = media_id(conn, "b.png")
            assert [s.max_side for s in cache.existing("photo", b_id)] == [160, 480, 1200, 2560]
            add_folder(conn, library)
            assert state(conn, "b.png")[0] == 0  # add_folder lo dejó pendiente
            result = generate_pending_thumbnails(conn, registry=registry)
            assert (result.total, result.generated) == (1, 1)
            assert [s.max_side for s in cache.existing("photo", b_id)] == [160, 480, 1200, 2560]
            with Image.open(cache.path_for("photo", b_id, ALL_SIZES[-1])) as regenerated:
                assert regenerated.size == (300, 200)  # el tamaño grande antiguo (800 px) se sustituyó
            print("3. Original modificado: regenerado, y los cuatro tamaños se sustituyen")

            # Cinturón de seguridad: si 'file_mtime_ns' cambia por otra vía, también queda pendiente
            conn.execute("UPDATE media_items SET file_mtime_ns = file_mtime_ns + 1 WHERE id = ?", (b_id,))
            conn.commit()
            assert generate_pending_thumbnails(conn, registry=registry).generated == 1

            # ---- 4. Regeneración a demanda: por 'id', solo errores y todo ----
            assert invalidate_thumbnails(conn, [a_id, a_id, 999_999]) == 1  # repetidos y ausentes
            conn.commit()
            assert state(conn, "a.jpg")[0] == 0 and state(conn, "b.png")[0] == 1  # solo a.jpg
            result = generate_pending_thumbnails(conn, registry=registry)
            assert (result.total, result.generated) == (1, 1) and result.generated_ids == (a_id,)

            assert invalidate_thumbnails(conn, only_errors=True) == 2  # rota.jpg y iphone.heic
            conn.commit()
            heif_source.heif_support_available = lambda: True  # "se instala pillow-heif"
            result = generate_pending_thumbnails(conn, registry=registry)
            assert (result.total, result.generated, result.failed) == (2, 1, 1)
            assert state(conn, "iphone.heic") == (1, THUMBNAIL_VERSION, "heif", 0)
            assert [r[0] for r in db_rows(conn, "SELECT relative_path FROM scan_errors")] == ["rota.jpg"]
            print("4. Regenerar por id y 'solo errores': el HEIC se arregla al instalar la librería")

            assert invalidate_thumbnails(conn) == 6  # todas las filas, también el vídeo (sigue sin origen)
            conn.commit()
            result = generate_pending_thumbnails(conn, registry=registry)
            assert (result.total, result.generated, result.failed) == (5, 4, 1)

            # ---- 5. Sube la versión del motor: se regenera todo, también lo que falló ----
            result = generate_pending_thumbnails(conn, registry=registry, version=THUMBNAIL_VERSION + 1)
            assert (result.total, result.generated, result.failed) == (5, 4, 1)
            assert state(conn, "a.jpg")[1] == THUMBNAIL_VERSION + 1
            assert generate_pending_thumbnails(conn, registry=registry, version=THUMBNAIL_VERSION + 1).total == 0
            print("5. Subir la versión del motor regenera todo")

            # ---- 6. Archivo que desaparece y unidad desconectada ----
            (library / "b.png").unlink()
            invalidate_thumbnails(conn, [b_id])
            conn.commit()
            result = generate_pending_thumbnails(conn, registry=registry)
            assert result.missing == 1 and state(conn, "b.png")[3] == 1
            assert not db_rows(conn, "SELECT 1 FROM scan_errors WHERE relative_path = 'b.png'")

            invalidate_thumbnails(conn)
            conn.commit()
            library.rename(base / "Fotos_desconectada")
            result = generate_pending_thumbnails(conn, registry=registry)
            # Pendientes de tipo foto y presentes: a.jpg, rota.jpg, iphone.heic y raw.dng (b.png ya no existe)
            assert result.skipped_offline == 4 and result.generated == 0 and result.has_warnings
            assert state(conn, "a.jpg")[0] == 0  # sigue pendiente
            (base / "Fotos_desconectada").rename(library)
            result = generate_pending_thumbnails(conn, registry=registry)
            assert (result.generated, result.failed, result.skipped_offline) == (3, 1, 0)  # rota.jpg sigue rota
            print("6. Archivo desaparecido y unidad desconectada: sin falsos errores")

            # ---- 7. Cancelación a mitad y reanudación ----
            for index in range(30):
                (library / "lote" / f"f{index:02d}.jpg").parent.mkdir(exist_ok=True)
                (library / "lote" / f"f{index:02d}.jpg").write_bytes(_testing.jpeg_bytes((1200 + index, 800)))
            add_folder(conn, library)
            event = threading.Event()
            calls = {"n": 0}

            def cancel_after_ten(_progress: JobProgress) -> None:
                calls["n"] += 1
                if calls["n"] == 10:
                    event.set()

            result = generate_pending_thumbnails(
                conn, registry=registry, progress=cancel_after_ten, cancel_event=event,
                batch_size=6, max_workers=2,
            )
            pending_after = db_rows(conn, "SELECT COUNT(*) FROM media_items WHERE thumbnail_status = 0 AND media_type = 'photo' AND is_missing = 0")[0][0]
            assert result.cancelled and 0 < result.generated < 30 and pending_after > 0
            rest = generate_pending_thumbnails(conn, registry=registry)
            assert not rest.cancelled and result.generated + rest.generated == 30
            assert db_rows(conn, "SELECT COUNT(*) FROM media_items WHERE relative_path LIKE 'lote/%' AND thumbnail_status = 1") == [(30,)]
            print(f"7. Cancelación: {result.generated} generadas, el resto ({rest.generated}) en la siguiente ejecución")

            # ---- 8. La caché no se puede escribir: el trabajo se aborta SIN marcar nada como fallido ----
            for index in range(12):
                (library / "lote2").mkdir(exist_ok=True)
                (library / "lote2" / f"g{index:02d}.jpg").write_bytes(_testing.jpeg_bytes((900, 700)))
            add_folder(conn, library)
            errors_before = db_rows(conn, "SELECT COUNT(*) FROM media_items WHERE thumbnail_status = 2")[0][0]
            shutil.rmtree(cache.root / "photo")
            (cache.root / "photo").write_bytes(b"estorbo")  # un archivo donde debería haber carpetas
            try:
                generate_pending_thumbnails(conn, registry=registry, batch_size=4, max_workers=2)
            except ThumbnailStorageError as error:
                print("8. Caché sin escritura:", str(error)[:60])
            else:
                raise AssertionError("Debería abortar si no se puede escribir en la caché")
            assert db_rows(conn, "SELECT COUNT(*) FROM media_items WHERE thumbnail_status = 2")[0][0] == errors_before
            assert db_rows(conn, "SELECT COUNT(*) FROM media_items WHERE relative_path LIKE 'lote2/%' AND thumbnail_status = 0") == [(12,)]
            (cache.root / "photo").unlink()
            (cache.root / "photo").mkdir()
            result = generate_pending_thumbnails(conn, registry=registry)
            assert result.generated == 12 and result.failed == 0
            print("   ...y al recuperarse la caché se genera todo lo que quedaba")

            # ---- 9. Sin orígenes registrados no se hace nada; una base en memoria se rechaza ----
            assert generate_pending_thumbnails(conn, registry=SourceRegistry()).total == 0
            with closing(sqlite3.connect(":memory:")) as memory_conn:
                try:
                    generate_pending_thumbnails(memory_conn, registry=registry)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Una base en memoria debería rechazarse")
            assert catalog_directory_of(conn) == db_path.parent
            assert not list(base.rglob("*.tmp"))

        heif_source.heif_support_available = real_support

    print("Autoprueba finalizada correctamente.")
