"""Registro de extractores: qué extractor lee cada tipo de medio.

>>> AQUÍ SE REGISTRA LA LECTURA DE UN TIPO DE MEDIO NUEVO (vídeo, audio, ebooks...). <<<

Este módulo NO depende de Qt. Para añadir un tipo nuevo basta con crear su extractor
(ver 'core/metadata/LEEME.md') y registrarlo en 'default_registry()'.

Imágenes: se usa ExifTool (lee RAW, HEIC, XMP, IPTC...). Si ExifTool no está instalado
o no funciona, se usa el extractor con Pillow, que solo lee JPEG, PNG, TIFF, WebP, GIF y
BMP y solo EXIF; los demás formatos quedan "sin soporte todavía" hasta que haya
ExifTool, y entonces se leen solos (la versión del extractor de ExifTool es mayor).

Tracks GPS (GPX): extractor propio, sin ExifTool (el GPX es XML y se lee directamente).

Vídeos: solo con ExifTool (core/metadata/video/). Sin él, siguen pendientes y se leen
solos en cuanto lo haya.

2.2.1 Docstring de 'default_registry' al día (el vídeo ya tiene extractor).
2.2.0 Se registra el extractor de vídeo (VideoExtractor), si hay ExifTool.
2.1.0 Se registra el extractor de tracks (TrackExtractor).
"""

__version__ = "2.2.1"
__all__ = ["ExtractorRegistry", "default_registry"]

# Librerías estándar
from collections.abc import Iterator

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.base import MetadataExtractor
from core.metadata.exiftool_runner import ExifToolError, ExifToolRunner
from core.metadata.image.extractor import ImageExtractor
from core.metadata.image.pillow_extractor import ImageMetadataExtractor as PillowImageExtractor
from core.metadata.track.extractor import TrackExtractor
from core.metadata.video.extractor import VideoExtractor


class ExtractorRegistry:
    """Colección de extractores, con uno como máximo por tipo de medio."""

    def __init__(self) -> None:
        self._extractors: dict[MediaType, MetadataExtractor] = {}

    def register(self, extractor: MetadataExtractor) -> None:
        """Añade un extractor (sustituye al que hubiera para ese tipo de medio)."""
        self._extractors[extractor.media_type] = extractor

    def get(self, media_type: MediaType | str) -> MetadataExtractor | None:
        """Devuelve el extractor de un tipo de medio, o None si no hay ninguno.

        Acepta el valor en texto ('photo'), tal como viene de la base de datos.
        """
        try:
            return self._extractors.get(MediaType(media_type))
        except ValueError:
            return None

    def __iter__(self) -> Iterator[MetadataExtractor]:
        return iter(self._extractors.values())

    def __len__(self) -> int:
        return len(self._extractors)


def default_registry() -> ExtractorRegistry:
    """Crea el registro con todos los extractores disponibles.

    Los tipos sin extractor (de momento audio y ebooks) se ignoran: sus
    archivos siguen pendientes hasta que se registre uno.
    """
    registry = ExtractorRegistry()

    # --- Imágenes: ExifTool si funciona; si no, Pillow ---
    # --- Vídeos: solo con ExifTool (sin él, siguen pendientes hasta que lo haya) ---
    try:
        runner = ExifToolRunner()
        runner.version()  # comprueba que se puede ejecutar de verdad
        registry.register(ImageExtractor(runner))
        registry.register(VideoExtractor(runner))
    except ExifToolError as error:
        logger.warning(
            f"ExifTool no está disponible ({str(error).splitlines()[0]}). Las imágenes se "
            "leen con Pillow: solo JPEG, PNG, TIFF, WebP, GIF y BMP, y solo EXIF."
        )
        registry.register(PillowImageExtractor())

    # --- Tracks GPS (GPX): no dependen de ExifTool ---
    registry.register(TrackExtractor())

    # --- Audio, ebooks...: se registrarán aquí, p. ej.:
    #     registry.register(AudioExtractor(runner))

    return registry
