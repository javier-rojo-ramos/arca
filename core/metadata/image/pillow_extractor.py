"""Extractor de metadatos EXIF básicos de imágenes (paso 1: con Pillow).

Este módulo NO depende de Qt. Solo lee la cabecera del archivo (no decodifica los
píxeles), así que es rápido: unos pocos milisegundos por imagen.

Qué lee (todo opcional: lo que no esté en el archivo queda vacío):

    En 'media_items' (columnas comunes):
        width, height, orientation        tamaño (ya girado según la orientación)
        content_created_at + fuente/precisión/zona horaria
                                          fecha de captura: EXIF DateTimeOriginal,
                                          o DateTimeDigitized, o DateTime; si no hay
                                          ninguna, la fecha de modificación del archivo
        latitude, longitude, altitude     GPS
        creator, copyright, description   Artist, Copyright, ImageDescription

    En 'photo_details' (campos propios de las fotos):
        camera_make, camera_model, lens_model, focal_length_mm, focal_length_35mm,
        f_number, exposure_time_s, iso, exposure_bias_ev, flash_fired, software

Formatos: JPEG, PNG, TIFF, WebP, GIF y BMP. Los demás (RAW, HEIC...) se avisan
como 'UnsupportedFormatError' y quedan pendientes de un extractor que los sepa
leer (paso siguiente: ExifTool). Los TIFF "con forma de RAW" (NEF, DNG...) se
excluyen a propósito: Pillow los abriría, pero devolvería el tamaño de su
miniatura incrustada, que sería un dato erróneo.

Ampliación futura: XMP e IPTC (título, pie de foto, ubicación, género...) llegarán
con otro motor; este extractor seguirá sirviendo como alternativa sin dependencias.

Prueba rápida (desde la raíz del proyecto):
    python -m core.metadata.image_extractor
"""

__version__ = "1.0.0"
__all__ = ["IMAGE_EXTRACTOR_VERSION", "ImageMetadataExtractor"]

# Librerías estándar
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger
from PIL import Image, UnidentifiedImageError

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.base import (
    ExtractionResult,
    MetadataError,
    MetadataExtractor,
    UnsupportedFormatError,
)

# Versión de este extractor: súbela cada vez que lea campos nuevos (se reprocesan
# las imágenes con una versión menor).
IMAGE_EXTRACTOR_VERSION = 3

# Extensiones que Pillow lee bien y cuyo tamaño es el real
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".webp", ".gif", ".bmp"}
)

# Etiquetas EXIF (números fijos del estándar, para no depender de la versión de Pillow)
# --- IFD principal (IFD0) ---
_TAG_IMAGE_DESCRIPTION = 0x010E
_TAG_MAKE = 0x010F
_TAG_MODEL = 0x0110
_TAG_ORIENTATION = 0x0112
_TAG_SOFTWARE = 0x0131
_TAG_DATETIME = 0x0132
_TAG_ARTIST = 0x013B
_TAG_COPYRIGHT = 0x8298
_TAG_EXIF_IFD = 0x8769  # puntero al IFD con los datos de la toma
_TAG_GPS_IFD = 0x8825  # puntero al IFD con los datos GPS
# --- IFD Exif (datos de la toma) ---
_TAG_EXPOSURE_TIME = 0x829A
_TAG_F_NUMBER = 0x829D
_TAG_ISO_SPEED_RATINGS = 0x8827
_TAG_ISO_SPEED = 0x8833
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_DATETIME_DIGITIZED = 0x9004
_TAG_OFFSET_TIME = 0x9010
_TAG_OFFSET_TIME_ORIGINAL = 0x9011
_TAG_OFFSET_TIME_DIGITIZED = 0x9012
_TAG_EXPOSURE_BIAS = 0x9204
_TAG_FLASH = 0x9209
_TAG_FOCAL_LENGTH = 0x920A
_TAG_FOCAL_LENGTH_35MM = 0xA405
_TAG_LENS_MODEL = 0xA434
# --- IFD GPS ---
_GPS_LATITUDE_REF = 1
_GPS_LATITUDE = 2
_GPS_LONGITUDE_REF = 3
_GPS_LONGITUDE = 4
_GPS_ALTITUDE_REF = 5
_GPS_ALTITUDE = 6

