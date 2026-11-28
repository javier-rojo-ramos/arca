"""Escritores de los datos del usuario: quién sabe guardar qué, fuera del catálogo.

Este módulo NO depende de Qt ni de la base de datos. Aquí está la INTERFAZ que cumple todo
escritor ('UserDataWriter') y dos de los tres que hay: el del archivo de carpeta
('.arca.json') y el de XMP (con ExifTool); el de las etiquetas de las canciones está en
'audio_writer.py' (MUS 6.2b). El trabajo que decide QUÉ hay pendiente y anota el resultado en el
catálogo es 'sync.write_pending_user_data': reparte los archivos entre los escritores y no
sabe cómo escribe cada uno (docs/PENDIENTE.md, GEN 14).

>>> AQUÍ SE AÑADE UN ESCRITOR NUEVO (etiquetas de audio, OPF de un EPUB...). <<<
    1. Una clase que herede de 'UserDataWriter' (en su propio archivo, si es larga) con
       'write': recibe los 'WriteItem' de un lote y deja en cada uno cómo le ha ido.
    2. Su destino en 'policy.py' ('UserDataDestination' y las extensiones que lo usan).
    3. Su línea en 'default_writers'.
    4. Si NO sabe guardar todos los campos (unas etiquetas de audio no tienen dónde poner
       el color), 'fields_for': los que sí. Lo demás va solo al archivo de carpeta.
    'sync.py' no se toca.

UN ARCHIVO, DOS DESTINOS ('split_items'): los campos pendientes que el escritor de un
formato no sabe guardar se escriben en el '.arca.json' de su carpeta. El elemento se parte
en dos 'WriteItem' del mismo archivo, cada uno con sus campos ('only'), y cada parte quita
sus marcas de pendiente por separado: si una falla, solo esa sigue pendiente. El primer
formato que se parte es el MP3 (MUS 6.2b): sus etiquetas al archivo y la valoración, la
marca, el color y las palabras clave al '.arca.json'. Las fotos no se parten (XMP sabe
guardar todo). La LECTURA de un formato partido (qué sale del archivo y qué del
'.arca.json') la dice 'policy.folder_file_fields'.

Lo que 'write' deja en cada 'WriteItem' (el trabajo lo lee después):
    ok          el destino tiene ya los valores pedidos (escritos ahora o de antes)
    written     se ha modificado algo en el disco
    message     por qué ha fallado ('' si fue bien)
    deferred    no se ha intentado (falta la herramienta, se canceló): sigue pendiente, sin
                contar como fallo del archivo
    db_updates  columnas de 'media_items' que hay que anotar (tamaño y fecha nuevos...)
    rescan      el archivo había cambiado fuera de la aplicación: hay que releerlo entero
                (también la miniatura)
    reread      se le ha escrito algo que el catálogo no sabe (un MP3 al que se le crea el
                ID3v2: su tipo de etiqueta): hay que releer solo sus metadatos
Un escritor NUNCA lanza una excepción por un archivo o por su herramienta: lo apunta en el
elemento. Si su herramienta no está (ExifTool), pone además 'unavailable'.

Reglas que cumple todo escritor (CLAUDE.md, «Archivos del usuario»): solo cambia los campos
pedidos ('WriteItem.wanted': los pendientes), conserva lo que no conoce, comprueba lo escrito
y nunca deja un archivo a medias.

1.2.0 El escritor de las etiquetas de las canciones ('audio_writer.AudioFileWriter', destino
      AUDIO_TAGS) en 'default_writers', con la etiqueta preferida de los MP3 de las
      Opciones ('preferred_mp3'); 'WriteItem.reread' (MUS 6.2b).
1.1.0 Un archivo, dos destinos: 'UserDataWriter.fields_for', 'WriteItem.only' y
      'split_items' (docs/PENDIENTE.md, GEN 14, paso 2).
1.0.0 Primera versión (16/11/2026; docs/PENDIENTE.md, GEN 14): la interfaz, y los dos
      escritores que estaban dentro de 'sync.py' ('_write_folder_items' y
      '_write_xmp_items'), movidos sin cambiar lo que hacen.

Prueba (la de 'sync.py' los ejercita de ida y vuelta; necesita ExifTool):
    python -m core.userdata.sync
"""

__version__ = "1.2.0"
__all__ = [
    "USER_COLUMNS",
    "FolderFileWriter",
    "UserDataWriter",
    "WriteItem",
    "XmpFileWriter",
    "default_writers",
    "split_items",
]

