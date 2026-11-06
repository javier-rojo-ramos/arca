"""Eliminar elementos: quitarlos del catálogo y, si se pide, enviar sus archivos a la papelera.

Este módulo NO depende de Qt. Las funciones reciben la conexión como primer parámetro
(para 'CatalogDatabaseManager.execute_async' y 'JobManager.start'). La papelera NO la
implementa este módulo: se recibe como función ('trash'), que la interfaz construye con
Qt ('QFile.moveToTrash'). Así 'core/' sigue sin Qt y la autoprueba usa una papelera
simulada.

Dos modos (los elige el usuario en el diálogo "Eliminar"):

    QUITAR DEL CATÁLOGO (por defecto): se borran las filas de 'media_items' (y en cascada
        sus detalles y su pertenencia a colecciones), sus errores de 'scan_errors' y sus
        miniaturas de la caché. NUNCA se toca el disco del usuario. Como en Lightroom, el
        archivo sigue en su carpeta y vuelve a aparecer (con su valoración, marca y color,
        que viven en el XMP o en el '.arca.json') si se sincroniza la carpeta: no hay lista
        de excluidos (decidido por el autor: sencillez).

    ENVIAR A LA PAPELERA: lo mismo y, ANTES, cada archivo va a la papelera del sistema:
        - Sidecar '.xmp' de un RAW (destino XMP_SIDECAR): también a la papelera, como hace
          Lightroom. 'IMG_0001.CR3.xmp' siempre; 'IMG_0001.xmp' (convención de Adobe) solo
          si no hay otro RAW con el mismo nombre en la carpeta ('IMG_0001.CR2' +
          'IMG_0001.CR3' lo comparten). El sidecar de un JPEG o DNG no se toca: no es suyo.
        - Formatos con archivo de carpeta (vídeo, audio, GPX...): se borra su entrada del
          '.arca.json'. Si no, sus datos se aplicarían a otro archivo que apareciera más
          tarde con el mismo nombre.
        - Solo del catálogo (sin tocar el disco), aunque se pida la papelera: los archivos
          AUSENTES, los de una ubicación DESCONECTADA y los de una UNIDAD DE RED (en
          Windows, una carpeta de red no tiene papelera y "enviar a la papelera" borraría
          el archivo para siempre; ver 'is_network_path').
        - Si un archivo no se puede enviar a la papelera (abierto en otro programa, sin
          permisos...), NO se quita del catálogo: se informa y se queda como estaba.

Cambios aún sin escribir: con "Quitar del catálogo", si quien llama pasa 'write_pending'
(la función que escribe en los archivos los datos del usuario pendientes,
'core/userdata/sync.write_pending_user_data'), se llama ANTES de quitar nada. Así una
valoración puesta hace un instante (que aún esperaba los 2 s de la escritura diferida)
llega al archivo y vuelve con él al sincronizar. Si falla, se avisa y se sigue.

Orden y seguridad: por lotes; primero el disco (sin transacción abierta) y después, en
una transacción corta, la base de datos (con 'commit'). Si se cancela, se termina el lote
en curso: lo que ya está en la papelera se quita siempre del catálogo, para que ninguna
fila apunte a un archivo enviado a la papelera. Las miniaturas se borran tras el
'commit' (si algo fallara antes, no se pierde la miniatura de un elemento que sigue).

Uso desde la interfaz:
    plan = plan_removal(conn, ids)                # qué se puede enviar a la papelera
    remove_media_items(conn, ids, to_trash=..., trash=move_to_trash, progress=..., ...)

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.media_removal
"""

__version__ = "1.0.1"
__all__ = [
    "CATALOG_ONLY_REASONS",
    "REASON_MISSING",
    "REASON_NETWORK",
    "REASON_OFFLINE",
    "RemovalPlan",
    "RemovalResult",
    "TrashFunction",
    "is_network_path",
    "plan_removal",
    "remove_media_items",
]

# Librerías estándar
import os
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.jobs.progress import JobProgress
from core.metadata.exiftool_runner import find_sidecars
from core.userdata.folder_file import (
    FolderFileError,
    find_entry_key,
    read_folder_file,
    write_folder_file,
)
from core.userdata.policy import UserDataDestination, destination_for

# Función que envía UN archivo a la papelera del sistema. Debe lanzar OSError si no puede
# (el archivo se queda donde estaba). La pone la interfaz ('ui_file_manager.move_to_trash').
TrashFunction = Callable[[Path], None]

