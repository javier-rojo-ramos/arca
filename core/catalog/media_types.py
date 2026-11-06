"""Tipos de medio que puede gestionar el catálogo.

Es el único sitio donde se define qué tipos existen. Para ampliar la aplicación
(por ejemplo a cómics o documentos), basta con añadir un valor aquí: las carpetas
de caché se crean solas a partir de esta lista.

Los valores de texto ("photo", "video"...) son los que se guardan en la columna
'media_type' de la base de datos, así que NO deben cambiarse una vez creados
catálogos reales.

'media_type' es el tipo TÉCNICO del archivo (qué es: una foto, un vídeo, un track...).
No confundir con la biblioteca a la que pertenece (qué sidebar lo gestiona: un vídeo
del móvil es de la biblioteca de imágenes; una película, de la de vídeo). La biblioteca
se añadirá más adelante como un concepto aparte.

1.01 Se añade TRACK ("track"): rutas GPS (GPX).
"""

__version__ = "1.01"
# ruff: noqa: RUF022
__all__ = ["MediaType", "CACHEABLE_MEDIA_TYPES"]

# Librerías estándar
from enum import StrEnum


class MediaType(StrEnum):
    """Tipo de medio de un elemento del catálogo.

    Al ser un 'StrEnum', cada miembro se comporta también como un 'str': se puede
    pasar directamente a SQLite y usar para construir rutas (p. ej. "cache/photo").
    """

    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    EBOOK = "ebook"
    TRACK = "track"  # ruta GPS (GPX): puntos con posición, altitud y hora
    OTHER = "other"


# Tipos que se catalogan y tienen su propia subcarpeta en 'cache/'
# 'OTHER' se excluye porque no se cataloga ni genera nada en caché
CACHEABLE_MEDIA_TYPES: tuple[MediaType, ...] = (
    MediaType.PHOTO,
    MediaType.VIDEO,
    MediaType.AUDIO,
    MediaType.EBOOK,
    MediaType.TRACK,
)
