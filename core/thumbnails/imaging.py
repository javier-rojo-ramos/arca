"""Tratamiento de imagen común a todos los orígenes de miniaturas (solo Pillow).

Este módulo NO depende de Qt ni de la base de datos: son funciones puras que reciben
una imagen de Pillow y devuelven otra. Cubre lo que hay que hacer SIEMPRE, venga la
imagen de un JPEG, de un HEIC o de la vista previa incrustada en un RAW:

    1. Orientación        'apply_orientation': girar según el código EXIF (1-8).
    2. Modo de color      'to_working_mode' y 'to_srgb': pasar cualquier modo raro
                          (paleta, 16 bits, CMYK, transparencia...) a RGB de 8 bits.
    3. Perfil de color    'to_srgb': convertir de Display P3 / Adobe RGB / CMYK a sRGB.
                          Sin este paso, las fotos del iPhone (Display P3) se ven
                          apagadas al mostrarlas como si fueran sRGB.
    4. Escalado           'plan_sizes' y 'build_ladder': la escalera de tamaños, sin
                          ampliar nunca.

Orden recomendado (lo aplica 'generator.py'): modo de trabajo -> reducir al tamaño
mayor -> sRGB -> escalera. El perfil se convierte DESPUÉS de reducir porque la
conversión es cara y así se hace sobre muchos menos píxeles.

Prueba rápida (desde la raíz del proyecto):
    python -m core.thumbnails.imaging
"""

__version__ = "1.0.0"
__all__ = [
    "ALPHA_BACKGROUND",
    "apply_orientation",
    "build_ladder",
    "draft_size",
    "fit_size",
    "plan_sizes",
    "read_orientation",
    "resize_to_long_side",
    "to_srgb",
    "to_working_mode",
]

# Librerías estándar
import io
import math
from collections.abc import Iterable, Sequence

# Librerías de terceros
from loguru import logger
from PIL import Image, ImageCms

# Módulos del proyecto
from core.thumbnails.sizes import ThumbnailSize

# Color sobre el que se "aplanan" las imágenes con transparencia (PNG, GIF, WebP...).
# Un gris medio se ve bien tanto con dibujos claros como con oscuros.
ALPHA_BACKGROUND: tuple[int, int, int] = (128, 128, 128)

# Número de la etiqueta EXIF "Orientation"
_EXIF_ORIENTATION_TAG = 0x0112

# Código de orientación EXIF -> transformación que deja la imagen derecha.
# (Son las mismas que usa 'ImageOps.exif_transpose'; el 1 no necesita ninguna.)
_ORIENTATION_TRANSPOSE: dict[int, Image.Transpose] = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}

# Modos de Pillow con más de 8 bits por canal (escala de grises de 16/32 bits)
_HIGH_DEPTH_MODES = frozenset({"I", "I;16", "I;16L", "I;16B", "I;16N"})


# -----------------------------------------------------------------------------
# Orientación
# -----------------------------------------------------------------------------


def read_orientation(image: Image.Image) -> int:
    """Devuelve la orientación EXIF (1-8) de una imagen de Pillow, o 1 si no consta.

    Un EXIF corrupto es muy frecuente: en ese caso se toma la imagen como normal.
    """
    try:
        value = image.getexif().get(_EXIF_ORIENTATION_TAG, 1)
    except Exception:  # noqa: BLE001 - cualquier fallo de Pillow con un EXIF roto
        return 1
    return value if isinstance(value, int) and 1 <= value <= 8 else 1


def apply_orientation(image: Image.Image, code: int) -> Image.Image:
    """Gira la imagen para dejarla derecha según un código de orientación EXIF.

    Args:
        image: Imagen tal como está guardada.
        code: Código EXIF 1-8. El 1 (o un valor desconocido) devuelve la misma
            imagen, sin copiarla.
    """
    method = _ORIENTATION_TRANSPOSE.get(code)
    return image if method is None else image.transpose(method)


# -----------------------------------------------------------------------------
# Tamaños
# -----------------------------------------------------------------------------


def fit_size(size: tuple[int, int], max_side: int) -> tuple[int, int]:
    """Calcula el tamaño que cabe en 'max_side' (lado largo) conservando la proporción.

    Nunca amplía: si el lado largo ya es igual o menor, devuelve el mismo tamaño.
    """
    width, height = size
    if max(width, height) <= max_side:
        return size
    scale = max_side / max(width, height)
    if width >= height:
        return max_side, max(1, round(height * scale))
    return max(1, round(width * scale)), max_side