# Por qué un archivo solo se puede quitar del catálogo (clave -> texto para la interfaz)
REASON_MISSING = "missing"
REASON_OFFLINE = "offline"
REASON_NETWORK = "network"
CATALOG_ONLY_REASONS: dict[str, str] = {
    REASON_MISSING: "no está en el disco (ausente)",
    REASON_OFFLINE: "su disco no está conectado",
    REASON_NETWORK: "está en una unidad de red (sin papelera)",
}

# Elementos por lote: disco + una transacción corta en la base de datos
DEFAULT_BATCH_SIZE = 100

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500

# Sistemas de archivos de red (Linux: /proc/mounts; macOS: salida de 'mount')
_NETWORK_FILESYSTEMS: frozenset[str] = frozenset(
    {
        "nfs", "nfs4", "cifs", "smb3", "smbfs", "smb2", "afpfs", "webdav", "davfs",
        "fuse.davfs2", "sshfs", "fuse.sshfs", "fuse.rclone", "9p", "afs", "ceph",
        "glusterfs", "fuse.glusterfs", "lustre",
    }
)  # fmt: skip

# Windows: tipo de unidad "remota" de GetDriveTypeW
_DRIVE_REMOTE = 4


# -----------------------------------------------------------------------------
# Unidades de red
# -----------------------------------------------------------------------------


def _mount_type_for(path: str, mounts: Iterable[tuple[str, str]]) -> str | None:
    """Tipo de sistema de archivos del punto de montaje que contiene 'path'.

    Se elige el punto de montaje MÁS LARGO que sea prefijo de la ruta ('/mnt/nas' gana a
    '/'). Función pura, para poder probarla con cualquier lista de montajes.

    Args:
        path: Ruta absoluta (estilo POSIX).
        mounts: Pares (punto de montaje, tipo).
    """
    target = PurePosixPath(path)
    best: tuple[int, str] | None = None
    for mount_point, fs_type in mounts:
        point = PurePosixPath(mount_point)
        if target == point or point in target.parents:
            length = len(point.parts)
            if best is None or length > best[0]:
                best = (length, fs_type)
    return best[1] if best else None


def _parse_proc_mounts(text: str) -> list[tuple[str, str]]:
    """Montajes de Linux ('/proc/mounts': "origen punto tipo opciones 0 0")."""
    mounts = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            # Los espacios del punto de montaje vienen como '\040'
            mounts.append((parts[1].replace("\\040", " "), parts[2]))
    return mounts


def _parse_macos_mount(text: str) -> list[tuple[str, str]]:
    """Montajes de macOS (salida de 'mount': "origen on /punto (tipo, opciones)")."""
    mounts = []
    for line in text.splitlines():
        source_and_point, _sep, rest = line.rpartition(" (")
        _source, sep, point = source_and_point.partition(" on ")
        if sep and rest:
            mounts.append((point, rest.split(",", 1)[0].rstrip(")").strip()))
    return mounts


@lru_cache(maxsize=1)
def _system_mounts() -> tuple[tuple[str, str], ...]:
    """Montajes del sistema (Linux y macOS). Se leen una vez por sesión."""
    try:
        if sys.platform == "darwin":
            output = subprocess.run(
                ["/sbin/mount"], capture_output=True, text=True, timeout=5, check=False
            ).stdout
            return tuple(_parse_macos_mount(output))
        return tuple(_parse_proc_mounts(Path("/proc/mounts").read_text(encoding="utf-8")))
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        logger.debug(f"No se pudieron leer los puntos de montaje: {exc}")
        return ()


def is_network_path(path: str | Path) -> bool:
    """True si la ruta está en una unidad de red (donde no hay papelera fiable).

    - Windows: rutas UNC ('\\\\servidor\\recurso') y unidades asignadas de red
      ('GetDriveTypeW' = DRIVE_REMOTE). Es el caso peligroso: allí "enviar a la papelera"
      borra el archivo para siempre.
    - Linux y macOS: el tipo del punto de montaje (NFS, SMB/CIFS, AFP, WebDAV, SSHFS...).
      Allí, sin papelera, Qt falla en lugar de borrar, pero se trata igual para que el
      comportamiento sea el mismo en todos los sistemas.
    Si no se puede averiguar, devuelve False.
    """
    text = os.path.abspath(str(path))
    if sys.platform == "win32":
        if text.startswith(("\\\\", "//")):
            return True
        drive = os.path.splitdrive(text)[0]
        if not drive:
            return False
        try:
            import ctypes  # solo en Windows

            return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == _DRIVE_REMOTE
        except (AttributeError, OSError):
            return False
    fs_type = _mount_type_for(text, _system_mounts())
    return fs_type is not None and fs_type.lower() in _NETWORK_FILESYSTEMS


