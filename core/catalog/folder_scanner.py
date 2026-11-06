"""Escáner de carpetas: recorre una carpeta y devuelve los archivos que hay que catalogar.

Este módulo NO depende de Qt ni de la base de datos: es Python puro, así que se
puede probar desde la consola y ejecutar en un hilo secundario. NO abre ningún
archivo ni modifica nada en disco: solo lista carpetas y lee nombres y atributos.

Es el paso que une las dos primeras fases del embudo de importación:

    1. ScanFilter          -> descarta ruido (scan_filter.py)
    2. MediaTypeDetector   -> clasifica lo que queda (media_detector.py)
    3. FolderScanner       -> recorre la carpeta y entrega los candidatos (este módulo)
    4. (siguiente paso)    -> insertar los candidatos en 'media_items' y extraer
                              sus metadatos (fotos: EXIF, audio: ID3...)

'FolderScanner.scan()' es un GENERADOR: no construye una lista con todo, sino que
va entregando los candidatos de uno en uno. Así una carpeta con cientos de miles
de archivos no consume memoria, se puede mostrar el progreso mientras avanza y se
puede cancelar a mitad. Si se quiere una lista completa, basta con 'list(...)'.

Ejemplo (en un hilo secundario), insertando por lotes de 500:

    registration = register_folder(conn, folder)  # storage_locations.py
    scanner = FolderScanner(
        registration.location.absolute_path,
        excluded_directories=[catalog_path],      # ¡importante! ver más abajo
    )
    scan_root = registration.location.absolute_path / registration.relative_folder
    for batch in itertools.batched(scanner.scan(scan_root), 500):
        ...  # insertar el lote en la base de datos (una transacción por lote)
    print(scanner.stats.summary())

Carpetas de catálogo: si un catálogo está DENTRO de la carpeta que se escanea (p. ej.
'D:/Fotos/MiCatálogo'), sus miniaturas de 'cache/' pasarían el filtro y el detector
y se catalogarían como fotos. Hay dos defensas:
    - 'excluded_directories': el catálogo activo se pasa por ruta.
    - Cualquier carpeta que contenga un archivo 'catalogo.db' se trata como carpeta
      de catálogo y no se recorre. Funciona aunque la ruta esté escrita de otra
      forma (p. ej. una unidad de red mapeada en Windows, que se compara distinto
      de su ruta real) y protege también de catálogos ajenos (el de otra biblioteca).

Un archivo ignorado NO es un error. Lo que sí se anota en 'stats.issues' son los
problemas reales de lectura (carpeta sin permisos, archivo que desaparece mientras
se escanea...), con el formato de la tabla 'scan_errors' (fase 'walk').

1.3.0 'ScanCandidate.library': biblioteca del archivo (la pone 'add_folder').

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.folder_scanner
"""

__version__ = "1.3.0"
__all__ = [
    "SCAN_STAGE_WALK",
    "FolderScanner",
    "ScanCandidate",
    "ScanError",
    "ScanIssue",
    "ScanStats",
]

# Librerías estándar
import os
import threading
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.catalog_builder import CatalogBuilder
from core.catalog.media_detector import MediaTypeDetector
from core.catalog.media_types import MediaType
from core.catalog.scan_filter import ScanFilter, SkipReason
from core.catalog.storage_locations import make_relative_path

# Nombre de la fase para la columna 'stage' de la tabla 'scan_errors'
SCAN_STAGE_WALK = "walk"

# Formato de fecha de la base de datos (texto UTC, como CURRENT_TIMESTAMP)
_DB_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Clave para agrupar en 'ignored_extensions' los archivos sin extensión
_NO_EXTENSION = "(sin extensión)"


class ScanError(Exception):
    """La carpeta a escanear no es válida (mensaje pensado para mostrar al usuario)."""


