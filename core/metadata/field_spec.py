"""Descripción declarativa de los campos que se extraen con ExifTool.

Este módulo NO depende de Qt ni de la base de datos. Define cómo se escribe, en una
lista, "este campo de la base de datos sale de estas etiquetas de ExifTool":

    common("city", ("XMP-photoshop:City", "IPTC:City"), text)
    detail("iso", ("ExifIFD:ISO", "XMP-exif:ISO"), integer)

    common(...)  columna de 'media_items' (comunes a todos los tipos de medio).
    detail(...)  columna de la tabla de detalles del tipo ('photo_details'...).

Cada FUENTE es una etiqueta de ExifTool escrita como la devuelve con '-G1':
    "Grupo:Etiqueta"   solo esa etiqueta en ese grupo exacto ("IFD0:Make").
    "Etiqueta"         esa etiqueta en cualquier grupo ("Make").
Las fuentes se prueban por orden: gana la primera que exista Y se pueda convertir.
Ese orden ES la regla de prioridad entre EXIF, IPTC y XMP.

Con 'python -m core.metadata.inspect_cli archivo.jpg' se ve qué etiquetas y grupos
trae cada archivo.

Los CONVERSORES transforman el valor de ExifTool (número, texto o lista) en el valor
de la base de datos, y devuelven None si no sirve (así se pasa a la siguiente fuente).
"""

__version__ = "1.0.0"
__all__ = [
    "FieldSpec",
    "ParsedDate",
    "common",
    "datetime_text",
    "detail",
    "image_height",
    "image_width",
    "integer",
    "lookup",
    "orientation_code",
    "parse_datetime",
    "parse_offset",
    "pick_flag",
    "rating_value",
    "read_field",
    "real",
    "text",
]

# Librerías estándar
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple

Converter = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Un campo que se lee de ExifTool y se guarda en una columna.

    Attributes:
        column: Nombre de la columna en la base de datos.
        sources: Etiquetas de ExifTool por orden de prioridad (ver la cabecera).
        convert: Función que convierte el valor de ExifTool en el de la columna.
        target: "common" (tabla 'media_items') o "details" (tabla de detalles del tipo).
    """

    column: str
    sources: tuple[str, ...]
    convert: Converter
    target: str = "common"


def common(column: str, sources: tuple[str, ...], convert: Converter) -> FieldSpec:
    """Campo que va a una columna de 'media_items'."""
    return FieldSpec(column, sources, convert, "common")


def detail(column: str, sources: tuple[str, ...], convert: Converter) -> FieldSpec:
    """Campo que va a la tabla de detalles del tipo de medio."""
    return FieldSpec(column, sources, convert, "details")


# -----------------------------------------------------------------------------
# Lectura de etiquetas
# -----------------------------------------------------------------------------


def _is_empty(value: Any) -> bool:
    """True para None, texto vacío o colecciones vacías."""
    return value is None or (isinstance(value, (str, list, tuple, dict)) and len(value) == 0)


def lookup(tags: Mapping[str, Any], source: str) -> Any | None:
    """Busca una fuente ("Grupo:Etiqueta" o "Etiqueta") entre las etiquetas de un archivo.

    Devuelve None si no existe o está vacía.
    """
    if ":" in source:
        value = tags.get(source)
        return None if _is_empty(value) else value
    for key, value in tags.items():
        if key.rpartition(":")[2] == source and not _is_empty(value):
            return value
    return None


def read_field(spec: FieldSpec, tags: Mapping[str, Any]) -> Any | None:
    """Obtiene el valor de un campo: la primera fuente que exista y se pueda convertir."""
    for source in spec.sources:
        raw = lookup(tags, source)
        if raw is None:
            continue
        converted = spec.convert(raw)
        if converted is not None:
            return converted
    return None


# -----------------------------------------------------------------------------
# Conversores
# -----------------------------------------------------------------------------


def text(value: Any) -> str | None:
    """Texto limpio. Las listas se unen con ', '. Devuelve None si queda vacío."""
    if isinstance(value, bool) or isinstance(value, dict):
        return None
    if isinstance(value, (list, tuple)):
        parts = [part for part in (text(item) for item in value) if part]
        return ", ".join(parts) or None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, (int, float)):
        # P. ej. un número de serie que ExifTool entrega como número
        return str(value)
    if isinstance(value, str):
        cleaned = value.replace("\x00", "").strip()
        return cleaned or None
    return None


def real(value: Any) -> float | None:
    """Número decimal. Acepta números, texto numérico y fracciones ('1/35'); la lista, su primer valor."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        candidate = value.strip()
        fraction = re.fullmatch(r"(-?\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)", candidate)
        try:
            if fraction:
                number = float(fraction.group(1)) / float(fraction.group(2))
            else:
                number = float(candidate)
        except (ValueError, ZeroDivisionError):
            return None
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    # 'inf' y 'nan' no son datos
    return number if math.isfinite(number) else None