# -----------------------------------------------------------------------------
# Plan: qué se puede enviar a la papelera (para el diálogo)
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RemovalPlan:
    """Qué se puede hacer con una selección (lo muestra el diálogo "Eliminar").

    Attributes:
        total: Elementos elegidos que siguen en el catálogo.
        trashable: Cuántos se pueden enviar a la papelera.
        catalog_only: Motivo -> cuántos solo se pueden quitar del catálogo (ver
            'CATALOG_ONLY_REASONS').
    """

    total: int = 0
    trashable: int = 0
    catalog_only: dict[str, int] = field(default_factory=dict)

    @property
    def can_trash(self) -> bool:
        """True si al menos un archivo se puede enviar a la papelera."""
        return self.trashable > 0

    def catalog_only_text(self) -> str:
        """Frase para el aviso del diálogo ('' si todos se pueden enviar a la papelera).

        Ejemplo: "3 archivos solo se quitarán del catálogo: 2 porque están en una unidad
        de red (sin papelera), 1 porque no está en el disco (ausente)."
        """
        count = sum(self.catalog_only.values())
        if not count:
            return ""
        head = "1 archivo solo se quitará" if count == 1 else f"{count} archivos solo se quitarán"
        parts = [
            f"{number} porque {CATALOG_ONLY_REASONS[reason]}"
            if number == 1
            else f"{number} porque {_plural_reason(reason)}"
            for reason, number in self.catalog_only.items()
            if number
        ]
        return f"{head} del catálogo: {', '.join(parts)}."


def _plural_reason(reason: str) -> str:
    """Motivo en plural ("no están en el disco", "están en una unidad de red"...)."""
    return {
        REASON_MISSING: "no están en el disco (ausentes)",
        REASON_OFFLINE: "su disco no está conectado",
        REASON_NETWORK: "están en una unidad de red (sin papelera)",
    }[reason]


# Datos de cada elemento para decidir qué hacer con él
_ITEM_SQL = """
    SELECT m.id AS id, m.storage_location_id AS location_id, m.relative_path AS relative_path,
           m.file_name AS file_name, m.file_extension AS file_extension,
           m.media_type AS media_type, m.is_missing AS is_missing,
           l.absolute_path AS root, l.is_online AS is_online
      FROM media_items AS m
      JOIN storage_locations AS l ON l.id = m.storage_location_id"""


def _fetch_items(conn: sqlite3.Connection, media_ids: Sequence[int]) -> list[sqlite3.Row]:
    """Filas de '_ITEM_SQL' de esos 'id' (por trozos), con acceso por nombre de columna.

    Usa un cursor propio con 'sqlite3.Row': no cambia el 'row_factory' de la conexión.
    """
    ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))  # sin repetidos
    rows: list[sqlite3.Row] = []
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        marks = ",".join("?" * len(chunk))
        rows.extend(cursor.execute(f"{_ITEM_SQL} WHERE m.id IN ({marks})", chunk).fetchall())
    return rows


def _catalog_only_reason(
    row: Mapping[str, Any], is_remote: Callable[[str], bool], remote_cache: dict[int, bool]
) -> str | None:
    """Por qué un elemento solo se puede quitar del catálogo, o None si va a la papelera.

    La comprobación de red se hace una vez por ubicación (todos sus archivos comparten
    carpeta raíz y, por tanto, unidad).
    """
    if not row["is_online"]:
        return REASON_OFFLINE
    if row["is_missing"]:
        return REASON_MISSING
    location_id = row["location_id"]
    if location_id not in remote_cache:
        remote_cache[location_id] = is_remote(row["root"])
    if remote_cache[location_id]:
        return REASON_NETWORK
    return None


def plan_removal(
    conn: sqlite3.Connection,
    media_ids: Sequence[int],
    *,
    is_remote: Callable[[str], bool] = is_network_path,
) -> RemovalPlan:
    """Cuenta qué elementos se pueden enviar a la papelera y cuáles solo quitar del catálogo.

    Solo lee (no hace 'commit'). Usa lo que dice el catálogo ('is_missing', 'is_online'):
    el trabajo vuelve a comprobarlo en el disco justo antes de tocar cada archivo.

    Args:
        conn: Conexión sqlite3.
        media_ids: Elementos elegidos.
        is_remote: Función que dice si una carpeta está en una unidad de red (para pruebas).
    """
    rows = _fetch_items(conn, media_ids)
    remote_cache: dict[int, bool] = {}
    catalog_only: dict[str, int] = {}
    trashable = 0
    for row in rows:
        reason = _catalog_only_reason(row, is_remote, remote_cache)
        if reason is None:
            trashable += 1
        else:
            catalog_only[reason] = catalog_only.get(reason, 0) + 1
    return RemovalPlan(total=len(rows), trashable=trashable, catalog_only=catalog_only)


