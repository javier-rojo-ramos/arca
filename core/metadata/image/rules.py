"""Reglas especiales de las imágenes: lo que no es un simple "etiqueta -> columna".

Se ejecutan DESPUÉS de rellenar la lista de campos ('fields.py'), con los valores ya
leídos, y los ajustan en el sitio. Son seis:

    1. Orientación y tamaño: las imágenes giradas (orientación EXIF 5 a 8 o, en HEIC, HEIF
       y AVIF, el cuarto de vuelta de su caja 'irot') intercambian ancho y alto. Se
       guarda el tamaño "de pantalla", que es la proporción real de la miniatura. En los
       RAW de Nikon, Olympus y Pentax, el área útil (la de Lightroom), no el sensor completo.
    1b. Recorte de Lightroom ("Dimensiones actuales"): se calcula con los ajustes de
       revelado del XMP ('crs:Crop*') y el tamaño, antes de girarlo.
    2. Fecha de captura: depende de varias etiquetas a la vez (fecha, zona horaria,
       de dónde salió y con qué precisión) y tiene respaldo en la fecha del archivo. Los
       CRW, sin EXIF, la traen en 'CanonRaw:DateTimeOriginal' (origen 'crw').
    3. Flash: 'flash_fired' (0 o 1) se deriva del código de flash.
    4. GPS: la latitud y la longitud salen de una sola fuente (el XMP si tiene las dos; si
       no, el EXIF), la altitud del XMP lleva su referencia aparte (sobre o bajo el nivel
       del mar) y se descartan las coordenadas imposibles.
    5. Nota del fabricante: el objetivo de las cámaras que no guardan su nombre (las
       réflex Nikon), compuesto con sus números como Lightroom («20.0 mm f/1.8»), y el
       número de serie de los CRW, con sus 10 cifras.

Si cambias algo aquí, sube 'IMAGE_FIELDS_VERSION' (en 'fields.py').

El tamaño, comprobado con Lightroom el 21/11/2026: los HEIC y AVIF (ExifTool da el tamaño
sin girar: 'Composite:ImageSize' 4032 3024 en una foto vertical del iPhone) y RAW de
Canon (CR2, CR3, CRW), Fujifilm, Panasonic, Sony (ARW), Nikon (NEF), OM System, Pentax (PEF)
y DNG.
Sin arreglo: Nikon Coolpix (NRW) y los Sony SRF y SR2 antiguos dan el sensor completo,
entre un 0,5 % y un 3 % más que Lightroom (no traen ninguna etiqueta con el área útil).
Con 'python -m core.metadata.inspect_cli archivo.heic --campos' se ve qué guarda
la aplicación y se compara con Lightroom.

1.7.0 PEF (Pentax): el área útil de 'Pentax:RawImageSize', la de Lightroom (4928 × 3264 en
      una K-5), en lugar del sensor completo ('IMAGE_FIELDS_VERSION' 13).
1.6.0 Los CRW (sin EXIF): la fecha de 'CanonRaw:DateTimeOriginal' (antes, la del archivo) y
      el número de serie; el objetivo de las réflex Nikon, de 'Nikon:Lens' (salían sin
      objetivo) ('IMAGE_FIELDS_VERSION' 12).
1.5.0 RAW de Nikon y Olympus: el área útil de su nota del fabricante ('Nikon:CropArea',
      'Nikon:AFImageWidth/Height', 'Olympus:CropWidth/Height'), la que muestra Lightroom,
      en lugar del sensor completo ('IMAGE_FIELDS_VERSION' 11).
1.4.0 HEIC, HEIF y AVIF: el giro de su caja 'irot' ('QuickTime:Rotation') decide si se
      intercambian ancho y alto; un AVIF con el giro solo ahí salía apaisado
      ('IMAGE_FIELDS_VERSION' 10).
1.3.0 'gps_from_tags' y 'GPS_SOURCE_TAGS': el GPS de un archivo leído como el extractor, para
      comprobar lo escrito (core/userdata/xmp_writer.py). La lectura no cambia.
1.2.0 GPS: pareja de coordenadas de una sola fuente (primero el XMP) y altitud del XMP con
      su referencia ('IMAGE_FIELDS_VERSION' 9).
"""

