"""Marcas de cámara: el nombre corto que se guarda, como Lightroom («Nikon», «Ricoh»...).

Este módulo NO depende de Qt ni de la base de datos: es una lista declarativa.

Cada fabricante escribe su marca a su manera, y a veces de varias: «NIKON CORPORATION» y
«NIKON», «bq» y «BQ», «RICOH IMAGING COMPANY, LTD.». Lightroom muestra un nombre corto
(«Nikon», «Ricoh»), y así se guarda también en el catálogo (decidido por el autor el
21/11/2026): el inspector lo muestra corto y el filtro «Marca de la cámara» junta las
variantes de una misma marca.

La lista va por la PRIMERA PALABRA de la marca, sin distinguir mayúsculas: una línea cubre
todas las formas de un fabricante. Una marca que no está en la lista se guarda tal cual la
escribe el archivo. El MODELO no se cambia nunca («PENTAX K-70», aunque Lightroom diga
«Pentax K-70»: lo saca de su propia lista de cámaras).

Un valor sin ninguna letra ni cifra («--», que escriben algunos programas) no es una marca
ni un modelo: se guarda vacío.

Uso:
    maker_name("NIKON CORPORATION")       # 'Nikon'
    maker_name("RICOH IMAGING COMPANY, LTD.")  # 'Ricoh'
    maker_name("OM Digital Solutions")    # 'OM Digital Solutions' (no está: tal cual)
    maker_name("--")                      # None
    model_name("PENTAX K-70")             # 'PENTAX K-70' (tal cual)
    starts_with_maker("PENTAX K-70")      # True: el modelo ya dice la marca

Añadir una marca: una línea en 'CAMERA_MAKERS' (su primera palabra, en minúsculas, y el
nombre que se guarda) y subir 'IMAGE_FIELDS_VERSION' y 'VIDEO_FIELDS_VERSION', para que se
vuelvan a leer las fotos y los vídeos (docs/COMO_AMPLIAR.md).

1.0.0 Primera versión (21/11/2026; IMAGE_FIELDS_VERSION 14, VIDEO_FIELDS_VERSION 6).

Prueba rápida (desde la raíz del proyecto):
    python -m core.metadata.camera_makers
"""

__version__ = "1.0.0"
__all__ = ["CAMERA_MAKERS", "maker_name", "model_name", "starts_with_maker"]

# Librerías estándar
import re
from typing import Any

# Módulos del proyecto
from core.metadata.field_spec import text

# Primera palabra de la marca (en minúsculas) -> nombre que se guarda. Comentadas, las
# formas vistas en archivos reales o en la documentación de ExifTool
CAMERA_MAKERS: dict[str, str] = {
    "apple": "Apple",
    "asahi": "Pentax",  # ASAHI OPTICAL CO.,LTD (Pentax antiguas)
    "bq": "BQ",  # bq, BQ
    "canon": "Canon",
    "casio": "Casio",  # CASIO COMPUTER CO.,LTD.
    "dji": "DJI",
    "eastman": "Kodak",  # EASTMAN KODAK COMPANY
    "fuji": "Fujifilm",  # FUJI PHOTO FILM CO., LTD.
    "fujifilm": "Fujifilm",  # FUJIFILM
    "google": "Google",
    "gopro": "GoPro",
    "hasselblad": "Hasselblad",
    "htc": "HTC",
    "huawei": "Huawei",  # HUAWEI
    "kodak": "Kodak",  # KODAK
    "konica": "Konica Minolta",  # KONICA MINOLTA, Konica Minolta Camera, Inc.
    "leica": "Leica",  # LEICA CAMERA AG
    "lg": "LG",  # LG Electronics
    "minolta": "Minolta",  # Minolta Co., Ltd.
    "motorola": "Motorola",  # motorola
    "nikon": "Nikon",  # NIKON CORPORATION, NIKON
    "nokia": "Nokia",  # NOKIA
    "olympus": "Olympus",  # OLYMPUS IMAGING CORP., OLYMPUS CORPORATION
    "oneplus": "OnePlus",
    "oppo": "OPPO",
    "panasonic": "Panasonic",
    "pentax": "Pentax",  # PENTAX, PENTAX Corporation
    "ricoh": "Ricoh",  # RICOH IMAGING COMPANY, LTD., RICOH
    "samsung": "Samsung",  # SAMSUNG, Samsung, SAMSUNG TECHWIN
    "sigma": "Sigma",  # SIGMA
    "sony": "Sony",  # SONY
    "xiaomi": "Xiaomi",
}  # fmt: skip

