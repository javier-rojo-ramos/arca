"""Origen de miniaturas de las canciones: su carátula incrustada, leída con mutagen.

Este módulo NO depende de Qt. La carátula es la misma imagen cuyos datos guarda el catálogo
(la primera «Portada» o, si no hay, la primera imagen: 'tag_reader.cover_index'), leída del
propio archivo con mutagen ('tag_reader.read_cover'), sin descodificar el audio. Después se
trata como una foto: 'load_pillow_image' la descodifica (reducida, si es un JPEG grande) y la
endereza, y 'generator.py' hace la escalera de siempre, con los cuatro tamaños (decidido por
el autor el 26/11/2026: como las fotos, por si más adelante se amplía a 1:1).

    - Sin carátula: 'NoImageError'. No es un error: la tarjeta lleva su marcador.
    - Carátula dañada (no es una imagen): 'ThumbnailError'.
    - Canción dañada o que mutagen no entiende: 'ThumbnailError'.
    - Sin mutagen: 'UnsupportedSourceError', como los HEIC sin pillow-heif.

Sirve para cualquier canción (extensions = None): mutagen reconoce el formato por su contenido
(MP3, M4A, FLAC, Ogg, Opus; uno sin etiquetas con imágenes, sin carátula).

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 3.1).

Prueba rápida (desde la raíz del proyecto; crea canciones mínimas en una carpeta temporal):
    python -m core.thumbnails.sources.audio_cover_source
"""

__version__ = "1.0.0"
__all__ = ["AudioCoverSource"]

# Librerías estándar
import io
from importlib.util import find_spec
from typing import ClassVar

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.thumbnails.sources.base import (
    LoadedImage,
    NoImageError,
    ThumbnailError,
    ThumbnailRequest,
    ThumbnailSource,
    UnsupportedSourceError,
)
from core.thumbnails.sources.pillow_source import load_pillow_image

_INSTALL_HINT = "Falta la librería para leer las canciones: instala 'mutagen' (pip install mutagen)."
_NO_COVER = "La canción no tiene carátula"


class AudioCoverSource(ThumbnailSource):
    """La carátula incrustada en una canción (ver el docstring del archivo)."""

    name: ClassVar[str] = "audio_cover"
    media_type: ClassVar[MediaType] = MediaType.AUDIO
    extensions: ClassVar[frozenset[str] | None] = None  # cualquier canción

    def is_available(self) -> bool:
        """True si mutagen está instalada."""
        return find_spec("mutagen") is not None

    def load(self, request: ThumbnailRequest, target_side: int) -> LoadedImage:
        """La carátula de la canción, ya derecha (ver 'ThumbnailSource.load').

        Raises:
            FileNotFoundError: Si la canción ya no está.
            NoImageError: Si no tiene carátula.
            UnsupportedSourceError: Si falta mutagen.
            ThumbnailError: Si la canción o su carátula están dañadas.
        """
        # mutagen se importa aquí: sin ella, el registro de orígenes se sigue pudiendo crear
        try:
            from core.audio.tag_reader import AudioReadError, read_cover
        except ImportError as error:
            raise UnsupportedSourceError(_INSTALL_HINT) from error
        if not request.path.is_file():
            raise FileNotFoundError(request.path)  # quien llama la marca como ausente
        try:
            data = read_cover(request.path)
        except AudioReadError as error:
            raise ThumbnailError(str(error)) from error
        if not data:
            raise NoImageError(_NO_COVER)
        return load_pillow_image(io.BytesIO(data), target_side, source_name=self.name)


if __name__ == "__main__":
    # Autoprueba (sin Qt). Ejecutar desde la raíz:  python -m core.thumbnails.sources.audio_cover_source
    import tempfile
    from pathlib import Path

    from mutagen.id3 import APIC, ID3
    from PIL import Image

    from core.thumbnails.cache import ThumbnailCache
    from core.thumbnails.generator import generate_thumbnails
    from core.thumbnails.registry import SourceRegistry
    from core.thumbnails.sizes import ALL_SIZES

    def jpeg(size: tuple[int, int], color: str) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, "JPEG")
        return buffer.getvalue()

    # Un MP3 mínimo: diez tramas de silencio (MPEG-1 Layer III, 128 kbps) con sus imágenes
    frame = b"\xff\xfb\x90\x00" + bytes(413)

    def song(path: Path, pictures: list[tuple[int, bytes]]) -> ThumbnailRequest:
        path.write_bytes(frame * 10)
        tags = ID3()
        for kind, data in pictures:
            tags.add(APIC(encoding=1, mime="image/jpeg", type=kind, desc=str(kind), data=data))
        tags.save(path, v2_version=3)
        return ThumbnailRequest(1, MediaType.AUDIO, path)

    source = AudioCoverSource()
    assert source.is_available() and source.extensions is None

    with tempfile.TemporaryDirectory(prefix="arca_cover_") as folder:
        root = Path(folder)
        # La portada (tipo 3), aunque la contraportada (tipo 4) vaya delante
        request = song(root / "a.mp3", [(4, jpeg((50, 40), "blue")), (3, jpeg((600, 600), "red"))])
        loaded = source.load(request, 2560)
        assert loaded.image.size == (600, 600) and loaded.source_name == "audio_cover"
        assert loaded.image.getpixel((300, 300))[0] > 200  # roja: la portada
        # Sin portada, la primera imagen
        assert source.load(song(root / "b.mp3", [(4, jpeg((50, 40), "blue"))]), 160).image.size == (50, 40)

        # Sin carátula; carátula que no es una imagen; canción dañada; canción que ya no está
        damaged = root / "rota.flac"
        damaged.write_bytes(b"fLaC\x00\x00")
        for bad, error_type in (
            (song(root / "sin.mp3", []), NoImageError),
            (song(root / "mala.mp3", [(3, b"no es una imagen")]), ThumbnailError),
            (ThumbnailRequest(2, MediaType.AUDIO, damaged), ThumbnailError),
            (ThumbnailRequest(3, MediaType.AUDIO, root / "no_existe.mp3"), FileNotFoundError),
        ):
            try:
                source.load(bad, 160)
                raise AssertionError(f"debía fallar: {bad.path.name}")
            except error_type as error:
                # La carátula dañada y la canción dañada son errores, no «sin carátula»
                assert error_type is NoImageError or not isinstance(error, NoImageError), bad

        # De punta a punta: los cuatro tamaños de siempre, sin ampliar (160, 480, 600, 600)
        registry = SourceRegistry()
        registry.register(source)
        result = generate_thumbnails(request, ThumbnailCache(root / "catalogo"), registry, ALL_SIZES)
        assert [max(t.width, t.height) for t in result.thumbnails] == [160, 480, 600, 600], result
        assert all("audio" in t.path.parts for t in result.thumbnails)

    print("Autoprueba finalizada correctamente.")
