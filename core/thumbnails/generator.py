"""Generación de las miniaturas de UN archivo: de la imagen original a la caché.

Este módulo NO depende de Qt ni de la base de datos. 'generate_thumbnails' es la
función que lo hace todo para un elemento, y es la que llamará el trabajo en segundo
plano (para cada archivo pendiente) y la "regeneración a demanda" (para los archivos
que el usuario elija):

    1. Busca la cadena de orígenes del archivo (registry.py) y obtiene la imagen de
       partida, ya derecha (sources/).
    2. Decide a cuántos píxeles sale cada tamaño, sin ampliar nunca (imaging.plan_sizes).
    3. Reduce al tamaño mayor y convierte los colores a sRGB (imaging).
    4. Genera la escalera de tamaños, cada uno a partir del anterior.
    5. Guarda cada tamaño en la caché (cache.py), sustituyendo lo que hubiera.

Generar y regenerar son LA MISMA operación: se sobrescribe lo que hubiera. Es
idempotente, así que se puede repetir sin miedo tras un fallo o un cambio de original.

No toca la base de datos ni decide QUÉ archivos procesar: eso es del trabajo en
segundo plano (siguiente paso). Aquí solo hay una función por archivo, segura para
llamar desde varios hilos a la vez.

1.2.0 'load_source_image' pública (antes, '_load_source_image'): la usa también
      'full_image.py' (el original a tamaño completo para la vista individual a 1:1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.thumbnails.generator
"""

__version__ = "1.2.0"
__all__ = ["THUMBNAIL_VERSION", "ThumbnailResult", "generate_thumbnails", "load_source_image"]

# Librerías estándar
import time
from collections.abc import Iterable
from dataclasses import dataclass

# Módulos del proyecto
from core.thumbnails.cache import StoredThumbnail, ThumbnailCache
from core.thumbnails.imaging import (
    build_ladder,
    plan_sizes,
    resize_to_long_side,
    to_srgb,
    to_working_mode,
)
from core.thumbnails.registry import SourceRegistry
from core.thumbnails.sizes import DEFAULT_SIZES, ThumbnailSize
from core.thumbnails.sources.base import (
    LoadedImage,
    ThumbnailError,
    ThumbnailRequest,
    UnsupportedSourceError,
)

# Versión de lo que genera este motor. Se guarda en 'media_items.thumbnail_version' de cada
# archivo procesado. SÚBELA cada vez que cambie el RESULTADO: los tamaños o su calidad
# (sizes.py), el formato de la caché (cache.py), el tratamiento del color o la orientación
# (imaging.py) o la elección de la imagen de partida (sources/). Al subirla, el trabajo en
# segundo plano vuelve a generar todas las miniaturas con una versión menor.
# (La autoprueba de 'job.py' avisa si se cambian los tamaños sin subirla.)
# Historial: 1 = primera versión (se omitían los tamaños mayores que la imagen de partida);
#            2 = la escalera sale siempre completa (esos tamaños contienen la imagen, sin ampliar).
THUMBNAIL_VERSION = 2


@dataclass(frozen=True, slots=True)
class ThumbnailResult:
    """Lo que ha ocurrido al generar las miniaturas de un archivo.

    Attributes:
        request: El elemento procesado.
        source_name: Origen que entregó la imagen ('pillow', 'heif', 'raw_preview:PreviewImage'...).
        source_size: Tamaño (ancho, alto) de la imagen de partida, ya derecha. Puede
            ser menor que el original si se decodificó reducida (JPEG).
        original_size: Tamaño del original completo, ya derecho, si el origen lo sabe.
        thumbnails: Las miniaturas escritas, de menor a mayor.
        seconds: Tiempo empleado.
    """

    request: ThumbnailRequest
    source_name: str
    source_size: tuple[int, int]
    original_size: tuple[int, int] | None
    thumbnails: tuple[StoredThumbnail, ...]
    seconds: float