__version__ = "1.7.0"
__all__ = ["GPS_COLUMNS", "GPS_SOURCE_TAGS", "apply_image_rules", "crop_size", "gps_from_tags"]

# Librerías estándar
import math
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

# Módulos del proyecto
from core.metadata.field_spec import (
    common,
    integer,
    lens_from_spec,
    lookup,
    orientation_code,
    parse_datetime,
    parse_offset,
    read_field,
    real,
)
from core.metadata.image.fields import IMAGE_FIELDS

# Parejas de coordenadas, en orden: el XMP y, si no tiene las dos, el compuesto de ExifTool
# (sale del EXIF). Son las mismas etiquetas, y en el mismo orden, que en 'fields.py'
_GPS_PAIRS: tuple[tuple[str, str], ...] = (
    ("XMP-exif:GPSLatitude", "XMP-exif:GPSLongitude"),
    ("Composite:GPSLatitude", "Composite:GPSLongitude"),
)

# Columnas del GPS, sus líneas de 'fields.py' y TODAS las etiquetas de las que se leen (con
# la referencia de la altitud del XMP): para leer el GPS de un archivo como el extractor
GPS_COLUMNS: tuple[str, ...] = ("latitude", "longitude", "altitude", "gps_direction")
_GPS_FIELDS = tuple(spec for spec in IMAGE_FIELDS if spec.column in GPS_COLUMNS)
GPS_SOURCE_TAGS: tuple[str, ...] = (
    *dict.fromkeys(tag for spec in _GPS_FIELDS for tag in spec.sources),
    "XMP-exif:GPSAltitudeRef",
)

# Orígenes de la fecha de captura, por orden de fiabilidad:
# (etiqueta, nombre del origen, etiqueta con la zona horaria si la fecha no la trae)
_CAPTURE_DATE_SOURCES: tuple[tuple[str, str, str | None], ...] = (
    ("ExifIFD:DateTimeOriginal", "exif", "ExifIFD:OffsetTimeOriginal"),
    ("ExifIFD:CreateDate", "exif", "ExifIFD:OffsetTimeDigitized"),
    # Los CRW (Canon, hasta 2004) no tienen EXIF: la de la cámara va en su propio formato
    ("CanonRaw:DateTimeOriginal", "crw", None),
    ("XMP-photoshop:DateCreated", "xmp", None),
    ("Composite:DateTimeCreated", "iptc", None),
    ("IFD0:ModifyDate", "exif", "ExifIFD:OffsetTime"),  # la menos fiable: la última edición
)

_ORIENTATION = common("orientation", ("IFD0:Orientation", "XMP-tiff:Orientation"), orientation_code)

# HEIC, HEIF y AVIF ('File:FileType') guardan el giro en su propia caja 'irot', que ExifTool
# da como 'QuickTime:Rotation': cuartos de vuelta en sentido antihorario, de 0 a 3 (con '-n').
# Es el giro que aplican libheif y Pillow al decodificar (el de la miniatura), así que, si
# está, manda sobre la orientación EXIF. Los HEIC del iPhone traen los dos, iguales; un AVIF
# puede traer solo el 'irot' (Pillow, al escribirlo, pasa ahí la orientación y la quita del EXIF).
_HEIF_FILE_TYPES = frozenset({"HEIC", "HEIF", "AVIF"})
# Del 'irot' a la orientación EXIF que gira lo mismo. Sin espejo: la caja 'imir' no cambia el
# tamaño, y ExifTool no la da
_IROT_ORIENTATIONS: dict[int, int] = {0: 1, 1: 8, 2: 3, 3: 6}