# -----------------------------------------------------------------------------
# El trabajo: eliminar
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class RemovalResult:
    """Resultado de 'remove_media_items' (cumple el protocolo 'JobResult').

    Attributes:
        to_trash: Si se pidió enviar a la papelera.
        removed: Elementos quitados del catálogo (en total).
        trashed: Archivos enviados a la papelera.
        sidecars_trashed: Sidecars '.xmp' enviados a la papelera.
        catalog_only: Pedida la papelera, cuántos solo se quitaron del catálogo (motivo ->
            número).
        failed: Archivos que no se pudieron enviar a la papelera (siguen en el catálogo):
            (ruta, mensaje).
        warnings: Problemas menores (un sidecar o un '.arca.json' que no se pudo tocar).
        removed_ids: 'id' quitados (para que la interfaz actualice la cuadrícula).
        thumbnails_deleted: Archivos de miniatura borrados de la caché.
        cancelled: Si el usuario lo canceló (lo ya hecho se conserva).
    """

    to_trash: bool = False
    removed: int = 0
    trashed: int = 0
    sidecars_trashed: int = 0
    catalog_only: dict[str, int] = field(default_factory=dict)
    failed: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    removed_ids: list[int] = field(default_factory=list)
    thumbnails_deleted: int = 0
    cancelled: bool = False

    @property
    def has_warnings(self) -> bool:
        """True si algo no salió como se pidió (fallos, avisos o cancelación)."""
        return bool(self.failed or self.warnings or self.cancelled)

    def status_text(self) -> str:
        """Frase corta para la barra de estado."""
        if self.to_trash:
            text = f"Enviados a la papelera: {self.trashed}"
            only = sum(self.catalog_only.values())
            if only:
                text += f" · solo quitados del catálogo: {only}"
        else:
            text = f"Quitados del catálogo: {self.removed}"
        if self.failed:
            text += f" · no se pudieron eliminar: {len(self.failed)}"
        if self.cancelled:
            text += " (cancelado)"
        return text