def draft_size(size: tuple[int, int], target_side: int) -> tuple[int, int]:
    """Tamaño mínimo que se le pide a un JPEG para decodificarlo reducido ('draft').

    Un JPEG puede decodificarse directamente a 1/2, 1/4 o 1/8 de su tamaño, mucho más
    rápido que decodificarlo entero y reducirlo después. Pillow elige la mayor
    reducción que no deje NINGUNA de las dos dimensiones por debajo de lo pedido, así
    que se pide la proporción real de la imagen con el lado largo igual a
    'target_side' (si se pidiera un cuadrado, una foto apaisada casi nunca se reduciría).
    """
    width, height = size
    long_side = max(width, height)
    if long_side <= target_side:
        return size
    scale = target_side / long_side
    return max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale))


def resize_to_long_side(image: Image.Image, max_side: int) -> Image.Image:
    """Reduce la imagen para que su lado largo mida 'max_side'. Nunca la amplía.

    Si ya mide eso (o menos), devuelve la misma imagen sin copiarla.
    """
    new_size = fit_size(image.size, max_side)
    if new_size == image.size:
        return image
    # reducing_gap: primero un reescalado entero rápido y después LANCZOS (como 'thumbnail')
    return image.resize(new_size, Image.Resampling.LANCZOS, reducing_gap=2.0)


def plan_sizes(
    source_long_side: int, sizes: Iterable[ThumbnailSize]
) -> list[tuple[ThumbnailSize, int]]:
    """Decide a cuántos píxeles se genera cada tamaño, sin ampliar nunca.

    La escalera sale SIEMPRE completa: todos los tamaños pedidos tienen su archivo. Cada uno
    mide su lado largo, salvo que la imagen de partida sea más pequeña: entonces ese tamaño
    contiene la propia imagen, a su medida y sin ampliar. Así quien necesite un tamaño lo
    encuentra siempre en su carpeta, sin tener que buscar alternativas, y comprobar la caché es
    trivial (todo archivo con miniaturas las tiene todas). A cambio, una imagen pequeña se guarda
    repetida en los tamaños mayores que ella, lo que ocupa poco precisamente porque es pequeña.

    Ejemplos con los tamaños 160, 480, 1200 y 2560:
        partida de 6000 px -> 160, 480, 1200 y 2560
        partida de 1024 px -> 160, 480, 1024 y 1024
        partida de  100 px -> 100, 100, 100 y 100

    Args:
        source_long_side: Lado largo de la imagen de partida, en píxeles.
        sizes: Tamaños deseados (en cualquier orden).

    Returns:
        Lista (tamaño, lado largo real) de menor a mayor.
    """
    return [
        (size, min(size.max_side, source_long_side))
        for size in sorted(set(sizes), key=lambda item: item.max_side)
    ]


def build_ladder(
    image: Image.Image, plan: Sequence[tuple[ThumbnailSize, int]]
) -> list[tuple[ThumbnailSize, Image.Image]]:
    """Genera las imágenes de la escalera a partir de la imagen mayor.

    Cada tamaño se obtiene reduciendo el anterior (el mayor sale de la imagen de
    partida, el siguiente del mayor, etc.): es más rápido que partir siempre del
    original y la pérdida de calidad es inapreciable con LANCZOS.

    Args:
        image: Imagen de partida, en RGB. Debe medir al menos lo que pide el tamaño
            mayor del plan (si mide menos, ese tamaño sale a la medida de la imagen).
        plan: Resultado de 'plan_sizes' (de menor a mayor).

    Returns:
        Lista (tamaño, imagen) de menor a mayor.
    """
    ladder: list[tuple[ThumbnailSize, Image.Image]] = []
    current = image
    for size, target_side in reversed(plan):
        current = resize_to_long_side(current, target_side)
        ladder.append((size, current))
    ladder.reverse()
    return ladder


# -----------------------------------------------------------------------------
# Modo de color y perfil
# -----------------------------------------------------------------------------


def to_working_mode(image: Image.Image) -> Image.Image:
    """Convierte los modos que Pillow no sabe reducir bien a uno que sí.

    Deja pasar RGB, RGBA, L (grises) y CMYK. Convierte la paleta ('P'), que solo se
    puede reducir "a lo bruto", los grises de 16 bits, los de 1 bit y los demás.
    """
    mode = image.mode
    if mode in ("RGB", "RGBA", "L", "CMYK"):
        return image

    if mode in _HIGH_DEPTH_MODES:
        # De 16 bits a 8: 65535 -> 255. 'point' solo admite "valor * escala" en estos modos
        try:
            return image.point(lambda value: value * (1 / 256)).convert("L")
        except ValueError:
            return image.convert("L")

    if mode in ("P", "PA"):
        has_alpha = mode == "PA" or "transparency" in image.info
        return image.convert("RGBA" if has_alpha else "RGB")
    if mode == "LA":
        return image.convert("RGBA")
    if mode == "1":
        return image.convert("L")
    return image.convert("RGB")  # YCbCr, LAB, HSV, F...