# RAW que no son DNG: el área útil, la que Lightroom muestra como "Dimensiones de archivo"
# ('Composite:ImageSize' es el sensor completo, algo mayor), sale de la nota del fabricante.
# Comprobado con Lightroom el 21/11/2026: Nikon Df (AF) y Z6 (las dos), OM System OM-1 y
# Pentax K-5. En los DNG manda 'DefaultCropSize' ('fields.py'). Por orden: 'Nikon:CropArea'
# ('izquierda arriba ancho alto'), las etiquetas con 'ancho alto' y las parejas (ancho, alto)
_RAW_USEFUL_SIZE_TAGS: tuple[str, ...] = ("Pentax:RawImageSize",)
_RAW_USEFUL_SIZE_PAIRS: tuple[tuple[str, str], ...] = (
    ("Nikon:AFImageWidth", "Nikon:AFImageHeight"),
    ("Olympus:CropWidth", "Olympus:CropHeight"),
)
# El área útil recorta solo los bordes del sensor (Df, 98,7 %): un valor por debajo de esta
# proporción, o mayor que el sensor, no es eso y se ignora
_RAW_USEFUL_MIN_RATIO = 0.9

# Objetivo descrito con sus números (focal mínima y máxima, diafragma máximo en cada una):
# las réflex Nikon no guardan su nombre, y con '-n' 'Composite:LensID' es un código
_LENS_SPEC_TAG = "Nikon:Lens"

# Número de serie de los CRW: con '-n' llega como número (910501743); ExifTool y Lightroom
# lo muestran con sus 10 cifras («0910501743»)
_CRW_SERIAL_TAG = "CanonRaw:SerialNumber"


def apply_image_rules(
    tags: Mapping[str, Any], common_values: dict[str, Any], details: dict[str, Any], path: Path
) -> None:
    """Aplica las reglas especiales de imagen. Ver la cabecera del módulo."""
    _orientation_and_size(tags, common_values, details)
    _capture_date(tags, common_values, path)
    _flash(details)
    _gps(tags, common_values)
    _maker_note_details(tags, details)


def _maker_note_details(tags: Mapping[str, Any], details: dict[str, Any]) -> None:
    """Objetivo y número de serie de la nota del fabricante, si no hay otros."""
    if details.get("lens_model") is None:
        details["lens_model"] = lens_from_spec(lookup(tags, _LENS_SPEC_TAG))
    if details.get("body_serial_number") is None:
        serial = integer(lookup(tags, _CRW_SERIAL_TAG))
        details["body_serial_number"] = f"{serial:010d}" if serial and serial > 0 else None


def _orientation_and_size(
    tags: Mapping[str, Any], common_values: dict[str, Any], details: dict[str, Any]
) -> None:
    """Orientación (1 si no consta), tamaño y recorte ya girados."""
    turns = _heif_rotation(tags)
    # La orientación, la del EXIF o el XMP; si no consta, la que equivale al 'irot'
    orientation = read_field(_ORIENTATION, tags) or (
        _IROT_ORIENTATIONS[turns] if turns is not None else 1
    )
    common_values["orientation"] = orientation
    # Cuarto de vuelta: con 'irot', lo dice el 'irot' (aunque el EXIF diga otra cosa); si no,
    # las orientaciones EXIF 5 a 8
    quarter_turn = turns % 2 == 1 if turns is not None else orientation >= 5
    width, height = common_values.get("width"), common_values.get("height")
    useful = _raw_useful_size(tags, width, height)
    if useful is not None:
        width, height = useful
        common_values["width"], common_values["height"] = width, height
    # El recorte se calcula sobre el tamaño SIN girar (así lo guarda Lightroom)
    crop = crop_size(tags, width, height)
    if quarter_turn and width and height:
        common_values["width"], common_values["height"] = height, width
        if crop is not None:
            crop = (crop[1], crop[0])
    details["crop_width"], details["crop_height"] = crop if crop is not None else (None, None)