def remove_media_items(
    conn: sqlite3.Connection,
    media_ids: Sequence[int],
    *,
    to_trash: bool = False,
    trash: TrashFunction | None = None,
    catalog_dir: str | Path | None = None,
    is_remote: Callable[[str], bool] = is_network_path,
    write_pending: Callable[[sqlite3.Connection], Any] | None = None,
    progress: Callable[[JobProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> RemovalResult:
    """Quita elementos del catálogo y, si se pide, envía sus archivos a la papelera.

    Es un trabajo para 'JobManager.start' (progreso y cancelación); hace 'commit' por
    lote. Ver la cabecera del módulo para las reglas.

    Args:
        conn: Conexión sqlite3 propia del trabajo.
        media_ids: Elementos a eliminar.
        to_trash: True = enviar también a la papelera; False = solo quitar del catálogo.
        trash: Función que envía un archivo a la papelera (obligatoria con 'to_trash').
        catalog_dir: Carpeta del catálogo (para borrar las miniaturas). None = se deduce
            del archivo de la base de datos (en memoria: no se tocan).
        is_remote: Función que dice si una carpeta está en una unidad de red.
        write_pending: Solo con "Quitar del catálogo": función que escribe antes en los
            archivos los datos del usuario pendientes (recibe la conexión). None = no se
            escribe nada (p. ej. si la opción "Escribir los cambios en los archivos" está
            desactivada).
        progress: Función a la que se avisa del avance.
        cancel_event: Si se activa, se termina el lote en curso y se para.
        batch_size: Elementos por lote.

    Raises:
        ValueError: Si se pide la papelera sin función 'trash'.
    """
    if to_trash and trash is None:
        raise ValueError("Para enviar a la papelera hace falta la función 'trash'.")

    result = RemovalResult(to_trash=to_trash)

    # Quitar del catálogo: antes, lo pendiente de escribir llega a los archivos (con la
    # papelera da igual: el archivo se va). Un fallo aquí no impide quitar lo pedido
    if write_pending is not None and not to_trash:
        try:
            write_pending(conn)
        except Exception as exc:  # noqa: BLE001 - se informa y se sigue
            if conn.in_transaction:
                conn.rollback()
            result.warnings.append(f"No se pudieron escribir antes los cambios pendientes: {exc}")

    rows = _fetch_items(conn, media_ids)
    total = len(rows)
    folder = Path(catalog_dir) if catalog_dir is not None else _catalog_directory(conn)
    remote_cache: dict[int, bool] = {}
    done = 0
    if progress:
        progress(JobProgress(0, total))

    for start in range(0, total, max(1, batch_size)):
        batch = rows[start : start + batch_size]

        # 1. Disco (sin transacción abierta): qué filas se pueden quitar del catálogo
        if to_trash:
            removable, folder_entries = _trash_batch(
                batch, trash, is_remote, remote_cache, result, cancel_event
            )
            _clean_folder_files(folder_entries, result)
        else:
            removable = list(batch)

        # 2. Base de datos: una transacción corta por lote
        _delete_rows(conn, removable)
        conn.commit()
        result.removed += len(removable)
        result.removed_ids.extend(row["id"] for row in removable)

        # 3. Miniaturas (tras el commit)
        result.thumbnails_deleted += _delete_thumbnails(folder, removable)

        done += len(batch)
        if progress:
            progress(JobProgress(done, total))
        if cancel_event is not None and cancel_event.is_set():
            result.cancelled = done < total
            break

    logger.info(
        f"Eliminar ({'papelera' if to_trash else 'solo catálogo'}): {result.status_text()}; "
        f"miniaturas borradas: {result.thumbnails_deleted}"
    )
    for path, message in result.failed:
        logger.warning(f"No se pudo enviar a la papelera {path}: {message}")
    for warning in result.warnings:
        logger.warning(warning)
    return result


def _trash_batch(
    batch: Sequence[sqlite3.Row],
    trash: TrashFunction,
    is_remote: Callable[[str], bool],
    remote_cache: dict[int, bool],
    result: RemovalResult,
    cancel_event: threading.Event | None,
) -> tuple[list[sqlite3.Row], dict[Path, list[str]]]:
    """Envía a la papelera los archivos de un lote.

    Returns:
        (filas que se pueden quitar del catálogo, carpeta -> nombres cuya entrada hay que
        borrar del '.arca.json'). Una fila cuyo archivo no se pudo enviar a la papelera NO
        está en la lista (se queda en el catálogo). Si se cancela a mitad, el resto del
        lote no se toca (ni en el disco ni en el catálogo).
    """
    removable: list[sqlite3.Row] = []
    folder_entries: dict[Path, list[str]] = {}
    for row in batch:
        if cancel_event is not None and cancel_event.is_set():
            break
        reason = _catalog_only_reason(row, is_remote, remote_cache)
        path = Path(row["root"]) / row["relative_path"]
        if reason is None and not path.is_file():
            reason = REASON_MISSING  # ha desaparecido desde que se miró el catálogo
        if reason is not None:
            result.catalog_only[reason] = result.catalog_only.get(reason, 0) + 1
            removable.append(row)
            continue

        destination = destination_for(row["file_extension"] or path)
        # Los sidecars se buscan ANTES de mover el RAW (después ya no estaría para comparar)
        sidecars = (
            _own_sidecars(path) if destination == UserDataDestination.XMP_SIDECAR else []
        )
        try:
            trash(path)
        except OSError as exc:
            result.failed.append((str(path), str(exc) or exc.__class__.__name__))
            continue
        result.trashed += 1
        removable.append(row)

        for sidecar in sidecars:
            try:
                trash(sidecar)
                result.sidecars_trashed += 1
            except OSError as exc:
                result.warnings.append(f"No se pudo enviar a la papelera el sidecar {sidecar}: {exc}")
        if destination == UserDataDestination.FOLDER_FILE:
            folder_entries.setdefault(path.parent, []).append(path.name)
    return removable, folder_entries


def _own_sidecars(raw_path: Path) -> list[Path]:
    """Sidecars '.xmp' que pertenecen SOLO a este RAW (los que se envían con él a la papelera).

    'IMG_0001.CR3.xmp' es solo suyo. 'IMG_0001.xmp' (Adobe) es suyo salvo que en la carpeta
    haya otro RAW con el mismo nombre y otra extensión ('IMG_0001.CR2'), que lo comparte.
    """
    own: list[Path] = []
    for sidecar in find_sidecars(raw_path):
        # 'IMG_0001.CR3.xmp' lleva el nombre completo del RAW: solo puede ser suyo
        named_after_raw = sidecar.name.casefold() == f"{raw_path.name}.xmp".casefold()
        if named_after_raw or not _other_raw_with_same_stem(raw_path):
            own.append(sidecar)
    return own


def _other_raw_with_same_stem(raw_path: Path) -> bool:
    """True si en la carpeta hay otro RAW (destino sidecar) con el mismo nombre base."""
    stem = raw_path.stem.casefold()
    try:
        with os.scandir(raw_path.parent) as entries:
            for entry in entries:
                if entry.name == raw_path.name or not entry.is_file():
                    continue
                other = Path(entry.name)
                if (
                    other.stem.casefold() == stem
                    and destination_for(other.suffix) == UserDataDestination.XMP_SIDECAR
                ):
                    return True
    except OSError:
        return True  # sin poder comprobarlo, se conserva el sidecar (lo prudente)
    return False


def _clean_folder_files(folder_entries: Mapping[Path, list[str]], result: RemovalResult) -> None:
    """Borra del '.arca.json' de cada carpeta las entradas de los archivos enviados a la papelera.

    Una lectura y una escritura por carpeta. Un archivo de carpeta dañado no se toca (ni
    se reescribe a ciegas): queda como aviso.
    """
    for directory, names in folder_entries.items():
        try:
            data = read_folder_file(directory)
            if not data.exists:
                continue
            keys = [key for name in names if (key := find_entry_key(data.items, name))]
            if not keys:
                continue
            for key in keys:
                data.items.pop(key, None)
            write_folder_file(data)
        except FolderFileError as exc:
            result.warnings.append(f"No se pudo actualizar el archivo de carpeta de {directory}: {exc}")


def _delete_rows(conn: sqlite3.Connection, rows: Sequence[sqlite3.Row]) -> None:
    """Borra las filas (y en cascada detalles y colecciones) y sus errores de lectura."""
    if not rows:
        return
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    ids = [row["id"] for row in rows]
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM media_items WHERE id IN ({marks})", chunk)
    conn.executemany(
        "DELETE FROM scan_errors WHERE storage_location_id = ? AND relative_path = ?",
        ((row["location_id"], row["relative_path"]) for row in rows),
    )


def _delete_thumbnails(folder: Path | None, rows: Sequence[sqlite3.Row]) -> int:
    """Borra las miniaturas de esos elementos; devuelve cuántos archivos se borraron."""
    if folder is None or not rows:
        return 0
    # Importación diferida: solo hace falta aquí (y arrastra Pillow)
    from core.thumbnails.cache import ThumbnailCache

    cache = ThumbnailCache(folder)
    deleted = 0
    for row in rows:
        try:
            deleted += len(cache.delete(row["media_type"], row["id"]))
        except ValueError:
            continue  # tipo de medio desconocido: no tiene carpeta en la caché
    return deleted


def _catalog_directory(conn: sqlite3.Connection) -> Path | None:
    """Carpeta del catálogo (la que contiene el .db), o None si la base está en memoria."""
    for _sequence, schema_name, file_path in conn.execute("PRAGMA database_list;"):
        if schema_name == "main" and file_path:
            return Path(file_path).parent
    return None


if __name__ == "__main__":
    # Autoprueba con archivos temporales, un catálogo de verdad y una papelera SIMULADA
    # (mueve los archivos a una carpeta 'Papelera'). Nunca toca la papelera del sistema.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.media_removal
    import shutil
    import tempfile

    from core.catalog.catalog_builder import CatalogBuilder
    from core.catalog.catalog_schema import configure_connection
    from core.userdata.folder_file import FolderData

    # 1. Unidades de red: montajes de Linux y de macOS (funciones puras)
    proc = (
        "/dev/nvme0n1p2 / ext4 rw 0 0\n"
        "//nas/fotos /mnt/nas cifs rw 0 0\n"
        "server:/export /mnt/mis\\040fotos nfs4 rw 0 0\n"
    )
    linux = _parse_proc_mounts(proc)
    assert _mount_type_for("/home/javier/a.jpg", linux) == "ext4"
    assert _mount_type_for("/mnt/nas/2024/a.jpg", linux) == "cifs"
    assert _mount_type_for("/mnt/nasa/a.jpg", linux) == "ext4"  # '/mnt/nasa' no es '/mnt/nas'
    assert _mount_type_for("/mnt/mis fotos/a.jpg", linux) == "nfs4"
    mac = _parse_macos_mount(
        "/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)\n"
        "//javier@nas._smb._tcp.local/Fotos on /Volumes/Fotos (smbfs, nodev, nosuid, mounted by javier)\n"
    )
    assert _mount_type_for("/Volumes/Fotos/a.jpg", mac) == "smbfs"
    assert _mount_type_for("/Users/javier/a.jpg", mac) == "apfs"
    print("1. Unidades de red: puntos de montaje de Linux y macOS")

    # 2. Textos del plan
    mixed = RemovalPlan(total=5, trashable=2, catalog_only={REASON_NETWORK: 2, REASON_MISSING: 1})
    assert mixed.can_trash and mixed.catalog_only_text() == (
        "3 archivos solo se quitarán del catálogo: 2 porque están en una unidad de red "
        "(sin papelera), 1 porque no está en el disco (ausente)."
    ), mixed.catalog_only_text()
    assert RemovalPlan(total=1, trashable=1).catalog_only_text() == ""
    print("2. Textos del aviso del diálogo")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        local, nas, bin_dir = base / "Local", base / "NAS", base / "Papelera"
        for directory in (local / "Viaje", nas, bin_dir):
            directory.mkdir(parents=True)
        db_path = CatalogBuilder(base / "Catalogo").build()
        conn = sqlite3.connect(db_path)
        configure_connection(conn)
        conn.execute("INSERT INTO storage_locations(id, name, absolute_path) VALUES (1, 'L', ?)", (str(local),))
        conn.execute("INSERT INTO storage_locations(id, name, absolute_path) VALUES (2, 'N', ?)", (str(nas),))
        conn.execute(
            "INSERT INTO storage_locations(id, name, absolute_path, is_online) VALUES (3, 'X', ?, 0)",
            (str(base / "Desconectado"),),
        )

        def add(location: int, relative: str, media_type: str, *, missing: int = 0,
                create: bool = True) -> int:
            """Crea el archivo (si procede) y su fila en el catálogo; devuelve el 'id'."""
            root = {1: local, 2: nas, 3: base / "Desconectado"}[location]
            if create:
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes(b"x")
            name = relative.rpartition("/")[2]
            return int(conn.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       file_extension, media_type, mime_type, file_size, file_mtime_ns,
                       title, is_missing)
                   VALUES (?, ?, ?, ?, ?, 'x', 1, 0, 't', ?)""",
                (location, relative, name, name.rpartition(".")[2].lower(), media_type, missing),
            ).lastrowid)  # fmt: skip

        ids = {
            "jpg": add(1, "Viaje/a.jpg", "photo"),
            "nef": add(1, "Viaje/DSC_1.NEF", "photo"),        # RAW con sidecar propio
            "cr2": add(1, "Viaje/IMG_1.CR2", "photo"),        # comparte IMG_1.xmp con el CR3
            "mov": add(1, "Viaje/clip.mov", "video"),         # con entrada en el .arca.json
            "locked": add(1, "Viaje/bloqueado.jpg", "photo"),  # la papelera falla
            "gone": add(1, "Viaje/borrada.jpg", "photo", missing=1, create=False),
            "nas": add(2, "b.jpg", "photo"),                  # unidad de red
            "off": add(3, "c.jpg", "photo", create=False),    # disco desconectado
        }  # fmt: skip
        (local / "Viaje" / "DSC_1.xmp").write_text("x")
        (local / "Viaje" / "IMG_1.CR3").write_bytes(b"x")
        (local / "Viaje" / "IMG_1.xmp").write_text("x")
        write_folder_file(FolderData(local / "Viaje", items={
            "clip.mov": {"rating": 4}, "otro.mp4": {"rating": 2}}))  # fmt: skip
        conn.execute("INSERT INTO collections(id, kind, name) VALUES (1, 'static', 'C')")
        conn.execute("INSERT INTO collection_items(collection_id, media_id) VALUES (1, ?)", (ids["jpg"],))
        conn.execute(
            "INSERT INTO scan_errors(storage_location_id, relative_path, stage, message) "
            "VALUES (1, 'Viaje/a.jpg', 'metadata', 'x')"
        )
        # Una miniatura de la foto, para ver que se borra
        thumb = base / "Catalogo" / "cache" / "photo" / "160" / "0" / f"{ids['jpg']}.jpg"
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(b"x")
        conn.commit()

        def fake_remote(root: str) -> bool:
            return Path(root) == nas

        def fake_trash(path: Path) -> None:
            """Papelera simulada: falla con 'bloqueado.jpg'; si no, mueve a 'Papelera'."""
            if path.name == "bloqueado.jpg":
                raise PermissionError("El archivo está abierto en otro programa")
            shutil.move(str(path), str(bin_dir / path.name))

        # 3. Plan de la selección mixta
        plan = plan_removal(conn, list(ids.values()), is_remote=fake_remote)
        assert plan.total == 8 and plan.trashable == 5, plan
        assert plan.catalog_only == {REASON_MISSING: 1, REASON_NETWORK: 1, REASON_OFFLINE: 1}
        print("3. Plan: 5 a la papelera; 3 solo del catálogo (red, ausente, desconectado)")

        # 4. Sin función de papelera no se puede pedir la papelera
        try:
            remove_media_items(conn, [ids["jpg"]], to_trash=True)
        except ValueError:
            pass
        else:
            raise AssertionError("debería exigir la función 'trash'")

        # 5. Enviar a la papelera (lotes de 3 para probar varios lotes)
        seen: list[JobProgress] = []
        result = remove_media_items(
            conn, list(ids.values()), to_trash=True, trash=fake_trash,
            is_remote=fake_remote, progress=seen.append, batch_size=3,
        )  # fmt: skip
        assert result.trashed == 4 and result.removed == 7, result
        assert result.catalog_only == {REASON_MISSING: 1, REASON_NETWORK: 1, REASON_OFFLINE: 1}
        assert [Path(p).name for p, _m in result.failed] == ["bloqueado.jpg"]
        assert result.has_warnings and "no se pudieron eliminar: 1" in result.status_text()
        assert seen[0] == JobProgress(0, 8) and seen[-1] == JobProgress(8, 8)
        # El disco: lo enviado está en la "papelera"; lo de red y lo bloqueado, en su sitio
        in_bin = {p.name for p in bin_dir.iterdir()}
        assert in_bin == {"a.jpg", "DSC_1.NEF", "DSC_1.xmp", "IMG_1.CR2", "clip.mov"}, in_bin
        assert result.sidecars_trashed == 1
        assert (local / "Viaje" / "IMG_1.xmp").exists()  # lo sigue usando IMG_1.CR3
        assert (nas / "b.jpg").exists() and (local / "Viaje" / "bloqueado.jpg").exists()
        # El catálogo: solo queda el bloqueado; colecciones, errores y miniatura, fuera
        left = [row[0] for row in conn.execute("SELECT file_name FROM media_items")]
        assert left == ["bloqueado.jpg"], left
        assert conn.execute("SELECT COUNT(*) FROM collection_items").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0] == 0
        assert not thumb.exists() and result.thumbnails_deleted == 1
        assert sorted(result.removed_ids) == sorted(v for k, v in ids.items() if k != "locked")
        # El .arca.json conserva solo la entrada del otro vídeo
        assert read_folder_file(local / "Viaje").items == {"otro.mp4": {"rating": 2}}
        print("5. Papelera: archivos, sidecar propio (el compartido no), .arca.json y catálogo")

        # 6. Solo quitar del catálogo: el disco no se toca
        keep = add(1, "Viaje/queda.jpg", "photo")
        conn.commit()
        flushed: list[str] = []
        result = remove_media_items(
            conn, [keep, ids["locked"]], trash=fake_trash,
            write_pending=lambda _conn: flushed.append("escrito"),
        )  # fmt: skip
        assert flushed == ["escrito"]  # lo pendiente se escribe ANTES de quitar
        assert result.removed == 2 and result.trashed == 0 and not result.has_warnings
        assert (local / "Viaje" / "queda.jpg").exists()
        assert result.status_text() == "Quitados del catálogo: 2"
        # Si escribir lo pendiente falla, se avisa y se quita igual
        other = add(1, "Viaje/otra.jpg", "photo")
        conn.commit()

        def failing_write(_conn: sqlite3.Connection) -> None:
            raise RuntimeError("ExifTool no responde")

        result = remove_media_items(conn, [other], write_pending=failing_write)
        assert result.removed == 1 and result.warnings and result.has_warnings
        print("6. Quitar del catálogo: el disco no se toca; antes se escribe lo pendiente")

        # 7. Cancelar: se termina el lote en curso y se para; lo ya enviado sale del catálogo
        many = [add(1, f"Viaje/m{i}.jpg", "photo") for i in range(5)]
        conn.commit()
        stop = threading.Event()

        def trash_and_cancel(path: Path) -> None:
            """Papelera que pide cancelar tras el primer archivo."""
            fake_trash(path)
            stop.set()

        result = remove_media_items(
            conn, many, to_trash=True, trash=trash_and_cancel, is_remote=fake_remote,
            cancel_event=stop, batch_size=2,
            write_pending=lambda _conn: flushed.append("no debería"),  # con papelera, no
        )  # fmt: skip
        assert flushed == ["escrito"]
        assert result.cancelled and result.trashed == 1 and result.removed == 1, result
        remaining = conn.execute("SELECT COUNT(*) FROM media_items").fetchone()[0]
        assert remaining == 4  # los otros cuatro, ni en la papelera ni fuera del catálogo
        assert conn.row_factory is None  # la conexión conserva su 'row_factory'
        conn.close()
        print("7. Cancelar: nada queda a medias")
    print("Autoprueba finalizada correctamente.")
