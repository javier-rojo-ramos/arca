"""Origen de miniaturas para archivos RAW: la vista previa JPEG que llevan incrustada.

Este módulo NO depende de Qt. Casi todos los RAW (DNG, NEF, CR2, CR3, ARW, ORF, RW2,
PEF, RAF...) guardan dentro uno o varios JPEG ya revelados por la cámara. ExifTool los
extrae en milisegundos; revelar el RAW de verdad (demosaico) costaría uno o dos
segundos por archivo y obligaría a depender de LibRaw. Es lo que hacen también los
exploradores de fotos rápidos.

Cómo funciona, con UNA llamada a ExifTool por archivo:

    exiftool -j -n -G1 -a -b -JpgFromRaw -PreviewImage -OtherImage -ThumbnailImage -Orientation

Con '-b' en modo JSON, los datos binarios salen codificados en base64 ("base64:/9j/4A...").
Se decodifican todas las vistas previas que haya, se mide cada una SIN decodificar los
píxeles y se usa la de más píxeles. Un mismo RAW puede traer varias (p. ej. el DNG de
Lightroom: 1024 px incrustada, más una miniatura de 256 px; la de una Nikon, además,
trae la suya en el bloque MakerNotes).

Orientación: las vistas previas de los RAW suelen salir SIN orientación propia, y la
posición de la cámara figura en el RAW (etiqueta 'IFD0:Orientation'). Se aplica esa,
salvo que la vista previa traiga la suya, que entonces manda.

Límite que hay que conocer: la vista previa suele ser MENOR que el sensor (1024 px en
ese DNG, 1620 px en los CR3 antiguos...). 'plan_sizes' nunca amplía, así que de un RAW
con una vista previa de 1024 px se generan los tamaños de 160 y 480, y uno de 1024 en
lugar del de 1200. Si algún día esto no basta, se añadirá un segundo origen que revele
el RAW con LibRaw (rawpy) y se probará solo cuando falle este o la vista previa sea
pequeña.
"""

__version__ = "1.0.0"
__all__ = ["RAW_EXTENSIONS", "RawPreviewSource"]

# Librerías estándar
import base64
import binascii
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger
from PIL import Image

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.exiftool_runner import (
    ExifToolError,
    ExifToolLaunchError,
    ExifToolRunner,
    FileMetadata,
)
from core.thumbnails.sources.base import (
    LoadedImage,
    ThumbnailError,
    ThumbnailRequest,
    ThumbnailSource,
    UnsupportedSourceError,
)
from core.thumbnails.sources.pillow_source import load_pillow_image

# Extensiones de RAW. Para que un archivo llegue al catálogo, 'media_detector.py' también
# tiene que conocer su extensión (DEFAULT_EXTENSION_TO_TYPE); aquí hay alguna más por si se añade.
RAW_EXTENSIONS: frozenset[str] = frozenset(
    {
        "dng", "nef", "nrw", "cr2", "cr3", "crw", "arw", "srf", "sr2", "orf",
        "rw2", "pef", "raf", "srw", "rwl", "3fr", "erf", "mrw", "x3f", "iiq",
    }
)  # fmt: skip

# Etiquetas de ExifTool que pueden contener una vista previa
_PREVIEW_TAGS: tuple[str, ...] = ("JpgFromRaw", "PreviewImage", "OtherImage", "ThumbnailImage")

# Argumentos que se añaden a la llamada de ExifTool (ver la cabecera del módulo)
_EXIFTOOL_ARGUMENTS: tuple[str, ...] = (
    "-b",
    *(f"-{tag}" for tag in _PREVIEW_TAGS),
    "-Orientation",
)

_BASE64_PREFIX = "base64:"


@dataclass(frozen=True, slots=True)
class _Preview:
    """Una vista previa encontrada dentro de un RAW."""

    tag: str  # con su grupo, p. ej. 'SubIFD1:PreviewImage'
    data: bytes
    size: tuple[int, int]

    @property
    def pixels(self) -> int:
        return self.size[0] * self.size[1]


