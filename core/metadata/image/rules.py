"""Reglas especiales de las imágenes: lo que no es un simple "etiqueta -> columna".

Se ejecutan DESPUÉS de rellenar la lista de campos ('fields.py'), con los valores ya
leídos, y los ajustan en el sitio. Son cinco:

    1. Orientación y tamaño: las imágenes giradas (orientación EXIF 5 a 8) intercambian
       ancho y alto. Se guarda el tamaño "de pantalla", que es la proporción real de
       la miniatura.
    1b. Recorte de Lightroom ("Dimensiones actuales"): se calcula con los ajustes de
       revelado del XMP ('crs:Crop*') y el tamaño, antes de girarlo.
    2. Fecha de captura: depende de varias etiquetas a la vez (fecha, zona horaria,
       de dónde salió y con qué precisión) y tiene respaldo en la fecha del archivo.
    3. Flash: 'flash_fired' (0 o 1) se deriva del código de flash.
    4. GPS: se descartan las coordenadas imposibles.

Si cambias algo aquí, sube 'IMAGE_FIELDS_VERSION' (en 'fields.py').

Pendiente de comprobar con archivos reales: el tamaño de los HEIC (si ExifTool ya
devuelve la imagen girada o no) y el de los RAW (varias imágenes dentro del archivo).
Con 'python -m core.metadata.inspect_cli archivo.heic --campos' se ve qué guarda
la aplicación y se compara con Lightroom.
"""

__version__ = "1.1.0"
__all__ = ["apply_image_rules", "crop_size"]

# Librerías estándar
import math
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

# Módulos del proyecto
from core.metadata.field_spec import (
    common,
    lookup,
    orientation_code,
    parse_datetime,
    parse_offset,
    read_field,
)

# Orígenes de la fecha de captura, por orden de fiabilidad:
# (etiqueta, nombre del origen, etiqueta con la zona horaria si la fecha no la trae)
_CAPTURE_DATE_SOURCES: tuple[tuple[str, str, str | None], ...] = (
    ("ExifIFD:DateTimeOriginal", "exif", "ExifIFD:OffsetTimeOriginal"),
    ("ExifIFD:CreateDate", "exif", "ExifIFD:OffsetTimeDigitized"),
    ("XMP-photoshop:DateCreated", "xmp", None),
    ("Composite:DateTimeCreated", "iptc", None),
    ("IFD0:ModifyDate", "exif", "ExifIFD:OffsetTime"),  # la menos fiable: la última edición
)

_ORIENTATION = common("orientation", ("IFD0:Orientation", "XMP-tiff:Orientation"), orientation_code)


def apply_image_rules(
    tags: Mapping[str, Any], common_values: dict[str, Any], details: dict[str, Any], path: Path
) -> None:
    """Aplica las reglas especiales de imagen. Ver la cabecera del módulo."""
    _orientation_and_size(tags, common_values, details)
    _capture_date(tags, common_values, path)
    _flash(details)
    _gps(common_values)


def _orientation_and_size(
    tags: Mapping[str, Any], common_values: dict[str, Any], details: dict[str, Any]
) -> None:
    """Orientación (1 si no consta), tamaño y recorte ya girados."""
    orientation = read_field(_ORIENTATION, tags) or 1
    common_values["orientation"] = orientation
    width, height = common_values.get("width"), common_values.get("height")
    # El recorte se calcula sobre el tamaño SIN girar (así lo guarda Lightroom)
    crop = crop_size(tags, width, height)
    if orientation >= 5 and width and height:
        common_values["width"], common_values["height"] = height, width
        if crop is not None:
            crop = (crop[1], crop[0])
    details["crop_width"], details["crop_height"] = crop if crop is not None else (None, None)


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


def _gps(common_values: dict[str, Any]) -> None:
    """Descarta coordenadas fuera de rango o '0, 0' (el valor que ponen algunas cámaras sin fix)."""
    latitude, longitude = common_values.get("latitude"), common_values.get("longitude")
    invalid = (
        latitude is None
        or longitude is None
        or abs(latitude) > 90
        or abs(longitude) > 180
        or (latitude == 0 and longitude == 0)
    )
    if invalid:
        common_values["latitude"] = None
        common_values["longitude"] = None