def integer(value: Any) -> int | None:
    """Número entero (redondeado). Mismas entradas que 'real'."""
    number = real(value)
    return None if number is None else int(round(number))


def rating_value(value: Any) -> int | None:
    """Valoración XMP ('xmp:Rating') como entero de 0 a 5; None si no hay o no es válida.

    Un 0 ESCRITO es un dato ("sin estrellas", a propósito) y se devuelve 0; None significa
    que el archivo no dice nada (la etiqueta no está). La diferencia importa al releer:
    un 0 quita las estrellas del catálogo; una etiqueta ausente no toca nada.
    El -1 (rechazo en Bridge) no se interpreta aquí: la marca de rechazo se lee de
    'xmpDM:Pick' (ver 'pick_flag').
    """
    if isinstance(value, bool):
        return None
    number = integer(value)
    return number if number is not None and 0 <= number <= 5 else None


def pick_flag(value: Any) -> int | None:
    """Marca XMP ('xmpDM:Pick'): 1 aceptada, 0 sin marca, -1 rechazada; None si no está."""
    if isinstance(value, bool):
        return None
    number = integer(value)
    return number if number in (-1, 0, 1) else None


def orientation_code(value: Any) -> int | None:
    """Orientación EXIF: un entero de 1 a 8; cualquier otro valor se descarta."""
    number = integer(value)
    return number if number is not None and 1 <= number <= 8 else None


def _image_dimension(value: Any, index: int) -> int | None:
    """Ancho (índice 0) o alto (índice 1) de un valor suelto ('4032') o de una pareja ('4032 2688')."""
    if isinstance(value, str):
        numbers = re.findall(r"\d+", value)
        if len(numbers) == 2:
            number: int | None = int(numbers[index])
        elif len(numbers) == 1:
            number = int(numbers[0])
        else:
            return None
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        number = integer(value[index])
    else:
        number = integer(value)
    return number if number is not None and number > 0 else None


def image_width(value: Any) -> int | None:
    """Ancho en píxeles, de un número suelto o de la pareja 'ancho alto' (Composite:ImageSize)."""
    return _image_dimension(value, 0)


def image_height(value: Any) -> int | None:
    """Alto en píxeles, de un número suelto o de la pareja 'ancho alto' (Composite:ImageSize)."""
    return _image_dimension(value, 1)


# Fecha de ExifTool: "2026:08:27 21:33:57", "2026:08:27 21:33:57.160+02:00",
# "2026-08-27T21:33:57Z" o solo "2026:08:27"
_DATE_PATTERN = re.compile(
    r"^\s*(\d{4})[:\-](\d{2})[:\-](\d{2})"
    r"(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:[.,]\d+)?)?"
    r"\s*(Z|[+-]\d{2}:?\d{2})?\s*$"
)


class ParsedDate(NamedTuple):
    """Una fecha de ExifTool ya interpretada.

    Attributes:
        text: 'YYYY-MM-DD HH:MM:SS' (hora local, sin zona).
        offset: Desfase horario '+02:00' si la fecha lo traía, o None.
        precision: 'second', o 'day' si la fecha no traía hora.
    """

    text: str
    offset: str | None
    precision: str


def parse_offset(value: Any) -> str | None:
    """Desfase horario normalizado a '+02:00' ('+0200', 'Z' = '+00:00'), o None si no vale."""
    candidate = text(value)
    if candidate is None:
        return None
    if candidate == "Z":
        return "+00:00"
    match = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", candidate)
    if match is None or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        return None
    return f"{match.group(1)}{match.group(2)}:{match.group(3)}"


def parse_datetime(value: Any) -> ParsedDate | None:
    """Interpreta una fecha de ExifTool. None si no es una fecha real ('0000:00:00 00:00:00')."""
    candidate = text(value)
    match = _DATE_PATTERN.match(candidate) if candidate else None
    if match is None:
        return None
    year, month, day, hour, minute, second, offset = match.groups()
    try:
        parsed = datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0)
        )
    except ValueError:
        return None
    return ParsedDate(
        parsed.isoformat(sep=" "),
        parse_offset(offset) if offset else None,
        "second" if hour is not None else "day",
    )