def generate_thumbnails(
    request: ThumbnailRequest,
    cache: ThumbnailCache,
    registry: SourceRegistry,
    sizes: Iterable[ThumbnailSize] = DEFAULT_SIZES,
) -> ThumbnailResult:
    """Genera (o regenera) las miniaturas de un archivo y las guarda en la caché.

    Args:
        request: El elemento: su id, su tipo de medio y la ruta del archivo.
        cache: Caché del catálogo donde se guardan.
        registry: Orígenes disponibles.
        sizes: Tamaños deseados. Todos se generan; los mayores que la imagen de partida
            contienen la propia imagen, sin ampliar (ver 'plan_sizes'). Los tamaños que NO
            estén en esta lista no se tocan.

    Returns:
        Un 'ThumbnailResult' con lo escrito.

    Raises:
        ValueError: Si 'sizes' está vacío.
        FileNotFoundError: Si el archivo original ya no existe.
        UnsupportedSourceError: Si ningún origen sabe leer el archivo (p. ej. falta pillow-heif).
        ThumbnailError: Si el archivo está dañado o no contiene una imagen utilizable.
        ThumbnailStorageError: Si no se puede escribir en la caché (disco lleno...); es un
            fallo general de la caché, no del archivo.
    """
    started = time.perf_counter()
    wanted = sorted(set(sizes), key=lambda size: size.max_side)
    if not wanted:
        raise ValueError("Hay que indicar al menos un tamaño de miniatura.")

    loaded = load_source_image(request, registry, wanted[-1].max_side)
    try:
        # Se reduce primero (es lo más barato) y solo después se convierte el color
        image = to_working_mode(loaded.image)
        source_size = image.size
        plan = plan_sizes(max(image.size), wanted)
        largest = resize_to_long_side(image, plan[-1][1])
        largest = to_srgb(largest, loaded.icc_profile)

        stored = tuple(
            cache.store(request.media_type, request.media_id, size, thumbnail)
            for size, thumbnail in build_ladder(largest, plan)
        )
    finally:
        # Libera ya la memoria de la imagen grande (con varios hilos, 24 megapíxeles pesan)
        loaded.image.close()

    return ThumbnailResult(
        request=request,
        source_name=loaded.source_name,
        source_size=source_size,
        original_size=loaded.original_size,
        thumbnails=stored,
        seconds=time.perf_counter() - started,
    )


def load_source_image(
    request: ThumbnailRequest, registry: SourceRegistry, target_side: int
) -> LoadedImage:
    """Prueba los orígenes del archivo, en orden, hasta que uno entregue la imagen.

    Args:
        request: El elemento: su id, su tipo de medio y la ruta del archivo.
        registry: Orígenes disponibles.
        target_side: Lado largo que hace falta (pista para decodificar reducido; ver
            'ThumbnailSource.load').

    Raises:
        FileNotFoundError, UnsupportedSourceError, ThumbnailError: como
            'generate_thumbnails'.
    """
    chain = registry.chain_for(request.media_type, request.extension)
    if not chain:
        raise UnsupportedSourceError(
            f"No hay ningún origen de miniaturas para '.{request.extension}'"
        )

    errors: list[ThumbnailError] = []
    for source in chain:
        try:
            return source.load(request, target_side)
        except ThumbnailError as error:  # FileNotFoundError no se captura: sale directo
            errors.append(error)

    # Todos fallaron. El mensaje más útil es el de un fallo real del archivo; los
    # "este origen no puede" (falta una librería) solo se muestran si no hay otro.
    real_errors = [e for e in errors if not isinstance(e, UnsupportedSourceError)]
    raise (real_errors or errors)[0]


