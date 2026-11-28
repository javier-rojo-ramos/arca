"""Mover y renombrar archivos del catálogo en el disco, con el catálogo al día.

Este módulo NO depende de Qt. Las funciones reciben la conexión como primer parámetro;
'execute_file_moves' es un trabajo para 'JobManager.start' (progreso, cancelación y 'commit'
por archivo). Reglas en docs/DECISIONES.md (19/11/2026; docs/PENDIENTE.md, CAT 4).

Renombrar un archivo es moverlo a otro nombre en su misma carpeta: las dos operaciones son
una lista de peticiones ('FileMoveRequest': este elemento, a esta ruta) que siguen el
patrón de «Eliminar»:

    rename_request / move_requests  →  plan_file_moves (lee el catálogo y el disco; no
    cambia nada: qué se hará y qué se omite y por qué, para el aviso)  →  el aviso  →
    execute_file_moves (el trabajo)

El catálogo SIGUE al archivo: el 'id' no cambia, así que la valoración, las palabras clave,
las colecciones y las miniaturas (la caché va por 'id') se conservan. Por cada archivo:

    1. Se apunta en el REGISTRO DE OPERACIONES ('file_operations', migración 5) y se
       confirma, ANTES de tocar el disco.
    2. En el disco: el archivo ('os.rename'), después su '.xmp' si es un RAW (se COPIA si lo
       comparte con otro RAW del mismo nombre, que conserva el suyo) y su entrada del
       '.arca.json' si es de los que guardan ahí sus datos (vídeo, audio, GPX...).
    3. En UNA transacción: la ruta, el nombre y la ubicación del elemento, el título si era
       el nombre del archivo (un título propio no se toca), 'is_missing' a 0 (está donde se
       acaba de dejar), sus errores de lectura... y se borra su nota del registro.
    Si el paso 3 falla, se deshace el 2. Si la aplicación se cierra a mitad, al abrir el
    catálogo 'reconcile_file_operations' mira el disco y termina o descarta lo apuntado.

Reglas (las comprueba el plan y, justo antes de cada archivo, otra vez):
    - Nunca se sobrescribe: si el destino ya existe (en el disco o en el catálogo), ese
      archivo se omite. En macOS y Linux 'os.rename' sustituiría el archivo sin avisar: por
      eso se mira justo antes (queda un margen mínimo, aceptado).
    - Cambiar solo mayúsculas y minúsculas ('img.jpg' → 'IMG.jpg') sí se puede.
    - No cambia la extensión. El nombre nuevo vale en los tres sistemas ('naming.py').
    - Solo con las dos ubicaciones conectadas, con el archivo en el disco y la carpeta de
      destino existente. Mover a otro disco (copiar, comprobar y borrar) llegará en CAT 4.5:
      hoy se omite.
    - Quien lo lanza comprueba antes que no haya trabajos que usen rutas (lectura,
      miniaturas, escritura de datos del usuario, añadir carpeta).

La carpeta de destino se apunta en las carpetas del catálogo ('catalog_folders.py', CAT 5)
con el elemento. La de origen, aunque se quede vacía, sigue en el disco y en el árbol con 0
(como en Lightroom; para borrarla, «Quitar del catálogo...»).

MOVER A UNA CARPETA (CAT 4.4b; soltar tarjetas sobre una carpeta del árbol): 'plan_move'
hace las peticiones y el plan, y además omite lo que no admite la carpeta de destino si se
declaró de una biblioteca («¿Qué contiene esta carpeta?»: fotos no van a una de Música).

CREAR UNA CARPETA (CAT 4.4a; «Nueva carpeta…» del menú de una carpeta del árbol, como en
Lightroom): 'plan_new_folder' comprueba el nombre y que no exista, y planea mover a ella lo
elegido (si se pide: también se puede crear vacía, CAT 5); 'execute_new_folder' la crea
('os.mkdir'), la apunta en las carpetas del catálogo (si no se puede, la vuelve a borrar:
lo que se hace en el disco desde la aplicación tiene que verse en ella) y mueve.
Crearla no se apunta en el registro (si la aplicación se cierra justo después de crearla,
aparece al sincronizar); lo que se mueve, sí.

RENOMBRAR UNA CARPETA (CAT 4.3) es otra operación: un solo 'os.rename' de la carpeta (sus
archivos, sus '.xmp' y su '.arca.json' van dentro: no se tocan uno a uno) y, en una
transacción, las rutas de todo lo que tiene debajo en el catálogo, lo que se dijo en
«¿Qué contiene esta carpeta?», sus errores de lectura y las carpetas apuntadas. También se apunta antes en el
registro (tipo 'folder') y, si el catálogo falla, se deshace. La raíz de una ubicación,
todavía no (cambiaría la ubicación).

    plan = plan_folder_rename(conn, location_id, "2024/Viaje", "Ordesa")    # para el aviso
    result = execute_folder_rename(conn, plan)                              # el trabajo

MOVER UNA CARPETA (CAT 4.4c; arrastrarla a otra del árbol del Catálogo) es lo mismo que
renombrarla, pero a otra carpeta de su MISMA ubicación (o a su raíz) y con su nombre:
'plan_folder_move' hace el plan y el trabajo es 'execute_folder_rename'. Además de las
reglas de renombrar: ni a ella misma ni a una de dentro, ni a la que ya tiene encima, y solo
a una carpeta con su mismo «¿Qué contiene esta carpeta?» (el propio o el heredado: una
carpeta nunca cambia de contenido al moverla; como con los archivos, decidido por el autor).
Si en la de destino ya hay algo con su nombre, no se mueve: nunca se fusionan. Una
declaración propia que en su sitio nuevo es igual a la heredada sobra y se borra.

    plan = plan_folder_move(conn, location_id, "2024/Viaje", "2023")        # → '2023/Viaje'
    result = execute_folder_rename(conn, plan)

Uso:
    request = rename_request(conn, media_id, "Boda")              # o move_requests(...)
    plan = plan_file_moves(conn, [request])                       # para el aviso
    result = execute_file_moves(conn, plan, progress=..., cancel_event=...)   # el trabajo
    reconcile_file_operations(conn)                               # al abrir el catálogo

1.6.2 La entrada del '.arca.json' va con los archivos que la tienen
      ('policy.has_folder_entry'; antes, «su destino es FOLDER_FILE»: hoy, los mismos).
      Preparado para el MP3 partido (MUS 6.2a).
1.6.1 Al mover una carpeta, si al final no se mueve (algo cambió en el disco), la barra
      de estado dice «Movidos: 0», no «Renombrados: 0».
1.6.0 Mover una carpeta a otra de su ubicación (CAT 4.4c): 'plan_folder_move' (el trabajo
      es 'execute_folder_rename'), 'FolderRenamePlan.target_name' y
      'FileMoveResult.moved_to' («Carpeta «Viaje» movida a «2023»»); la declaración propia
      de «¿Qué contiene...?» que sobra en su sitio nuevo se borra.
1.5.0 Las carpetas del catálogo (CAT 5): la de destino se apunta al mover; renombrar una
      cambia también las apuntadas; «Nueva carpeta» se puede crear vacía (sin
      'SKIP_NO_FILES') y se apunta. Las carpetas de origen que se vacían ya no se borran
      (fuera 'MovePlan.empty_folders', 'FileMoveResult.folders_deleted' y 'folders_kept', y
      el parámetro 'trash' de 'execute_file_moves' y 'execute_new_folder').
1.4.1 Una carpeta nueva, siempre con archivos ('SKIP_NO_FILES'): una vacía no se vería
      en el árbol (regla del autor).
1.4.0 Crear una carpeta (CAT 4.4a): 'plan_new_folder', 'execute_new_folder',
      'NewFolderPlan', 'FileMoveResult.created_folder'; 'plan_file_moves(..., new_folders=)'
      (carpetas que se crean antes de mover).
1.3.0 Mover a una carpeta (CAT 4.4b): 'plan_move' (con la biblioteca de destino y las
      carpetas de origen que se quedan vacías, 'MovePlan.empty_folders') y, en
      'execute_file_moves', su borrado con 'trash'; 'FileMoveResult.folders_deleted' y
      'folders_kept'.
1.2.0 Renombrar una carpeta (CAT 4.3): 'plan_folder_rename', 'execute_folder_rename',
      'renamed_folder_path' y su revisión al abrir; 'FileMoveResult.folder'.
1.1.0 'plan_rename': la petición y el plan de renombrar un archivo, de una vez (para
      'execute_async'; CAT 4.2).
1.0.0 Primera versión (CAT 4.1b).

Prueba rápida (desde la raíz del proyecto):
    python -m core.file_ops.moves
"""

__version__ = "1.6.2"
__all__ = [
    "FileMoveRequest",
    "FileMoveResult",
    "FolderRenamePlan",
    "MovePlan",
    "NewFolderPlan",
    "PlannedMove",
    "ReconcileResult",
    "SidecarMove",
    "execute_file_moves",
    "execute_folder_rename",
    "execute_new_folder",
    "move_requests",
    "plan_file_moves",
    "plan_folder_move",
    "plan_folder_rename",
    "plan_move",
    "plan_new_folder",
    "plan_rename",
    "reconcile_file_operations",
    "rename_request",
    "renamed_folder_path",
]

# Librerías estándar
import os
import shutil
import sqlite3
import sys
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.catalog_folders import add_folders
from core.catalog.libraries import (
    ALLOWED_MEDIA_TYPES,
    FOLDER_AUTO,
    LIBRARY_NAMES,
    FolderContentResolver,
    folder_content_name,
)
from core.file_ops.naming import name_problem, rename_keeping_extension, split_extension
from core.jobs.progress import JobProgress
from core.metadata.exiftool_runner import find_sidecars
from core.userdata.editable_fields import default_title
from core.userdata.folder_file import (
    FolderFileError,
    find_entry_key,
    read_folder_file,
    write_folder_file,
)
from core.userdata.policy import UserDataDestination, destination_for, has_folder_entry