@dataclass(frozen=True, slots=True)
class ScanCandidate:
    """Un archivo que ha superado el filtro y el detector: hay que catalogarlo.

    Contiene los campos del 'BLOQUE A' de 'media_items' que se conocen sin abrir el
    archivo. Los metadatos internos (EXIF, ID3...) se leen en el paso siguiente.

    Attributes:
        path: Ruta completa del archivo (para abrirlo en la fase de metadatos).
        relative_path: Ruta relativa a la ubicación de almacenamiento, con '/'.
        file_name: Nombre con extensión.
        file_extension: Minúsculas y sin punto ('jpg'), o None si no tiene.
        media_type: Tipo de medio detectado (nunca 'OTHER').
        mime_type: MIME estimado o real (nunca vacío).
        file_size: Tamaño en bytes.
        file_mtime_ns: Fecha de modificación en nanosegundos (como 'os.stat').
        file_created_at: Creación según el sistema ('YYYY-MM-DD HH:MM:SS' UTC), o
            None si el sistema no la proporciona (p. ej. Linux).
        sidecar_mtime_ns: Fecha de modificación (ns) de su sidecar '.xmp'
            ('IMG_0001.xmp' o 'IMG_0001.CR3.xmp'; si hay los dos, la más reciente), o
            None si no tiene. Sirve para notar que otro programa (Lightroom) ha cambiado
            el sidecar de un RAW, que no cambia por ello.
        library: Biblioteca del archivo ('image', 'video'...; None = sin clasificar).
            El escáner no la conoce (depende del tipo de contenido de la carpeta): la
            pone 'add_folder' con 'dataclasses.replace' antes de guardar.
    """

    path: Path
    relative_path: str
    file_name: str
    file_extension: str | None
    media_type: MediaType
    mime_type: str
    file_size: int
    file_mtime_ns: int
    file_created_at: str | None
    sidecar_mtime_ns: int | None = None
    library: str | None = None

    @property
    def default_title(self) -> str:
        """Título por defecto: el nombre del archivo sin extensión."""
        return Path(self.file_name).stem


@dataclass(frozen=True, slots=True)
class ScanIssue:
    """Un problema real de lectura durante el recorrido (no un archivo ignorado).

    Tiene la forma de una fila de 'scan_errors'.

    Attributes:
        relative_path: Archivo o carpeta afectada, relativa a la ubicación.
        stage: Fase que falló (aquí siempre 'walk').
        message: Descripción del error.
    """

    relative_path: str
    stage: str
    message: str


@dataclass
class ScanStats:
    """Contadores de un recorrido. Se van actualizando mientras avanza el escaneo.

    Attributes:
        directories_visited: Carpetas recorridas con éxito.
        files_seen: Archivos encontrados (incluidos los que luego se descartan).
        candidates: Archivos entregados para catalogar.
        unsupported_files: Archivos que superan el filtro pero no son un medio
            soportado (p. ej. .txt, .pdf).
        skipped: Entradas descartadas por el filtro, por motivo. Una carpeta
            descartada cuenta como una sola entrada (no se mira su contenido).
        ignored_extensions: Extensiones de los 'unsupported_files', para poder
            avisar al usuario de qué se ha quedado fuera.
        issues: Problemas reales de lectura (ver 'ScanIssue').
        cancelled: True si el recorrido se interrumpió antes de terminar.
    """

    directories_visited: int = 0
    files_seen: int = 0
    candidates: int = 0
    unsupported_files: int = 0
    skipped: Counter[SkipReason] = field(default_factory=Counter)
    ignored_extensions: Counter[str] = field(default_factory=Counter)
    issues: list[ScanIssue] = field(default_factory=list)
    cancelled: bool = False

    def summary(self) -> str:
        """Resumen en texto, útil para el log o para mostrar al terminar."""
        lines = [
            f"Carpetas recorridas: {self.directories_visited}",
            f"Archivos encontrados: {self.files_seen}",
            f"Para catalogar: {self.candidates}",
            f"No son un medio soportado: {self.unsupported_files}",
            f"Descartados por el filtro: {sum(self.skipped.values())}",
            f"Problemas de lectura: {len(self.issues)}",
        ]
        if self.cancelled:
            lines.append("El escaneo se canceló antes de terminar.")
        return "\n".join(lines)


