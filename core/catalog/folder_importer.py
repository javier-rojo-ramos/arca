"""Añadir una carpeta al catálogo: orquesta registro, escaneo y guardado.

Este módulo NO depende de Qt: es Python puro. 'add_folder' es LA función a la que
llama el menú "Añadir carpeta". Recibe una conexión sqlite3 como primer parámetro,
así que se envía tal cual al gestor asíncrono y se ejecuta en un hilo secundario:

    folder = QFileDialog.getExistingDirectory(self, "Añadir carpeta al catálogo")
    if folder:
        self._cancel_event = threading.Event()  # el botón "Cancelar" hará .set()
        self.db.execute_async(
            add_folder, folder, cancel_event=self._cancel_event,
            progress=self.scan_progress.emit,  # señal Qt: segura entre hilos
            on_result=self._on_folder_added, on_error=self._on_add_folder_error,
        )

Qué hace 'add_folder', en este orden:

    1. register_folder()    Decide a qué ubicación de almacenamiento pertenece la
                            carpeta (reutiliza una existente o crea una nueva).
       set_folder_content() Si se ha elegido qué contiene la carpeta ("¿Qué contiene
                            esta carpeta?"), se guarda (ver core/catalog/libraries.py).
    2. FolderScanner        Recorre la carpeta aplicando el filtro y el detector
                            (sin abrir archivos). La carpeta del propio catálogo se
                            excluye sola.
    3. Tipo de contenido    Cada archivo se compara con el tipo de contenido de SU
                            carpeta (el declarado o el heredado): lo que no encaja
                            (p. ej. un .jpg en una carpeta de música) se ignora; al
                            resto se le asigna su biblioteca.
       save_candidates()    Guarda lo encontrado por lotes de 500, con un 'commit'
                            por lote: nuevos se insertan, cambiados se marcan para
                            reprocesar y sin cambios no se tocan.
       apply_folder_files() En el mismo lote, recupera la valoración, la marca y el
                            color de los archivos sin XMP (vídeo, audio...) desde el
                            archivo '.arca.json' de su carpeta (ver core/userdata/).
    4. Al terminar          Marca como desaparecido lo que ya no está, y guarda en
                            'scan_errors' los problemas de lectura.

Añadir una carpeta y reescanearla son LA MISMA operación: si la carpeta ya está en
el catálogo, 'add_folder' la recorre otra vez y solo aplica las diferencias. Se
puede interrumpir en cualquier momento (cancel_event o cerrar la aplicación): lo
guardado hasta entonces es coherente y la siguiente llamada continúa sin duplicar.

Excepción a la regla del gestor asíncrono: aquí SÍ se hace 'commit' (uno por
lote). Una operación larga con una única transacción bloquearía la escritura al
resto de la aplicación durante minutos y perdería todo si se cancela.

Archivos ignorados por el tipo de contenido: se anotan como VISTOS (no se marcan como
desaparecidos). Si ya estaban catalogados (p. ej. la carpeta se añadió antes como
"auto" y ahora se declara "Música"), se quedan como estaban: quitarlos del catálogo
será una acción aparte (paso 2b).

1.5.1 Comentarios con el nombre nuevo del archivo de carpeta ('.arca.json').
1.5.0 Vídeos de carpetas automáticas por el nombre; vídeos sin clasificar en el resumen.
1.4.0 Tipo de contenido de las carpetas y biblioteca de cada archivo ('content').

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.folder_importer
"""

__version__ = "1.5.1"
__all__ = [
    "DEFAULT_BATCH_SIZE",
    "AddFolderProgress",
    "AddFolderResult",
    "add_folder",
]

# Librerías estándar
import itertools
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.catalog_writer import (
    BatchResult,
    count_active_items,
    mark_missing,
    record_seen_paths,
    replace_walk_issues,
    reset_seen_paths,
    save_candidates,
)
from core.catalog.folder_scanner import (
    FolderScanner,
    ScanCandidate,
    ScanError,
    ScanStats,
)
from core.catalog.libraries import (
    FolderContentResolver,
    count_unclassified,
    is_allowed,
    library_for,
    parent_folder,
    set_folder_content,
    validate_folder_content,
)
from core.catalog.media_types import MediaType
from core.catalog.storage_locations import StorageLocation, register_folder
from core.userdata.sync import FolderFileCache, apply_folder_files

