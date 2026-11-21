"""Origen de miniaturas basado en Pillow: JPEG, PNG, WebP, GIF, BMP, TIFF, AVIF y JPEG 2000.

Este módulo NO depende de Qt. Contiene además 'load_pillow_image', la función que
abre, decodifica y endereza una imagen con Pillow, y que reutilizan los otros
orígenes que acaban teniendo una imagen "normal" entre manos (HEIC, vista previa de
un RAW).

Los JPEG se decodifican REDUCIDOS ('draft'): para una foto de 24 megapíxeles de la
que solo hacen falta 2560 px, la decodificación a 1/2 de tamaño es mucho más rápida
que la completa.

Limitaciones conocidas de Pillow: no abre los TIFF de 16 bits por canal en color, y
rechaza las imágenes de más de ~179 megapíxeles (protección contra "bombas de
descompresión"). En ambos casos el archivo se anota como error de miniatura. AVIF y
JPEG 2000 dependen de las librerías con que se compiló Pillow (las ruedas oficiales de
Pillow 12 las traen: 'PIL.features.check("avif")'); sin ellas, el archivo da el error
«formato no reconocido».

1.2.0 Un TIFF con orientación salía girado dos veces (miniatura, vista individual y 1:1):
      Pillow 12 ya lo endereza al cargarlo. Sin subir 'THUMBNAIL_VERSION' (decidido por
      el autor el 21/11/2026): ningún TIFF del catálogo tenía una orientación distinta de 1;
      si alguno tuviera ya miniatura, se arregla con «Regenerar miniaturas».
1.1.0 AVIF y JPEG 2000 ('.jp2'), que ya se catalogaban como fotos. Comprobado el
      19/11/2026 con Pillow 12.3: los dos se leen, y el AVIF con su orientación.
"""

__version__ = "1.2.0"
__all__ = ["PillowSource", "load_pillow_image"]

# Librerías estándar
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, ClassVar

# Librerías de terceros
from PIL import Image, UnidentifiedImageError

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.thumbnails.imaging import apply_orientation, draft_size, read_orientation
from core.thumbnails.sources.base import (
    LoadedImage,
    ThumbnailError,
    ThumbnailRequest,
    ThumbnailSource,
)


@contextmanager
def translated_errors() -> Iterator[None]:
    """Convierte los errores de Pillow y del disco en 'ThumbnailError' con un mensaje legible.

    'FileNotFoundError' se deja pasar tal cual: quien llama lo trata como "archivo
    desaparecido".
    """
    try:
        yield
    except FileNotFoundError:
        raise
    except PermissionError as exc:
        raise ThumbnailError("Sin permiso para leer el archivo") from exc
    except UnidentifiedImageError as exc:
        raise ThumbnailError("No es una imagen válida o su formato no se reconoce") from exc
    except Image.DecompressionBombError as exc:
        raise ThumbnailError("La imagen es demasiado grande para procesarla") from exc
    except (OSError, SyntaxError, ValueError, EOFError) as exc:
        # Archivo truncado, cabecera corrupta, datos inconsistentes...
        raise ThumbnailError(
            f"Imagen dañada o incompleta ({type(exc).__name__})"
        ) from exc


def load_pillow_image(
    file: str | Path | IO[bytes],
    target_side: int,
    *,
    source_name: str,
    fallback_orientation: int = 1,
) -> LoadedImage:
    """Abre una imagen con Pillow, la decodifica (reducida si es JPEG) y la endereza.

    Args:
        file: Ruta del archivo o un objeto de archivo binario (p. ej. 'BytesIO').
        target_side: Lado largo del mayor tamaño que se va a generar (pista para decodificar reducido).
        source_name: Nombre que se anotará en 'LoadedImage.source_name'.
        fallback_orientation: Orientación EXIF a aplicar si la imagen NO trae la suya.
            Se usa con las vistas previas de los RAW, que suelen salir sin orientación
            y dependen de la que indique el RAW.

    Raises:
        FileNotFoundError, ThumbnailError: ver 'translated_errors'.
    """
    with translated_errors(), Image.open(file) as image:
        icc_profile = image.info.get("icc_profile")

        # La propia orientación de la imagen manda; si no trae ninguna (1), la de respaldo
        own_orientation = read_orientation(image)
        orientation = own_orientation if own_orientation != 1 else fallback_orientation

        original_size = image.size
        if orientation >= 5:  # giro de 90°: ancho y alto se intercambian
            original_size = (original_size[1], original_size[0])

        # Decodificación reducida (solo hace algo con los JPEG; con el resto no tiene efecto)
        image.draft(image.mode, draft_size(image.size, target_side))
        image.load()

        # Pillow endereza él mismo algunos formatos al cargarlos: con Pillow 12, los TIFF
        # ('load_end' aplica 'exif_transpose' y quita la orientación). Si la orientación propia
        # ha desaparecido al cargar, la imagen ya está derecha y no se gira otra vez (girada
        # dos veces quedaba de lado o boca abajo); su tamaño ya es el de la imagen derecha y
        # completa (los TIFF no se decodifican reducidos)
        if own_orientation != 1 and read_orientation(image) == 1:
            orientation = 1
            original_size = image.size
        upright = apply_orientation(image, orientation)

    return LoadedImage(
        image=upright,
        icc_profile=icc_profile,
        source_name=source_name,
        original_size=original_size,
    )


class PillowSource(ThumbnailSource):
    """Lee con Pillow las imágenes de uso común."""

    name: ClassVar[str] = "pillow"
    media_type: ClassVar[MediaType] = MediaType.PHOTO
    extensions: ClassVar[frozenset[str] | None] = frozenset(
        {"jpg", "jpeg", "jpe", "jfif", "png", "gif", "bmp", "tif", "tiff", "webp", "avif", "jp2"}
    )

    def _ensure_ready(self) -> None:
        """Punto de enganche para los orígenes derivados que necesitan preparar algo antes de abrir."""

    def load(self, request: ThumbnailRequest, target_side: int) -> LoadedImage:
        """Carga la imagen del propio archivo. Ver 'ThumbnailSource.load'."""
        self._ensure_ready()
        return load_pillow_image(
            str(request.path), target_side, source_name=self.name
        )