class FolderScanner:
    """Recorre carpetas y entrega los archivos que hay que catalogar.

    Una instancia sirve para varios recorridos, pero NO en paralelo: 'stats' se
    reinicia en cada llamada a 'scan()'. Para escanear dos carpetas a la vez, usar
    dos instancias.
    """

    def __init__(
        self,
        location_path: str | Path,
        *,
        scan_filter: ScanFilter | None = None,
        detector: MediaTypeDetector | None = None,
        excluded_directories: Iterable[str | Path] = (),
    ) -> None:
        """Prepara el escáner (todavía no toca el disco).

        Args:
            location_path: Carpeta raíz de la ubicación de almacenamiento. Las rutas
                relativas de los candidatos se calculan respecto a ella.
            scan_filter: Filtro previo. Por defecto, 'ScanFilter()'.
            detector: Detector de tipo de medio. Por defecto, 'MediaTypeDetector()'.
            excluded_directories: Carpetas en las que NO se entra (normalmente, la
                carpeta del propio catálogo).
        """
        self._location_path = Path(os.path.abspath(location_path))
        self._filter = scan_filter or ScanFilter()
        self._detector = detector or MediaTypeDetector()
        self._excluded: frozenset[Path] = frozenset(
            Path(os.path.abspath(folder)) for folder in excluded_directories
        )
        self.stats = ScanStats()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def scan(
        self,
        folder: str | Path | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[ScanCandidate]:
        """Recorre una carpeta (y sus subcarpetas) entregando los candidatos.

        Los errores de validación se lanzan al llamar a este método, no al empezar
        a iterar. El orden es estable: carpetas y archivos por nombre, sin
        distinguir mayúsculas.

        Args:
            folder: Carpeta a recorrer. Debe estar dentro de la ubicación. Por
                defecto, la ubicación completa.
            cancel_event: Si se activa ('set()') desde otro hilo, el recorrido se
                detiene en cuanto puede y 'stats.cancelled' queda en True.

        Returns:
            Un generador de 'ScanCandidate'. Los contadores están en 'self.stats'.

        Raises:
            ScanError: Si la carpeta no existe, está fuera de la ubicación o está
                dentro de una carpeta excluida.
        """
        root = self._validate_root(folder)
        self.stats = ScanStats()
        return self._walk(root, cancel_event)

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    def _validate_root(self, folder: str | Path | None) -> Path:
        """Comprueba que la carpeta a recorrer es válida y la devuelve normalizada."""
        root = self._location_path if folder is None else Path(os.path.abspath(folder))

        try:
            is_folder = root.is_dir()
        except OSError as exc:
            raise ScanError(f"No se pudo acceder a la carpeta:\n{root}\n({exc})") from exc
        if not is_folder:
            raise ScanError(f"La ruta no existe o no es una carpeta:\n{root}")

        if not root.is_relative_to(self._location_path):
            raise ScanError(
                f"La carpeta no pertenece a la ubicación de almacenamiento:\n{root}"
            )

        if any(root.is_relative_to(excluded) for excluded in self._excluded):
            raise ScanError(
                "La carpeta elegida es (o está dentro de) una carpeta excluida del "
                f"escaneo, como la del propio catálogo:\n{root}"
            )

        # Segunda defensa: la propia carpeta elegida es la de un catálogo
        if self._is_catalog_directory(str(root)):
            raise ScanError(
                f"La carpeta elegida es la de un catálogo, no se puede escanear:\n{root}"
            )
        return root

    def _walk(
        self, root: Path, cancel_event: threading.Event | None
    ) -> Iterator[ScanCandidate]:
        """Recorre el árbol de carpetas sin recursión y entrega los candidatos."""
        stats = self.stats
        follow_symlinks = self._filter.follow_symlinks
        logger.info(f"Iniciando escaneo de: {root}")

        # Protección contra bucles: solo hace falta si se siguen enlaces simbólicos
        # (con la configuración por defecto, el filtro ya los descarta).
        visited_real_paths: set[str] = {os.path.realpath(root)} if follow_symlinks else set()

        # Pila de carpetas pendientes. Sin recursión: un árbol muy profundo no puede
        # provocar un 'RecursionError'.
        pending: list[Path] = [root]

        try:
            while pending:
                if cancel_event is not None and cancel_event.is_set():
                    stats.cancelled = True
                    return

                current = pending.pop()

                # Se lista la carpeta entera de una vez (ordenada por nombre) y se
                # cierra el iterador enseguida: no se dejan carpetas abiertas.
                try:
                    with os.scandir(current) as iterator:
                        entries = sorted(iterator, key=lambda entry: entry.name.lower())
                except OSError as exc:
                    self._add_issue(current, exc)
                    continue
                stats.directories_visited += 1

                # Sidecars .xmp de esta carpeta (nombre en minúsculas -> fecha): se miran
                # aquí, con el listado ya hecho, para no consultar el disco por cada archivo
                sidecars = self._sidecar_mtimes(entries)

                subdirectories: list[Path] = []
                for entry in entries:
                    if cancel_event is not None and cancel_event.is_set():
                        stats.cancelled = True
                        return

                    try:
                        is_directory = entry.is_dir(follow_symlinks=follow_symlinks)
                    except OSError as exc:
                        self._add_issue(Path(entry.path), exc)
                        continue

                    if is_directory:
                        subdirectory = self._accept_directory(
                            entry, visited_real_paths, follow_symlinks
                        )
                        if subdirectory is not None:
                            subdirectories.append(subdirectory)
                        continue

                    candidate = self._build_candidate(entry, sidecars)
                    if candidate is not None:
                        stats.candidates += 1
                        yield candidate

                # Se apilan al revés para que salgan por orden alfabético
                pending.extend(reversed(subdirectories))
        finally:
            # Se ejecuta al terminar, al cancelar o si el consumidor cierra el generador
            logger.info(f"Escaneo terminado:\n{stats.summary()}")

    def _accept_directory(
        self,
        entry: os.DirEntry[str],
        visited_real_paths: set[str],
        follow_symlinks: bool,
    ) -> Path | None:
        """Decide si se entra en una subcarpeta. Devuelve su ruta, o None si se descarta."""
        reason = self._filter.check_directory(entry)
        directory = Path(entry.path)

        # Carpetas excluidas a propósito (la del catálogo activo) o que son la carpeta
        # de algún catálogo: mismo motivo que las del sistema, ya que para el recuento
        # da igual por qué no se entra
        if reason is None and (
            directory in self._excluded or self._is_catalog_directory(entry.path)
        ):
            reason = SkipReason.EXCLUDED_DIRECTORY

        # Bucle de enlaces simbólicos: la carpeta ya se recorrió por otro camino
        if reason is None and follow_symlinks:
            real_path = os.path.realpath(entry.path)
            if real_path in visited_real_paths:
                reason = SkipReason.SYMLINK
            else:
                visited_real_paths.add(real_path)

        if reason is not None:
            self.stats.skipped[reason] += 1
            return None
        return directory

    @staticmethod
    def _is_catalog_directory(directory: str) -> bool:
        """Indica si una carpeta es la de un catálogo (contiene 'catalogo.db').

        Cuesta una sola consulta al disco por carpeta (no por archivo).
        """
        return os.path.isfile(os.path.join(directory, CatalogBuilder.DB_FILENAME))

    def _sidecar_mtimes(self, entries: list[os.DirEntry[str]]) -> dict[str, int]:
        """Fechas de modificación de los '.xmp' de una carpeta (nombre en minúsculas -> ns).

        Solo se consulta el disco por los archivos .xmp (en Windows, ni eso: la fecha
        viene con el listado de la carpeta).
        """
        mtimes: dict[str, int] = {}
        for entry in entries:
            name = entry.name.lower()
            if not name.endswith(".xmp"):
                continue
            try:
                if entry.is_file(follow_symlinks=self._filter.follow_symlinks):
                    info = entry.stat(follow_symlinks=self._filter.follow_symlinks)
                    mtimes[name] = info.st_mtime_ns
            except OSError:
                continue  # si no se puede leer, para el escáner es como si no estuviera
        return mtimes

    def _build_candidate(
        self, entry: os.DirEntry[str], sidecars: dict[str, int] | None = None
    ) -> ScanCandidate | None:
        """Pasa un archivo por el filtro y el detector. None si no hay que catalogarlo."""
        stats = self.stats
        stats.files_seen += 1

        reason = self._filter.check_file(entry)
        if reason is not None:
            stats.skipped[reason] += 1
            return None

        detection = self._detector.detect_with_mime(entry.path)
        extension = os.path.splitext(entry.name)[1].lower().lstrip(".") or None
        if not detection.is_supported:
            stats.unsupported_files += 1
            stats.ignored_extensions[extension or _NO_EXTENSION] += 1
            return None

        try:
            info = entry.stat(follow_symlinks=self._filter.follow_symlinks)
        except OSError as exc:
            # Por ejemplo, el archivo se borró mientras se escaneaba
            self._add_issue(Path(entry.path), exc)
            return None

        # Sidecar: 'IMG_0001.xmp' (Adobe) o 'IMG_0001.CR3.xmp' (otros programas)
        sidecar_mtime_ns: int | None = None
        if sidecars:
            lower = entry.name.lower()
            found = [
                sidecars[name]
                for name in (os.path.splitext(lower)[0] + ".xmp", lower + ".xmp")
                if name in sidecars and name != lower
            ]
            sidecar_mtime_ns = max(found) if found else None

        path = Path(entry.path)
        return ScanCandidate(
            path=path,
            relative_path=make_relative_path(self._location_path, path),
            file_name=entry.name,
            file_extension=extension,
            media_type=detection.media_type,
            mime_type=detection.mime_type,
            file_size=info.st_size,
            file_mtime_ns=info.st_mtime_ns,
            file_created_at=self._creation_date(info),
            sidecar_mtime_ns=sidecar_mtime_ns,
        )

    @staticmethod
    def _creation_date(info: os.stat_result) -> str | None:
        """Fecha de creación en texto UTC, o None si el sistema no la proporciona.

        'st_birthtime' existe en Windows y macOS; en Linux no hay una fecha de
        creación fiable ('st_ctime' es el último cambio de metadatos, no la creación).
        """
        timestamp = getattr(info, "st_birthtime", None)
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC).strftime(_DB_DATE_FORMAT)
        except (OverflowError, OSError, ValueError):
            # Fechas absurdas (corrupción del sistema de archivos, años fuera de rango)
            return None

    def _add_issue(self, path: Path, error: OSError) -> None:
        """Anota un problema real de lectura (formato de 'scan_errors')."""
        try:
            relative = make_relative_path(self._location_path, path) or "."
        except ValueError:
            relative = str(path)
        self.stats.issues.append(ScanIssue(relative, SCAN_STAGE_WALK, str(error)))
        logger.warning(f"No se pudo leer '{path}': {error}")