def _raw_useful_size(
    tags: Mapping[str, Any], width: int | None, height: int | None
) -> tuple[int, int] | None:
    """Área útil (ancho, alto) de un RAW que no es DNG, sin girar; None si no consta.

    'width' y 'height' son el tamaño del sensor completo: el área útil tiene que caber en
    él y ocupar al menos '_RAW_USEFUL_MIN_RATIO' en las dos medidas.
    """
    if not width or not height or lookup(tags, "DefaultCropSize") is not None:
        return None
    candidates: list[tuple[int | None, int | None]] = []
    numbers = [int(n) for n in re.findall(r"\d+", str(lookup(tags, "Nikon:CropArea") or ""))]
    if len(numbers) == 4:
        candidates.append((numbers[2], numbers[3]))
    for size_tag in _RAW_USEFUL_SIZE_TAGS:
        numbers = [int(n) for n in re.findall(r"\d+", str(lookup(tags, size_tag) or ""))]
        if len(numbers) == 2:
            candidates.append((numbers[0], numbers[1]))
    for width_tag, height_tag in _RAW_USEFUL_SIZE_PAIRS:
        candidates.append((integer(lookup(tags, width_tag)), integer(lookup(tags, height_tag))))
    for useful_width, useful_height in candidates:
        if (
            useful_width
            and useful_height
            and _RAW_USEFUL_MIN_RATIO * width <= useful_width <= width
            and _RAW_USEFUL_MIN_RATIO * height <= useful_height <= height
        ):
            return useful_width, useful_height
    return None


def _heif_rotation(tags: Mapping[str, Any]) -> int | None:
    """Cuartos de vuelta del 'irot' de un HEIC, HEIF o AVIF (0 a 3), o None si no lo trae."""
    if lookup(tags, "File:FileType") not in _HEIF_FILE_TYPES:
        return None
    turns = integer(lookup(tags, "QuickTime:Rotation"))
    return turns if turns in _IROT_ORIENTATIONS else None