# Archivos por lote (y por transacción). Debe ser <= catalog_writer.MAX_BATCH_SIZE.
DEFAULT_BATCH_SIZE = 500


@dataclass(frozen=True, slots=True)
class AddFolderProgress:
    """Avance del proceso, que 'add_folder' notifica tras guardar cada lote.

    Se envía desde el hilo secundario: para actualizar la interfaz hay que pasar
    por una señal de Qt (p. ej. 'progress=self.scan_progress.emit').

    Attributes:
        directories_visited: Carpetas recorridas hasta ahora.
        files_seen: Archivos encontrados hasta ahora (incluidos los descartados).
        saved_items: Archivos para catalogar ya procesados (nuevos o no).
        new_items: De ellos, cuántos eran nuevos.
    """

    directories_visited: int
    files_seen: int
    saved_items: int
    new_items: int


@dataclass(frozen=True, slots=True)
class AddFolderResult:
    """Resultado final de 'add_folder'.

    Attributes:
        location: Ubicación de almacenamiento a la que pertenece la carpeta.
        relative_folder: Carpeta escaneada, relativa a la ubicación ('' = toda).
        location_created: True si la ubicación se creó en esta llamada.
        new_items: Archivos nuevos insertados.
        changed_items: Archivos que habían cambiado (quedan pendientes de reprocesar).
        revived_items: Archivos que habían desaparecido y han vuelto.
        unchanged_items: Archivos sin cambios.
        missing_items: Archivos marcados como desaparecidos en esta llamada.
        missing_check_skipped: Motivo por el que NO se comprobó qué archivos han
            desaparecido (escaneo cancelado, carpeta ilegible o vacía...), o None
            si se comprobó.
        cancelled: True si el proceso se interrumpió antes de terminar.
        stats: Contadores del recorrido (descartados por el filtro, extensiones
            ignoradas, problemas de lectura...).
        user_data_applied: Elementos cuya valoración, marca o color se ha tomado de
            los archivos de carpeta '.arca.json'.
        folder_content: Tipo de contenido efectivo de la carpeta escaneada ('auto' o
            una biblioteca; ver core/catalog/libraries.py).
        excluded_items: Archivos soportados que no se han catalogado porque no encajan
            con el tipo de contenido de su carpeta.
        excluded_extensions: Extensiones de esos archivos (para el resumen).
        reclassified_items: Elementos que ya existían y han cambiado de biblioteca.
        unclassified_items: Elementos de la carpeta que siguen sin biblioteca (vídeos de
            carpetas automáticas cuyo nombre no lo dice), contando los que ya había.
    """

    location: StorageLocation
    relative_folder: str
    location_created: bool
    new_items: int
    changed_items: int
    revived_items: int
    unchanged_items: int
    missing_items: int
    missing_check_skipped: str | None
    cancelled: bool
    stats: ScanStats
    user_data_applied: int = 0
    folder_content: str = "auto"
    excluded_items: int = 0
    excluded_extensions: Counter[str] = field(default_factory=Counter)
    reclassified_items: int = 0
    unclassified_items: int = 0

    def summary(self) -> str:
        """Resumen en texto (varias líneas), pensado para mostrar al usuario al terminar.

        Solo incluye las líneas que aportan algo: lo que vale cero se omite, salvo
        los archivos nuevos y los que no han cambiado.
        """
        lines = [
            f"Archivos nuevos: {self.new_items}",
            f"Archivos modificados: {self.changed_items}",
            f"Sin cambios: {self.unchanged_items}",
        ]
        if self.revived_items:
            lines.append(f"Archivos que han vuelto a aparecer: {self.revived_items}")
        if self.user_data_applied:
            lines.append(
                f"Valoraciones, marcas o colores recuperados de las carpetas: {self.user_data_applied}"
            )
        if self.missing_items:
            lines.append(f"Archivos que ya no están en disco: {self.missing_items}")

        # Lo que se ha dejado fuera, con las extensiones más frecuentes
        if self.stats.unsupported_files:
            top_extensions = ", ".join(
                f"{extension} ({count})"
                for extension, count in self.stats.ignored_extensions.most_common(5)
            )
            lines.append(
                f"Ignorados por no ser un medio soportado: {self.stats.unsupported_files}"
                f" [{top_extensions}]"
            )
        if self.excluded_items:
            top_extensions = ", ".join(
                f"{extension} ({count})"
                for extension, count in self.excluded_extensions.most_common(5)
            )
            lines.append(
                f"Ignorados por no encajar con el contenido de la carpeta: "
                f"{self.excluded_items} [{top_extensions}]"
            )
        if self.reclassified_items:
            lines.append(f"Cambiados de biblioteca: {self.reclassified_items}")
        if self.unclassified_items:
            lines.append(
                f"Vídeos sin clasificar: {self.unclassified_items} (se revisan en «Sin "
                "clasificar», en la sección Catálogo; clic derecho > Biblioteca)"
            )
        if self.stats.issues:
            lines.append(f"No se pudieron leer: {len(self.stats.issues)} (ver el registro)")

        # Avisos sobre un resultado incompleto
        if self.cancelled:
            lines.append("El proceso se canceló antes de terminar.")
        if self.missing_check_skipped:
            lines.append(f"No se comprobó qué archivos han desaparecido: {self.missing_check_skipped}.")
        return "\n".join(lines)