def to_srgb(image: Image.Image, icc_profile: bytes | None) -> Image.Image:
    """Deja la imagen en RGB de 8 bits y espacio sRGB, listo para guardar como JPEG.

    - Si trae un perfil ICC distinto de sRGB (Display P3 del iPhone, Adobe RGB de una
      cámara, un CMYK de imprenta...), convierte los colores a sRGB.
    - Si tiene transparencia, la aplana sobre 'ALPHA_BACKGROUND'.
    - Si el perfil está dañado, la conversión se omite sin fallar: es mejor una
      miniatura con los colores algo apagados que ninguna.

    Args:
        image: Imagen ya pasada por 'to_working_mode'.
        icc_profile: Bytes del perfil ICC incrustado, o None.
    """
    alpha = None
    if image.mode == "RGBA":
        alpha = image.getchannel("A")
        image = image.convert("RGB")

    if icc_profile and image.mode in ("RGB", "CMYK"):
        image = _apply_profile(image, icc_profile)

    if image.mode != "RGB":
        image = image.convert("RGB")  # grises, o CMYK sin perfil

    if alpha is not None:
        flattened = Image.new("RGB", image.size, ALPHA_BACKGROUND)
        flattened.paste(image, mask=alpha)
        image = flattened
    return image


def _apply_profile(image: Image.Image, icc_profile: bytes) -> Image.Image:
    """Convierte la imagen de su perfil ICC a sRGB. Si no se puede, la devuelve igual."""
    try:
        source = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))

        # Si ya es sRGB no hay nada que convertir (es el caso de casi todos los JPEG)
        description = ImageCms.getProfileDescription(source).strip().lower()
        if image.mode == "RGB" and description.startswith("srgb"):
            return image

        converted = ImageCms.profileToProfile(
            image,
            source,
            ImageCms.createProfile("sRGB"),
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            outputMode="RGB",
            flags=ImageCms.Flags.BLACKPOINTCOMPENSATION,
        )
        return converted if converted is not None else image
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError) as exc:
        logger.debug(f"Perfil ICC no utilizable, se omite la conversión: {exc}")
        return image