def _crop_number(tags: Mapping[str, Any], name: str) -> float | None:
    """Un valor numérico 'XMP-crs:<name>' (del archivo o del sidecar), o None."""
    value = lookup(tags, f"XMP-crs:{name}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_true(value: Any) -> bool:
    """ExifTool da los booleanos XMP como True/False o como texto 'True'/'False'."""
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def crop_size(tags: Mapping[str, Any], width: int | None, height: int | None) -> tuple[int, int] | None:
    """Ancho y alto del recorte de Lightroom ("Dimensiones actuales"), o None si no hay.

    Lightroom guarda el recorte en los ajustes de revelado del XMP:
        crs:HasCrop                          True si hay recorte.
        crs:CropLeft/Top/Right/Bottom        Esquinas SUPERIOR IZQUIERDA (Left, Top) e
                                             INFERIOR DERECHA (Right, Bottom) del recorte,
                                             de 0 a 1 sobre la imagen sin girar.
        crs:CropAngle                        Enderezado, en grados.
        crs:AlreadyApplied                   True si el recorte ya está en los píxeles.

    Con ángulo, el recorte es un rectángulo girado y esas dos esquinas son opuestas: la
    diagonal (dx, dy) en píxeles, girada el ángulo, da el ancho y el alto:
        ancho = dx·cos(a) + dy·sen(a)      alto = −dx·sen(a) + dy·cos(a)
    Comprobado con Lightroom Classic 15.6: DNG 3200 × 2128 sin ángulo -> 2865 × 1910;
    JPG 4051 × 2700 con −4,2° -> 3658 × 2439 (las «Dimensiones actuales» exactas).

    Args:
        tags: Etiquetas de ExifTool (con el sidecar ya combinado).
        width, height: Tamaño de la imagen SIN girar por la orientación.
    """
    if not width or not height or not _is_true(lookup(tags, "XMP-crs:HasCrop")):
        return None
    if _is_true(lookup(tags, "XMP-crs:AlreadyApplied")):
        return None  # el archivo ya está recortado: sus dimensiones son las actuales
    left, top = _crop_number(tags, "CropLeft"), _crop_number(tags, "CropTop")
    right, bottom = _crop_number(tags, "CropRight"), _crop_number(tags, "CropBottom")
    if None in (left, top, right, bottom):
        return None
    angle = math.radians(_crop_number(tags, "CropAngle") or 0.0)
    dx, dy = (right - left) * width, (bottom - top) * height
    crop_width = round(dx * math.cos(angle) + dy * math.sin(angle))
    crop_height = round(-dx * math.sin(angle) + dy * math.cos(angle))
    if crop_width <= 0 or crop_height <= 0:
        return None  # datos incoherentes
    return crop_width, crop_height


def _capture_date(tags: Mapping[str, Any], common_values: dict[str, Any], path: Path) -> None:
    """Fecha de captura con su zona horaria, origen y precisión."""
    for tag, origin, offset_tag in _CAPTURE_DATE_SOURCES:
        parsed = parse_datetime(lookup(tags, tag))
        if parsed is None:
            continue
        # La zona horaria puede venir en la propia fecha o en una etiqueta aparte
        offset = parsed.offset or (parse_offset(lookup(tags, offset_tag)) if offset_tag else None)
        common_values.update(
            content_created_at=parsed.text,
            content_date_precision=parsed.precision,
            content_date_source=origin,
            timezone_offset=offset,
        )
        return

    # Sin ninguna fecha en el archivo: la de modificación (hora local, como las de EXIF).
    # Se anota como origen 'file_mtime' para distinguirla de una fecha de captura real.
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        common_values.update(
            content_created_at=modified.replace(microsecond=0).isoformat(sep=" "),
            content_date_precision="second",
            content_date_source="file_mtime",
            timezone_offset=None,
        )
    except (OSError, OverflowError, ValueError):
        common_values.update(
            content_created_at=None,
            content_date_precision=None,
            content_date_source=None,
            timezone_offset=None,
        )


def _flash(details: dict[str, Any]) -> None:
    """'flash_fired' = bit 0 del código EXIF del flash (1 = disparado)."""
    code = details.get("flash_code")
    details["flash_fired"] = None if code is None else int(code) & 1


def _gps(tags: Mapping[str, Any], common_values: dict[str, Any]) -> None:
    """Coordenadas de una sola fuente, altitud del XMP con su signo y nada imposible.

    - La latitud y la longitud salen de la MISMA fuente: del XMP si tiene las dos y, si
      no, del compuesto de ExifTool (el EXIF). Campo a campo se podría juntar una latitud
      del XMP con una longitud del EXIF.
    - La altitud del XMP no lleva el signo: va en 'XMP-exif:GPSAltitudeRef' (1 = bajo el
      nivel del mar; sin ella, sobre él, que es lo que escribe Lightroom). La del
      compuesto ya lo lleva, y la de 'GPS:GPSAltitude' solo se usa sin referencia.
    - Se descartan las coordenadas fuera de rango o '0, 0' (el valor que ponen algunas
      cámaras sin cobertura).
    """
    latitude = longitude = None
    for latitude_tag, longitude_tag in _GPS_PAIRS:
        latitude, longitude = real(tags.get(latitude_tag)), real(tags.get(longitude_tag))
        if latitude is not None and longitude is not None:
            break
    invalid = (
        latitude is None
        or longitude is None
        or abs(latitude) > 90
        or abs(longitude) > 180
        or (latitude == 0 and longitude == 0)
    )
    common_values["latitude"] = None if invalid else latitude
    common_values["longitude"] = None if invalid else longitude

    # La altitud salió del XMP si lo tiene (es su primera fuente en 'fields.py')
    altitude = common_values.get("altitude")
    if altitude is not None and real(tags.get("XMP-exif:GPSAltitude")) is not None:
        common_values["altitude"] = (
            -abs(altitude) if _below_sea_level(tags.get("XMP-exif:GPSAltitudeRef")) else abs(altitude)
        )


def gps_from_tags(tags: Mapping[str, Any]) -> dict[str, float | None]:
    """El GPS de un archivo leído EXACTAMENTE como el extractor (lista de campos y regla).

    Para saber si un archivo ya tiene el GPS pedido y comprobar lo escrito
    (core/userdata/xmp_writer.py). Las etiquetas tienen que incluir 'GPS_SOURCE_TAGS'.

    Returns:
        Columna de 'GPS_COLUMNS' -> valor (None si no tiene).
    """
    values = {spec.column: read_field(spec, tags) for spec in _GPS_FIELDS}
    _gps(tags, values)
    return values


def _below_sea_level(ref: Any) -> bool:
    """True si la referencia de la altitud dice «bajo el nivel del mar» (1, con '-n')."""
    text = str(ref).strip().lower()
    return text == "1" or text.startswith("below")