def add_folder(
    conn: sqlite3.Connection,
    folder: str | Path,
    *,
    content: str | None = None,
    name: str | None = None,
    default_media_type: MediaType | str | None = None,
    progress: Callable[[AddFolderProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> AddFolderResult:
    """Añade una carpeta al catálogo (o la reescanea si ya estaba).

    Args:
        conn: Conexión sqlite3 al catálogo (con o sin 'row_factory').
        folder: Carpeta elegida por el usuario. Debe existir.
        content: Qué contiene la carpeta según el usuario ('auto' o una biblioteca: ver
            core/catalog/libraries.py); se guarda para ella y sus subcarpetas. None = no
            cambiar nada (p. ej. al sincronizar): vale lo que ya estuviera declarado.
        name: Nombre de la ubicación si hay que crearla (por defecto, el de la carpeta).
        default_media_type: Tipo de medio por defecto de la ubicación, si se crea.
        progress: Función a la que se avisa tras cada lote. Se llama desde el hilo
            secundario; si falla, el error se registra pero el proceso continúa.
        cancel_event: Si se activa ('set()') desde otro hilo, el proceso se detiene
            en cuanto puede. Lo ya guardado se conserva.
        batch_size: Archivos por lote y por transacción.

    Returns:
        Un 'AddFolderResult' con los recuentos.

    Raises:
        InvalidFolderError: Si la ruta no existe o no es una carpeta.
        OverlappingLocationError: Si la carpeta contiene ubicaciones ya existentes.
        ScanError: Si la carpeta es la del propio catálogo (o está dentro de ella).
        ValueError: Si 'content', 'default_media_type' o 'batch_size' no son válidos.
        sqlite3.Error: Si falla la base de datos (se deshace el lote en curso).
    """
    if not 0 < batch_size <= DEFAULT_BATCH_SIZE * 2:
        raise ValueError(f"batch_size no válido: {batch_size}")
    if content is not None:
        content = validate_folder_content(content)  # antes de tocar la base de datos

    try:
        # 1. Ubicación. 'register_folder' deja una transacción abierta (no se confirma
        #    todavía): si la carpeta resulta no escaneable, se deshace y no queda
        #    una ubicación huérfana en la base de datos.
        registration = register_folder(
            conn, folder, name=name, default_media_type=default_media_type
        )
        location = registration.location
        relative_folder = registration.relative_folder

        # Qué contiene la carpeta (si el usuario lo ha elegido), en la misma transacción
        # que la ubicación: si algo falla después, se deshacen las dos
        if content is not None:
            set_folder_content(conn, location.id, relative_folder, content)
        contents = FolderContentResolver.load(conn, location.id)

        # 2. Escáner. La carpeta del catálogo se excluye automáticamente: es la
        #    carpeta que contiene el archivo .db de esta conexión.
        catalog_directory = _catalog_directory(conn)
        scanner = FolderScanner(
            location.absolute_path,
            excluded_directories=[catalog_directory] if catalog_directory else [],
        )
        scan_root = location.absolute_path / relative_folder
        # La validación se hace aquí, al llamar (no al empezar a iterar)
        scan_iterator = scanner.scan(scan_root, cancel_event=cancel_event)

        # Si se puede escanear, la ubicación está conectada (por si constaba como
        # desconectada: p. ej. se acaba de enchufar el disco externo)
        conn.execute(
            "UPDATE storage_locations SET is_online = 1 WHERE id = ? AND is_online = 0",
            (location.id,),
        )

        # La ubicación ya es segura de conservar
        conn.commit()
    except Exception:
        # Cualquier fallo (ruta no válida, solapamiento, carpeta del catálogo...)
        # deshace también el alta de la ubicación
        conn.rollback()
        raise

    logger.info(f"Añadiendo carpeta al catálogo: {scan_root}")

    totals = BatchResult()
    user_data_applied = 0
    excluded_extensions: Counter[str] = Counter()
    folder_files: FolderFileCache = {}  # archivos '.arca.json' ya leídos en este escaneo
    try:
        # 3. Escaneo y guardado por lotes (un commit por lote)
        reset_seen_paths(conn)
        conn.commit()

        for batch in itertools.batched(scan_iterator, batch_size):
            # Lo que encaja con el contenido de su carpeta (ya con su biblioteca) y lo que no
            accepted, rejected = _split_by_folder_content(batch, contents)
            excluded_extensions.update(
                candidate.file_extension or "(sin extensión)" for candidate in rejected
            )
            try:
                totals += save_candidates(conn, location.id, accepted)
                # Se anotan como vistos TODOS (también los ignorados): un archivo ignorado
                # no ha desaparecido, así que nunca se debe marcar como ausente
                record_seen_paths(conn, (candidate.relative_path for candidate in batch))
                # Datos del usuario de los archivos sin XMP: manda su archivo de carpeta
                user_data_applied += apply_folder_files(
                    conn,
                    location.absolute_path,
                    location.id,
                    (candidate.relative_path for candidate in accepted),
                    folder_files,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

            _notify_progress(progress, scanner.stats, totals)

        # 4. Cierre: desaparecidos y errores de lectura (una sola transacción)
        stats = scanner.stats
        skip_reason = _missing_check_skip_reason(
            conn, location.id, relative_folder, stats
        )
        missing_count = 0
        try:
            if skip_reason is None:
                missing_count = mark_missing(
                    conn,
                    location.id,
                    relative_folder,
                    (issue.relative_path for issue in stats.issues),
                )
            else:
                logger.warning(f"No se comprueban los archivos desaparecidos: {skip_reason}")

            replace_walk_issues(
                conn,
                location.id,
                relative_folder,
                stats.issues,
                clear_previous=not stats.cancelled,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        # Se cierra el generador (por si hubo un error a medias) y se libera la
        # tabla temporal de la conexión
        scan_iterator.close()
        _drop_seen_paths(conn)

    result = AddFolderResult(
        location=location,
        relative_folder=relative_folder,
        location_created=registration.created,
        new_items=totals.new,
        changed_items=totals.changed,
        revived_items=totals.revived,
        unchanged_items=totals.unchanged,
        missing_items=missing_count,
        missing_check_skipped=skip_reason,
        cancelled=stats.cancelled,
        stats=stats,
        user_data_applied=user_data_applied,
        folder_content=contents.content_of(relative_folder),
        excluded_items=sum(excluded_extensions.values()),
        excluded_extensions=excluded_extensions,
        reclassified_items=totals.reclassified,
        unclassified_items=count_unclassified(conn, location.id, relative_folder),
    )
    logger.info(
        f"Carpeta procesada: {result.new_items} nuevos, {result.changed_items} "
        f"cambiados, {result.revived_items} reaparecidos, {result.unchanged_items} "
        f"sin cambios, {result.missing_items} desaparecidos, {result.excluded_items} "
        f"ignorados por el contenido de la carpeta ({result.folder_content})"
    )
    return result


# -----------------------------------------------------------------------------
# Pasos internos
# -----------------------------------------------------------------------------


def _split_by_folder_content(
    batch: Sequence[ScanCandidate], contents: FolderContentResolver
) -> tuple[list[ScanCandidate], list[ScanCandidate]]:
    """Separa un lote según el tipo de contenido de la carpeta de cada archivo.

    Returns:
        (aceptados, ignorados). Los aceptados llevan ya su biblioteca
        ('ScanCandidate.library'); los ignorados no encajan con su carpeta (p. ej. una
        carátula .jpg en una carpeta de música).
    """
    accepted: list[ScanCandidate] = []
    rejected: list[ScanCandidate] = []
    for candidate in batch:
        content = contents.content_of(parent_folder(candidate.relative_path))
        if is_allowed(candidate.media_type, content):
            library = library_for(candidate.media_type, content, candidate.file_name)
            accepted.append(replace(candidate, library=library))
        else:
            rejected.append(candidate)
    return accepted, rejected


def _catalog_directory(conn: sqlite3.Connection) -> Path | None:
    """Devuelve la carpeta del catálogo (la que contiene el .db), o None si no hay archivo.

    'PRAGMA database_list' indica el archivo de cada base de datos de la conexión;
    en una base en memoria el campo viene vacío.
    """
    for _sequence, schema_name, file_path in conn.execute("PRAGMA database_list;"):
        if schema_name == "main" and file_path:
            return Path(file_path).parent
    return None


def _missing_check_skip_reason(
    conn: sqlite3.Connection,
    location_id: int,
    relative_folder: str,
    stats: ScanStats,
) -> str | None:
    """Indica por qué NO es fiable marcar archivos como desaparecidos (None = sí lo es).

    Marcar archivos como desaparecidos solo tiene sentido si el escaneo vio TODO lo
    que había. Si no, un fallo puntual (unidad desconectada, permisos, cancelación)
    marcaría como desaparecida una biblioteca entera.
    """
    if stats.cancelled:
        return "el escaneo se canceló antes de terminar"

    # Ruta con la que 'FolderScanner' anota un problema en la propia carpeta raíz
    root_issue_path = relative_folder or "."
    if any(issue.relative_path == root_issue_path for issue in stats.issues):
        return "no se pudo leer la carpeta raíz del escaneo"

    # En Linux y macOS, una unidad desconectada deja su punto de montaje como una
    # carpeta vacía que SÍ se puede leer: sin este control, se marcaría todo.
    if stats.files_seen == 0 and count_active_items(conn, location_id, relative_folder) > 0:
        return "la carpeta aparece vacía (¿la unidad está desconectada?)"

    return None


def _notify_progress(
    progress: Callable[[AddFolderProgress], None] | None,
    stats: ScanStats,
    totals: BatchResult,
) -> None:
    """Avisa del avance. Un fallo en el aviso no debe interrumpir el guardado."""
    if progress is None:
        return
    try:
        progress(
            AddFolderProgress(
                directories_visited=stats.directories_visited,
                files_seen=stats.files_seen,
                saved_items=totals.new + totals.changed + totals.revived + totals.unchanged,
                new_items=totals.new,
            )
        )
    except Exception:  # noqa: BLE001 - el aviso es opcional
        logger.exception("Error en la función de progreso de add_folder.")


def _drop_seen_paths(conn: sqlite3.Connection) -> None:
    """Elimina las tablas temporales del escaneo (solo existen en esta conexión)."""
    try:
        conn.execute("DROP TABLE IF EXISTS temp.scan_seen_paths;")
        conn.execute("DROP TABLE IF EXISTS temp.scan_unreadable_paths;")
        conn.commit()
    except sqlite3.Error:
        logger.opt(exception=True).warning("No se pudieron eliminar las tablas temporales.")


if __name__ == "__main__":
    # Autoprueba con un catálogo REAL en una carpeta temporal.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.folder_importer
    import os
    import tempfile
    from contextlib import closing

    from core.catalog.catalog_builder import CatalogBuilder
    from core.catalog.catalog_schema import configure_connection
    from core.catalog.storage_locations import OverlappingLocationError

    def rows(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> list:
        """Atajo para consultar la base de datos."""
        return connection.execute(sql, params).fetchall()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        library = base / "Fotos"
        files = ["a.jpg", "b.jpg", "2024/c.jpg", "2024/d.mp4", "2024/notas.txt", "musica/e.flac"]
        for name in files:
            target = library / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * 10)

        # El catálogo está DENTRO de la carpeta que se va a añadir (caso delicado)
        catalog_dir = library / "MiCatalogo"
        db_path = CatalogBuilder(catalog_dir).build()
        (catalog_dir / "cache" / "photo" / "0001.jpg").write_bytes(b"x")

        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)

            # 1. Primera vez: se crea la ubicación y se catalogan 5 archivos
            progress_log: list[AddFolderProgress] = []
            result = add_folder(conn, library, progress=progress_log.append, batch_size=2)
            print(f"Primera vez: {result.new_items} nuevos | avisos de progreso: {len(progress_log)}")
            assert result.location_created and result.new_items == 5
            assert len(progress_log) == 3  # 5 archivos en lotes de 2 -> 2 + 2 + 1
            assert progress_log[-1].saved_items == 5
            assert result.missing_items == 0 and result.missing_check_skipped is None
            catalogued = [r[0] for r in rows(conn, "SELECT relative_path FROM media_items ORDER BY 1")]
            assert not any(path.startswith("MiCatalogo") for path in catalogued)
            assert result.stats.ignored_extensions["txt"] == 1
            summary_text = result.summary()
            assert "Archivos nuevos: 5" in summary_text and "txt (1)" in summary_text
            assert "cancel" not in summary_text and "desaparecido" not in summary_text

            # 2. Reescaneo sin cambios: no se toca nada
            conn.execute("UPDATE media_items SET rating = 3 WHERE relative_path = 'a.jpg'")
            conn.commit()
            result = add_folder(conn, library)
            assert not result.location_created and result.unchanged_items == 5
            assert result.new_items == result.changed_items == result.missing_items == 0
            print("Reescaneo sin cambios: 5 sin cambios")

            # 3. Un archivo cambia, otro desaparece y otro nuevo aparece
            os.utime(library / "b.jpg", ns=(5_000_000_000, 5_000_000_000))  # cambia la fecha
            (library / "2024" / "d.mp4").unlink()
            (library / "nueva.jpg").write_bytes(b"x" * 10)
            result = add_folder(conn, library)
            print(f"Tras cambios: {result.new_items} nuevo, {result.changed_items} cambiado, "
                  f"{result.missing_items} desaparecido")
            assert (result.new_items, result.changed_items, result.missing_items) == (1, 1, 1)
            assert rows(conn, "SELECT is_missing FROM media_items WHERE relative_path = '2024/d.mp4'") == [(1,)]
            assert rows(conn, "SELECT rating FROM media_items WHERE relative_path = 'a.jpg'") == [(3,)]
            assert rows(conn, "SELECT scan_version FROM media_items WHERE relative_path = 'b.jpg'") == [(0,)]

            # 4. El archivo borrado vuelve: reaparece
            (library / "2024" / "d.mp4").write_bytes(b"x" * 10)
            os.utime(library / "2024" / "d.mp4", ns=(1, 1))  # fecha distinta: cuenta como cambiado
            result = add_folder(conn, library)
            assert result.changed_items == 1 and result.missing_items == 0
            assert rows(conn, "SELECT is_missing FROM media_items WHERE relative_path = '2024/d.mp4'") == [(0,)]

            # 5. Añadir una subcarpeta: misma ubicación, solo se escanea esa subcarpeta
            result = add_folder(conn, library / "2024")
            assert not result.location_created and result.relative_folder == "2024"
            assert result.stats.files_seen == 3  # c.jpg, d.mp4, notas.txt
            assert rows(conn, "SELECT COUNT(*) FROM storage_locations") == [(1,)]
            print("Subcarpeta: misma ubicación, relativa '2024'")

            # 6. Carpeta ilegible: lo que hay debajo no se marca como desaparecido
            real_scandir = os.scandir

            def failing_scandir(path):
                if Path(path).name == "musica":
                    raise PermissionError(13, "Permiso denegado", str(path))
                return real_scandir(path)

            os.scandir = failing_scandir
            try:
                result = add_folder(conn, library)
            finally:
                os.scandir = real_scandir
            assert result.missing_items == 0
            assert rows(conn, "SELECT is_missing FROM media_items WHERE relative_path = 'musica/e.flac'") == [(0,)]
            assert [r[0] for r in rows(conn, "SELECT relative_path FROM scan_errors")] == ["musica"]
            result = add_folder(conn, library)  # ya legible: el error se limpia solo
            assert rows(conn, "SELECT COUNT(*) FROM scan_errors") == [(0,)]
            print("Carpeta ilegible: protegida, y el error se limpia al resolverse")

            # 7. Carpeta vacía (¿unidad desconectada?): NO se marca nada
            for item in (library / "musica").iterdir():
                item.unlink()
            result = add_folder(conn, library / "musica")
            assert result.missing_check_skipped is not None and result.missing_items == 0
            assert rows(conn, "SELECT is_missing FROM media_items WHERE relative_path = 'musica/e.flac'") == [(0,)]
            print("Carpeta vacía:", result.missing_check_skipped)

            # 8. Cancelación: se cancela tras el primer lote
            event = threading.Event()
            result = add_folder(conn, library, cancel_event=event, batch_size=1,
                                progress=lambda _p: event.set())
            assert result.cancelled and result.missing_check_skipped is not None
            assert result.stats.candidates < 7
            assert "cancel" in result.summary()
            print("Cancelación:", result.missing_check_skipped)

            # 9. Errores: carpeta del propio catálogo, solapamiento y ruta inexistente
            locations_before = rows(conn, "SELECT COUNT(*) FROM storage_locations")
            for bad_folder, expected_error in (
                (catalog_dir, ScanError),
                (library.parent, OverlappingLocationError),
            ):
                try:
                    add_folder(conn, bad_folder)
                except expected_error:
                    print(f"Rechazada correctamente: {bad_folder.name} ({expected_error.__name__})")
                else:
                    raise AssertionError(f"{bad_folder} debería rechazarse")
            assert rows(conn, "SELECT COUNT(*) FROM storage_locations") == locations_before
            # (la ubicación de MiCatalogo no queda registrada: se hizo rollback)

            # 10. Las tablas temporales no quedan en la conexión
            assert rows(conn, "SELECT name FROM sqlite_temp_master WHERE name LIKE 'scan_%'") == []

    # 11. Tipo de contenido de las carpetas y biblioteca (catálogo aparte)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        files = [
            "Musica/Rock/cancion.mp3", "Musica/Rock/cover.jpg", "Musica/Rock/clip.mp4",
            "Fotos/a.jpg", "Fotos/b.mov", "Fotos/nota.mp3",
            "Mezcla/c.jpg", "Mezcla/d.mp4", "Mezcla/e.mp3", "Mezcla/ruta.gpx",
        ]
        for name in files:
            target = base / "Discos" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * 10)
        db_path = CatalogBuilder(base / "Cat").build()

        def libraries_in(connection: sqlite3.Connection, prefix: str) -> dict:
            """Ruta -> biblioteca de los elementos catalogados bajo una carpeta."""
            return dict(rows(
                connection,
                "SELECT relative_path, library FROM media_items WHERE relative_path LIKE ?",
                (prefix + "%",),
            ))

        with closing(sqlite3.connect(db_path)) as conn:
            configure_connection(conn)

            # a) Carpeta de música: solo el audio; la carátula y el vídeo se ignoran
            discos = base / "Discos"
            result = add_folder(conn, discos / "Musica", content="audio")
            assert result.folder_content == "audio" and result.new_items == 1
            assert result.excluded_items == 2 and result.excluded_extensions == {"jpg": 1, "mp4": 1}
            assert "Ignorados por no encajar" in result.summary()
            assert libraries_in(conn, "") == {"Rock/cancion.mp3": "audio"}
            location_id = result.location.id

            # b) Sincronizar (sin elegir nada) respeta lo declarado
            result = add_folder(conn, discos / "Musica")
            assert result.folder_content == "audio" and result.excluded_items == 2
            assert result.unchanged_items == 1 and result.missing_items == 0

            # c) Otra carpeta, de fotos y vídeos: el vídeo va a Imagen; el audio, fuera
            result = add_folder(conn, discos / "Fotos", content="image")
            assert libraries_in(conn, "a.jpg") == {"a.jpg": "image"}
            assert libraries_in(conn, "b.mov") == {"b.mov": "image"}
            assert result.excluded_items == 1

            # d) Carpeta automática: todo se cataloga; el vídeo queda sin clasificar
            (discos / "Mezcla" / "IMG_0001.MOV").write_bytes(b"x" * 10)
            result = add_folder(conn, discos / "Mezcla")
            assert result.folder_content == "auto" and result.new_items == 5
            assert result.unclassified_items == 1 and "Vídeos sin clasificar: 1" in result.summary()
            assert libraries_in(conn, "IMG_0001") == {"IMG_0001.MOV": "image"}  # por el nombre
            assert libraries_in(conn, "").items() >= {
                "c.jpg": "image", "d.mp4": None, "e.mp3": "audio", "ruta.gpx": "tracks"
            }.items()

            # e) Esa carpeta se vuelve a añadir declarada como películas: el vídeo se
            #    reclasifica y el resto se ignora, pero NO se marca como ausente
            result = add_folder(conn, discos / "Mezcla", content="video")
            # (IMG_0001.MOV y d.mp4 pasan a 'video'; c.jpg, e.mp3 y ruta.gpx no encajan)
            assert result.reclassified_items == 2 and result.excluded_items == 3
            assert result.unclassified_items == 0
            assert result.missing_items == 0 and result.missing_check_skipped is None
            assert libraries_in(conn, "d.mp4") == {"d.mp4": "video"}
            assert rows(conn, "SELECT COUNT(*) FROM media_items WHERE is_missing = 1") == [(0,)]
            assert rows(conn, "SELECT library FROM media_items WHERE relative_path = 'c.jpg'") == [
                ("image",)
            ]  # ya catalogado: se queda como estaba (quitarlo será el paso 2b)

            # f) Tipo de contenido no válido: se rechaza sin tocar la base de datos
            locations_before = rows(conn, "SELECT COUNT(*) FROM storage_locations")
            (discos.parent / "Otra").mkdir()
            try:
                add_folder(conn, discos.parent / "Otra", content="Música")
            except ValueError:
                pass
            else:
                raise AssertionError("debería rechazar un tipo de contenido desconocido")
            assert rows(conn, "SELECT COUNT(*) FROM storage_locations") == locations_before
            assert rows(
                conn, "SELECT folder, content FROM folder_libraries WHERE storage_location_id = ?",
                (location_id,),
            ) == [("", "audio")]
    print("Tipo de contenido de las carpetas: filtra, asigna la biblioteca y no marca ausentes")

    print("Autoprueba finalizada correctamente.")
