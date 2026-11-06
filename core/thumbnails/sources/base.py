"""Contrato común de los orígenes de miniaturas.

Este módulo NO depende de Qt ni de la base de datos. Un "origen" (source) sabe
obtener LA IMAGEN de la que se sacarán las miniaturas de un elemento del catálogo:

    - una foto JPEG/PNG/WebP           -> el propio archivo (PillowSource)
    - un HEIC                          -> el propio archivo, vía pillow-heif (HeifSource)
    - un RAW                           -> la vista previa que lleva incrustada
                                          (RawPreviewSource, con ExifTool)
    - (futuro) una canción             -> la carátula incrustada en el MP3/M4A
    - (futuro) una película            -> el póster descargado o un marcador de posición

El origen NO reduce, ni cambia de espacio de color, ni guarda nada: eso es común a
todos y lo hace 'generator.py'. Solo tiene que devolver una 'LoadedImage' ya DERECHA
(con la orientación aplicada).

Cómo añadir un formato o un tipo de medio nuevo: ver 'core/thumbnails/LEEME.md'.
"""

__version__ = "1.0.0"
__all__ = [
    "LoadedImage",
    "ThumbnailError",
    "ThumbnailRequest",
    "ThumbnailSource",
    "UnsupportedSourceError",
]

# Librerías estándar
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

# Librerías de terceros
from PIL import Image

# Módulos del proyecto
from core.catalog.media_types import MediaType


class ThumbnailError(Exception):
    """No se pudo obtener o generar la miniatura de un archivo.

    El mensaje es corto y en español: se guarda en la tabla 'scan_errors' (fase
    'thumbnail') y se muestra en la lista de errores.
    """


class UnsupportedSourceError(ThumbnailError):
    """Este origen no puede leer el archivo, pero no por culpa del archivo.

    Ejemplos: falta una librería opcional (pillow-heif) o ExifTool no está instalado.
    Cuando hay varios orígenes para un formato, se prueba con el siguiente.
    """


@dataclass(frozen=True, slots=True)
class ThumbnailRequest:
    """Lo que hay que saber de un elemento para generar sus miniaturas.

    Attributes:
        media_id: Identificador del elemento ('media_items.id'); determina la ruta
            de sus miniaturas en la caché.
        media_type: Tipo de medio del elemento.
        path: Ruta completa del archivo original.
    """

    media_id: int
    media_type: MediaType
    path: Path

    @property
    def extension(self) -> str:
        """Extensión del archivo en minúsculas y sin punto ('' si no tiene)."""
        return self.path.suffix.lower().lstrip(".")


@dataclass(slots=True)
class LoadedImage:
    """La imagen de partida que entrega un origen.

    Attributes:
        image: Imagen de Pillow, ya derecha (orientación aplicada). Puede venir
            reducida si el origen supo decodificarla más rápido así (los JPEG), pero
            nunca por debajo de lo que se le pidió ('target_side').
        icc_profile: Perfil de color ICC incrustado, o None (se asume sRGB).
        source_name: Nombre del origen (y, si procede, de dónde sacó la imagen).
        original_size: Tamaño de la imagen original completa, ya derecha, si se
            conoce. Es solo informativo.
    """

    image: Image.Image
    icc_profile: bytes | None = None
    source_name: str = ""
    original_size: tuple[int, int] | None = None


class ThumbnailSource(ABC):
    """Origen de la imagen de partida para un tipo de medio (y, opcionalmente, unas extensiones).

    Attributes:
        name: Nombre corto del origen ('pillow', 'heif', 'raw_preview'...).
        media_type: Tipo de medio para el que sirve.
        extensions: Extensiones que sabe leer, en minúsculas y sin punto. None
            significa "cualquier archivo de ese tipo de medio" (p. ej. el origen de
            los pósters de vídeo, que no depende de la extensión).
    """

    name: ClassVar[str]
    media_type: ClassVar[MediaType]
    extensions: ClassVar[frozenset[str] | None] = None

    def is_available(self) -> bool:
        """Indica si el origen puede funcionar (librería opcional o programa externo presentes)."""
        return True

    @abstractmethod
    def load(self, request: ThumbnailRequest, target_side: int) -> LoadedImage:
        """Obtiene la imagen de partida de un elemento.

        Debe ser seguro llamarlo desde un hilo secundario (no tocar la interfaz).

        Args:
            request: El elemento del que se quiere la imagen.
            target_side: Lado largo del mayor tamaño que se va a generar. Es solo una
                pista: sirve para decodificar reducido (los JPEG) y ahorrar tiempo. El
                origen puede devolver una imagen más grande, nunca una más pequeña que
                eso salvo que el original lo sea.

        Raises:
            FileNotFoundError: Si el archivo ya no existe.
            UnsupportedSourceError: Si este origen no puede leerlo (falta una
                librería...) y conviene probar con el siguiente.
            ThumbnailError: Si el archivo está dañado o no contiene imagen utilizable.
        """