# "2026:09:12 14:48:51" (algunas cámaras usan '-' o 'T' en lugar de ':' y ' ')
_EXIF_DATE_PATTERN = re.compile(
    r"^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})"
)
_OFFSET_PATTERN = re.compile(r"^[+-]\d{2}:\d{2}$")


class ImageMetadataExtractor(MetadataExtractor):
    """Lee los metadatos EXIF básicos de imágenes con Pillow."""

    media_type: ClassVar[MediaType] = MediaType.PHOTO
    version: ClassVar[int] = IMAGE_EXTRACTOR_VERSION
    details_table: ClassVar[str | None] = "photo_details"

    def extract(self, path: Path) -> ExtractionResult:
        """Lee la cabecera de una imagen. Ver 'MetadataExtractor.extract'."""
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFormatError(
                f"Formato sin soporte todavía: {extension or 'sin extensión'}"
            )

        try:
            # 'Image.open' solo lee la cabecera: no decodifica los píxeles
            with Image.open(path) as image:
                width, height = image.size
                ifd0, exif_ifd, gps_ifd = self._read_ifds(image)
                xmp = _read_xmp(image)
        except FileNotFoundError:
            raise  # el procesador lo trata como "archivo desaparecido"
        except PermissionError as exc:
            raise MetadataError("Sin permiso para leer el archivo") from exc
        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            OSError,
            SyntaxError,
            ValueError,
        ) as exc:
            raise MetadataError(
                f"No es una imagen válida o está dañada ({type(exc).__name__})"
            ) from exc

        # La orientación EXIF 5 a 8 gira la imagen 90°: el tamaño "de pantalla" intercambia
        # ancho y alto. Se guarda ya girado: es la proporción real de la miniatura.
        orientation = _orientation(ifd0.get(_TAG_ORIENTATION))
        if orientation >= 5:
            width, height = height, width

        common: dict[str, Any] = {
            "width": width,
            "height": height,
            "orientation": orientation,
            "creator": _clean_text(ifd0.get(_TAG_ARTIST)),
            "copyright": _clean_text(ifd0.get(_TAG_COPYRIGHT)),
            "description": _clean_text(ifd0.get(_TAG_IMAGE_DESCRIPTION)),
            "latitude": _gps_coordinate(
                gps_ifd.get(_GPS_LATITUDE), gps_ifd.get(_GPS_LATITUDE_REF), "S", 90.0
            ),
            "longitude": _gps_coordinate(
                gps_ifd.get(_GPS_LONGITUDE), gps_ifd.get(_GPS_LONGITUDE_REF), "W", 180.0
            ),
            "altitude": _gps_altitude(
                gps_ifd.get(_GPS_ALTITUDE), gps_ifd.get(_GPS_ALTITUDE_REF)
            ),
            "sublocation": _find_xmp_value(xmp, "Location"),
            "city": _find_xmp_value(xmp, "City"),
            "region": _find_xmp_value(xmp, "State"),
            "country": _find_xmp_value(xmp, "Country"),
        }
        common.update(_content_date(ifd0, exif_ifd, path))

        details: dict[str, Any] = {
            "camera_make": _clean_text(ifd0.get(_TAG_MAKE)),
            "camera_model": _clean_text(ifd0.get(_TAG_MODEL)),
            "lens_model": _clean_text(exif_ifd.get(_TAG_LENS_MODEL)),
            "focal_length_mm": _to_float(exif_ifd.get(_TAG_FOCAL_LENGTH)),
            "focal_length_35mm": _to_float(exif_ifd.get(_TAG_FOCAL_LENGTH_35MM)),
            "f_number": _to_float(exif_ifd.get(_TAG_F_NUMBER)),
            "exposure_time_s": _to_float(exif_ifd.get(_TAG_EXPOSURE_TIME)),
            "iso": _iso(exif_ifd),
            "exposure_bias_ev": _to_float(exif_ifd.get(_TAG_EXPOSURE_BIAS)),
            "flash_fired": _flash_fired(exif_ifd.get(_TAG_FLASH)),
            "software": _clean_text(ifd0.get(_TAG_SOFTWARE)),
        }
        return ExtractionResult(common=common, details=details)

    @staticmethod
    def _read_ifds(image: Image.Image) -> tuple[dict, dict, dict]:
        """Devuelve los tres bloques EXIF (principal, de la toma y GPS) como diccionarios.

        Un EXIF mal formado es muy frecuente: si no se puede interpretar, la imagen
        sigue siendo válida y simplemente se queda sin esos datos.
        """
        try:
            exif = image.getexif()
            return (
                dict(exif),
                dict(exif.get_ifd(_TAG_EXIF_IFD)),
                dict(exif.get_ifd(_TAG_GPS_IFD)),
            )
        except Exception:  # noqa: BLE001 - cualquier fallo de Pillow en un EXIF corrupto
            logger.debug("EXIF ilegible; se continúa sin él.")
            return {}, {}, {}