if __name__ == "__main__":
    # Autoprueba: crea un árbol de carpetas falso y comprueba qué se entrega y qué no.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.folder_scanner
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "Fotos"

        # nombre relativo -> debe entregarse como candidato (True) o no (False)
        files: dict[str, bool] = {
            "IMG_001.JPG": True,
            "libro.epub": True,
            "2024/viaje/clip.mp4": True,
            "2024/viaje/RAW_0001.CR2": True,
            "musica/tema.flac": True,
            "notas.txt": False,  # pasa el filtro, pero no es un medio
            "datos.pdf": False,  # idem (hoy los PDF no se catalogan)
            "sin_extension": False,  # contenido sin firma conocida
            ".DS_Store": False,  # filtro: basura
            "._IMG_001.JPG": False,  # filtro: AppleDouble
            "descarga.mp4.part": False,  # filtro: temporal
            ".git/objects/oculta.jpg": False,  # filtro: carpeta oculta
            "$RECYCLE.BIN/borrada.jpg": False,  # filtro: carpeta del sistema
            "MiCatalogo/cache/photo/0001.jpg": False,  # carpeta del catálogo (excluida)
            "MiCatalogo/catalogo.db": False,
            "OtroCatalogo/catalogo.db": False,  # catálogo ajeno: se detecta por su .db
            "OtroCatalogo/cache/photo/0002.jpg": False,
        }
        for name in files:
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * 10)

        scanner = FolderScanner(base, excluded_directories=[base / "MiCatalogo"])

        # 1. Recorrido completo
        found = list(scanner.scan())
        found_paths = [candidate.relative_path for candidate in found]
        print("Candidatos:", found_paths)
        # Orden estable: primero los archivos de cada carpeta (por nombre, sin
        # distinguir mayúsculas) y después sus subcarpetas
        assert found_paths == [
            "IMG_001.JPG",
            "libro.epub",
            "2024/viaje/clip.mp4",
            "2024/viaje/RAW_0001.CR2",
            "musica/tema.flac",
        ]
        assert set(found_paths) == {name for name, ok in files.items() if ok}
        first = next(c for c in found if c.relative_path == "2024/viaje/clip.mp4")
        assert first.media_type == MediaType.VIDEO and first.file_extension == "mp4"
        assert first.file_size == 10 and first.file_mtime_ns > 0
        assert first.default_title == "clip" and first.path == base / "2024/viaje/clip.mp4"
        assert scanner.stats.candidates == 5
        assert scanner.stats.files_seen == 11  # 8 en la raíz + 2 en viaje + 1 en musica
        assert scanner.stats.skipped[SkipReason.JUNK_NAME] == 2
        assert scanner.stats.skipped[SkipReason.TEMPORARY] == 1
        assert scanner.stats.skipped[SkipReason.HIDDEN] == 1  # .git
        # '$RECYCLE.BIN', 'MiCatalogo' (excluida a propósito) y 'OtroCatalogo' (por su .db)
        assert scanner.stats.skipped[SkipReason.EXCLUDED_DIRECTORY] == 3
        assert scanner.stats.ignored_extensions["txt"] == 1
        assert scanner.stats.ignored_extensions["pdf"] == 1
        assert not scanner.stats.issues and not scanner.stats.cancelled
        print(scanner.stats.summary())

        # 1b. Sin lista de exclusión, las carpetas de catálogo se detectan igualmente
        #     por contener 'catalogo.db' (p. ej. si la ruta del catálogo está escrita
        #     de otra forma y no coincide con la de la lista)
        bare_scanner = FolderScanner(base)
        bare_paths = [c.relative_path for c in bare_scanner.scan()]
        assert bare_paths == found_paths
        assert bare_scanner.stats.skipped[SkipReason.EXCLUDED_DIRECTORY] == 3
        print("Carpetas de catálogo detectadas sin lista de exclusión")

        # 2. Escanear solo una subcarpeta: las rutas relativas siguen siendo respecto
        #    a la ubicación
        sub_paths = [c.relative_path for c in scanner.scan(base / "2024")]
        assert sub_paths == ["2024/viaje/clip.mp4", "2024/viaje/RAW_0001.CR2"]

        # 3. Cancelación: se activa el evento tras el primer candidato
        event = threading.Event()
        generator = scanner.scan(cancel_event=event)
        next(generator)
        event.set()
        assert list(generator) == []
        assert scanner.stats.cancelled
        print("Cancelación correcta")

        # 4. Una carpeta ilegible se anota como problema y el resto sigue
        real_scandir = os.scandir

        def failing_scandir(path):
            if Path(path).name == "musica":
                raise PermissionError(13, "Permiso denegado", str(path))
            return real_scandir(path)

        os.scandir = failing_scandir
        try:
            partial = [c.relative_path for c in scanner.scan()]
        finally:
            os.scandir = real_scandir
        assert "musica/tema.flac" not in partial and "IMG_001.JPG" in partial
        assert [issue.relative_path for issue in scanner.stats.issues] == ["musica"]
        print("Carpeta ilegible anotada:", scanner.stats.issues[0])

        # 5. Rutas no válidas: el error salta al llamar a scan(), sin iterar
        for invalid in (
            base / "no_existe",
            base / "libro.epub",
            base.parent,
            base / "MiCatalogo",
            base / "OtroCatalogo",  # carpeta de catálogo no incluida en la lista
        ):
            try:
                scanner.scan(invalid)
            except ScanError:
                print(f"ScanError correcto: {invalid.name}")
            else:
                raise AssertionError(f"{invalid} debería rechazarse")

        # 6. Bucle de enlaces simbólicos (solo si se siguen): debe terminar
        try:
            os.symlink(base, base / "2024" / "bucle", target_is_directory=True)
        except (OSError, NotImplementedError):
            print("(Se omite la prueba de bucles: no hay permisos para crear enlaces)")
        else:
            default_paths = {c.relative_path for c in scanner.scan()}
            assert not any("bucle" in path for path in default_paths)  # se descarta
            assert scanner.stats.skipped[SkipReason.SYMLINK] == 1

            following = FolderScanner(
                base,
                scan_filter=ScanFilter(follow_symlinks=True),
                excluded_directories=[base / "MiCatalogo"],
            )
            looped = list(following.scan())  # sin protección, no terminaría
            print(f"Con follow_symlinks=True terminó: {len(looped)} candidatos")
            assert len(looped) == 5  # el enlace del bucle no duplica nada

    print("Autoprueba finalizada correctamente.")
