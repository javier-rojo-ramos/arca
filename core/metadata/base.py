"""Contrato común de los extractores de metadatos (uno por tipo de medio).

Este módulo NO depende de Qt ni de la base de datos: un extractor solo recibe rutas
de archivos y devuelve diccionarios de valores. Quien los guarda en la base de datos
es 'processor.py'. La organización completa del paquete está en 'LEEME.md'.

Un extractor puede implementar solo 'extract' (un archivo cada vez) o, si su motor
es más eficiente por lotes (ExifTool lo es), sobrescribir también 'extract_batch'.
El procesador siempre llama a 'extract_batch'.

Cómo ampliar un extractor con campos nuevos: ver 'LEEME.md'.

2.0.2 'metadata_edit_pending' (migración 2) en 'PROTECTED_COLUMNS'.
2.0.1 Docstring de 'ExtractionResult': un título None ya no conserva el anterior (el
      procesador pone el nombre del archivo sin extensión).
"""

__version__ = "2.0.2"
__all__ = [
    "PROTECTED_COLUMNS",
    "ExtractionResult",
    "MetadataError",
    "MetadataExtractor",
    "UnsupportedFormatError",
]

# Librerías estándar
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

# Módulos del proyecto
from core.catalog.media_types import MediaType

# Columnas de 'media_items' que un extractor NUNCA puede escribir: las que describen
# el archivo en disco, las del usuario y las de control interno (BLOQUES A, C y D del
# esquema). El procesador rechaza cualquier extractor que intente escribirlas, y su
# autoprueba comprueba que todas existen realmente en la tabla.
# El resto de columnas de 'media_items' (BLOQUE B: metadatos extraídos) sí se pueden
# rellenar. Si algún día se añade una columna que sea del usuario, hay que añadirla
# aquí.
PROTECTED_COLUMNS: frozenset[str] = frozenset(
    {
        # Identidad y archivo en disco (BLOQUE A)
        "id",
        "storage_location_id",
        "relative_path",
        "file_name",
        "file_extension",
        "media_type",
        "mime_type",
        "file_size",
        "file_mtime_ns",
        "file_created_at",
        "hash_partial",
        "hash_full",
        "hash_verified_at",
        "is_missing",
        "sidecar_mtime_ns",
        # Datos del usuario (BLOQUE C)
        "rating",
        "flag",
        "color_label",
        "is_favorite",
        "is_archived",
        "user_notes",
        "play_count",
        "last_played_at",
        # Caché y control interno (BLOQUE D)
        "thumbnail_status",
        "thumbnail_mtime_ns",
        "thumbnail_version",
        "thumbnail_source",
        "scan_version",
        "last_scanned_at",
        "added_at",
        "updated_at",
        "user_data_pending",
        "keywords_pending",
        "metadata_edit_pending",
    }
)


class MetadataError(Exception):
    """No se pudieron leer los metadatos de un archivo.

    El mensaje es corto y en español: se guarda en la tabla 'scan_errors' y se
    muestra en la lista de errores.
    """


class UnsupportedFormatError(MetadataError):
    """El extractor no sabe leer este formato (todavía).

    No es un fallo del archivo: el procesador lo cuenta aparte y lo marca como
    procesado con la versión actual, de modo que cuando el extractor aprenda el
    formato (y suba su versión) se vuelva a intentar.
    """


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Lo que un extractor ha leído de un archivo.

    Attributes:
        common: Valores para columnas de 'media_items' (nunca las de
            'PROTECTED_COLUMNS'). Un valor None deja la columna vacía, salvo
            'title', que nunca se vacía (es NOT NULL): con None, el procesador pone el
            nombre del archivo sin extensión.
        details: Valores para la tabla de detalles del tipo (columna -> valor).
        user_data: Datos del USUARIO que el archivo trae consigo (columna -> valor,
            con 'rating', 'flag' y 'color_label'; None si el archivo no los trae) y,
            en las imágenes, 'keywords' (un 'FileKeywords' de 'keyword_tags.py').
            El extractor NUNCA escribe el BLOQUE C: solo transporta estos valores y
            es el procesador quien decide si los aplica (ver
            'core.userdata.sync.apply_file_user_data').
    """

    common: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    user_data: dict[str, Any] = field(default_factory=dict)


class MetadataExtractor(ABC):
    """Extractor de metadatos de un tipo de medio.

    Attributes:
        media_type: Tipo de medio que sabe leer.
        version: Versión del extractor. Se guarda en 'media_items.scan_version'
            de cada archivo procesado. Súbela cada vez que el extractor lea
            campos nuevos: los archivos con una versión menor se reprocesan.
        details_table: Tabla 1:1 con 'media_items' donde van los campos
            específicos del tipo ('photo_details'...), o None si no tiene.
    """

    media_type: ClassVar[MediaType]
    version: ClassVar[int]
    details_table: ClassVar[str | None] = None

    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult:
        """Lee los metadatos de un archivo.

        Debe ser seguro llamarlo desde un hilo secundario (no tocar la interfaz).

        Args:
            path: Ruta completa del archivo.

        Raises:
            FileNotFoundError: Si el archivo ya no existe.
            UnsupportedFormatError: Si no sabe leer ese formato todavía.
            MetadataError: Si el archivo está dañado o no se puede interpretar.
        """

    def extract_batch(
        self, paths: Sequence[Path], cancel_event: threading.Event | None = None
    ) -> list[ExtractionResult | Exception | None]:
        """Lee los metadatos de varios archivos.

        La implementación por defecto llama a 'extract' archivo a archivo. Un
        extractor cuyo motor sea más rápido por lotes la sobrescribe.

        Args:
            paths: Rutas completas de los archivos.
            cancel_event: Si se activa, deja de leer.

        Returns:
            Una lista del mismo tamaño y orden que 'paths'. Cada elemento es:
            el 'ExtractionResult' si se leyó bien; la excepción que corresponda
            (FileNotFoundError, UnsupportedFormatError, MetadataError...) si ese
            archivo falló, SIN lanzarla (un archivo malo no debe parar a los
            demás); o None si no se llegó a leer por haberse cancelado.
        """
        results: list[ExtractionResult | Exception | None] = []
        for path in paths:
            if cancel_event is not None and cancel_event.is_set():
                results.append(None)
                continue
            try:
                results.append(self.extract(path))
            except Exception as exc:  # noqa: BLE001 - un archivo malo no debe parar a los demás
                results.append(exc)
        return results