# Motivos por los que un archivo se omite (para el aviso y el registro)
SKIP_GONE = "ya no está en el catálogo"
SKIP_OFFLINE = "su disco no está conectado"
SKIP_MISSING = "no está en el disco"
SKIP_SAME = "ya tiene ese nombre"
SKIP_EXTENSION = "no se puede cambiar la extensión"
SKIP_NO_FOLDER = "la carpeta de destino no existe"
SKIP_OTHER_DISK = "está en otro disco (mover entre discos llegará más adelante)"
SKIP_EXISTS = "ya existe un archivo con ese nombre"
SKIP_IN_CATALOG = "ya hay un archivo con ese nombre en el catálogo"
SKIP_DUPLICATE = "otro archivo de la lista va al mismo nombre"
SKIP_SIDECAR_EXISTS = "ya existe un .xmp con ese nombre"
SKIP_LIBRARY = "la carpeta de destino es de «{}»"  # con el nombre de la biblioteca
SKIP_ROOT = "la carpeta raíz de una ubicación aún no se puede renombrar"
SKIP_FOLDER_MISSING = "la carpeta no está en el disco"
SKIP_FOLDER_EXISTS = "ya existe una carpeta con ese nombre"
SKIP_FOLDER_IN_CATALOG = "ya hay archivos del catálogo con esa ruta"
# Al mover una carpeta (CAT 4.4c)
SKIP_MOVE_ROOT = "es la raíz de una ubicación"
SKIP_INTO_ITSELF = "la carpeta de destino es ella misma o está dentro de ella"
SKIP_SAME_PLACE = "ya está en esa carpeta"
SKIP_FOLDER_LIBRARY = "es de «{}» y la carpeta de destino, de «{}»"  # lo que contiene cada una
SKIP_NAME_TAKEN = "en la carpeta de destino ya hay una con ese nombre"

_IGNORE_CASE = sys.platform in ("win32", "darwin")  # sistemas sin distinguir mayúsculas


@dataclass(frozen=True, slots=True)
class FileMoveRequest:
    """Una petición: este elemento del catálogo, a esta ruta.

    Attributes:
        media_id: 'media_items.id'.
        target_location_id: Ubicación de destino ('storage_locations.id').
        target_path: Ruta relativa a esa ubicación, con '/' (con el nombre del archivo).
    """

    media_id: int
    target_location_id: int
    target_path: str


@dataclass(frozen=True, slots=True)
class SidecarMove:
    """Un '.xmp' que acompaña a un RAW: rutas relativas a la ubicación de origen y destino."""

    source_path: str
    target_path: str
    copy: bool = False  # lo comparte con otro RAW del mismo nombre: se copia


@dataclass(frozen=True, slots=True)
class PlannedMove:
    """Un archivo que se va a mover o renombrar (lo calcula 'plan_file_moves')."""

    media_id: int
    source_location_id: int
    source_root: Path
    source_path: str
    target_location_id: int
    target_root: Path
    target_path: str
    title: str | None = None  # el título que tiene ahora
    sidecars: tuple[SidecarMove, ...] = ()
    folder_file: bool = False  # sus datos del usuario van en el '.arca.json'

    @property
    def source(self) -> Path:
        return self.source_root / self.source_path

    @property
    def target(self) -> Path:
        return self.target_root / self.target_path


