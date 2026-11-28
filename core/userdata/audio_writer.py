"""Escritor de las etiquetas de las canciones en la cola de escritura (MP3, FLAC, Ogg, Opus,
M4A).

Este módulo NO depende de Qt ni de la base de datos. Une la cola de escritura
('sync.write_pending_user_data', que reparte los archivos pendientes entre los escritores
de 'writers.py') con el motor que escribe dentro del propio archivo
('core/audio/tag_writer.write_tags', MUS 6.1c).

Su destino, AUDIO_TAGS ('policy.py'), es PARTIDO: este escritor guarda los campos de las
etiquetas ('audio_fields.AUDIO_TAG_COLUMNS': título, artista, comentario, álbum, artista
del álbum, pista, disco, género y compositor); la valoración, la marca, el color, las
palabras clave y lo demás van al '.arca.json' ('fields_for' y 'writers.split_items').

Por cada canción (docs/MOD_MUSICA.md §5, MUS 6.2b):
    - Si había cambiado fuera de la aplicación desde el último escaneo (otro tamaño u otra
      fecha), se escribe igual lo pendiente y se marca para releerla entera ('rescan'),
      como hace el escritor de XMP.
    - 'write_tags' con lo pendiente ('audio_fields.tag_changes') y la etiqueta preferida de
      las Opciones (la recibe al crearse: 'writers.default_writers').
    - Si va bien: 'ok'. Si cambió el archivo, su tamaño y su fecha nuevos ('db_updates': así
      el escáner no lo toma por un cambio externo, ni se regenera su miniatura); y si
      cambió su tipo de etiqueta (se le creó el ID3v2), 'reread': el catálogo relee sus
      metadatos (su «Tipo de etiqueta»).
    - Si no ('AudioWriteError'): el archivo queda como estaba y el motivo va a 'message';
      sigue pendiente y se reintenta la próxima vez. Lo que no vale de lo editado (sería un
      error de la aplicación, no del archivo) también va a 'message', para no parar el
      trabajo por una canción.
    - Sin mutagen: 'unavailable' y todo queda pendiente ('deferred'), como sin ExifTool.
    - Si se cancela el trabajo: lo que falte, 'deferred'.
Nunca lanza una excepción por una canción.

1.0.2 Escribe también M4A: lo atiende el motor (MUS 6.4); aquí solo cambia la
      documentación.
1.0.1 Escribe también FLAC, Ogg y Opus: los atiende el motor (MUS 6.3b); aquí solo cambia
      la documentación.
1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 6.2b).

Prueba (la de 'sync.py' lo ejercita de ida y vuelta, con un MP3):
    python -m core.userdata.sync
"""

__version__ = "1.0.2"
__all__ = ["AudioFileWriter"]

# Librerías estándar
import threading
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.audio.tag_set import DEFAULT_MP3_TAGS, TagSet
from core.userdata.audio_fields import AUDIO_TAG_COLUMNS, tag_changes
from core.userdata.writers import UserDataWriter, WriteItem


class AudioFileWriter(UserDataWriter):
    """Las etiquetas de las canciones, dentro del propio archivo (ver el docstring del
    archivo). mutagen se importa al primer lote: si no está, sus elementos quedan
    pendientes y 'unavailable' pasa a True."""

    name: ClassVar[str] = "audio_tags"

    def __init__(self, preferred: TagSet = DEFAULT_MP3_TAGS) -> None:
        """Args:
            preferred: La etiqueta preferida de los MP3 (Opciones > Música): la que se crea
                en uno al que le falta el ID3v2.
        """
        super().__init__()
        self._preferred = preferred

    def fields_for(self, item: WriteItem) -> frozenset[str] | None:
        return AUDIO_TAG_COLUMNS

    def write(self, items: list[WriteItem], cancel_event: threading.Event | None = None) -> None:
        if not items:
            return
        try:
            from core.audio import tag_writer  # necesita mutagen
        except ImportError as error:
            logger.warning(f"Sin mutagen no se escriben las etiquetas de las canciones: {error}")
            self.unavailable = True
            for item in items:
                item.deferred = True
            return
        for item in items:
            if cancel_event is not None and cancel_event.is_set():
                item.deferred = True  # cancelado antes de llegar a ella: sigue pendiente
                continue
            self._write_one(item, tag_writer)

    def _write_one(self, item: WriteItem, tag_writer: Any) -> None:
        """Escribe una canción y apunta en 'item' cómo ha ido."""
        try:
            before = item.path.stat()
        except FileNotFoundError:
            item.message = "El archivo no existe (se marcará al reescanear la carpeta)"
            return
        except OSError as error:
            item.message = f"No se puede acceder al archivo ({error.strerror or error})"
            return
        # ¿Cambió fuera de la aplicación desde el último escaneo? (Mp3tag, otro programa)
        if (before.st_size, before.st_mtime_ns) != (item.file_size, item.file_mtime_ns):
            item.rescan = True

        changes = tag_changes(item.wanted, item.metadata)
        try:
            result = tag_writer.write_tags(item.path, changes, self._preferred)
        except tag_writer.AudioWriteError as error:
            item.message = str(error)
        except (ValueError, TypeError) as error:
            # Lo editado no vale: un error de la aplicación (se ve en el registro)
            logger.error(f"No se escriben las etiquetas de «{item.path}»: {error}")
            item.message = f"Valor no válido: {error}"
        else:
            item.ok = True
            item.written = result.written
            item.reread = result.tags_changed

        if not (item.written or item.rescan):
            return  # el archivo no ha cambiado: nada que anotar
        # Se anota SIEMPRE el estado actual (como el escritor de XMP): así la próxima pasada
        # no vuelve a ver un «cambio externo» en el mismo archivo
        try:
            state = item.path.stat()
        except OSError:
            return  # se corregirá en el próximo escaneo
        item.db_updates = {"file_size": state.st_size, "file_mtime_ns": state.st_mtime_ns}