if __name__ == "__main__":
    # Autoprueba con imágenes sintéticas (no toca el disco).
    # Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.imaging
    from PIL import ImageOps

    from core.thumbnails.sizes import ALL_SIZES

    # --- Orientación: coincide con 'ImageOps.exif_transpose' para los 8 códigos ---
    base = Image.new("RGB", (3, 2))
    base.putdata([(10, 0, 0), (20, 0, 0), (30, 0, 0), (40, 0, 0), (50, 0, 0), (60, 0, 0)])
    for code in range(1, 9):
        tagged = base.copy()
        exif = Image.Exif()
        exif[_EXIF_ORIENTATION_TAG] = code
        tagged.info["exif"] = exif.tobytes()
        expected = ImageOps.exif_transpose(tagged)
        got = apply_orientation(base, code)
        assert got.size == expected.size and got.tobytes() == expected.tobytes(), code
        assert read_orientation(tagged) == code or code == 1
    assert apply_orientation(base, 1) is base and apply_orientation(base, 99) is base
    assert apply_orientation(base, 6).size == (2, 3)  # 90°: ancho y alto se intercambian
    assert read_orientation(base) == 1
    print("Orientación: los 8 códigos coinciden con Pillow")

    # --- Tamaños ---
    assert fit_size((6000, 4000), 2560) == (2560, 1707)
    assert fit_size((4000, 6000), 2560) == (1707, 2560)
    assert fit_size((100, 60), 160) == (100, 60)  # nunca amplía
    assert fit_size((1000, 1), 160) == (160, 1)  # la proporción extrema no da 0
    assert draft_size((6000, 4000), 2560) == (2560, 1707)
    assert draft_size((900, 600), 2560) == (900, 600)

    sizes = list(ALL_SIZES)
    assert [(s.max_side, px) for s, px in plan_sizes(6000, sizes)] == [
        (160, 160), (480, 480), (1200, 1200), (2560, 2560)
    ]
    # La escalera sale siempre completa: los tamaños mayores que la imagen la contienen a su medida
    assert [(s.max_side, px) for s, px in plan_sizes(1024, sizes)] == [
        (160, 160), (480, 480), (1200, 1024), (2560, 1024)
    ]
    assert [(s.max_side, px) for s, px in plan_sizes(100, sizes)] == [
        (160, 100), (480, 100), (1200, 100), (2560, 100)
    ]
    assert [(s.max_side, px) for s, px in plan_sizes(160, sizes)] == [
        (160, 160), (480, 160), (1200, 160), (2560, 160)
    ]
    assert [(s.max_side, px) for s, px in plan_sizes(161, sizes)] == [
        (160, 160), (480, 161), (1200, 161), (2560, 161)
    ]
    assert plan_sizes(5000, [ALL_SIZES[2], ALL_SIZES[0]]) == [(ALL_SIZES[0], 160), (ALL_SIZES[2], 1200)]
    assert plan_sizes(5000, []) == []
    print("Tamaños: la escalera sale completa y nunca amplía")

    # --- Escalera: lados largos exactos, proporción conservada, sin ampliar ---
    photo = Image.new("RGB", (6000, 4000), (200, 50, 50))
    ladder = build_ladder(photo, plan_sizes(6000, sizes))
    assert [(s.max_side, img.size) for s, img in ladder] == [
        (160, (160, 107)), (480, (480, 320)), (1200, (1200, 800)), (2560, (2560, 1707))
    ]
    small = Image.new("RGB", (300, 400), (0, 0, 255))  # vertical y pequeña
    ladder = build_ladder(small, plan_sizes(400, sizes))
    assert [(s.max_side, img.size) for s, img in ladder] == [
        (160, (120, 160)), (480, (300, 400)), (1200, (300, 400)), (2560, (300, 400))
    ]  # los mayores contienen la propia imagen, sin ampliar
    print("Escalera:", [(s.max_side, img.size) for s, img in ladder])

    # --- Modos de color ---
    palette = Image.new("P", (4, 4), 0)
    palette.putpalette([255, 0, 0] + [0] * 765)
    assert to_working_mode(palette).mode == "RGB"
    palette.info["transparency"] = 0
    assert to_working_mode(palette).mode == "RGBA"
    assert to_working_mode(Image.new("LA", (2, 2))).mode == "RGBA"
    assert to_working_mode(Image.new("1", (2, 2))).mode == "L"
    deep = Image.new("I;16", (2, 1))
    deep.putdata([65535, 256])
    deep8 = to_working_mode(deep)
    assert deep8.mode == "L" and deep8.tobytes() == bytes([255, 1])
    for mode in ("RGB", "RGBA", "L", "CMYK"):
        image_in = Image.new(mode, (2, 2))
        assert to_working_mode(image_in) is image_in
    cmyk_to_rgb = to_srgb(Image.new("CMYK", (2, 2), (0, 0, 0, 0)), None)  # sin tinta = blanco
    assert cmyk_to_rgb.mode == "RGB" and cmyk_to_rgb.getpixel((0, 0)) == (255, 255, 255)
    assert to_srgb(Image.new("L", (2, 2), 77), None).getpixel((0, 0)) == (77, 77, 77)
    print("Modos de color: paleta, 1 bit, 16 bits, LA y CMYK correctos")

    # --- Transparencia: se aplana sobre el color de fondo ---
    rgba = Image.new("RGBA", (2, 1))
    rgba.putdata([(255, 0, 0, 255), (255, 0, 0, 0)])
    flat = to_srgb(rgba, None)
    assert flat.mode == "RGB"
    assert flat.getpixel((0, 0)) == (255, 0, 0) and flat.getpixel((1, 0)) == ALPHA_BACKGROUND
    print("Transparencia: aplanada sobre", ALPHA_BACKGROUND)

    # --- Perfil ICC: un Display P3 de verdad (ver _testing.py) ---
    from core.thumbnails._testing import display_p3_profile

    display_p3 = display_p3_profile()
    srgb_bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    p3_image = Image.new("RGB", (2, 1))
    p3_image.putdata([(128, 128, 128), (200, 100, 50)])
    converted = to_srgb(p3_image, display_p3)
    gray_in, gray_out = (128, 128, 128), converted.getpixel((0, 0))
    color_in, color_out = (200, 100, 50), converted.getpixel((1, 0))
    assert max(abs(a - b) for a, b in zip(gray_in, gray_out)) <= 3, gray_out  # el gris sigue gris
    assert max(abs(a - b) for a, b in zip(color_in, color_out)) >= 6, color_out  # el color SÍ cambia
    assert color_out[0] > color_in[0] and color_out[2] < color_in[2]  # más saturado en sRGB
    print(f"Display P3 -> sRGB: gris {gray_in}->{gray_out}, color {color_in}->{color_out}")

    # Un perfil sRGB no se toca; uno dañado se ignora sin fallar
    assert to_srgb(p3_image, srgb_bytes).getpixel((1, 0)) == (200, 100, 50)
    assert to_srgb(p3_image, b"esto no es un perfil").getpixel((1, 0)) == (200, 100, 50)
    assert to_srgb(p3_image, display_p3[:200]).getpixel((1, 0)) == (200, 100, 50)  # truncado
    print("Perfil sRGB intacto; perfil dañado omitido sin errores")

    print("Autoprueba finalizada correctamente.")