@dataclass(frozen=True, slots=True)
class MovePlan:
    """Qué se hará con una lista de peticiones.

    Attributes:
        moves: Los archivos que se moverán o renombrarán.
        skipped: Los que se omiten: (ruta de origen o 'id', motivo).
    """

    moves: tuple[PlannedMove, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()

    @property
    def is_rename(self) -> bool:
        """True si todos se quedan en su carpeta (es renombrar, no mover)."""
        return all(
            move.source_location_id == move.target_location_id
            and PurePosixPath(move.source_path).parent == PurePosixPath(move.target_path).parent
            for move in self.moves
        )


@dataclass(slots=True)
class FileMoveResult:
    """Resultado de 'execute_file_moves' (cumple el protocolo 'JobResult').

    Attributes:
        renamed: Si era renombrar (para la frase de la barra de estado).
        moved: Archivos movidos o renombrados.
        moved_ids: Sus 'id' (para que la interfaz ponga al día la cuadrícula).
        skipped: Omitidos, del plan o al ir a moverlos: (ruta, motivo).
        failed: Los que el sistema no dejó mover (abiertos en otro programa...): (ruta, motivo).
        warnings: Problemas menores (un '.xmp' o un '.arca.json' que no se pudo tocar).
        cancelled: Si se paró antes de terminar.
        folder: Al renombrar una carpeta, si se hizo: (ubicación, ruta vieja, ruta nueva).
            La interfaz lo usa para poner al día lo que recuerda por la ruta.
        created_folder: Al crear una carpeta, si se creó: (ubicación, ruta).
        moved_to: Al MOVER una carpeta, si se hizo: el nombre de la de destino (el de la
            ubicación si es su raíz), para la barra de estado. None al renombrarla.
    """

    renamed: bool = False
    moved: int = 0
    moved_ids: list[int] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False
    folder: tuple[int, str, str] | None = None
    created_folder: tuple[int, str] | None = None
    moved_to: str | None = None

    @property
    def has_warnings(self) -> bool:
        return bool(self.skipped or self.failed or self.warnings or self.cancelled)

    def status_text(self) -> str:
        if self.folder is not None:
            old, new = PurePosixPath(self.folder[1]).name, PurePosixPath(self.folder[2]).name
            if self.moved_to is not None:
                return f"Carpeta «{old}» movida a «{self.moved_to}»"
            return f"Carpeta renombrada: «{old}» → «{new}»"
        if self.created_folder is not None:
            text = f"Carpeta creada: «{PurePosixPath(self.created_folder[1]).name}»"
            if self.moved:
                text += f" · movidos: {self.moved}"
        else:
            text = f"{'Renombrados' if self.renamed else 'Movidos'}: {self.moved}"
        if self.skipped:
            text += f" · omitidos: {len(self.skipped)}"
        if self.failed:
            verb = "renombrar" if self.renamed else "mover"
            text += f" · no se pudieron {verb}: {len(self.failed)}"
        if self.cancelled:
            text += " (cancelado)"
        return text


@dataclass(slots=True)
class ReconcileResult:
    """Lo que hizo 'reconcile_file_operations' con lo que quedó a medias.

    Attributes:
        completed: Archivos que se habían movido y ya están al día en el catálogo.
        discarded: Notas descartadas (no se llegó a mover, o el disco no deja decidirlo).
        kept: Notas que se quedan para la próxima vez (disco desconectado).
    """

    completed: int = 0
    discarded: int = 0
    kept: int = 0


# -----------------------------------------------------------------------------
# Peticiones
# -----------------------------------------------------------------------------


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _folder_of(path: str) -> str:
    """La carpeta de una ruta relativa ('' si está en la raíz): '2024/a.jpg' → '2024'."""
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent


def _join(folder: str, name: str) -> str:
    folder = _normalize(folder)
    return f"{folder}/{name}" if folder else name


def rename_request(
    conn: sqlite3.Connection, media_id: int, new_stem: str
) -> FileMoveRequest | None:
    """Petición de renombrar un archivo (en su carpeta, con su extensión). None si no existe."""
    row = conn.execute(
        "SELECT storage_location_id, relative_path, file_name FROM media_items WHERE id = ?",
        (media_id,),
    ).fetchone()
    if row is None:
        return None
    location_id, relative_path, file_name = row
    folder = str(PurePosixPath(relative_path).parent)
    target = _join("" if folder == "." else folder, rename_keeping_extension(file_name, new_stem))
    return FileMoveRequest(media_id, location_id, target)


def move_requests(
    conn: sqlite3.Connection, media_ids: Iterable[int], location_id: int, folder: str
) -> list[FileMoveRequest]:
    """Peticiones de mover varios archivos a una carpeta (con el mismo nombre)."""
    requests = []
    for media_id in dict.fromkeys(media_ids):
        row = conn.execute("SELECT file_name FROM media_items WHERE id = ?", (media_id,))
        found = row.fetchone()
        if found is not None:
            requests.append(FileMoveRequest(media_id, location_id, _join(folder, found[0])))
    return requests


# -----------------------------------------------------------------------------
# Plan
# -----------------------------------------------------------------------------


def _exists_exactly(path: Path) -> bool:
    """True si existe un archivo con ESE nombre, mayúsculas incluidas.

    En Windows y macOS 'IMG.jpg' existe si existe 'img.jpg': para cambiar solo mayúsculas
    hay que mirar el nombre real en la carpeta.
    """
    if not path.exists():
        return False
    if not _IGNORE_CASE:
        return True
    try:
        return path.name in os.listdir(path.parent)
    except OSError:
        return True  # sin poder mirarlo, se da por existente (lo prudente)


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _location(conn: sqlite3.Connection, location_id: int) -> Path | None:
    """Raíz de una ubicación conectada (y que existe), o None."""
    row = conn.execute(
        "SELECT absolute_path, is_online FROM storage_locations WHERE id = ?", (location_id,)
    ).fetchone()
    if row is None or not row[1]:
        return None
    root = Path(row[0])
    return root if root.is_dir() else None


def _shares_sidecar(raw: Path) -> bool:
    """True si en la carpeta hay otro RAW con el mismo nombre base (comparten 'IMG_1.xmp').

    Es la misma regla que 'media_removal._other_raw_with_same_stem'.
    """
    stem = raw.stem.casefold()
    try:
        with os.scandir(raw.parent) as entries:
            for entry in entries:
                if entry.name == raw.name or not entry.is_file():
                    continue
                other = Path(entry.name)
                if (
                    other.stem.casefold() == stem
                    and destination_for(other.suffix) == UserDataDestination.XMP_SIDECAR
                ):
                    return True
    except OSError:
        return True  # sin poder comprobarlo, se copia (lo prudente: el original se queda)
    return False


def _sidecar_moves(raw: Path, source_path: str, target_path: str) -> list[SidecarMove]:
    """Los '.xmp' de un RAW y adónde van.

    'IMG_1.xmp' (Adobe) → 'Boda.xmp'; 'IMG_1.CR3.xmp' (con el nombre completo) → 'Boda.CR3.xmp'.
    """
    source_folder = PurePosixPath(source_path).parent
    target = PurePosixPath(target_path)
    moves = []
    for sidecar in find_sidecars(raw):
        named_after_raw = sidecar.name.casefold() == f"{raw.name}.xmp".casefold()
        suffix = sidecar.suffix  # '.xmp' o '.XMP', como estaba
        new_name = f"{target.name}{suffix}" if named_after_raw else f"{target.stem}{suffix}"
        moves.append(
            SidecarMove(
                str(source_folder / sidecar.name).removeprefix("./"),
                str(target.parent / new_name).removeprefix("./"),
                copy=not named_after_raw and _shares_sidecar(raw),
            )
        )
    return moves


def plan_file_moves(
    conn: sqlite3.Connection,
    requests: Sequence[FileMoveRequest],
    *,
    new_folders: frozenset[tuple[int, str]] = frozenset(),
) -> MovePlan:
    """Decide qué se moverá y qué se omite (y por qué). No cambia nada.

    Lee el catálogo y el disco (poco), así que se llama en segundo plano.

    Args:
        conn: Conexión.
        requests: Las peticiones.
        new_folders: Carpetas (ubicación, ruta) que se crearán antes de mover (CAT 4.4a):
            cuentan como existentes si existe la de encima.
    """
    moves: list[PlannedMove] = []
    skipped: list[tuple[str, str]] = []
    targets: set[tuple[int, str]] = set()
    sidecar_targets: set[tuple[int, str]] = set()
    roots: dict[int, Path | None] = {}
    contents: dict[int, FolderContentResolver] = {}

    def root_of(location_id: int) -> Path | None:
        if location_id not in roots:
            roots[location_id] = _location(conn, location_id)
        return roots[location_id]

    def key(location_id: int, relative: str) -> tuple[int, str]:
        return location_id, relative.casefold() if _IGNORE_CASE else relative

    for request in requests:
        row = conn.execute(
            """SELECT storage_location_id, relative_path, file_name, file_extension, title,
                      is_missing, media_type
                 FROM media_items WHERE id = ?""",
            (request.media_id,),
        ).fetchone()
        if row is None:
            skipped.append((str(request.media_id), SKIP_GONE))
            continue
        location_id, source_path, file_name, extension, title, is_missing, media_type = row
        target_path = _normalize(request.target_path)
        new_name = PurePosixPath(target_path).name
        source_root, target_root = root_of(location_id), root_of(request.target_location_id)

        def skip(reason: str, path: str = source_path) -> None:
            skipped.append((path, reason))

        if (request.target_location_id, target_path) == (location_id, source_path):
            skip(SKIP_SAME)
            continue
        problem = name_problem(new_name)
        if problem:
            skip(problem)
            continue
        if split_extension(new_name)[1].casefold() != split_extension(file_name)[1].casefold():
            skip(SKIP_EXTENSION)
            continue
        if source_root is None or target_root is None:
            skip(SKIP_OFFLINE)
            continue
        target_folder = _folder_of(target_path)
        moving = (request.target_location_id, target_folder) != (
            location_id, _folder_of(source_path)
        )
        if moving:
            # Una carpeta declarada de una biblioteca solo admite sus tipos de archivo
            if request.target_location_id not in contents:
                contents[request.target_location_id] = FolderContentResolver.load(
                    conn, request.target_location_id
                )
            content = contents[request.target_location_id].content_of(target_folder)
            if content != FOLDER_AUTO and media_type not in ALLOWED_MEDIA_TYPES.get(content, ()):
                skip(SKIP_LIBRARY.format(LIBRARY_NAMES.get(content, content)))
                continue
        source, target = source_root / source_path, target_root / target_path
        if is_missing or not source.is_file():
            skip(SKIP_MISSING)
            continue
        creating = (request.target_location_id, target_folder) in new_folders
        folder_dir = target.parent
        if not (folder_dir.is_dir() or (creating and folder_dir.parent.is_dir())):
            skip(SKIP_NO_FOLDER)
            continue
        try:
            existing = folder_dir if folder_dir.is_dir() else folder_dir.parent
            other_disk = source.parent.stat().st_dev != existing.stat().st_dev
        except OSError:
            other_disk = True
        if other_disk:
            skip(SKIP_OTHER_DISK)
            continue
        if _exists_exactly(target) or (target.exists() and not _same_file(source, target)):
            skip(SKIP_EXISTS)
            continue
        in_catalog = conn.execute(
            "SELECT 1 FROM media_items WHERE storage_location_id = ? AND id <> ? AND "
            + ("relative_path = ? COLLATE NOCASE" if _IGNORE_CASE else "relative_path = ?"),
            (request.target_location_id, request.media_id, target_path),
        ).fetchone()
        if in_catalog:
            skip(SKIP_IN_CATALOG)
            continue
        if key(request.target_location_id, target_path) in targets:
            skip(SKIP_DUPLICATE)
            continue

        destination = destination_for(extension or file_name)
        sidecars: list[SidecarMove] = []
        if destination == UserDataDestination.XMP_SIDECAR:
            clash = False
            for sidecar in _sidecar_moves(source, source_path, target_path):
                sidecar_key = key(request.target_location_id, sidecar.target_path)
                if sidecar_key in sidecar_targets:
                    continue  # otro RAW de la lista ya lo deja allí (lo compartían)
                sidecar_source = source_root / sidecar.source_path
                sidecar_target = target_root / sidecar.target_path
                if _exists_exactly(sidecar_target) or (
                    sidecar_target.exists() and not _same_file(sidecar_source, sidecar_target)
                ):
                    clash = True
                    break
                sidecars.append(sidecar)
            if clash:
                skip(SKIP_SIDECAR_EXISTS)
                continue
            sidecar_targets.update(key(request.target_location_id, s.target_path) for s in sidecars)

        targets.add(key(request.target_location_id, target_path))
        moves.append(
            PlannedMove(
                media_id=request.media_id,
                source_location_id=location_id,
                source_root=source_root,
                source_path=source_path,
                target_location_id=request.target_location_id,
                target_root=target_root,
                target_path=target_path,
                title=title,
                sidecars=tuple(sidecars),
                folder_file=has_folder_entry(extension or file_name),
            )
        )
    return MovePlan(tuple(moves), tuple(skipped))


def plan_move(
    conn: sqlite3.Connection, media_ids: Iterable[int], location_id: int, folder: str
) -> MovePlan:
    """El plan de mover archivos a una carpeta (soltarlos en el árbol; CAT 4.4b).

    Es 'plan_file_moves' con las peticiones de 'move_requests', de una vez (para
    'execute_async'). Las carpetas de origen que se vacían se quedan (CAT 5).
    """
    return plan_file_moves(conn, move_requests(conn, media_ids, location_id, folder))


def plan_rename(conn: sqlite3.Connection, media_id: int, new_stem: str) -> MovePlan:
    """El plan de renombrar un archivo (en su carpeta, con su extensión). Ver 'plan_file_moves'."""
    request = rename_request(conn, media_id, new_stem)
    if request is None:
        return MovePlan(skipped=((str(media_id), SKIP_GONE),))
    return plan_file_moves(conn, [request])


# -----------------------------------------------------------------------------
# Ejecución
# -----------------------------------------------------------------------------


def _begin(conn: sqlite3.Connection) -> None:
    """Abre una transacción de escritura (o sigue la que hubiera abierta)."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")


def _record(conn: sqlite3.Connection, batch_id: int, moves: Sequence[PlannedMove]) -> None:
    """Apunta en el registro todo lo que se va a mover, en una transacción."""
    rows: list[tuple[Any, ...]] = []
    for move in moves:
        source, target = move.source_location_id, move.target_location_id
        rows.append(
            (batch_id, "file", move.media_id, source, move.source_path, target, move.target_path)
        )
        for sidecar in move.sidecars:
            kind = "sidecar_copy" if sidecar.copy else "sidecar"
            rows.append(
                (batch_id, kind, move.media_id, source, sidecar.source_path, target,
                 sidecar.target_path)
            )  # fmt: skip
    _begin(conn)
    conn.executemany(
        """INSERT INTO file_operations(batch_id, kind, media_id, source_location_id,
               source_path, target_location_id, target_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()


def _forget(conn: sqlite3.Connection, batch_id: int, media_ids: Iterable[int]) -> None:
    """Borra del registro las notas de esos elementos (lo que no se llegó a hacer)."""
    ids = list(media_ids)
    if not ids:
        return
    conn.executemany(
        "DELETE FROM file_operations WHERE batch_id = ? AND media_id = ?",
        ((batch_id, media_id) for media_id in ids),
    )
    conn.commit()


def _move_folder_file_entry(
    source_dir: Path, source_name: str, target_dir: Path, target_name: str
) -> None:
    """Pasa la entrada de un archivo de un '.arca.json' a otro (o a otro nombre en el mismo).

    Primero se escribe el destino y después el origen: si algo falla a mitad, la entrada
    está en los dos (mejor repetida que perdida). Si el origen ya no la tiene, no hace nada.

    Raises:
        FolderFileError: Si no se pudo leer o escribir alguno de los dos.
    """
    source = read_folder_file(source_dir)
    source_key = find_entry_key(source.items, source_name)
    if source_key is None:
        return
    entry = source.items.pop(source_key)
    if os.path.normcase(source_dir) == os.path.normcase(target_dir):
        source.items[target_name] = entry
        write_folder_file(source)
        return
    target = read_folder_file(target_dir)
    stale = find_entry_key(target.items, target_name)
    if stale is not None:
        target.items.pop(stale)  # de un archivo que ya no está: lo sustituye el que llega
    target.items[target_name] = entry
    write_folder_file(target)
    write_folder_file(source)


def _update_catalog(
    conn: sqlite3.Connection,
    media_id: int,
    source: tuple[int, str],
    target: tuple[int, str],
    title: str | None,
    batch_id: int | None,
) -> None:
    """Pone el catálogo al día y borra la nota del registro, en UNA transacción."""
    old_name = PurePosixPath(source[1]).name
    new_name = PurePosixPath(target[1]).name
    if not title or title == default_title(old_name):
        title = default_title(new_name)  # el nombre del archivo hacía de título
    _begin(conn)
    try:
        conn.execute(
            """UPDATE media_items
                  SET storage_location_id = ?, relative_path = ?, file_name = ?, title = ?,
                      is_missing = 0
                WHERE id = ?""",
            (target[0], target[1], new_name, title, media_id),
        )
        # La carpeta de destino, en las del catálogo (CAT 5), por si no lo estaba
        add_folders(conn, target[0], [_folder_of(target[1])])
        conn.execute(
            "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ?", target
        )
        conn.execute(
            """UPDATE scan_errors SET storage_location_id = ?, relative_path = ?
                WHERE storage_location_id = ? AND relative_path = ?""",
            (*target, *source),
        )
        if batch_id is None:
            conn.execute("DELETE FROM file_operations WHERE media_id = ?", (media_id,))
        else:
            conn.execute(
                "DELETE FROM file_operations WHERE batch_id = ? AND media_id = ?",
                (batch_id, media_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _move_sidecars(move: PlannedMove, result: FileMoveResult) -> list[SidecarMove]:
    """Mueve (o copia) los '.xmp' de un RAW ya movido. Devuelve los que se hicieron."""
    done = []
    for sidecar in move.sidecars:
        source = move.source_root / sidecar.source_path
        target = move.target_root / sidecar.target_path
        if not source.exists():
            continue  # ya no está: nada que llevar
        if _exists_exactly(target) or (target.exists() and not _same_file(source, target)):
            result.warnings.append(f"Ya existe {target}: su .xmp se queda en {source}")
            continue
        try:
            if sidecar.copy:
                shutil.copy2(source, target)
            else:
                os.rename(source, target)
            done.append(sidecar)
        except OSError as exc:
            result.warnings.append(f"No se pudo llevar el .xmp {source}: {exc}")
    return done


def _undo(move: PlannedMove, sidecars: Sequence[SidecarMove], folder_file_moved: bool) -> None:
    """Deshace en el disco lo hecho con un archivo (si el catálogo no se pudo poner al día).

    Raises:
        OSError, FolderFileError: Si no se pudo deshacer (la nota se queda en el registro).
    """
    if folder_file_moved:
        _move_folder_file_entry(
            move.target.parent, move.target.name, move.source.parent, move.source.name
        )
    for sidecar in sidecars:
        target = move.target_root / sidecar.target_path
        if sidecar.copy:
            target.unlink(missing_ok=True)
        else:
            os.rename(target, move.source_root / sidecar.source_path)
    os.rename(move.target, move.source)


def _move_one(
    conn: sqlite3.Connection, move: PlannedMove, batch_id: int, result: FileMoveResult
) -> None:
    """Mueve un archivo (ya apuntado en el registro) y pone el catálogo al día."""
    source, target = move.source, move.target
    # Otra vez justo antes: el disco puede haber cambiado desde el plan
    if not source.is_file():
        result.skipped.append((move.source_path, SKIP_MISSING))
        _forget(conn, batch_id, [move.media_id])
        return
    if _exists_exactly(target) or (target.exists() and not _same_file(source, target)):
        result.skipped.append((move.source_path, SKIP_EXISTS))
        _forget(conn, batch_id, [move.media_id])
        return
    try:
        os.rename(source, target)
    except OSError as exc:
        result.failed.append((str(source), str(exc) or exc.__class__.__name__))
        _forget(conn, batch_id, [move.media_id])
        return

    sidecars = _move_sidecars(move, result)
    folder_file_moved = False
    if move.folder_file:
        try:
            _move_folder_file_entry(source.parent, source.name, target.parent, target.name)
            folder_file_moved = True
        except FolderFileError as exc:
            result.warnings.append(f"No se pudo actualizar el archivo de carpeta: {exc}")

    try:
        _update_catalog(
            conn,
            move.media_id,
            (move.source_location_id, move.source_path),
            (move.target_location_id, move.target_path),
            move.title,
            batch_id,
        )
    except sqlite3.Error as exc:
        logger.error(f"No se pudo poner al día el catálogo tras mover {source}: {exc}")
        try:
            _undo(move, sidecars, folder_file_moved)
        except (OSError, FolderFileError) as undo_error:
            # La nota se queda: al abrir el catálogo se terminará
            result.failed.append((str(source), f"{exc}; no se pudo deshacer: {undo_error}"))
            return
        _forget(conn, batch_id, [move.media_id])
        result.failed.append((str(source), str(exc)))
        return
    result.moved += 1
    result.moved_ids.append(move.media_id)


def execute_file_moves(
    conn: sqlite3.Connection,
    plan: MovePlan,
    *,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> FileMoveResult:
    """Mueve o renombra los archivos del plan (un trabajo para 'JobManager.start').

    Ver la cabecera del módulo para las reglas. No lanza excepciones por un archivo: lo que
    falla se anota en el resultado y el resto sigue.
    """
    result = FileMoveResult(renamed=plan.is_rename, skipped=list(plan.skipped))
    total = len(plan.moves)
    if progress:
        progress(JobProgress(0, total))
    if not total:
        return result

    batch_id = conn.execute("SELECT COALESCE(MAX(batch_id), 0) + 1 FROM file_operations")
    batch_id = int(batch_id.fetchone()[0])
    _record(conn, batch_id, plan.moves)

    done = 0
    try:
        for move in plan.moves:
            if cancel_event is not None and cancel_event.is_set():
                result.cancelled = True
                break
            try:
                _move_one(conn, move, batch_id, result)
            except Exception as exc:  # noqa: BLE001 - un archivo no debe parar a los demás
                logger.opt(exception=True).error(f"Error inesperado moviendo {move.source}")
                result.failed.append((str(move.source), str(exc)))
            done += 1
            if progress:
                progress(JobProgress(done, total))
    finally:
        # Lo que no se llegó a intentar (cancelado) sale del registro: no se tocó
        _forget(conn, batch_id, [move.media_id for move in plan.moves[done:]])

    logger.info(f"Mover o renombrar archivos: {result.status_text()}")
    for path, reason in result.skipped:
        logger.info(f"Omitido {path}: {reason}")
    for path, reason in result.failed:
        logger.warning(f"No se pudo mover {path}: {reason}")
    for warning in result.warnings:
        logger.warning(warning)
    return result


# -----------------------------------------------------------------------------
# Renombrar una carpeta
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FolderRenamePlan:
    """Lo que hay que saber antes de renombrar o mover una carpeta (lo calculan
    'plan_folder_rename' y 'plan_folder_move'; el trabajo, para los dos, es
    'execute_folder_rename').

    Attributes:
        location_id: Su ubicación.
        source_path: La carpeta, relativa a la ubicación, con '/'.
        target_path: Dónde queda: con el nombre nuevo o dentro de la carpeta de destino.
        root: Raíz de la ubicación (None si no está conectada).
        count: Elementos del catálogo dentro de ella (con sus subcarpetas), para el aviso.
        problem: Por qué no se puede (None si se puede).
        target_name: Al moverla, el nombre de la carpeta de destino (el de la ubicación si es
            su raíz), para los textos; '' al renombrarla.
    """

    location_id: int
    source_path: str
    target_path: str
    root: Path | None = None
    count: int = 0
    problem: str | None = None
    target_name: str = ""


def renamed_folder_path(path: str, old: str, new: str) -> str | None:
    """La ruta 'path' después de renombrar la carpeta 'old' a 'new' (None si no está dentro).

    'old' misma o algo de debajo: '2024/Viaje' → '2024/Ordesa', '2024/Viaje/Día 1' →
    '2024/Ordesa/Día 1'; '2024/Viajes' no está dentro de '2024/Viaje'.
    """
    if path == old:
        return new
    if old and path.startswith(old + "/"):
        return new + path[len(old) :]
    return None


def _items_under(conn: sqlite3.Connection, location_id: int, folder: str) -> int:
    """Elementos del catálogo dentro de una carpeta (con sus subcarpetas)."""
    row = conn.execute(
        "SELECT COUNT(*) FROM media_items WHERE storage_location_id = ? "
        "AND relative_path >= ? AND relative_path < ?",
        (location_id, f"{folder}/", f"{folder}0"),
    ).fetchone()
    return int(row[0])


def plan_folder_rename(
    conn: sqlite3.Connection, location_id: int, folder: str, new_name: str
) -> FolderRenamePlan:
    """Decide si una carpeta se puede renombrar y cuántos elementos tiene. No cambia nada.

    Los motivos van en este orden, así que con el nombre que ya tiene ('SKIP_SAME') sirve
    también para saber, antes de preguntar el nombre nuevo, si se podrá renombrar.
    """
    source = _normalize(folder)
    parent = str(PurePosixPath(source).parent) if source else ""
    target = _join("" if parent == "." else parent, new_name)

    def plan(problem: str | None, root: Path | None = None, count: int = 0) -> FolderRenamePlan:
        return FolderRenamePlan(location_id, source, target, root, count, problem)

    if not source:
        return plan(SKIP_ROOT)
    root = _location(conn, location_id)
    if root is None:
        return plan(SKIP_OFFLINE)
    count = _items_under(conn, location_id, source)
    if not (root / source).is_dir() or not _exists_exactly(root / source):
        return plan(SKIP_FOLDER_MISSING, root, count)
    if target == source:
        return plan(SKIP_SAME, root, count)
    problem = name_problem(new_name)
    if problem:
        return plan(problem, root, count)
    source_dir, target_dir = root / source, root / target
    if _exists_exactly(target_dir) or (
        target_dir.exists() and not _same_file(source_dir, target_dir)
    ):
        return plan(SKIP_FOLDER_EXISTS, root, count)
    if _items_under(conn, location_id, target):
        return plan(SKIP_FOLDER_IN_CATALOG, root, count)
    return plan(None, root, count)


def _same_path(first: str, second: str) -> bool:
    """True si dos rutas relativas son la misma carpeta (sin mayúsculas en Windows y macOS)."""
    if _IGNORE_CASE:
        return first.casefold() == second.casefold()
    return first == second


def _is_within(path: str, folder: str) -> bool:
    """True si 'path' es 'folder' o está dentro de ella (rutas relativas, con '/')."""
    if _IGNORE_CASE:
        path, folder = path.casefold(), folder.casefold()
    return path == folder or path.startswith(folder + "/")


def plan_folder_move(
    conn: sqlite3.Connection, location_id: int, folder: str, target_folder: str
) -> FolderRenamePlan:
    """Decide si una carpeta se puede mover a otra de su ubicación (CAT 4.4c). No cambia nada.

    Lee el catálogo y el disco (poco), así que se llama en segundo plano. El trabajo es
    'execute_folder_rename'. Reglas en la cabecera del módulo.

    Args:
        conn: Conexión.
        location_id: La ubicación de las dos carpetas.
        folder: La carpeta que se mueve, relativa a la ubicación.
        target_folder: La carpeta a la que va ('' = la raíz de la ubicación).
    """
    source = _normalize(folder)
    destination = _normalize(target_folder)
    target = _join(destination, PurePosixPath(source).name) if source else destination

    def plan(
        problem: str | None, root: Path | None = None, count: int = 0, target_name: str = ""
    ) -> FolderRenamePlan:
        return FolderRenamePlan(location_id, source, target, root, count, problem, target_name)

    if not source:
        return plan(SKIP_MOVE_ROOT)
    root = _location(conn, location_id)
    if root is None:
        return plan(SKIP_OFFLINE)
    count = _items_under(conn, location_id, source)
    source_dir, destination_dir, target_dir = root / source, root / destination, root / target
    if not source_dir.is_dir() or not _exists_exactly(source_dir):
        return plan(SKIP_FOLDER_MISSING, root, count)
    if _is_within(destination, source):
        return plan(SKIP_INTO_ITSELF, root, count)
    if _same_path(destination, _folder_of(source)):
        return plan(SKIP_SAME_PLACE, root, count)
    if not destination_dir.is_dir():
        return plan(SKIP_NO_FOLDER, root, count)
    try:
        # Una carpeta de la ubicación puede ser un punto de montaje de otro disco
        other_disk = source_dir.stat().st_dev != destination_dir.stat().st_dev
    except OSError:
        other_disk = True
    if other_disk:
        return plan(SKIP_OTHER_DISK, root, count)
    # Lo que contiene (propio o heredado), igual en las dos: no cambia al moverla
    resolver = FolderContentResolver.load(conn, location_id)
    now, there = resolver.content_of(source), resolver.content_of(destination)
    if now != there:
        problem = SKIP_FOLDER_LIBRARY.format(folder_content_name(now), folder_content_name(there))
        return plan(problem, root, count)
    if target_dir.exists() or _exists_exactly(target_dir):
        return plan(SKIP_NAME_TAKEN, root, count)
    if _items_under(conn, location_id, target):
        return plan(SKIP_FOLDER_IN_CATALOG, root, count)
    if destination:
        target_name = PurePosixPath(destination).name
    else:
        row = conn.execute(
            "SELECT name FROM storage_locations WHERE id = ?", (location_id,)
        ).fetchone()
        target_name = str(row[0] or root) if row else str(root)
    return plan(None, root, count, target_name)


def _update_catalog_folder(
    conn: sqlite3.Connection, location_id: int, source: str, target: str, operation_id: int | None
) -> None:
    """Cambia la carpeta en el catálogo (rutas, «¿Qué contiene...?», errores, carpetas
    apuntadas) y borra la nota.

    En UNA transacción. Lo que hubiera ya con la ruta nueva en «¿Qué contiene...?», en los
    errores y en las carpetas apuntadas es de una carpeta que ya no existe (se ha comprobado
    que no hay elementos): se borra antes, para que no choque.
    """
    shift = len(source) + 1  # 'substr' empieza a contar en 1: desde la '/' que sigue
    under_source = (location_id, source, f"{source}/", f"{source}0")
    under_target = (location_id, target, f"{target}/", f"{target}0")
    _begin(conn)
    try:
        conn.execute(
            """UPDATE media_items SET relative_path = ? || substr(relative_path, ?)
                WHERE storage_location_id = ? AND relative_path >= ? AND relative_path < ?""",
            (target, shift, location_id, f"{source}/", f"{source}0"),
        )
        tables = (
            ("folder_libraries", "folder"),
            ("scan_errors", "relative_path"),
            ("folders", "relative_path"),
        )
        for table, column in tables:
            where = (
                f"storage_location_id = ? AND ({column} = ? OR ({column} >= ? AND {column} < ?))"
            )
            conn.execute(f"DELETE FROM {table} WHERE {where}", under_target)
            conn.execute(
                f"UPDATE {table} SET {column} = ? || substr({column}, ?) WHERE {where}",
                (target, shift, *under_source),
            )
        # Movida (CAT 4.4c), su declaración propia puede ser ya la que hereda: sobra (como en
        # 'set_folder_content', la tabla solo tiene lo necesario). Al renombrarla, nunca
        resolver = FolderContentResolver.load(conn, location_id)
        conn.execute(
            "DELETE FROM folder_libraries "
            "WHERE storage_location_id = ? AND folder = ? AND content = ?",
            (location_id, target, resolver.inherited_content(target)),
        )
        add_folders(conn, location_id, [target])  # por si no estaba apuntada
        if operation_id is not None:
            conn.execute("DELETE FROM file_operations WHERE id = ?", (operation_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def execute_folder_rename(
    conn: sqlite3.Connection,
    plan: FolderRenamePlan,
    *,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> FileMoveResult:
    """Renombra o mueve una carpeta en el disco y en el catálogo (un trabajo para
    'JobManager.start'; el plan, de 'plan_folder_rename' o de 'plan_folder_move').

    Ver la cabecera del módulo. No lanza excepciones: lo que falla va en el resultado.
    'cancel_event' no se usa (es un solo paso), pero el trabajo lo recibe como los demás.
    """
    # Moverla (CAT 4.4c) es renombrarla con otra carpeta encima: para los textos
    moving = _folder_of(plan.source_path) != _folder_of(plan.target_path)
    result = FileMoveResult(renamed=not moving)
    if plan.problem is not None or plan.root is None:
        result.skipped.append((plan.source_path, plan.problem or SKIP_OFFLINE))
        return result
    if progress:
        progress(JobProgress(0, 1))
    source, target = plan.root / plan.source_path, plan.root / plan.target_path

    batch = conn.execute("SELECT COALESCE(MAX(batch_id), 0) + 1 FROM file_operations")
    batch_id = int(batch.fetchone()[0])
    _begin(conn)
    cursor = conn.execute(
        """INSERT INTO file_operations(batch_id, kind, source_location_id, source_path,
               target_location_id, target_path)
           VALUES (?, 'folder', ?, ?, ?, ?)""",
        (batch_id, plan.location_id, plan.source_path, plan.location_id, plan.target_path),
    )
    operation_id = int(cursor.lastrowid)
    conn.commit()

    def forget() -> None:
        conn.execute("DELETE FROM file_operations WHERE id = ?", (operation_id,))
        conn.commit()

    # Otra vez justo antes: el disco puede haber cambiado desde el plan
    if not _exists_exactly(source):
        result.skipped.append((plan.source_path, SKIP_FOLDER_MISSING))
        forget()
        return result
    if _exists_exactly(target) or (target.exists() and not _same_file(source, target)):
        result.skipped.append((plan.source_path, SKIP_FOLDER_EXISTS))
        forget()
        return result
    try:
        os.rename(source, target)
    except OSError as exc:
        result.failed.append((str(source), str(exc) or exc.__class__.__name__))
        forget()
        return result
    try:
        _update_catalog_folder(
            conn, plan.location_id, plan.source_path, plan.target_path, operation_id
        )
    except sqlite3.Error as exc:
        logger.error(f"No se pudo poner al día el catálogo tras renombrar {source}: {exc}")
        try:
            os.rename(target, source)
        except OSError as undo_error:
            # La nota se queda: al abrir el catálogo se terminará
            result.failed.append((str(source), f"{exc}; no se pudo deshacer: {undo_error}"))
            return result
        forget()
        result.failed.append((str(source), str(exc)))
        return result
    result.moved = plan.count
    result.folder = (plan.location_id, plan.source_path, plan.target_path)
    if moving:
        result.moved_to = plan.target_name
    if progress:
        progress(JobProgress(1, 1))
    verb = "movida" if moving else "renombrada"
    logger.info(f"Carpeta {verb}: {source} → {target} ({plan.count} elementos)")
    return result


# -----------------------------------------------------------------------------
# Crear una carpeta
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NewFolderPlan:
    """Lo que hay que saber antes de crear una carpeta (lo calcula 'plan_new_folder').

    Attributes:
        location_id: Su ubicación.
        parent_path: La carpeta en la que se crea ('' = la raíz de la ubicación).
        folder_path: La carpeta nueva, relativa a la ubicación.
        root: Raíz de la ubicación (None si no está conectada).
        problem: Por qué no se puede (None si se puede).
        moves: Lo elegido que se moverá a ella (vacío si se crea vacía).
    """

    location_id: int
    parent_path: str
    folder_path: str
    root: Path | None = None
    problem: str | None = None
    moves: MovePlan = MovePlan()


def plan_new_folder(
    conn: sqlite3.Connection,
    location_id: int,
    parent: str,
    name: str,
    media_ids: Iterable[int] = (),
) -> NewFolderPlan:
    """Comprueba si se puede crear la carpeta y planea mover a ella lo elegido. No cambia nada.

    Args:
        conn: Conexión.
        location_id: La ubicación.
        parent: La carpeta en la que se crea ('' = la raíz).
        name: El nombre de la carpeta nueva.
        media_ids: Lo que se moverá a ella (sin nada, se crea vacía: se verá en el árbol con
            0, CAT 5).
    """
    parent = _normalize(parent)
    folder = _join(parent, name)

    def plan(problem: str | None, root: Path | None = None) -> NewFolderPlan:
        return NewFolderPlan(location_id, parent, folder, root, problem)

    root = _location(conn, location_id)
    if root is None:
        return plan(SKIP_OFFLINE)
    if not (root / parent).is_dir():
        return plan(SKIP_FOLDER_MISSING, root)
    problem = name_problem(name)
    if problem:
        return plan(problem, root)
    target = root / folder
    if target.exists():
        return plan(SKIP_FOLDER_EXISTS, root)
    if _items_under(conn, location_id, folder):
        return plan(SKIP_FOLDER_IN_CATALOG, root)
    ids = list(media_ids)
    if not ids:
        return plan(None, root)  # vacía
    moves = plan_file_moves(
        conn,
        move_requests(conn, ids, location_id, folder),
        new_folders=frozenset({(location_id, folder)}),
    )
    return NewFolderPlan(location_id, parent, folder, root, None, moves)


def execute_new_folder(
    conn: sqlite3.Connection,
    plan: NewFolderPlan,
    *,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> FileMoveResult:
    """Crea la carpeta, la apunta en el catálogo y mueve a ella lo elegido (un trabajo).

    Para 'JobManager.start'. Si no se puede apuntar en el catálogo, se vuelve a borrar del
    disco (no se vería en el árbol). Si lo elegido no se puede mover (o falla), la carpeta
    se queda, vacía: se ve en el árbol con 0. No lanza excepciones.
    """
    if plan.problem is not None or plan.root is None:
        result = FileMoveResult()
        result.skipped.append((plan.folder_path, plan.problem or SKIP_OFFLINE))
        return result
    folder = plan.root / plan.folder_path
    try:
        os.mkdir(folder)
    except FileExistsError:
        result = FileMoveResult()
        result.skipped.append((plan.folder_path, SKIP_FOLDER_EXISTS))
        return result
    except OSError as exc:
        result = FileMoveResult()
        result.failed.append((str(folder), str(exc) or exc.__class__.__name__))
        return result
    # En las carpetas del catálogo: sin ella no se vería en el árbol
    try:
        _begin(conn)
        add_folders(conn, plan.location_id, [plan.folder_path])
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        logger.error(f"No se pudo apuntar en el catálogo la carpeta nueva {folder}: {exc}")
        try:
            os.rmdir(folder)
        except OSError as undo_error:
            logger.warning(f"No se pudo volver a borrar {folder}: {undo_error}")
        result = FileMoveResult()
        result.failed.append((str(folder), str(exc)))
        return result
    logger.info(f"Carpeta creada: {folder}")

    if plan.moves.moves:
        result = execute_file_moves(
            conn, plan.moves, progress=progress, cancel_event=cancel_event
        )
    else:
        result = FileMoveResult(skipped=list(plan.moves.skipped))
        if progress:
            progress(JobProgress(1, 1))
    result.created_folder = (plan.location_id, plan.folder_path)
    return result


# -----------------------------------------------------------------------------
# Al abrir el catálogo: terminar o descartar lo que quedó a medias
# -----------------------------------------------------------------------------


def reconcile_file_operations(conn: sqlite3.Connection) -> ReconcileResult:
    """Termina o descarta las operaciones que quedaron a medias (la aplicación se cerró).

    Para cada archivo apuntado se mira el disco: si está en el destino y no en el origen,
    se movió y el catálogo no llegó a enterarse (se lleva su '.xmp' y su entrada del
    '.arca.json' si aún no están, y se pone el catálogo al día); si está en el origen y no
    en el destino, no se llegó a mover (se descarta la nota); si está en los dos o en
    ninguno, no se toca nada (se descarta, con un aviso en el registro: al sincronizar se
    verá como ausente o nuevo). Con un disco desconectado, la nota se queda para otra vez.

    Hace 'commit'. Se llama al abrir el catálogo, antes de que nadie lo use.
    """
    result = ReconcileResult()
    rows = conn.execute(
        """SELECT id, batch_id, kind, media_id, source_location_id, source_path,
                  target_location_id, target_path
             FROM file_operations ORDER BY batch_id, media_id, id"""
    ).fetchall()
    if not rows:
        return result

    groups: dict[tuple[int, int | None], list[tuple]] = {}
    for row in rows:
        groups.setdefault((row[1], row[3]), []).append(row)

    for (batch_id, media_id), group in groups.items():
        if media_id is None:
            for row in group:
                _reconcile_folder(conn, row, result)
            continue
        files = [row for row in group if row[2] == "file"]
        if len(files) != 1:
            logger.warning(f"Registro de operaciones: nota que no se sabe terminar: {group}")
            result.kept += len(group)
            continue
        source_location, source_path, target_location, target_path = files[0][4:8]
        source_root = _location(conn, source_location)
        target_root = _location(conn, target_location)
        if source_root is None or target_root is None:
            result.kept += len(group)
            continue
        source, target = source_root / source_path, target_root / target_path
        moved = _exists_exactly(target) and not _exists_exactly(source)
        not_moved = _exists_exactly(source) and not _exists_exactly(target)
        ids = [row[0] for row in group]
        if not moved:
            if not not_moved:
                logger.warning(
                    f"Registro de operaciones: no se puede saber si {source} se movió a "
                    f"{target} (están los dos, o ninguno): se deja como está"
                )
            conn.executemany("DELETE FROM file_operations WHERE id = ?", ((i,) for i in ids))
            conn.commit()
            result.discarded += len(group)
            continue

        # Se movió: lo que falte de su '.xmp' y de su entrada del '.arca.json', y el catálogo
        for row in group:
            if row[2] not in ("sidecar", "sidecar_copy"):
                continue
            sidecar_source, sidecar_target = source_root / row[5], target_root / row[7]
            if _exists_exactly(sidecar_source) and not _exists_exactly(sidecar_target):
                try:
                    if row[2] == "sidecar_copy":
                        shutil.copy2(sidecar_source, sidecar_target)
                    else:
                        os.rename(sidecar_source, sidecar_target)
                except OSError as exc:
                    logger.warning(
                        f"Registro de operaciones: no se pudo llevar {sidecar_source}: {exc}"
                    )
        item = conn.execute(
            "SELECT file_extension, file_name, title FROM media_items WHERE id = ?", (media_id,)
        ).fetchone()
        if item is None:
            continue  # el elemento ya no está (sus notas se fueron en cascada)
        extension, file_name, title = item
        if has_folder_entry(extension or file_name):
            try:
                _move_folder_file_entry(source.parent, source.name, target.parent, target.name)
            except FolderFileError as exc:
                logger.warning(f"Registro de operaciones: archivo de carpeta: {exc}")
        _update_catalog(
            conn, media_id, (source_location, source_path), (target_location, target_path),
            title, batch_id,
        )  # fmt: skip
        result.completed += 1
        logger.info(f"Registro de operaciones: terminado {source} → {target}")
    return result



def _reconcile_folder(conn: sqlite3.Connection, row: tuple, result: ReconcileResult) -> None:
    """Termina o descarta un renombrado de carpeta que quedó a medias (ver la de arriba)."""
    operation_id, kind, location_id, source_path, target_path = (
        row[0], row[2], row[4], row[5], row[7]
    )  # fmt: skip
    if kind != "folder":
        logger.warning(f"Registro de operaciones: nota que no se sabe terminar: {row}")
        result.kept += 1
        return
    root = _location(conn, location_id)
    if root is None:
        result.kept += 1
        return
    source, target = root / source_path, root / target_path
    if _exists_exactly(target) and not _exists_exactly(source):
        _update_catalog_folder(conn, location_id, source_path, target_path, operation_id)
        result.completed += 1
        logger.info(f"Registro de operaciones: terminado {source} → {target}")
        return
    if not (_exists_exactly(source) and not _exists_exactly(target)):
        logger.warning(
            f"Registro de operaciones: no se puede saber si la carpeta {source} se renombró a "
            f"{target} (están las dos, o ninguna): se deja como está"
        )
    conn.execute("DELETE FROM file_operations WHERE id = ?", (operation_id,))
    conn.commit()
    result.discarded += 1

if __name__ == "__main__":
    # Autoprueba con carpetas temporales y un catálogo en memoria (sin ExifTool ni Qt).
    # Ejecutar desde la raíz del proyecto:  python -m core.file_ops.moves
    import tempfile

    from core.catalog.catalog_folders import folders_under
    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.userdata.folder_file import FolderData

    logger.remove()  # solo el resultado de la prueba
    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Fotos"
        root.mkdir()
        db.execute(
            "INSERT INTO storage_locations(id, name, absolute_path) VALUES (1, 'F', ?)", (str(root),)
        )
        db.execute(
            "INSERT INTO storage_locations(id, name, absolute_path, is_online) "
            "VALUES (2, 'X', ?, 0)",
            (str(Path(tmp) / "Desconectado"),),
        )

        def add(
            relative: str, *, title: str | None = None, missing: int = 0, create: bool = True
        ) -> int:
            """Crea el archivo (si procede) y su fila; el título, por defecto, su nombre."""
            if create:
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes(b"x")
            name = PurePosixPath(relative).name
            cursor = db.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       file_extension, media_type, mime_type, file_size, file_mtime_ns, title,
                       is_missing)
                   VALUES (1, ?, ?, ?, 'photo', 'x', 1, 0, ?, ?)""",
                (relative, name, split_extension(name)[1].lstrip(".").lower(),
                 title or default_title(name), missing),
            )  # fmt: skip
            db.commit()
            return int(cursor.lastrowid)

        def item(media_id: int) -> tuple:
            return db.execute(
                "SELECT relative_path, file_name, title, is_missing FROM media_items WHERE id = ?",
                (media_id,),
            ).fetchone()

        def journal() -> int:
            return db.execute("SELECT COUNT(*) FROM file_operations").fetchone()[0]

        # ---- 1. Peticiones ----
        photo = add("2024/IMG_1.jpg")
        assert rename_request(db, photo, "Boda") == FileMoveRequest(photo, 1, "2024/Boda.jpg")
        loose = add("suelta.jpg")
        assert rename_request(db, loose, "Otra") == FileMoveRequest(loose, 1, "Otra.jpg")
        assert rename_request(db, 999, "x") is None
        assert plan_rename(db, 999, "x").skipped == (("999", SKIP_GONE),)
        assert move_requests(db, [photo, loose, photo], 1, "Destino") == [
            FileMoveRequest(photo, 1, "Destino/IMG_1.jpg"),
            FileMoveRequest(loose, 1, "Destino/suelta.jpg"),
        ]
        print("1. Peticiones de renombrar y mover")

        # ---- 2. El plan: lo que se omite y por qué ----
        add("2024/ocupado.jpg")
        absent = add("2024/ausente.jpg", missing=1, create=False)
        add("2024/en_catalogo.jpg", missing=1, create=False)  # ausente con ese nombre
        offline = int(db.execute(
            """INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
                   mime_type, file_size, file_mtime_ns, title)
               VALUES (2, 'd.jpg', 'd.jpg', 'photo', 'x', 1, 0, 'd')"""
        ).lastrowid)  # fmt: skip
        db.commit()
        cases = {
            "mismo": (FileMoveRequest(photo, 1, "2024/IMG_1.jpg"), SKIP_SAME),
            "nombre": (FileMoveRequest(photo, 1, "2024/con:dos.jpg"), "caracteres"),
            "extension": (FileMoveRequest(photo, 1, "2024/IMG_1.png"), SKIP_EXTENSION),
            "ausente": (FileMoveRequest(absent, 1, "2024/vuelve.jpg"), SKIP_MISSING),
            "desconectado": (FileMoveRequest(offline, 2, "e.jpg"), SKIP_OFFLINE),
            "existe": (FileMoveRequest(photo, 1, "2024/ocupado.jpg"), SKIP_EXISTS),
            "catalogo": (FileMoveRequest(photo, 1, "2024/en_catalogo.jpg"), SKIP_IN_CATALOG),
            "carpeta": (FileMoveRequest(photo, 1, "NoExiste/IMG_1.jpg"), SKIP_NO_FOLDER),
            "borrado": (FileMoveRequest(999, 1, "x.jpg"), SKIP_GONE),
        }
        for name, (request, reason) in cases.items():
            plan = plan_file_moves(db, [request])
            assert not plan.moves and reason in plan.skipped[0][1], (name, plan)
        plan = plan_file_moves(
            db, [FileMoveRequest(photo, 1, "2024/A.jpg"), FileMoveRequest(loose, 1, "2024/a.jpg")]
        )
        if _IGNORE_CASE:  # en Windows y macOS, 'A.jpg' y 'a.jpg' son el mismo nombre
            assert len(plan.moves) == 1 and plan.skipped[0][1] == SKIP_DUPLICATE, plan
        print(f"2. Plan: {len(cases)} motivos para omitir, cada uno con su texto")

        # ---- 3. Renombrar una foto: disco, catálogo (título y errores) y registro ----
        own = add("2024/propio.jpg", title="Atardecer en Ordesa")
        db.execute("INSERT INTO collections(id, kind, name) VALUES (1, 'static', 'C')")
        db.execute("INSERT INTO collection_items(collection_id, media_id) VALUES (1, ?)", (photo,))
        db.execute(
            "INSERT INTO scan_errors(storage_location_id, relative_path, stage, message) "
            "VALUES (1, '2024/IMG_1.jpg', 'metadata', 'x')"
        )
        db.commit()
        plan = plan_file_moves(
            db, [rename_request(db, photo, "Boda"), rename_request(db, own, "Ordesa")]
        )
        assert plan.is_rename and len(plan.moves) == 2
        steps: list[JobProgress] = []
        result = execute_file_moves(db, plan, progress=steps.append)
        assert result.moved == 2 and not result.has_warnings, result
        assert result.status_text() == "Renombrados: 2" and steps[-1] == JobProgress(2, 2)
        assert (root / "2024/Boda.jpg").is_file() and not (root / "2024/IMG_1.jpg").exists()
        assert item(photo) == ("2024/Boda.jpg", "Boda.jpg", "Boda", 0), item(photo)
        assert item(own)[2] == "Atardecer en Ordesa"  # un título propio no se toca
        assert db.execute("SELECT media_id FROM collection_items").fetchone() == (photo,)
        assert db.execute("SELECT relative_path FROM scan_errors").fetchone() == ("2024/Boda.jpg",)
        assert journal() == 0
        print("3. Renombrar: archivo, ruta, nombre, título (si era el nombre) y errores")

        # ---- 4. RAW con su .xmp; .xmp compartido (se copia); .xmp con el nombre completo ----
        nef = add("Raw/DSC_1.NEF")
        (root / "Raw/DSC_1.xmp").write_text("a")
        cr2 = add("Raw/IMG_1.CR2")
        add("Raw/IMG_1.CR3")
        (root / "Raw/IMG_1.xmp").write_text("compartido")
        cr3full = add("Raw/X.CR3")
        (root / "Raw/X.CR3.xmp").write_text("b")
        requests = [rename_request(db, nef, "Boda_1"), rename_request(db, cr2, "Boda_2"),
                    rename_request(db, cr3full, "Boda_3")]  # fmt: skip
        result = execute_file_moves(db, plan_file_moves(db, requests))
        assert result.moved == 3 and not result.warnings, result
        names = sorted(path.name for path in (root / "Raw").iterdir())
        assert names == ["Boda_1.NEF", "Boda_1.xmp", "Boda_2.CR2", "Boda_2.xmp", "Boda_3.CR3",
                         "Boda_3.CR3.xmp", "IMG_1.CR3", "IMG_1.xmp"], names  # fmt: skip
        assert (root / "Raw/Boda_2.xmp").read_text() == "compartido"  # copia; el original sigue
        print("4. RAW: su .xmp va con él; el compartido se copia")

        # ---- 5. Vídeo: su entrada del .arca.json cambia de nombre y, al mover, de archivo ----
        clip = add("Videos/clip.mov")
        db.execute("UPDATE media_items SET media_type = 'video' WHERE id = ?", (clip,))
        db.commit()
        write_folder_file(FolderData(root / "Videos", items={"clip.mov": {"rating": 4}}))
        execute_file_moves(db, plan_file_moves(db, [rename_request(db, clip, "Carrera")]))
        assert read_folder_file(root / "Videos").items == {"Carrera.mov": {"rating": 4}}
        (root / "Destino").mkdir()
        result = execute_file_moves(
            db, plan_file_moves(db, move_requests(db, [clip, loose], 1, "Destino"))
        )
        assert result.moved == 2 and result.status_text() == "Movidos: 2", result
        assert read_folder_file(root / "Destino").items == {"Carrera.mov": {"rating": 4}}
        assert not (root / "Videos/.arca.json").exists()  # se quedó sin entradas: se borra
        assert item(clip)[0] == "Destino/Carrera.mov" and item(loose)[0] == "Destino/suelta.jpg"
        print("5. Vídeo: la entrada del .arca.json sigue al archivo (renombrar y mover)")

        # ---- 6. Solo mayúsculas ----
        lower = add("caso.jpg")
        result = execute_file_moves(db, plan_file_moves(db, [rename_request(db, lower, "CASO")]))
        assert result.moved == 1 and "CASO.jpg" in os.listdir(root), result
        print("6. Cambiar solo mayúsculas y minúsculas")

        # ---- 7. Algo aparece en el destino tras el plan: se omite, sin tocar nada ----
        race = add("carrera.jpg")
        plan = plan_file_moves(db, [rename_request(db, race, "llega")])
        (root / "llega.jpg").write_bytes(b"otro")
        result = execute_file_moves(db, plan)
        assert result.moved == 0 and result.skipped == [("carrera.jpg", SKIP_EXISTS)], result
        assert (root / "carrera.jpg").exists() and (root / "llega.jpg").read_bytes() == b"otro"
        assert journal() == 0
        print("7. Un archivo nuevo en el destino antes de mover: se omite, nada se sobrescribe")

        # ---- 8. Si el catálogo falla, se deshace en el disco (también el .xmp) ----
        stuck = add("Raw/FALLA.NEF")
        (root / "Raw/FALLA.xmp").write_text("c")
        db.execute(
            f"""CREATE TEMP TRIGGER no_update BEFORE UPDATE ON media_items WHEN NEW.id = {stuck}
                BEGIN SELECT RAISE(ABORT, 'catálogo bloqueado'); END"""
        )
        result = execute_file_moves(db, plan_file_moves(db, [rename_request(db, stuck, "Nunca")]))
        assert result.moved == 0 and "catálogo bloqueado" in result.failed[0][1], result
        assert (root / "Raw/FALLA.NEF").exists() and (root / "Raw/FALLA.xmp").exists()
        assert not (root / "Raw/Nunca.NEF").exists() and not (root / "Raw/Nunca.xmp").exists()
        assert item(stuck)[0] == "Raw/FALLA.NEF" and journal() == 0
        db.execute("DROP TRIGGER no_update")
        print("8. El catálogo falla: el archivo y su .xmp vuelven a su sitio")

        # ---- 9. Cancelar antes de empezar: nada se mueve y el registro queda vacío ----
        stop = threading.Event()
        stop.set()
        result = execute_file_moves(
            db, plan_file_moves(db, [rename_request(db, race, "nunca")]), cancel_event=stop
        )
        assert result.cancelled and result.moved == 0 and journal() == 0
        print("9. Cancelado: nada se mueve")

        # ---- 10. Al abrir: terminar o descartar lo que quedó a medias ----
        def note(
            batch: int, kind: str, media_id: int, source: str, target: str, location: int = 1
        ) -> None:
            db.execute(
                """INSERT INTO file_operations(batch_id, kind, media_id, source_location_id,
                       source_path, target_location_id, target_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (batch, kind, media_id, location, source, location, target),
            )
            db.commit()

        # a) Se movió (y su .xmp no) y el catálogo no se enteró: se termina
        half = add("Raw/MITAD.NEF")
        (root / "Raw/MITAD.xmp").write_text("d")
        note(50, "file", half, "Raw/MITAD.NEF", "Raw/Hecho.NEF")
        note(50, "sidecar", half, "Raw/MITAD.xmp", "Raw/Hecho.xmp")
        os.rename(root / "Raw/MITAD.NEF", root / "Raw/Hecho.NEF")
        # b) No se llegó a mover: se descarta
        idle = add("quieto.jpg")
        note(51, "file", idle, "quieto.jpg", "movido.jpg")
        # c) Están los dos: no se toca
        both = add("uno.jpg")
        (root / "dos.jpg").write_bytes(b"x")
        note(52, "file", both, "uno.jpg", "dos.jpg")
        # d) Disco desconectado: se queda para otra vez
        note(53, "file", offline, "d.jpg", "e.jpg", location=2)
        outcome = reconcile_file_operations(db)
        assert (outcome.completed, outcome.discarded, outcome.kept) == (1, 2, 1), outcome
        assert item(half)[:3] == ("Raw/Hecho.NEF", "Hecho.NEF", "Hecho")
        assert (root / "Raw/Hecho.xmp").exists() and not (root / "Raw/MITAD.xmp").exists()
        assert item(idle)[0] == "quieto.jpg" and item(both)[0] == "uno.jpg"
        assert journal() == 1  # la del disco desconectado
        print("10. Al abrir: terminado lo que se movió (con su .xmp), descartado lo demás")

        # ---- 11. Renombrar una carpeta ----
        assert renamed_folder_path("2024/Viaje", "2024/Viaje", "2024/Ordesa") == "2024/Ordesa"
        assert renamed_folder_path("2024/Viaje/Día 1", "2024/Viaje", "2024/Ordesa") == (
            "2024/Ordesa/Día 1"
        )
        assert renamed_folder_path("2024/Viajes", "2024/Viaje", "2024/Ordesa") is None
        trip = [add("Viaje/a.jpg"), add("Viaje/Día 1/b.jpg")]
        other = add("Viajes/c.jpg")  # empieza igual, pero no está dentro
        write_folder_file(FolderData(root / "Viaje/Día 1", items={"clip.mov": {"rating": 2}}))
        db.executemany(
            "INSERT INTO folder_libraries(storage_location_id, folder, content) VALUES (1, ?, ?)",
            [("Viaje", "image"), ("Viaje/Día 1", "auto"), ("Ordesa", "audio")],  # 'Ordesa', viejo
        )
        db.executemany(
            "INSERT OR IGNORE INTO folders(storage_location_id, relative_path) VALUES (1, ?)",
            [("Viaje",), ("Viaje/Día 1",), ("Viaje/Vacía",), ("Viajes",), ("Ordesa",)],
        )
        db.execute(
            "INSERT INTO scan_errors(storage_location_id, relative_path, stage, message) "
            "VALUES (1, 'Viaje/Día 1/roto.jpg', 'metadata', 'x')"
        )
        db.commit()
        (root / "Ocupada").mkdir()
        add("Fantasma/x.jpg", missing=1, create=False)  # en el catálogo, no en el disco
        problems = {
            "": SKIP_ROOT,
            "Viaje:Viaje": SKIP_SAME,
            "Viaje:Ocupada": SKIP_FOLDER_EXISTS,
            "Viaje:Fantasma": SKIP_FOLDER_IN_CATALOG,
            "Viaje:mal?": "caracteres",
            "NoEsta:Otra": SKIP_FOLDER_MISSING,
        }
        for case, reason in problems.items():
            folder, _, name = case.partition(":")
            plan = plan_folder_rename(db, 1, folder, name or "x")
            assert plan.problem is not None and reason in plan.problem, (case, plan)
        assert plan_folder_rename(db, 2, "d", "e").problem == SKIP_OFFLINE
        plan = plan_folder_rename(db, 1, "Viaje", "Ordesa")
        assert plan.problem is None and plan.count == 2 and plan.target_path == "Ordesa", plan
        result = execute_folder_rename(db, plan)
        assert result.moved == 2 and result.folder == (1, "Viaje", "Ordesa"), result
        assert result.status_text() == "Carpeta renombrada: «Viaje» → «Ordesa»"
        assert (root / "Ordesa/Día 1/b.jpg").is_file() and not (root / "Viaje").exists()
        assert item(trip[1])[0] == "Ordesa/Día 1/b.jpg" and item(other)[0] == "Viajes/c.jpg"
        assert read_folder_file(root / "Ordesa/Día 1").items == {"clip.mov": {"rating": 2}}
        libraries = dict(db.execute("SELECT folder, content FROM folder_libraries"))
        assert libraries == {"Ordesa": "image", "Ordesa/Día 1": "auto"}, libraries
        errors = {row[0] for row in db.execute("SELECT relative_path FROM scan_errors")}
        assert "Ordesa/Día 1/roto.jpg" in errors
        assert not any(error.startswith("Viaje/") for error in errors)
        folders = set(folders_under(db, 1))
        assert {"Ordesa", "Ordesa/Día 1", "Ordesa/Vacía", "Viajes"} <= folders, folders
        assert not any(path == "Viaje" or path.startswith("Viaje/") for path in folders)
        assert journal() == 1  # solo la del disco desconectado (paso 10)
        print("11. Renombrar una carpeta: disco, rutas de dentro, «¿Qué contiene?» y errores")

        # ---- 12. Carpeta: el catálogo falla (se deshace) y la revisión al abrir ----
        db.execute(
            """CREATE TEMP TRIGGER no_update BEFORE UPDATE ON media_items
               BEGIN SELECT RAISE(ABORT, 'catálogo bloqueado'); END"""
        )
        result = execute_folder_rename(db, plan_folder_rename(db, 1, "Ordesa", "Nunca"))
        assert result.folder is None and "catálogo bloqueado" in result.failed[0][1], result
        assert (root / "Ordesa").is_dir() and not (root / "Nunca").exists()
        db.execute("DROP TRIGGER no_update")
        os.rename(root / "Ordesa", root / "Pirineo")  # se renombró y el catálogo no lo supo
        db.execute(
            """INSERT INTO file_operations(batch_id, kind, source_location_id, source_path,
                   target_location_id, target_path)
               VALUES (60, 'folder', 1, 'Ordesa', 1, 'Pirineo')"""
        )
        db.commit()
        outcome = reconcile_file_operations(db)
        assert outcome.completed == 1, outcome
        assert item(trip[0])[0] == "Pirineo/a.jpg" and journal() == 1
        assert "Pirineo/Vacía" in folders_under(db, 1, "Pirineo")
        print("12. Carpeta: si el catálogo falla, se deshace; al abrir, se termina")

        # ---- 13. Mover a una carpeta: la biblioteca de destino; la de origen se queda ----
        (root / "Musica").mkdir()
        db.execute(
            "INSERT INTO folder_libraries(storage_location_id, folder, content) "
            "VALUES (1, 'Musica', 'audio')"
        )
        db.commit()
        first, second = add("Origen/a.jpg"), add("Origen/b.jpg")
        plan = plan_move(db, [first], 1, "Musica")  # una foto no va a una carpeta de Música
        assert not plan.moves and plan.skipped[0][1] == SKIP_LIBRARY.format("Música"), plan
        (root / "Juntas").mkdir()
        result = execute_file_moves(db, plan_move(db, [first, second], 1, "Juntas"))
        assert result.moved == 2 and result.status_text() == "Movidos: 2", result
        assert item(first)[0] == "Juntas/a.jpg"
        assert (root / "Origen").is_dir()  # vacía, se queda: en el árbol con 0 (CAT 5)
        assert folders_under(db, 1, "Juntas") == ["Juntas"]  # el destino, apuntado
        print("13. Mover a una carpeta: biblioteca de destino; la de origen, vacía, se queda")

        # ---- 14. Crear una carpeta: con lo elegido dentro, o vacía (CAT 5) ----
        loose_a, loose_b = add("Sueltas/p.jpg"), add("Sueltas/q.jpg")
        assert plan_new_folder(db, 1, "Sueltas", "mal?").problem.startswith("El nombre")
        assert plan_new_folder(db, 1, "NoExiste", "X").problem == SKIP_FOLDER_MISSING
        assert plan_new_folder(db, 1, "", "Juntas").problem == SKIP_FOLDER_EXISTS
        assert plan_new_folder(db, 2, "", "X").problem == SKIP_OFFLINE
        plan = plan_new_folder(db, 1, "Sueltas", "Elegidas", [loose_a, loose_b])
        assert plan.problem is None and plan.folder_path == "Sueltas/Elegidas", plan
        assert len(plan.moves.moves) == 2
        result = execute_new_folder(db, plan)
        assert result.created_folder == (1, "Sueltas/Elegidas") and result.moved == 2, result
        assert result.status_text() == "Carpeta creada: «Elegidas» · movidos: 2"
        assert item(loose_a)[0] == "Sueltas/Elegidas/p.jpg"
        empty = plan_new_folder(db, 1, "", "Vacía")  # sin nada elegido: vacía
        assert empty.problem is None and not empty.moves.moves, empty
        result = execute_new_folder(db, empty)
        assert result.created_folder == (1, "Vacía") and (root / "Vacía").is_dir(), result
        assert result.status_text() == "Carpeta creada: «Vacía»" and "Vacía" in folders_under(db, 1)
        # Si el catálogo no deja apuntarla, se vuelve a borrar del disco
        db.execute(
            """CREATE TEMP TRIGGER no_folder BEFORE INSERT ON folders
               BEGIN SELECT RAISE(ABORT, 'catálogo bloqueado'); END"""
        )
        result = execute_new_folder(db, plan_new_folder(db, 1, "", "Nunca"))
        assert result.created_folder is None and "catálogo bloqueado" in result.failed[0][1]
        assert not (root / "Nunca").exists()
        db.execute("DROP TRIGGER no_folder")
        print("14. Crear una carpeta: con lo elegido o vacía, y apuntada en el catálogo")

        # ---- 15. Mover una carpeta a otra de su ubicación (CAT 4.4c) ----
        one = [add("Mover/Uno/a.jpg"), add("Mover/Uno/Sub/b.jpg")]
        db.execute(
            "INSERT OR IGNORE INTO folders(storage_location_id, relative_path) "
            "VALUES (1, 'Mover/Uno/Vacía')"
        )
        db.commit()
        (root / "Mover/Uno/Vacía").mkdir()
        (root / "Ocupada/Uno").mkdir()
        add("Juntas/Uno/fantasma.jpg", missing=1, create=False)  # en el catálogo, no en el disco
        problems = {
            ("", "Juntas"): SKIP_MOVE_ROOT,
            ("NoEsta", "Juntas"): SKIP_FOLDER_MISSING,
            ("Mover/Uno", "Mover/Uno"): SKIP_INTO_ITSELF,
            ("Mover/Uno", "Mover/Uno/Sub"): SKIP_INTO_ITSELF,
            ("Mover/Uno", "Mover"): SKIP_SAME_PLACE,
            ("Mover/Uno", "NoExiste"): SKIP_NO_FOLDER,
            ("Mover/Uno", "Musica"): "es de «Detectar automáticamente» y la carpeta de destino, "
            "de «Música»",
            ("Pirineo", "Musica"): "es de «Imágenes» y la carpeta de destino, de «Música»",
            ("Mover/Uno", "Ocupada"): SKIP_NAME_TAKEN,
            ("Mover/Uno", "Juntas"): SKIP_FOLDER_IN_CATALOG,
        }
        for (folder, destination), reason in problems.items():
            plan = plan_folder_move(db, 1, folder, destination)
            assert plan.problem == reason, (folder, destination, plan)
        assert plan_folder_move(db, 2, "d", "").problem == SKIP_OFFLINE
        if _IGNORE_CASE:  # 'mover/uno' es 'Mover/Uno': dentro de sí misma
            assert plan_folder_move(db, 1, "Mover/Uno", "mover/uno/sub").problem == SKIP_INTO_ITSELF
        plan = plan_folder_move(db, 1, "Mover/Uno", "Destino")
        assert plan.problem is None and plan.count == 2, plan
        assert (plan.target_path, plan.target_name) == ("Destino/Uno", "Destino"), plan
        result = execute_folder_rename(db, plan)
        assert result.folder == (1, "Mover/Uno", "Destino/Uno") and result.moved == 2, result
        assert result.status_text() == "Carpeta «Uno» movida a «Destino»", result.status_text()
        assert (root / "Destino/Uno/Sub/b.jpg").is_file() and not (root / "Mover/Uno").exists()
        assert item(one[1])[0] == "Destino/Uno/Sub/b.jpg"
        assert "Destino/Uno/Vacía" in folders_under(db, 1, "Destino")
        assert (root / "Mover").is_dir()  # la de origen, aunque se quede vacía, sigue
        # A la raíz de la ubicación: el destino se llama como ella
        plan = plan_folder_move(db, 1, "Destino/Uno", "")
        assert (plan.problem, plan.target_path, plan.target_name) == (None, "Uno", "F"), plan
        result = execute_folder_rename(db, plan)
        assert result.status_text() == "Carpeta «Uno» movida a «F»", result.status_text()
        assert item(one[0])[0] == "Uno/a.jpg"
        # Su declaración propia, igual a la que hereda en su sitio nuevo: sobra y se borra
        add("Propia/c.jpg")
        db.execute(
            "INSERT INTO folder_libraries(storage_location_id, folder, content) "
            "VALUES (1, 'Propia', 'image')"
        )
        db.commit()
        result = execute_folder_rename(db, plan_folder_move(db, 1, "Propia", "Pirineo"))
        assert result.folder == (1, "Propia", "Pirineo/Propia"), result
        libraries = dict(db.execute("SELECT folder, content FROM folder_libraries"))
        assert "Pirineo/Propia" not in libraries and libraries["Pirineo"] == "image", libraries
        assert FolderContentResolver.load(db, 1).content_of("Pirineo/Propia") == "image"
        assert journal() == 1  # solo la del disco desconectado (paso 10)
        print("15. Mover una carpeta: sus reglas, a otra y a la raíz; «¿Qué contiene?»")

    db.close()
    print("Autoprueba finalizada correctamente.")