# -----------------------------------------------------------------------------
# Conversión de valores (funciones puras, fáciles de probar)
# -----------------------------------------------------------------------------


def _clean_text(value: Any) -> str | None:
    """Convierte un valor de texto EXIF en un 'str' limpio, o None si está vacío.

    Muchas cámaras rellenan los textos con espacios o con caracteres nulos.
    """
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return None
    cleaned = _fix_utf8_read_as_latin1(value.replace("\x00", "").strip())
    return cleaned or None


def _fix_utf8_read_as_latin1(text: str) -> str:
    """Repara los acentos de un texto UTF-8 que Pillow ha leído como Latin-1.

    El estándar EXIF dice "ASCII", pero móviles, Lightroom y muchos programas
    escriben UTF-8 ('Pérez'). Pillow decodifica esos campos como Latin-1 y
    entrega 'PÃ©rez'. Si el texto, vuelto a Latin-1, es UTF-8 válido, se
    recupera; si no (es un Latin-1 auténtico), se deja tal cual.
    """
    if text.isascii():
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _to_float(value: Any) -> float | None:
    """Convierte un número EXIF (entero, decimal o fracción) en 'float', o None si no vale."""
    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
    if value is None or isinstance(value, (str, bytes)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    # Una fracción con denominador 0 da 'nan'
    return number if math.isfinite(number) else None


def _read_xmp(image: Image.Image) -> dict:
    """Lee el XMP de la imagen ({} si no tiene, está roto o falta defusedxml)."""
    try:
        return image.getxmp()
    except Exception:  # noqa: BLE001 - un XMP roto no debe invalidar la imagen
        return {}


def _find_xmp_value(node: Any, name: str) -> str | None:
    """Busca un campo XMP por su nombre (sin prefijo) en el diccionario anidado."""
    if isinstance(node, dict):
        if isinstance(node.get(name), str):
            return _clean_text(node[name])
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            if (found := _find_xmp_value(child, name)) is not None:
                return found
    return None


def _iso(exif_ifd: dict) -> int | None:
    """Sensibilidad ISO: etiqueta clásica o, si falta, la ampliada (cámaras recientes)."""
    iso = _to_float(exif_ifd.get(_TAG_ISO_SPEED_RATINGS))
    if iso is None:
        iso = _to_float(exif_ifd.get(_TAG_ISO_SPEED))
    return int(iso) if iso is not None and iso > 0 else None


def _flash_fired(value: Any) -> int | None:
    """1 si el flash se disparó, 0 si no, None si no consta. El bit 0 indica el disparo."""
    number = _to_float(value)
    return None if number is None else int(number) & 1


def _orientation(value: Any) -> int:
    """Orientación EXIF 1 a 8 (1 = normal). Cualquier valor raro se toma como normal."""
    number = _to_float(value)
    return int(number) if number is not None and 1 <= int(number) <= 8 else 1


def _parse_exif_datetime(value: Any) -> str | None:
    """'2026:09:12 14:48:51' -> '2026-09-12 14:48:51'. None si no es una fecha real.

    Rechaza las fechas vacías que ponen algunas cámaras ('0000:00:00 00:00:00').
    """
    text = _clean_text(value)
    match = _EXIF_DATE_PATTERN.match(text) if text else None
    if match is None:
        return None
    try:
        parsed = datetime(*(int(group) for group in match.groups()))
    except ValueError:
        return None
    return parsed.isoformat(sep=" ")


def _parse_offset(value: Any) -> str | None:
    """Desfase horario ISO 8601 ('+02:00'), o None si no tiene ese formato."""
    text = _clean_text(value)
    return text if text and _OFFSET_PATTERN.match(text) else None


def _gps_coordinate(
    dms: Any, reference: Any, negative_reference: str, limit: float
) -> float | None:
    """Convierte grados/minutos/segundos EXIF en grados decimales con signo.

    Args:
        dms: Tupla (grados, minutos, segundos) de fracciones.
        reference: 'N'/'S' o 'E'/'W'.
        negative_reference: Letra que hace negativo el valor ('S' o 'W').
        limit: Valor absoluto máximo válido (90 para latitud, 180 para longitud).
    """
    if not isinstance(dms, (tuple, list)) or not dms:
        return None
    parts = [_to_float(part) for part in dms]
    if any(part is None for part in parts):
        return None
    # grados + minutos/60 + segundos/3600
    value = sum(part / (60**index) for index, part in enumerate(parts))
    if isinstance(reference, bytes):
        reference = reference.decode("ascii", errors="ignore")
    if str(reference).strip().upper() == negative_reference:
        value = -value
    return value if abs(value) <= limit else None


def _gps_altitude(value: Any, reference: Any) -> float | None:
    """Altitud en metros. La referencia 1 indica por debajo del nivel del mar."""
    altitude = _to_float(value)
    if altitude is None:
        return None
    below_sea_level = reference in (1, b"\x01") or _to_float(reference) == 1
    return -altitude if below_sea_level else altitude


def _content_date(ifd0: dict, exif_ifd: dict, path: Path) -> dict[str, Any]:
    """Fecha de captura y datos asociados, probando varias fuentes por orden de fiabilidad.

    Orden: DateTimeOriginal, DateTimeDigitized, DateTime y, como último recurso,
    la fecha de modificación del archivo (se anota como fuente 'file_mtime' para
    poder distinguirla de una fecha de captura real).
    """
    candidates = (
        (exif_ifd.get(_TAG_DATETIME_ORIGINAL), exif_ifd.get(_TAG_OFFSET_TIME_ORIGINAL)),
        (
            exif_ifd.get(_TAG_DATETIME_DIGITIZED),
            exif_ifd.get(_TAG_OFFSET_TIME_DIGITIZED),
        ),
        (ifd0.get(_TAG_DATETIME), exif_ifd.get(_TAG_OFFSET_TIME)),
    )
    for raw_date, raw_offset in candidates:
        parsed = _parse_exif_datetime(raw_date)
        if parsed is not None:
            return {
                "content_created_at": parsed,
                "content_date_precision": "second",
                "content_date_source": "exif",
                "timezone_offset": _parse_offset(raw_offset),
            }

    # Sin fecha en el archivo: la de modificación (hora local, como las de EXIF)
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, OverflowError, ValueError):
        return {
            "content_created_at": None,
            "content_date_precision": None,
            "content_date_source": None,
            "timezone_offset": None,
        }
    return {
        "content_created_at": modified.replace(microsecond=0).isoformat(sep=" "),
        "content_date_precision": "second",
        "content_date_source": "file_mtime",
        "timezone_offset": None,
    }


