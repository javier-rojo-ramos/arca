"""El original a tamaño completo, para ver una foto a 1:1 en la vista individual.

Este módulo NO depende de Qt ni de la base de datos. 'load_full_image' tarda (decodificar
un JPEG de 24 megapíxeles lleva unas décimas de segundo): se llama desde un hilo
secundario, y es seguro llamarlo desde varios a la vez.

Lee la imagen con los MISMOS orígenes que las miniaturas ('registry.py', 'sources/') y le
da el MISMO tratamiento que a la caché ('imaging.to_working_mode' y 'to_srgb'): derecha
(orientación aplicada), en RGB de 8 bits y en sRGB, con la transparencia aplanada. Así,
al pasar de la imagen de la caché al original, no cambian ni el color ni la orientación:
solo se gana detalle. Lo único que no se hace es reducirla.

«Original» es la mayor imagen que se puede leer del archivo:
    - JPEG, PNG, TIFF, WebP, HEIC...: la foto entera, a su tamaño.
    - RAW y DNG: su mayor vista previa JPEG incrustada, como las miniaturas. En NEF, CR2 o
      ARW suele tener el tamaño del sensor; en un DNG guardado por Lightroom puede ser de
      solo 1024 px (ver MINIATURAS.md, «Límites conocidos»). Revelar el RAW con 'rawpy'
      está pendiente (PENDIENTE.md, C.3).

Uso (en un hilo secundario):
    full = load_full_image(ThumbnailRequest(media_id, MediaType.PHOTO, ruta), registry)
    full.image         # imagen de Pillow: RGB, sRGB y a tamaño completo
    full.size          # (ancho, alto), ya derecha
    full.source_name   # 'pillow', 'heif', 'raw_preview:JpgFromRaw'...

1.0.0 Primera versión (vista individual a 1:1, paso 1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.thumbnails.full_image
"""

__version__ = "1.0.0"
__all__ = ["FullImage", "load_full_image"]

# Librerías estándar
from dataclasses import dataclass

# Librerías de terceros
from PIL import Image

# Módulos del proyecto
from core.thumbnails.generator import load_source_image
from core.thumbnails.imaging import to_srgb, to_working_mode
from core.thumbnails.registry import SourceRegistry
from core.thumbnails.sources.base import ThumbnailRequest

# Lado largo que se pide a los orígenes: tan grande que ninguno reduce la imagen (un JPEG
# solo se decodifica reducido si el original pasa de lo pedido: 'imaging.draft_size')
_FULL_SIDE = 1 << 30


@dataclass(frozen=True, slots=True)
class FullImage:
    """El original de un archivo, listo para mostrar.

    Attributes:
        image: Imagen de Pillow en RGB de 8 bits y sRGB, derecha y a tamaño completo.
        source_name: Origen que la entregó ('pillow', 'heif', 'raw_preview:...').
    """

    image: Image.Image
    source_name: str

    @property
    def size(self) -> tuple[int, int]:
        """(ancho, alto) de la imagen, ya derecha."""
        return self.image.size


def load_full_image(request: ThumbnailRequest, registry: SourceRegistry) -> FullImage:
    """Lee el original de un archivo a tamaño completo, con el color de la caché.

    Args:
        request: El elemento: su id, su tipo de medio y la ruta del archivo.
        registry: Orígenes disponibles (los de las miniaturas: 'default_registry()').

    Raises:
        FileNotFoundError: Si el archivo ya no existe.
        UnsupportedSourceError: Si ningún origen sabe leerlo (p. ej. falta pillow-heif).
        ThumbnailError: Si el archivo está dañado o no contiene una imagen utilizable.
    """
    loaded = load_source_image(request, registry, _FULL_SIDE)
    source = loaded.image
    try:
        image = to_srgb(to_working_mode(source), loaded.icc_profile)
    except BaseException:
        source.close()
        raise
    if image is not source:
        source.close()  # suelta ya la intermedia: una foto grande pesa cientos de MB
    return FullImage(image, loaded.source_name)