# Separadores de la primera palabra ('CASIO COMPUTER CO.,LTD.', 'NIKON,')
_WORD_SEPARATORS = re.compile(r"[\s,.;]+")


def _first_word(value: str) -> str:
    """Primera palabra en minúsculas ('' si no hay)."""
    words = [word for word in _WORD_SEPARATORS.split(value.casefold()) if word]
    return words[0] if words else ""


def _meaningful(value: Any) -> str | None:
    """Texto limpio, o None si no tiene ninguna letra ni cifra ('--')."""
    cleaned = text(value)
    if cleaned is None or not any(character.isalnum() for character in cleaned):
        return None
    return cleaned


def maker_name(value: Any) -> str | None:
    """Marca de la cámara como se guarda: el nombre corto de la lista, o tal cual."""
    maker = _meaningful(value)
    if maker is None:
        return None
    return CAMERA_MAKERS.get(_first_word(maker), maker)


def model_name(value: Any) -> str | None:
    """Modelo de la cámara como se guarda: tal cual, sin los valores vacíos ('--')."""
    return _meaningful(value)


def starts_with_maker(model: str | None) -> bool:
    """True si el modelo empieza por una marca de la lista ('PENTAX K-70', 'NIKON Df')."""
    return bool(model) and _first_word(model) in CAMERA_MAKERS


if __name__ == "__main__":
    # Autoprueba (sin ventana). Ejecutar desde la raíz:  python -m core.metadata.camera_makers

    # Las marcas del catálogo del autor y las de los RAW de prueba (21/11/2026)
    for raw, expected in (
        ("NIKON CORPORATION", "Nikon"), ("NIKON", "Nikon"), ("Apple", "Apple"),
        ("bq", "BQ"), ("BQ", "BQ"), ("CASIO COMPUTER CO.,LTD.", "Casio"), ("SONY", "Sony"),
        ("Canon", "Canon"), ("RICOH IMAGING COMPANY, LTD.", "Ricoh"), ("PENTAX", "Pentax"),
        ("FUJIFILM", "Fujifilm"), ("SAMSUNG", "Samsung"), ("Samsung", "Samsung"),
        ("Panasonic", "Panasonic"), ("DJI", "DJI"), ("FUJI PHOTO FILM CO., LTD.", "Fujifilm"),
        ("EASTMAN KODAK COMPANY", "Kodak"), ("OLYMPUS IMAGING CORP.", "Olympus"),
        # Las que no están en la lista, tal cual
        ("OM Digital Solutions", "OM Digital Solutions"), ("DS GLOBAL", "DS GLOBAL"),
    ):  # fmt: skip
        assert maker_name(raw) == expected, (raw, maker_name(raw))

    # Vacíos y valores sin letras ni cifras
    for empty in (None, "", "   ", "--", "-", "?"):
        assert maker_name(empty) is None and model_name(empty) is None, empty
    assert maker_name("  Nikon \x00") == "Nikon"

    # El modelo, tal cual
    assert model_name("PENTAX K-70") == "PENTAX K-70" and model_name("NIKON Df") == "NIKON Df"

    # ¿El modelo ya dice la marca?
    assert starts_with_maker("PENTAX K-70") and starts_with_maker("NIKON Df")
    assert starts_with_maker("Canon EOS D60") and starts_with_maker("RICOH GR III")
    for model in ("iPhone 17 Pro", "COOLPIX P1000", "ILCE-7M3", "X-T4", "", None):
        assert not starts_with_maker(model), model

    # La lista: claves en minúsculas y de una sola palabra
    for key in CAMERA_MAKERS:
        assert key == key.casefold() and _first_word(key) == key, key

    print(f"{len(CAMERA_MAKERS)} marcas en la lista.")
    print("Autoprueba finalizada correctamente.")