if __name__ == "__main__":
    # Autoprueba con imágenes reales generadas en una carpeta temporal.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.image_extractor
    import os
    import tempfile

    from PIL.TiffImagePlugin import IFDRational

    extractor = ImageMetadataExtractor()

    def rational(numerator: int, denominator: int = 1) -> IFDRational:
        """Crea una fracción EXIF."""
        return IFDRational(numerator, denominator)

    def make_jpeg(path: Path, exif_data: dict | None = None, size=(400, 300)) -> Path:
        """Crea un JPEG pequeño con los datos EXIF indicados."""
        exif = Image.Exif()
        for tag, value in (exif_data or {}).items():
            exif[tag] = value
        extra = {"exif": exif} if exif_data else {}  # Pillow no admite exif=None
        Image.new("RGB", size, "gray").save(path, **extra)
        return path

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # 1. JPEG con EXIF completo, girado 90° y con GPS en el hemisferio norte/oeste
        full = make_jpeg(
            base / "completa.jpg",
            {
                _TAG_MAKE: "Canon\x00  ",
                _TAG_MODEL: "Canon EOS R5",
                _TAG_ORIENTATION: 6,
                _TAG_SOFTWARE: "Firmware 1.8",
                # Con acentos, como los escriben los móviles y Lightroom: bytes UTF-8
                # (Pillow solo sabe escribir ASCII a partir de un 'str')
                _TAG_ARTIST: "Ana Pérez".encode(),
                _TAG_COPYRIGHT: "© Ana Pérez".encode(),
                _TAG_IMAGE_DESCRIPTION: "Atardecer en Rascafría".encode(),
                _TAG_EXIF_IFD: {
                    _TAG_EXPOSURE_TIME: rational(1, 250),
                    _TAG_F_NUMBER: rational(28, 10),
                    _TAG_ISO_SPEED_RATINGS: 400,
                    _TAG_DATETIME_ORIGINAL: "2026:09:12 14:48:51",
                    _TAG_OFFSET_TIME_ORIGINAL: "+02:00",
                    _TAG_EXPOSURE_BIAS: rational(-7, 10),
                    _TAG_FLASH: 9,
                    _TAG_FOCAL_LENGTH: rational(85),
                    _TAG_FOCAL_LENGTH_35MM: 85,
                    _TAG_LENS_MODEL: "RF85mm F1.2 L USM",
                },
                _TAG_GPS_IFD: {
                    _GPS_LATITUDE_REF: "N",
                    _GPS_LATITUDE: (rational(40), rational(54), rational(833, 100)),
                    _GPS_LONGITUDE_REF: "W",
                    _GPS_LONGITUDE: (rational(3), rational(54), rational(5669, 100)),
                    _GPS_ALTITUDE_REF: 0,
                    _GPS_ALTITUDE: rational(1150),
                },
            },
        )
        result = extractor.extract(full)
        common, details = result.common, result.details
        print("JPEG completo:", {**common, **details})
        assert (common["width"], common["height"]) == (
            300,
            400,
        )  # girado por orientación 6
        assert common["orientation"] == 6
        assert common["content_created_at"] == "2026-09-12 14:48:51"
        assert (
            common["content_date_source"] == "exif"
            and common["timezone_offset"] == "+02:00"
        )
        assert (
            common["creator"] == "Ana Pérez"
            and common["description"] == "Atardecer en Rascafría"
        )
        assert abs(common["latitude"] - 40.902314) < 1e-5  # 40°54'8.33" N
        assert abs(common["longitude"] - (-3.915747)) < 1e-5  # 3°54'56.69" W
        assert common["altitude"] == 1150.0
        assert (
            details["camera_make"] == "Canon"
            and details["camera_model"] == "Canon EOS R5"
        )
        assert details["lens_model"] == "RF85mm F1.2 L USM"
        assert (
            details["focal_length_mm"] == 85.0 and details["focal_length_35mm"] == 85.0
        )
        assert (
            abs(details["f_number"] - 2.8) < 1e-9
            and abs(details["exposure_time_s"] - 0.004) < 1e-9
        )
        assert details["iso"] == 400 and abs(details["exposure_bias_ev"] + 0.7) < 1e-9
        assert details["flash_fired"] == 1 and details["software"] == "Firmware 1.8"

        # 2. PNG sin EXIF: dimensiones correctas y fecha de respaldo = modificación del archivo
        png = base / "sin_exif.png"
        Image.new("RGB", (64, 32), "red").save(png)
        os.utime(png, (1_700_000_000, 1_700_000_000))
        result = extractor.extract(png)
        assert (result.common["width"], result.common["height"]) == (64, 32)
        assert result.common["orientation"] == 1
        assert result.common["content_date_source"] == "file_mtime"
        assert (
            result.common["latitude"] is None and result.details["camera_make"] is None
        )
        print("PNG sin EXIF: fecha de respaldo =", result.common["content_created_at"])

        # 3. Fecha vacía de cámara ('0000:00:00...'): se ignora y se usa la siguiente fuente
        broken_date = make_jpeg(
            base / "fecha_vacia.jpg",
            {
                _TAG_EXIF_IFD: {
                    _TAG_DATETIME_ORIGINAL: "0000:00:00 00:00:00",
                    _TAG_DATETIME_DIGITIZED: "2020:01:02 03:04:05",
                }
            },
        )
        result = extractor.extract(broken_date)
        assert result.common["content_created_at"] == "2020-01-02 03:04:05"

        # 4. Hemisferio sur / este y altitud bajo el nivel del mar
        south = make_jpeg(
            base / "sur.jpg",
            {
                _TAG_GPS_IFD: {
                    _GPS_LATITUDE_REF: "S",
                    _GPS_LATITUDE: (rational(33), rational(30), rational(0)),
                    _GPS_LONGITUDE_REF: "E",
                    _GPS_LONGITUDE: (rational(151), rational(0), rational(0)),
                    _GPS_ALTITUDE_REF: 1,
                    _GPS_ALTITUDE: rational(10),
                }
            },
        )
        result = extractor.extract(south)
        assert (
            result.common["latitude"] == -33.5 and result.common["longitude"] == 151.0
        )
        assert result.common["altitude"] == -10.0

        # 5. Archivo dañado, formato sin soporte y archivo inexistente
        corrupt = base / "rota.jpg"
        corrupt.write_bytes(b"esto no es una imagen" * 50)
        try:
            extractor.extract(corrupt)
        except MetadataError as error:
            assert not isinstance(error, UnsupportedFormatError)
            print("Imagen dañada:", error)
        else:
            raise AssertionError("Debería rechazar un archivo dañado")

        heic = base / "iphone.HEIC"
        heic.write_bytes(b"x" * 100)
        try:
            extractor.extract(heic)
        except UnsupportedFormatError as error:
            print("Formato sin soporte:", error)
        else:
            raise AssertionError("HEIC aún no está soportado en este extractor")

        try:
            extractor.extract(base / "no_existe.jpg")
        except FileNotFoundError:
            print("Archivo inexistente: FileNotFoundError")
        else:
            raise AssertionError("Debería lanzar FileNotFoundError")

        # 6. Funciones de conversión con valores raros
        assert _parse_exif_datetime("0000:00:00 00:00:00") is None
        assert _parse_exif_datetime("2026-09-12T14:48:51") == "2026-09-12 14:48:51"
        assert (
            _parse_exif_datetime("basura") is None
            and _parse_exif_datetime(None) is None
        )
        assert _parse_offset("+02:00") == "+02:00" and _parse_offset("CEST") is None
        assert _to_float(rational(1, 0)) is None  # denominador 0
        assert _clean_text("  \x00  ") is None and _clean_text(b"Nikon \x00") == "Nikon"
        # UTF-8 leído como Latin-1 se repara; un Latin-1 auténtico se respeta
        assert _clean_text("PÃ©rez") == "Pérez" and _clean_text("Pérez") == "Pérez"
        assert (
            _gps_coordinate((rational(95), rational(0), rational(0)), "N", "S", 90.0)
            is None
        )
        assert _orientation(99) == 1 and _orientation("x") == 1 and _orientation(8) == 8
        assert _iso({_TAG_ISO_SPEED: 1600}) == 1600 and _iso({}) is None

    print("Autoprueba finalizada correctamente.")