class RawPreviewSource(ThumbnailSource):
    """Extrae con ExifTool la mayor vista previa incrustada de un RAW."""

    name: ClassVar[str] = "raw_preview"
    media_type: ClassVar[MediaType] = MediaType.PHOTO
    extensions: ClassVar[frozenset[str] | None] = RAW_EXTENSIONS

    def __init__(self, runner: ExifToolRunner) -> None:
        """Crea el origen.

        Args:
            runner: Lector de ExifTool ya configurado (el mismo que usa la lectura de metadatos).
        """
        self._runner = runner

    def load(self, request: ThumbnailRequest, target_side: int) -> LoadedImage:
        """Extrae y decodifica la mayor vista previa. Ver 'ThumbnailSource.load'."""
        if not request.path.is_file():
            raise FileNotFoundError(str(request.path))

        metadata = self._read(request.path)
        previews = self._find_previews(metadata.tags)
        if not previews:
            raise ThumbnailError(
                "El RAW no contiene ninguna vista previa incrustada utilizable"
            )
        best = max(previews, key=lambda preview: preview.pixels)
        found = ", ".join(f"{p.tag} {p.size[0]}x{p.size[1]}" for p in previews)
        logger.debug(f"{request.path.name}: vistas previas [{found}]; se usa {best.tag}")

        return load_pillow_image(
            io.BytesIO(best.data),
            target_side,
            source_name=f"{self.name}:{best.tag.rpartition(':')[2]}",
            fallback_orientation=self._raw_orientation(metadata.tags),
        )

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    def _read(self, path: Path) -> FileMetadata:
        """Pide a ExifTool las vistas previas y la orientación del RAW."""
        try:
            results = self._runner.read([path], tags=_EXIFTOOL_ARGUMENTS)
        except ExifToolLaunchError as exc:
            # Fallo general (no se puede ejecutar): no es culpa del archivo
            raise UnsupportedSourceError(f"No se pudo ejecutar ExifTool: {exc}") from exc
        except ExifToolError as exc:
            raise ThumbnailError(f"ExifTool no pudo leer el archivo: {exc}") from exc

        metadata = results.get(path)
        if metadata is None or metadata.error:
            reason = metadata.error if metadata is not None else "sin datos"
            raise ThumbnailError(f"ExifTool no pudo leer el archivo: {reason}")
        return metadata

    @staticmethod
    def _find_previews(tags: dict[str, Any]) -> list[_Preview]:
        """Decodifica del JSON de ExifTool todas las vistas previas que Pillow sepa abrir."""
        previews: list[_Preview] = []
        for key, value in tags.items():
            if key.rpartition(":")[2] not in _PREVIEW_TAGS:
                continue
            # Sin '-b' (o si el dato no es binario) ExifTool devuelve un texto del estilo
            # "(Binary data 14671 bytes...)": no es una vista previa
            if not isinstance(value, str) or not value.startswith(_BASE64_PREFIX):
                continue
            try:
                data = base64.b64decode(value[len(_BASE64_PREFIX) :])
                # Solo se lee la cabecera: no se decodifican los píxeles
                with Image.open(io.BytesIO(data)) as probe:
                    size = probe.size
            except (binascii.Error, OSError, ValueError, SyntaxError):
                # P. ej. las vistas previas JPEG XL de los DNG recientes, que Pillow no abre
                logger.debug(f"Vista previa '{key}' no utilizable; se ignora.")
                continue
            previews.append(_Preview(key, data, size))
        return previews

    @staticmethod
    def _raw_orientation(tags: dict[str, Any]) -> int:
        """Orientación EXIF (1-8) que indica el RAW; 1 si no consta."""
        value = tags.get("IFD0:Orientation")
        if value is None:
            value = next(
                (v for k, v in tags.items() if k.rpartition(":")[2] == "Orientation"),
                None,
            )
        try:
            code = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 1
        return code if 1 <= code <= 8 else 1