# Librerías estándar
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.audio.tag_set import DEFAULT_MP3_TAGS, TagSet
from core.catalog.keywords import same_keywords
from core.catalog.media_queries import USER_FIELD_BITS
from core.metadata.exiftool_runner import ExifToolError, ExifToolRunner, find_sidecars
from core.userdata.editable_fields import (
    EDITABLE_COLUMNS,
    XMP_COLUMNS,
    file_title,
    pending_columns,
)
from core.userdata.folder_file import (
    KEYWORDS_KEY,
    FolderFileError,
    edited_values_from_entry,
    find_entry_key,
    keywords_from_entry,
    merge_entry,
    read_folder_file,
    user_values_from_entry,
    write_folder_file,
)
from core.userdata.policy import UserDataDestination, sidecar_path_for_writing
from core.userdata.xmp_writer import XmpUserDataWriter, XmpWriteRequest

# Columnas de los datos del usuario que se sincronizan (mismo orden en todo el paquete)
USER_COLUMNS: tuple[str, ...] = ("rating", "flag", "color_label")

# Valor de un metadato que la entrada del archivo de carpeta no trae (no editado): distinto
# de None (vaciado a propósito), para decidir si hay que escribir la entrada
_NOT_EDITED = object()


# =============================================================================
# Un elemento pendiente y las dos escrituras (antes, en 'sync.py')
# =============================================================================


@dataclass(slots=True)
class WriteItem:
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
    # Si el archivo se reparte entre dos escritores ('split_items'): los campos de ESTA
    # parte. None = todos los pendientes
    only: frozenset[str] | None = None
    # Resultado
    ok: bool = False
    written: bool = False
    deferred: bool = False  # no se intentó (falta ExifTool): no es un fallo del archivo
    message: str = ""
    db_updates: dict[str, Any] = field(default_factory=dict)  # columnas a actualizar tras escribir
    rescan: bool = False  # el archivo cambió fuera de la aplicación: releer sus metadatos
    reread: bool = False  # se le escribió algo que el catálogo no sabe: releer sus metadatos

    @property
    def wanted(self) -> dict[str, Any]:
        """Solo los campos pendientes, con su valor de la BD (lo que hay que escribir)."""
        wanted: dict[str, Any] = {
            column: self.values[column]
            for column in USER_COLUMNS
            if self.pending & USER_FIELD_BITS[column]
        }
        if self.keywords_pending:
            wanted[KEYWORDS_KEY] = self.keywords
        # Metadatos editados: el título igual al nombre del archivo es «sin título»
        for column in pending_columns(self.metadata_pending):
            value = self.metadata[column]
            wanted[column] = file_title(value, self.path.name) if column == "title" else value
        if self.only is not None:
            wanted = {key: value for key, value in wanted.items() if key in self.only}
        return wanted


def _write_folder_items(items: list[WriteItem]) -> None:
    """Escribe en el archivo de carpeta los elementos de destino FOLDER_FILE.

    Una lectura y, como mucho, una escritura por carpeta. Si el archivo de una carpeta
    no se puede leer (dañado, sin permisos), NO se reescribe: sus elementos fallan y
    siguen pendientes (reescribirlo a ciegas podría borrar datos de otros archivos).
    """
    by_folder: dict[Path, list[WriteItem]] = {}
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
    writer: XmpUserDataWriter, items: list[WriteItem], cancel_event: threading.Event | None
) -> None:
    """Escribe los elementos de destino XMP (incrustado o sidecar) y prepara la BD.

    Raises:
        ExifToolError: Si ExifTool no se puede ejecutar (fallo general).
    """
    requests: list[XmpWriteRequest] = []
    targets: list[WriteItem] = []
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


# =============================================================================
# La interfaz y los escritores
# =============================================================================


class UserDataWriter(ABC):
    """Lo que cumple todo escritor (ver el docstring del archivo).

    Attributes:
        name: Nombre corto, para el registro.
        unavailable: True si en este trabajo su herramienta no ha estado disponible (sus
            elementos quedan pendientes, 'deferred', y se avisa al usuario).
    """

    name: ClassVar[str] = ""

    def __init__(self) -> None:
        self.unavailable = False

    def fields_for(self, item: WriteItem) -> frozenset[str] | None:
        """Los campos que sabe guardar en ese archivo (las claves de 'WriteItem.wanted':
        'rating', 'flag', 'color_label', 'keywords' y las columnas editables), o None si
        los sabe todos. Lo que no sepa va al archivo de carpeta ('split_items')."""
        return None

    @abstractmethod
    def write(self, items: list[WriteItem], cancel_event: threading.Event | None = None) -> None:
        """Deja el destino de cada elemento con sus valores pendientes ('item.wanted') y
        apunta en él cómo ha ido. No lanza excepciones por un archivo ni por su herramienta."""


class FolderFileWriter(UserDataWriter):
    """El archivo de carpeta '.arca.json': una lectura y, como mucho, una escritura por
    carpeta. No modifica el original; sabe guardar cualquier campo."""

    name = "folder_file"

    def write(self, items: list[WriteItem], cancel_event: threading.Event | None = None) -> None:
        _write_folder_items(items)


