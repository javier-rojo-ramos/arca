"""Registro de orígenes: qué origen lee cada tipo de medio y cada extensión.

>>> AQUÍ SE REGISTRA LA LECTURA DE UN FORMATO O TIPO DE MEDIO NUEVO. <<<

Este módulo NO depende de Qt. Para soportar un formato nuevo (PSD, AVIF...) o un tipo
de medio nuevo (carátulas de audio, pósters de vídeo) basta con escribir su origen en
'core/thumbnails/sources/' y registrarlo en 'default_registry()'. Ver 'LEEME.md'.

Para cada archivo se obtiene una CADENA de orígenes (los que coinciden en tipo de medio
y extensión, en el orden en que se registraron) y se prueban uno tras otro hasta que
uno entrega la imagen. Así un formato puede tener un origen rápido y otro de respaldo.
"""

__version__ = "1.0.0"
__all__ = ["SourceRegistry", "default_registry"]

# Librerías estándar
from collections.abc import Iterator

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.exiftool_runner import ExifToolError, ExifToolRunner
from core.thumbnails.sources.base import ThumbnailSource
from core.thumbnails.sources.heif_source import HeifSource
from core.thumbnails.sources.pillow_source import PillowSource
from core.thumbnails.sources.raw_preview_source import RawPreviewSource


class SourceRegistry:
    """Colección ordenada de orígenes de miniaturas."""

    def __init__(self) -> None:
        self._sources: list[ThumbnailSource] = []

    def register(self, source: ThumbnailSource) -> None:
        """Añade un origen al final de la lista (los primeros registrados se prueban antes)."""
        self._sources.append(source)

    def chain_for(self, media_type: MediaType | str, extension: str) -> list[ThumbnailSource]:
        """Devuelve los orígenes que sirven para un archivo, en orden de prueba.

        Args:
            media_type: Tipo de medio del archivo (acepta el texto de la base de datos, 'photo').
            extension: Extensión en minúsculas y sin punto.

        Returns:
            Lista de orígenes; vacía si ninguno sabe leer ese archivo.
        """
        try:
            wanted_type = MediaType(media_type)
        except ValueError:
            return []
        return [
            source
            for source in self._sources
            if source.media_type == wanted_type
            and (source.extensions is None or extension in source.extensions)
        ]

    def __iter__(self) -> Iterator[ThumbnailSource]:
        return iter(self._sources)

    def __len__(self) -> int:
        return len(self._sources)


def default_registry(runner: ExifToolRunner | None = None) -> SourceRegistry:
    """Crea el registro con todos los orígenes disponibles.

    Los orígenes que dependen de algo que no está instalado (pillow-heif, ExifTool)
    se avisan una vez en el registro de la aplicación; los archivos que los necesitan
    quedarán sin miniatura, con un mensaje que explica el motivo.

    Args:
        runner: Lector de ExifTool a usar. Si no se indica, se busca ExifTool igual
            que hace la lectura de metadatos (variable EXIFTOOL_PATH, 'tools/exiftool', PATH).
    """
    registry = SourceRegistry()

    # --- Imágenes ---
    registry.register(PillowSource())  # JPG, PNG, WebP, GIF, BMP, TIFF
    registry.register(HeifSource())  # HEIC / HEIF (necesita pillow-heif o pi-heif)

    if runner is None:
        try:
            runner = ExifToolRunner()
            runner.version()  # comprueba que se puede ejecutar de verdad
        except ExifToolError as error:
            logger.warning(
                f"ExifTool no está disponible ({str(error).splitlines()[0]}): los RAW y DNG "
                "no tendrán miniatura."
            )
            runner = None
    if runner is not None:
        registry.register(RawPreviewSource(runner))  # DNG, NEF, CR2, CR3, ARW...

    # --- Pendiente, siguientes pasos: se registrarán aquí, p. ej.
    #     registry.register(AudioCoverSource(runner))   # carátulas de MP3 / M4A / FLAC
    #     registry.register(VideoPosterSource())        # póster descargado o marcador de posición

    for source in registry:
        if not source.is_available():
            logger.warning(f"El origen de miniaturas '{source.name}' no está disponible.")
    return registry