def datetime_text(value: Any) -> str | None:
    """Fecha como 'YYYY-MM-DD HH:MM:SS' (sin zona ni milisegundos), o None si no vale."""
    parsed = parse_datetime(value)
    return None if parsed is None else parsed.text


if __name__ == "__main__":
    # Autoprueba de los conversores y de la lectura de fuentes.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.field_spec

    # --- text ---
    assert text("  Madrid \x00") == "Madrid" and text("   ") is None and text(None) is None
    assert text(["Paseo", "", "Playa"]) == "Paseo, Playa" and text([]) is None
    assert text(123456) == "123456" and text(True) is None and text({"a": 1}) is None

    # --- real / integer ---
    assert real(0.2) == 0.2 and real("1/35") == 1 / 35 and real("-0.27") == -0.27
    assert real("inf") is None and real("undef") is None and real("1/0") is None
    assert real([1000, 0]) == 1000.0 and real(True) is None and real(None) is None
    assert integer(1000.0) == 1000 and integer("200") == 200 and integer("x") is None

    # --- orientation_code ---
    assert orientation_code(6) == 6 and orientation_code(0) is None and orientation_code(9) is None

    # --- image_width / image_height ---
    assert image_width("4032 2688") == 4032 and image_height("4032 2688") == 2688
    assert image_width("4032x2688") == 4032 and image_height(2688) == 2688
    assert image_width([6000, 4000]) == 6000 and image_height([6000, 4000]) == 4000
    assert image_width("sin números") is None and image_width(0) is None

    # --- fechas ---
    assert parse_datetime("2026:08:27 21:33:57") == ("2026-08-27 21:33:57", None, "second")
    assert parse_datetime("2026:08:27 21:33:57.160+02:00") == ("2026-08-27 21:33:57", "+02:00", "second")
    assert parse_datetime("2026-08-27T21:33:57.016+0200") == ("2026-08-27 21:33:57", "+02:00", "second")
    assert parse_datetime("2026:08:27 19:33:52Z") == ("2026-08-27 19:33:52", "+00:00", "second")
    assert parse_datetime("2026:08:27") == ("2026-08-27 00:00:00", None, "day")
    assert parse_datetime("0000:00:00 00:00:00") is None and parse_datetime("2026:13:40 10:00:00") is None
    assert parse_datetime("basura") is None and parse_datetime(None) is None
    assert datetime_text("2026:09:03 20:23:56+02:00") == "2026-09-03 20:23:56"
    assert parse_offset("+02:00") == "+02:00" and parse_offset("-0530") == "-05:30"
    assert parse_offset("CEST") is None and parse_offset("+25:00") is None

    # --- lookup: grupo exacto o cualquier grupo; vacío = ausente ---
    tags = {
        "IFD0:Make": "Apple",
        "XMP-photoshop:City": "Madrid",
        "IPTC:City": "Alcobendas",
        "XMP-photoshop:Country": "",
        "ExifIFD:ISO": 1000,
        "XMP-dc:Subject": [],
    }
    assert lookup(tags, "IFD0:Make") == "Apple" and lookup(tags, "ExifIFD:Make") is None
    assert lookup(tags, "Make") == "Apple" and lookup(tags, "City") == "Madrid"
    assert lookup(tags, "XMP-photoshop:Country") is None and lookup(tags, "Subject") is None

    # --- read_field: prioridad, y se salta una fuente que existe pero no se puede convertir ---
    city = common("city", ("XMP-photoshop:City", "IPTC:City"), text)
    assert read_field(city, tags) == "Madrid" and city.target == "common"
    only_iptc = {"IPTC:City": "Alcobendas"}
    assert read_field(city, only_iptc) == "Alcobendas"  # cae a la siguiente fuente
    date_field = common("x", ("ExifIFD:DateTimeOriginal", "ExifIFD:CreateDate"), datetime_text)
    broken_then_ok = {"ExifIFD:DateTimeOriginal": "0000:00:00 00:00:00", "ExifIFD:CreateDate": "2020:01:02 03:04:05"}
    assert read_field(date_field, broken_then_ok) == "2020-01-02 03:04:05"
    iso = detail("iso", ("ExifIFD:ISO",), integer)
    assert read_field(iso, tags) == 1000 and iso.target == "details"
    assert read_field(city, {}) is None

    print("Autoprueba finalizada correctamente.")