class XmpFileWriter(UserDataWriter):
    """XMP con ExifTool: dentro del archivo o en el sidecar '.xmp' de un RAW.

    ExifTool se arranca al primer lote que lo necesita (una vez por trabajo). Si no está,
    o deja de funcionar, sus elementos quedan pendientes y 'unavailable' pasa a True.
    """

    name = "xmp"

    # Lo que cabe en XMP: los datos del usuario, las palabras clave y los metadatos
    # editables con etiqueta XMP (los que no la tienen, como la actividad de un track, no)
    FIELDS: ClassVar[frozenset[str]] = frozenset((*USER_COLUMNS, KEYWORDS_KEY, *XMP_COLUMNS))

    def __init__(self, runner_factory: Callable[[], ExifToolRunner] | None = None) -> None:
        """Args:
            runner_factory: Crea el lector de ExifTool (por defecto, 'ExifToolRunner()').
                Solo se llama si hay algún XMP que escribir.
        """
        super().__init__()
        self._runner_factory = runner_factory
        self._holder: dict[str, XmpUserDataWriter | None] = {}  # se crea al primer XMP

    def fields_for(self, item: WriteItem) -> frozenset[str] | None:
        return self.FIELDS

    def _engine(self) -> XmpUserDataWriter | None:
        """Crea (una vez por trabajo) el escritor de XMP. None si ExifTool no está disponible."""
        if "writer" not in self._holder:
            try:
                runner = self._runner_factory() if self._runner_factory else ExifToolRunner()
                runner.version()  # comprueba que se puede ejecutar de verdad
                self._holder["writer"] = XmpUserDataWriter(runner)
            except ExifToolError as error:
                logger.warning(f"ExifTool no disponible: no se escriben XMP ({error})")
                self._holder["writer"] = None
        return self._holder["writer"]

    def write(self, items: list[WriteItem], cancel_event: threading.Event | None = None) -> None:
        if not items:
            return
        writer = self._engine()
        if writer is None:
            self.unavailable = True
            for item in items:
                item.deferred = True
            return
        try:
            _write_xmp_items(writer, items, cancel_event)
        except ExifToolError as error:
            # Fallo general de ExifTool: el resto del lote queda pendiente
            self.unavailable = True
            logger.error(f"ExifTool no puede escribir: {error}")
            for item in items:
                if not item.ok:
                    item.deferred = True


def split_items(
    items: Sequence[WriteItem], writers: Mapping[UserDataDestination, UserDataWriter]
) -> list[WriteItem]:
    """Reparte cada elemento entre el escritor de su formato y el archivo de carpeta.

    Si el escritor de su destino no sabe guardar alguno de sus campos pendientes
    ('fields_for'), esos campos pasan a otro 'WriteItem' del mismo archivo con destino
    FOLDER_FILE ('only' dice los campos de cada parte). Si no sabe ninguno, el elemento
    entero va al archivo de carpeta. Lo normal es que no se parta nada: se devuelve tal cual.

    Returns:
        Las partes, en el orden de los elementos (la del formato, antes que la de carpeta).
    """
    fallback = writers.get(UserDataDestination.FOLDER_FILE)
    parts: list[WriteItem] = []
    for item in items:
        writer = writers[item.destination]
        known = writer.fields_for(item)
        if known is None or fallback is None or writer is fallback:
            parts.append(item)
            continue
        pending = frozenset(item.wanted)
        rest = pending - known
        if not rest:
            parts.append(item)
            continue
        # La parte que va al archivo de carpeta: el mismo archivo, con sus campos y sin
        # nada del resultado de la otra (su propio 'db_updates')
        extra = replace(
            item, destination=UserDataDestination.FOLDER_FILE, only=rest, db_updates={}
        )
        if pending & known:
            item.only = pending & known
            parts.append(item)
        parts.append(extra)
    return parts


def default_writers(
    runner_factory: Callable[[], ExifToolRunner] | None = None,
    preferred_mp3: TagSet = DEFAULT_MP3_TAGS,
) -> dict[UserDataDestination, UserDataWriter]:
    """Los escritores de un trabajo: uno por destino ('policy.destination_for').

    El orden es el de escritura: primero el archivo de carpeta, después los XMP (un mismo
    escritor para el incrustado y el sidecar) y las etiquetas de las canciones.

    Args:
        runner_factory: Crea el lector de ExifTool (por defecto, 'ExifToolRunner()').
        preferred_mp3: La etiqueta preferida de los MP3 (Opciones > Música): la que se crea
            en uno al que le falta el ID3v2.
    """
    # Aquí y no arriba: 'audio_writer' importa este módulo (su interfaz y 'WriteItem')
    from core.userdata.audio_writer import AudioFileWriter

    xmp = XmpFileWriter(runner_factory)
    return {
        UserDataDestination.FOLDER_FILE: FolderFileWriter(),
        UserDataDestination.XMP_EMBEDDED: xmp,
        UserDataDestination.XMP_SIDECAR: xmp,
        UserDataDestination.AUDIO_TAGS: AudioFileWriter(preferred_mp3),
    }