if __name__ == "__main__":
    # Autoprueba con archivos de verdad en una carpeta temporal y un ExifTool SIMULADO
    # para el RAW. Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.full_image
    import base64
    import json
    import os
    import sys
    import tempfile
    from pathlib import Path

    from core.catalog.media_types import MediaType
    from core.metadata.exiftool_runner import ExifToolRunner
    from core.thumbnails import _testing
    from core.thumbnails.cache import ThumbnailCache
    from core.thumbnails.generator import generate_thumbnails
    from core.thumbnails.imaging import ALPHA_BACKGROUND
    from core.thumbnails.sizes import ALL_SIZES
    from core.thumbnails.sources.base import ThumbnailError, UnsupportedSourceError
    from core.thumbnails.sources.pillow_source import PillowSource
    from core.thumbnails.sources.raw_preview_source import RawPreviewSource

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fake = base / "fake_exiftool.py"
        fake.write_text(_testing.FAKE_EXIFTOOL, encoding="utf-8")
        data_file = base / "exiftool_data.json"
        os.environ["FAKE_EXIFTOOL_DATA"] = str(data_file)
        registry = SourceRegistry()
        registry.register(PillowSource())
        registry.register(RawPreviewSource(ExifToolRunner(command=[sys.executable, str(fake)])))

        def request_for(name: str, media_id: int = 1) -> ThumbnailRequest:
            return ThumbnailRequest(media_id, MediaType.PHOTO, base / name)

        # 1. JPEG de 4000 × 3000 con orientación 6: entero (sin reducir) y derecho. Las
        #    miniaturas, con el mismo archivo, se quedan en 2560 px
        (base / "foto.jpg").write_bytes(_testing.jpeg_bytes((4000, 3000), orientation=6, marker=True))
        full = load_full_image(request_for("foto.jpg"), registry)
        assert full.size == (3000, 4000) and full.image.mode == "RGB", full.size
        assert full.source_name == "pillow"
        # La marca roja (arriba a la izquierda al guardarla) queda arriba a la DERECHA
        red, green, _blue = full.image.getpixel((2990, 10))
        assert red > 200 and green < 60, full.image.getpixel((2990, 10))
        cache = ThumbnailCache(base / "Catalogo")
        largest = generate_thumbnails(request_for("foto.jpg"), cache, registry).thumbnails[-1]
        assert (largest.width, largest.height) == (1920, 2560)

        # 2. El color, como la caché: un JPEG en Display P3 sale convertido a sRGB (el gris
        #    del archivo cambia un poco), igual que su miniatura
        (base / "p3.jpg").write_bytes(
            _testing.jpeg_bytes((600, 400), icc_profile=_testing.display_p3_profile())
        )
        full = load_full_image(request_for("p3.jpg", 2), registry)
        thumbnail = generate_thumbnails(request_for("p3.jpg", 2), cache, registry, ALL_SIZES[-1:])
        with Image.open(thumbnail.thumbnails[0].path) as cached:
            full_pixel, cached_pixel = full.image.getpixel((300, 200)), cached.getpixel((300, 200))
        assert max(abs(a - b) for a, b in zip(full_pixel, cached_pixel, strict=True)) <= 3, (
            full_pixel, cached_pixel)
        assert full_pixel != (120, 120, 120)  # convertido (sin convertir, el gris de partida)

        # 3. PNG con transparencia: aplanado sobre el gris de las miniaturas
        rgba = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
        rgba.paste((255, 0, 0, 255), (100, 50, 200, 150))
        rgba.save(base / "logo.png")
        full = load_full_image(request_for("logo.png", 3), registry)
        assert full.image.mode == "RGB" and full.size == (300, 200)
        assert full.image.getpixel((150, 100)) == (255, 0, 0)
        assert full.image.getpixel((2, 2)) == ALPHA_BACKGROUND, full.image.getpixel((2, 2))

        # 4. RAW: la MAYOR vista previa incrustada, entera, con la orientación del RAW
        def b64_jpeg(size: tuple[int, int]) -> str:
            return "base64:" + base64.b64encode(_testing.jpeg_bytes(size)).decode()

        (base / "foto.nef").write_bytes(b"no es un RAW de verdad")
        data_file.write_text(json.dumps({"foto.nef": {
            "JpgFromRaw": b64_jpeg((3008, 2000)),
            "PreviewImage": b64_jpeg((640, 424)),
            "Orientation": 8,
        }}), encoding="utf-8")  # fmt: skip
        full = load_full_image(request_for("foto.nef", 4), registry)
        assert full.size == (2000, 3008), full.size
        assert full.source_name.startswith("raw_preview"), full.source_name

        # 5. Errores, los mismos que al generar las miniaturas
        try:
            load_full_image(request_for("no_existe.jpg", 5), registry)
            raise AssertionError("debía avisar de que no existe")
        except FileNotFoundError:
            pass
        (base / "texto.xyz").write_text("hola", encoding="utf-8")
        try:
            load_full_image(request_for("texto.xyz", 6), registry)
            raise AssertionError("debía decir que no sabe leerlo")
        except UnsupportedSourceError:
            pass
        (base / "roto.jpg").write_bytes(b"\xff\xd8\xff no es un JPEG")
        try:
            load_full_image(request_for("roto.jpg", 7), registry)
            raise AssertionError("debía avisar de que está dañado")
        except ThumbnailError:
            pass
    print("Autoprueba finalizada correctamente.")