if __name__ == "__main__":
    # Autoprueba de punta a punta: archivos reales en una carpeta temporal, un ExifTool
    # SIMULADO para los RAW y un HEIC simulado (ver los avisos al final).
    # Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.generator
    import base64
    import json
    import os
    import sys
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from PIL import Image

    from core.catalog.media_types import MediaType
    from core.metadata.exiftool_runner import ExifToolRunner
    from core.thumbnails import _testing
    from core.thumbnails.imaging import ALPHA_BACKGROUND
    from core.thumbnails.sizes import ALL_SIZES
    from core.thumbnails.sources import heif_source
    from core.thumbnails.sources.base import ThumbnailSource
    from core.thumbnails.sources.pillow_source import PillowSource
    from core.thumbnails.sources.raw_preview_source import RawPreviewSource

    THUMB, MEDIUM, PREVIEW, FULL = ALL_SIZES

    def sizes_of(result: ThumbnailResult) -> dict[int, tuple[int, int]]:
        """{lado largo pedido: (ancho, alto) escrito} de un resultado."""
        return {t.size.max_side: (t.width, t.height) for t in result.thumbnails}

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        cache = ThumbnailCache(base / "Catalogo")
        fake = base / "fake_exiftool.py"
        fake.write_text(_testing.FAKE_EXIFTOOL, encoding="utf-8")
        os.environ["FAKE_EXIFTOOL_DATA"] = str(base / "exiftool_data.json")
        runner = ExifToolRunner(command=[sys.executable, str(fake)])

        registry = SourceRegistry()
        registry.register(PillowSource())
        registry.register(heif_source.HeifSource())
        registry.register(RawPreviewSource(runner))

        counter = iter(range(1, 1000))

        def request_for(name: str) -> ThumbnailRequest:
            return ThumbnailRequest(next(counter), MediaType.PHOTO, base / name)

        def generate(name: str, **options) -> ThumbnailResult:
            return generate_thumbnails(request_for(name), cache, registry, **options)

        # ---- 1. JPEG apaisado de 3000 px con orientación 6 (girado 90°): sale vertical ----
        (base / "paisaje.jpg").write_bytes(_testing.jpeg_bytes((3000, 2000), orientation=6))
        result = generate("paisaje.jpg")
        assert sizes_of(result) == {
            160: (107, 160), 480: (320, 480), 1200: (800, 1200), 2560: (1707, 2560)
        }, sizes_of(result)
        assert result.source_name == "pillow" and result.original_size == (2000, 3000)
        with Image.open(result.thumbnails[0].path) as thumb:
            assert thumb.size == (107, 160) and thumb.format == "JPEG"
        print("JPEG con orientación 6: vertical y con los 4 tamaños", sizes_of(result))

        # ---- 2. PNG con transparencia de 800 px: se aplana y el tamaño mayor sale a 800 ----
        rgba = Image.new("RGBA", (800, 600), (0, 0, 0, 0))  # todo transparente...
        rgba.paste((255, 0, 0, 255), (300, 200, 500, 400))  # ...menos un cuadrado rojo
        rgba.save(base / "logo.png")
        result = generate("logo.png")
        # La escalera sale completa: 1200 y 2560 contienen la imagen a su medida (800), sin ampliar
        assert sizes_of(result) == {160: (160, 120), 480: (480, 360), 1200: (800, 600), 2560: (800, 600)}
        with Image.open(result.thumbnails[0].path) as thumb:
            assert thumb.getpixel((2, 2)) == ALPHA_BACKGROUND or max(
                abs(a - b) for a, b in zip(thumb.getpixel((2, 2)), ALPHA_BACKGROUND)
            ) <= 3
        assert cache.resolve(MediaType.PHOTO, result.request.media_id, FULL) == result.thumbnails[-1].path
        print("PNG con transparencia: aplanado; 1200 y 2560 a su medida (800), sin ampliar:", sizes_of(result))

        # ---- 3. Imagen diminuta: los cuatro tamaños, todos a su medida (nunca se amplía) ----
        Image.new("RGB", (100, 60), (10, 200, 10)).save(base / "icono.jpg")
        result = generate("icono.jpg")
        assert sizes_of(result) == {160: (100, 60), 480: (100, 60), 1200: (100, 60), 2560: (100, 60)}
        assert cache.resolve(MediaType.PHOTO, result.request.media_id, FULL) == result.thumbnails[-1].path
        print("Imagen de 100 px: los cuatro tamaños existen, todos a 100 px")

        # ---- 4. Modos raros: grises de 16 bits, paleta con transparencia (GIF) y CMYK ----
        deep = Image.new("I;16", (400, 300))
        deep.putdata([i * 20 for i in range(400 * 300)][: 400 * 300])
        deep.save(base / "gris16.png")
        Image.new("P", (300, 200), 1).save(base / "animacion.gif", transparency=0)
        Image.new("CMYK", (300, 200), (0, 255, 255, 0)).save(base / "imprenta.jpg")
        for name in ("gris16.png", "animacion.gif", "imprenta.jpg"):
            result = generate(name)
            with Image.open(result.thumbnails[0].path) as thumb:
                assert thumb.mode == "RGB", name
        print("Modos raros (16 bits, paleta, CMYK): los tres salen en RGB")

        # ---- 5. Color: un JPEG en Display P3 se convierte a sRGB ----
        p3 = _testing.display_p3_profile()
        Image.new("RGB", (400, 300), (200, 100, 50)).save(base / "p3.jpg", quality=95, icc_profile=p3)
        Image.new("RGB", (400, 300), (200, 100, 50)).save(base / "srgb.jpg", quality=95)
        pixel_p3 = Image.open(generate("p3.jpg").thumbnails[0].path).getpixel((20, 20))
        pixel_srgb = Image.open(generate("srgb.jpg").thumbnails[0].path).getpixel((20, 20))
        assert pixel_p3[0] > pixel_srgb[0] + 8 and pixel_p3[2] < pixel_srgb[2] - 8, (pixel_p3, pixel_srgb)
        print(f"Color: el mismo (200,100,50) sale {pixel_srgb} si es sRGB y {pixel_p3} si es Display P3")

        # ---- 6. Errores: nada se escribe y el mensaje es legible ----
        (base / "rota.jpg").write_bytes(b"esto no es una imagen" * 50)
        good = _testing.jpeg_bytes((800, 600))
        (base / "cortada.jpg").write_bytes(good[: len(good) // 2])  # descarga a medias
        for name in ("rota.jpg", "cortada.jpg"):
            request = request_for(name)
            try:
                generate_thumbnails(request, cache, registry)
            except ThumbnailError as error:
                assert not isinstance(error, UnsupportedSourceError), name
                assert cache.existing(MediaType.PHOTO, request.media_id) == {}
                print(f"{name}: {error}")
            else:
                raise AssertionError(f"{name} debería fallar")
        for name, expected in (("no_existe.jpg", FileNotFoundError), ("raro.xyz", UnsupportedSourceError)):
            (base / "raro.xyz").write_bytes(b"x")
            try:
                generate(name)
            except expected as error:
                print(f"{name}: {type(error).__name__}")
            else:
                raise AssertionError(f"{name} debería lanzar {expected.__name__}")
        try:
            generate("paisaje.jpg", sizes=[])
        except ValueError:
            pass
        else:
            raise AssertionError("Sin tamaños debería rechazarse")

        # ---- 7. Regenerar: el original cambia a uno más pequeño y TODOS los tamaños se sustituyen ----
        request = request_for("cambiante.jpg")
        (base / "cambiante.jpg").write_bytes(_testing.jpeg_bytes((3000, 2000)))
        first = generate_thumbnails(request, cache, registry)
        assert sizes_of(first)[2560] == (2560, 1707)
        (base / "cambiante.jpg").write_bytes(_testing.jpeg_bytes((300, 200)))
        second = generate_thumbnails(request, cache, registry)
        assert sizes_of(second) == {160: (160, 107), 480: (300, 200), 1200: (300, 200), 2560: (300, 200)}
        assert list(cache.existing(MediaType.PHOTO, request.media_id)) == [THUMB, MEDIUM, PREVIEW, FULL]
        with Image.open(cache.path_for(MediaType.PHOTO, request.media_id, FULL)) as replaced:
            assert replaced.size == (300, 200)  # ya no queda la miniatura grande antigua
        print("Regeneración con un original más pequeño: los cuatro tamaños se sustituyen", sizes_of(second))

        # ---- 8. Un subconjunto de tamaños no toca el resto ----
        request = request_for("subconjunto.jpg")
        (base / "subconjunto.jpg").write_bytes(_testing.jpeg_bytes((3000, 2000)))
        generate_thumbnails(request, cache, registry)
        preview_path = cache.path_for(MediaType.PHOTO, request.media_id, PREVIEW)
        before = preview_path.stat().st_mtime_ns
        subset = generate_thumbnails(request, cache, registry, sizes=[THUMB, MEDIUM])
        assert [t.size for t in subset.thumbnails] == [THUMB, MEDIUM]
        assert preview_path.stat().st_mtime_ns == before
        print("Subconjunto [160, 480]: el tamaño de 1200 y el de 2560 no se tocan")

        # ---- 9. Cadena de orígenes: si el primero falla, se prueba el siguiente ----
        class BrokenSource(ThumbnailSource):
            name = "roto"
            media_type = MediaType.PHOTO
            extensions = frozenset({"cadena"})

            def load(self, request, target_side):
                raise ThumbnailError("el primer origen falla")

        class SecondSource(PillowSource):
            name = "segundo"
            extensions = frozenset({"cadena"})

        chain_registry = SourceRegistry()
        chain_registry.register(BrokenSource())
        chain_registry.register(SecondSource())
        (base / "archivo.cadena").write_bytes(_testing.jpeg_bytes((500, 400)))
        request = request_for("archivo.cadena")
        assert generate_thumbnails(request, cache, chain_registry).source_name == "segundo"
        only_broken = SourceRegistry()
        only_broken.register(BrokenSource())
        try:
            generate_thumbnails(request, cache, only_broken)
        except ThumbnailError as error:
            assert str(error) == "el primer origen falla"
        print("Cadena de orígenes: el segundo origen recoge lo que falla el primero")

        # ---- 10. HEIC: sin pillow-heif se explica cómo instalarlo; con él, se lee ----
        (base / "iphone.heic").write_bytes(_testing.jpeg_bytes((800, 600)))  # JPEG disfrazado de HEIC
        real_support = heif_source.heif_support_available
        try:
            heif_source.heif_support_available = lambda: False  # simula que NO está instalada
            try:
                generate("iphone.heic")
            except UnsupportedSourceError as error:
                assert "pillow-heif" in str(error)
                print("HEIC sin librería:", error)
            else:
                raise AssertionError("Sin pillow-heif debería avisar")
            heif_source.heif_support_available = lambda: True  # simula que SÍ lo está
            result = generate("iphone.heic")  # Pillow abre por contenido: se prueba el circuito del origen
            assert result.source_name == "heif" and sizes_of(result)[160] == (160, 120)
        finally:
            heif_source.heif_support_available = real_support
        print("HEIC (simulado): el circuito del origen funciona")

        # ---- 11. RAW con un ExifTool simulado ----
        def b64(data: bytes) -> str:
            return "base64:" + base64.b64encode(data).decode("ascii")

        dng_tags = {  # parecido al DNG real de Lightroom que se verificó
            "IFD0:Orientation": 6,
            "IFD0:ThumbnailTIFF": "(Binary data 131544 bytes, use -b option to extract)",
            "SubIFD1:PreviewImage": b64(_testing.jpeg_bytes((1024, 683))),
            "PreviewIFD:PreviewImage": b64(_testing.jpeg_bytes((160, 120))),
            "IFD0:ThumbnailImage": b64(b"esto no es una imagen"),  # no utilizable: se ignora
        }
        preview_with_own_orientation = _testing.jpeg_bytes((300, 200), orientation=8, marker=True)
        data = {
            "DSC_9140.dng": dng_tags,
            "sin_preview.nef": {"IFD0:Orientation": 1},
            "pequena.cr3": {"IFD0:Orientation": 1, "IFD0:PreviewImage": b64(_testing.jpeg_bytes((300, 200), marker=True))},
            "propia.arw": {"IFD0:Orientation": 6, "IFD0:PreviewImage": b64(preview_with_own_orientation)},
            "raw_girado.orf": {"IFD0:Orientation": 6, "IFD0:PreviewImage": b64(_testing.jpeg_bytes((300, 200), marker=True))},
        }
        Path(os.environ["FAKE_EXIFTOOL_DATA"]).write_text(json.dumps(data), encoding="utf-8")
        for name in data:
            (base / name).write_bytes(b"x")  # el contenido da igual: ExifTool es simulado

        result = generate("DSC_9140.dng")
        # Se elige la mayor (1024x683) y se gira por la orientación 6 del RAW -> 683x1024
        assert result.source_name == "raw_preview:PreviewImage" and result.source_size == (683, 1024)
        assert sizes_of(result) == {160: (107, 160), 480: (320, 480), 1200: (683, 1024), 2560: (683, 1024)}
        print("DNG simulado: vista previa de 1024 px girada, tamaños", sizes_of(result))

        def red_at(result: ThumbnailResult, corner: str) -> bool:
            """¿Está la marca roja en esa esquina de la miniatura pequeña?"""
            with Image.open(result.thumbnails[0].path) as thumb:
                w, h = thumb.size
                x, y = {"tl": (3, 3), "tr": (w - 4, 3), "bl": (3, h - 4), "br": (w - 4, h - 4)}[corner]
                r, g, b = thumb.getpixel((x, y))
                return r > 180 and g < 90 and b < 90

        # Orientación 6 del RAW: la esquina superior izquierda pasa a la superior derecha
        assert red_at(generate("raw_girado.orf"), "tr")
        # La vista previa trae su propia orientación (8) y MANDA sobre la del RAW (6)
        assert red_at(generate("propia.arw"), "bl")
        # Sin giro (orientación 1): se queda donde estaba
        assert red_at(generate("pequena.cr3"), "tl")
        print("Orientación de RAW: la del RAW, salvo que la vista previa traiga la suya")

        try:
            generate("sin_preview.nef")
        except ThumbnailError as error:
            assert not isinstance(error, UnsupportedSourceError)
            print("RAW sin vista previa:", error)
        else:
            raise AssertionError("Un RAW sin vista previa debería fallar")

        no_raw = SourceRegistry()
        no_raw.register(PillowSource())
        try:
            generate_thumbnails(request_for("DSC_9140.dng"), cache, no_raw)
        except UnsupportedSourceError as error:
            print("RAW sin ExifTool:", error)
        else:
            raise AssertionError("Sin origen de RAW debería avisar")

        (base / "explota.dng").write_bytes(b"x")  # el ExifTool simulado se cae con este nombre
        try:
            generate("explota.dng")
        except ThumbnailError as error:
            print("ExifTool que se cae:", str(error)[:70])
        else:
            raise AssertionError("Un fallo de ExifTool debería notificarse")

        # ---- 12. Varios hilos a la vez (como hará el trabajo en segundo plano) ----
        for index in range(12):
            (base / f"lote_{index}.jpg").write_bytes(_testing.jpeg_bytes((1600 + index, 1200)))
        requests = [request_for(f"lote_{index}.jpg") for index in range(12)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda r: generate_thumbnails(r, cache, registry), requests))
        # De 1600 px salen 160, 480, 1200 y, a su medida, el de 2560 (que queda en 1600)
        assert all(len(r.thumbnails) == 4 for r in results)
        assert all(max(r.thumbnails[-1].width, r.thumbnails[-1].height) < 2000 for r in results)
        assert not list(base.rglob("*.tmp"))
        print("12 archivos en 4 hilos: todos correctos y sin temporales")

    print("Autoprueba finalizada correctamente.")
