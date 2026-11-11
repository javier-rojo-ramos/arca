"""Lo que el usuario escribe en las cajas numéricas del inspector: GPS, altitud y dirección.

Funciones puras (sin Qt). Aceptan lo que muestra la propia fila ('formatting.py': así una
caja que se deja como está, o en la que solo se toca una parte, se entiende) y las formas
habituales de escribirlo (decididas por el autor el 11/11/2026, docs/DECISIONES.md):

    GPS        42°40'55,5204" N 0°4'11,9676" E   grados, minutos y segundos, como se ve
               41°23'14.64" N 2°10'6.96" E       (coma o punto; N/S y E/O/W, delante o
               42°40.925' N 0°4.199' O           detrás; minutos con decimales)
               42.682089° N 0.069991° E
               42.682089, 0.069991               decimales con punto (como Google Maps)
               42,682089 0,069991                decimales con coma, separados por un
               42,682089; 0,069991               espacio o «;»
               -33.4569, -70.6483                sur y oeste, con signo
    Altitud    1418,5 · 1418.5 · 1.418,5 m · −12,5 m · 100 m
    Dirección  Oeste · O · W · SO · noreste · 270 · 270° · 270,5°

Vacío = vaciar el campo (None). Lo que no se entiende o se sale de rango (latitud de más
de 90°, longitud de más de 180°, minutos o segundos de 60 o más, dirección fuera de 0 a
360, o las coordenadas 0, 0, que la lectura toma por «sin GPS») lanza 'ValueError' con
el aviso que ve el usuario junto a la caja ('INVALID_TEXTS', textos del autor).

Uso (lo hace 'metadata_section.py'):
    values = parse_numeric("gps", texto)   # {'latitude': 42.68..., 'longitude': 0.06...}

1.0.0 Primera versión: GPS, altitud y dirección (paso 5 de la edición del GPS).

Prueba rápida (sin Qt):
    python -m ui_helpers.inspector.value_parsing
"""

__version__ = "1.0.0"
__all__ = [
    "INVALID_TEXTS",
    "NUMERIC_COLUMNS",
    "parse_altitude",
    "parse_direction",
    "parse_gps",
    "parse_numeric",
]

# Librerías estándar
import math
import re
import unicodedata
from collections.abc import Callable

# Módulos del proyecto
from ui_helpers.inspector.formatting import format_direction

# Campos numéricos del inspector y las columnas que cambia cada uno (la caja «GPS», dos)
NUMERIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "gps": ("latitude", "longitude"),
    "altitude": ("altitude",),
    "direction": ("gps_direction",),
}

# Aviso junto a la caja cuando lo escrito no vale (textos decididos por el autor el
# 11/11/2026)
INVALID_TEXTS: dict[str, str] = {
    "gps": (
        "No es una ubicación válida. Escribe, por ejemplo,\n"
        "42.682089, 0.069991 o 42°40'55\" N 0°4'12\" E"
    ),
    "altitude": (
        "No es una altitud válida. Escribe los metros,\n"
        "por ejemplo 1418,5 (bajo el nivel del mar, con «−»)"
    ),
    "direction": (
        "No es una dirección válida. Escribe los grados\n"
        "(de 0 a 360, por ejemplo 270) o un rumbo\n"
        "(Norte, Noreste, Este...)"
    ),
}

# Un número con coma o punto decimal (sin separador de miles)
_NUMBER = r"\d+(?:[.,]\d+)?"

# Dos números decimales, separados por una coma, un «;» o espacios: '42.68, 0.07',
# '42,68 0,07', '42,68; 0,07'
_DECIMAL_PAIR = re.compile(
    rf"^\s*([-+]?{_NUMBER})\s*(?:[,;]\s*|\s+)([-+]?{_NUMBER})\s*$"
)

# Una coordenada en grados (y, si acaso, minutos y segundos), con su hemisferio delante
# ('N 42°40'') o detrás ('42°40' N'). Son dos expresiones: con las dos posiciones a la vez,
# en 'N 42° E 3°' la «E» de la segunda se tomaría como hemisferio de la primera. El texto
# llega ya normalizado ('_normalize': mayúsculas, ° ' ")
_DEGREES_MINUTES_SECONDS = rf"""
    (?P<sign>[-+])?\s*
    (?P<degrees>{_NUMBER})\s*°?\s*
    (?:(?P<minutes>{_NUMBER})\s*'\s*)?
    (?:(?P<seconds>{_NUMBER})\s*"\s*)?
"""
_COORDINATE_BEFORE = re.compile(
    rf"(?P<hemisphere>[NSEOW])\s*{_DEGREES_MINUTES_SECONDS}", re.VERBOSE
)
_COORDINATE_AFTER = re.compile(
    rf"{_DEGREES_MINUTES_SECONDS}(?P<hemisphere>[NSEOW](?![A-Z]))?", re.VERBOSE
)

# Hemisferio: a qué coordenada pertenece y con qué signo
_HEMISPHERES: dict[str, tuple[str, int]] = {
    "N": ("latitude", 1), "S": ("latitude", -1),
    "E": ("longitude", 1), "O": ("longitude", -1), "W": ("longitude", -1),
}  # fmt: skip

# Rumbos: los ocho que muestra la fila (de 'format_direction', así coinciden siempre), sus
# abreviaturas (en español y en inglés) y las variantes «nordeste», «sudeste», «sudoeste»
_DIRECTION_ABBREVIATIONS = ("n", "ne", "e", "se", "s", "so", "o", "no")
_ENGLISH_ABBREVIATIONS = {"sw": 225.0, "w": 270.0, "nw": 315.0}
_VARIANTS = {"nordeste": 45.0, "sudeste": 135.0, "sudoeste": 225.0}


def _fold(text: str) -> str:
    """Minúsculas y sin acentos, para comparar nombres ('Noreste' = 'noreste')."""
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _bearings() -> dict[str, float]:
    """Nombre o abreviatura de un rumbo (ya con '_fold') -> grados."""
    bearings: dict[str, float] = {}
    for index, abbreviation in enumerate(_DIRECTION_ABBREVIATIONS):
        degrees = index * 45.0
        bearings[_fold(format_direction(degrees))] = degrees
        bearings[abbreviation] = degrees
    bearings.update(_ENGLISH_ABBREVIATIONS)
    bearings.update(_VARIANTS)
    return bearings


_BEARINGS = _bearings()


def _normalize(text: str) -> str:
    """Unifica los símbolos que se teclean o se pegan: «º», «′», «″», «’», «−»..."""
    replacements = {
        "º": "°", "˚": "°", "′": "'", "’": "'", "´": "'", "″": '"', "“": '"', "”": '"',
        "−": "-", "–": "-", " ": " ", " ": " ",
    }  # fmt: skip
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.replace("''", '"').upper()


def _plain_number(text: str) -> float:
    """Número con coma o punto decimal (sin miles): '0,069991', '55.52'."""
    return float(text.replace(",", "."))


def parse_gps(text: str) -> tuple[float, float] | None:
    """Coordenadas escritas por el usuario: (latitud, longitud) con signo, o None si vacío.

    Raises:
        ValueError: Si no se entiende o no es una ubicación posible (ver la cabecera).
    """
    normalized = _normalize(text).strip()
    if not normalized:
        return None
    if re.search(r"[°'\"NSEOW]", normalized):
        latitude, longitude = _parse_coordinates(normalized)
    else:
        match = _DECIMAL_PAIR.match(normalized)
        if match is None:
            raise ValueError(INVALID_TEXTS["gps"])
        latitude, longitude = _plain_number(match[1]), _plain_number(match[2])
    if abs(latitude) > 90 or abs(longitude) > 180 or (latitude == 0 and longitude == 0):
        raise ValueError(INVALID_TEXTS["gps"])
    # Ocho decimales (un milímetro): lo que se relee de la fila no arrastra restos de la
    # conversión desde grados, minutos y segundos
    return round(latitude, 8), round(longitude, 8)


def _parse_coordinates(text: str) -> tuple[float, float]:
    """Dos coordenadas en grados (minutos y segundos), con o sin hemisferio."""
    found: list[tuple[str | None, float]] = []
    position = 0
    pattern = _COORDINATE_BEFORE if text[0] in _HEMISPHERES else _COORDINATE_AFTER
    for match in pattern.finditer(text):
        if not match.group("degrees"):
            continue
        # Entre una coordenada y la siguiente solo puede haber separadores
        if text[position : match.start()].strip(" ,;"):
            raise ValueError(INVALID_TEXTS["gps"])
        position = match.end()
        found.append(_coordinate_value(match))
    if len(found) != 2 or text[position:].strip(" ,;"):
        raise ValueError(INVALID_TEXTS["gps"])

    (first_axis, first), (second_axis, second) = found
    # Sin hemisferio, el orden manda (latitud y longitud); con él, el hemisferio
    if first_axis is None:
        first_axis = "longitude" if second_axis == "latitude" else "latitude"
    if second_axis is None:
        second_axis = "latitude" if first_axis == "longitude" else "longitude"
    if first_axis == second_axis:
        raise ValueError(INVALID_TEXTS["gps"])
    return (first, second) if first_axis == "latitude" else (second, first)


def _coordinate_value(match: re.Match[str]) -> tuple[str | None, float]:
    """(coordenada a la que pertenece por su hemisferio o None, valor con signo)."""
    hemisphere, sign = match.group("hemisphere"), match.group("sign")
    if hemisphere and sign:
        raise ValueError(INVALID_TEXTS["gps"])  # «-42° N»: o el signo o el hemisferio
    degrees = _plain_number(match.group("degrees"))
    minutes = _plain_number(match.group("minutes")) if match.group("minutes") else 0.0
    seconds = _plain_number(match.group("seconds")) if match.group("seconds") else 0.0
    # Solo la última parte puede llevar decimales, y minutos y segundos no llegan a 60
    if (match.group("minutes") and not degrees.is_integer()) or (
        match.group("seconds") and not minutes.is_integer()
    ):
        raise ValueError(INVALID_TEXTS["gps"])
    if minutes >= 60 or seconds >= 60:
        raise ValueError(INVALID_TEXTS["gps"])
    value = degrees + minutes / 60 + seconds / 3600
    if sign == "-":
        value = -value
    if hemisphere is None:
        return None, value
    axis, factor = _HEMISPHERES[hemisphere]
    return axis, value * factor


def parse_altitude(text: str) -> float | None:
    """Altitud escrita por el usuario, en metros (negativa bajo el nivel del mar).

    Admite la unidad ('m'), el signo menos tipográfico ('−') y el punto de miles como se
    muestra ('1.418,1 m'). Con un solo separador: la coma es decimal; el punto también,
    salvo que separe grupos de tres cifras ('1.418' = 1418, como se escribe en español).

    Raises:
        ValueError: Si no es un número.
    """
    normalized = _normalize(text).strip()
    if normalized.endswith("M"):
        normalized = normalized[:-1].strip()
    if not normalized:
        return None
    match = re.fullmatch(r"([-+]?)\s*([\d.,]+)", normalized.replace(" ", ""))
    if match is None:
        raise ValueError(INVALID_TEXTS["altitude"])
    sign, digits = match.groups()
    try:
        number = _number_with_thousands(digits)
    except ValueError:
        raise ValueError(INVALID_TEXTS["altitude"]) from None
    if not math.isfinite(number):
        raise ValueError(INVALID_TEXTS["altitude"])
    return -number if sign == "-" else number


def _number_with_thousands(digits: str) -> float:
    """'1.418,1' -> 1418.1; '1418.5' -> 1418.5; '1.418' -> 1418; '0.250' -> 0.25."""
    if "," in digits and "." in digits:
        # Los dos: el de más a la derecha es el decimal
        decimal = "," if digits.rfind(",") > digits.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        digits = digits.replace(thousands, "").replace(decimal, ".")
    elif "," in digits:
        if digits.count(",") > 1:
            raise ValueError(digits)
        digits = digits.replace(",", ".")
    elif re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+", digits):
        digits = digits.replace(".", "")  # punto de miles: '1.418', '12.500'
    elif digits.count(".") > 1:
        raise ValueError(digits)
    if not re.fullmatch(r"\d+(\.\d+)?", digits):
        raise ValueError(digits)
    return float(digits)


def parse_direction(text: str) -> float | None:
    """Dirección escrita por el usuario, en grados (0 a 360): un número o un rumbo.

    Raises:
        ValueError: Si no se entiende o se sale de 0 a 360.
    """
    folded = _fold(_normalize(text))
    if not folded:
        return None
    if folded in _BEARINGS:
        return _BEARINGS[folded]
    number = folded.removesuffix("°").strip()
    if not re.fullmatch(_NUMBER, number):
        raise ValueError(INVALID_TEXTS["direction"])
    degrees = _plain_number(number)
    if degrees > 360:
        raise ValueError(INVALID_TEXTS["direction"])
    return degrees


def _gps_values(text: str) -> dict[str, float | None]:
    coordinates = parse_gps(text)
    if coordinates is None:
        return {"latitude": None, "longitude": None}
    return {"latitude": coordinates[0], "longitude": coordinates[1]}


_PARSERS: dict[str, Callable[[str], dict[str, float | None]]] = {
    "gps": _gps_values,
    "altitude": lambda text: {"altitude": parse_altitude(text)},
    "direction": lambda text: {"gps_direction": parse_direction(text)},
}
assert set(_PARSERS) == set(NUMERIC_COLUMNS)


def parse_numeric(key: str, text: str) -> dict[str, float | None]:
    """Lo escrito en la caja de un campo numérico, como columnas y valores.

    Args:
        key: Campo del inspector ('gps', 'altitude' o 'direction': 'NUMERIC_COLUMNS').
        text: Lo escrito ("" = vaciar).

    Returns:
        Columna -> valor (None = vaciar), las de 'NUMERIC_COLUMNS[key]'.

    Raises:
        KeyError: Si el campo no es numérico.
        ValueError: Si lo escrito no vale; el mensaje es el aviso para el usuario.
    """
    return _PARSERS[key](text)


if __name__ == "__main__":
    # Autoprueba sin Qt: todas las formas de escribir y lo que no vale.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.inspector.value_parsing
    from ui_helpers.inspector.formatting import format_altitude, format_gps

    def near(got: tuple[float, float] | None, expected: tuple[float, float]) -> bool:
        pairs = zip(got or (), expected, strict=False)
        return got is not None and all(abs(a - b) < 1e-7 for a, b in pairs)

    # 1. GPS: lo que muestra la fila, Lightroom, decimales y hemisferios
    ordesa = (42.682089, 0.069991)
    for text in (
        format_gps(*ordesa),                          # 42°40'55,5204" N 0°4'11,9676" E
        "42°40'55.5204\" N 0°4'11.9676\" E",          # con punto, como Lightroom
        "42.682089, 0.069991",                         # Google Maps
        "42.682089,0.069991", "42.682089 0.069991", "42,682089 0,069991",
        "42,682089; 0,069991", "42,682089, 0,069991",
        "42.682089° N 0.069991° E", "N 42°40'55,5204\" E 0°4'11,9676\"",
        "0°4'11,9676\" E 42°40'55,5204\" N",          # al revés, con hemisferios
        "42º40'55,5204'' N, 0º4'11,9676'' E",         # «º» y '' del teclado español
        "42°40.92534' N 0°4.19946' E",                 # grados y minutos con decimales
        "  42.682089 ,  0.069991  ",
    ):
        assert near(parse_gps(text), ordesa), (text, parse_gps(text))
    south = (-33.4569, -70.6483)
    for text in ("-33.4569, -70.6483", format_gps(*south), "33°27'24.84\" S 70°38'53.88\" W",
                 "S 33.4569 W 70.6483", "−33,4569 −70,6483"):  # fmt: skip
        assert near(parse_gps(text), south), (text, parse_gps(text))
    assert parse_gps("41,2") == (41.0, 2.0)  # dos enteros separados por una coma
    for empty in ("", "   "):
        assert parse_gps(empty) is None
    for bad in ("abc", "42.68", "95, 10", "42, 190", "0, 0", "0°0'0\" N 0°0'0\" E",
                "42°60' N 0° E", "42°40'60\" N 0° E", "42.5°30' N 0° E", "42° N 43° S",
                "42° E 3° O", "-42° N 3° E", "N 42° N 3° E", "42.68, 0.07, 1",
                "42.68 x 0.07"):  # fmt: skip
        try:
            parse_gps(bad)
            raise AssertionError(f"debía rechazar {bad!r}")
        except ValueError as error:
            assert str(error) == INVALID_TEXTS["gps"]
    print("1. GPS: como se muestra, como Lightroom, decimales, hemisferios y lo que no vale")

    # 2. Altitud: como se muestra, con y sin unidad, signos y separadores
    for text, expected in (
        (format_altitude(1418.1), 1418.1), (format_altitude(-12.5), -12.5),
        ("1418,5", 1418.5), ("1418.5", 1418.5), ("1.418,5 m", 1418.5), ("1.418", 1418.0),
        ("12.500", 12500.0), ("0.250", 0.25), ("12.5", 12.5), ("100 m", 100.0), ("100m", 100.0),
        ("-430", -430.0), ("−430 m", -430.0), ("+8.848", 8848.0), ("1 418,1", 1418.1),
        ("1,418.5", 1418.5), ("0", 0.0),
    ):  # fmt: skip
        assert parse_altitude(text) == expected, (text, parse_altitude(text))
    assert parse_altitude("") is None and parse_altitude(" m ") is None
    for bad in ("abc", "12,5,3", "1.2.3", "12 km", "--3", "1e5"):
        try:
            parse_altitude(bad)
            raise AssertionError(f"debía rechazar {bad!r}")
        except ValueError as error:
            assert str(error) == INVALID_TEXTS["altitude"]
    print("2. Altitud: metros, signo, unidad y separadores")

    # 3. Dirección: los rumbos que muestra la fila, abreviaturas y grados
    for degrees in range(0, 360, 45):
        assert parse_direction(format_direction(float(degrees))) == degrees
    for text, expected in (("oeste", 270.0), ("O", 270.0), ("W", 270.0), ("SO", 225.0),
                           ("sw", 225.0), ("Nordeste", 45.0), ("Sudeste", 135.0),
                           ("270", 270.0), ("270°", 270.0), ("270,5°", 270.5), ("292.47", 292.47),
                           ("360", 360.0), ("0º", 0.0)):  # fmt: skip
        assert parse_direction(text) == expected, (text, parse_direction(text))
    assert parse_direction("") is None
    for bad in ("Nortee", "361", "-90", "abc", "90 grados"):
        try:
            parse_direction(bad)
            raise AssertionError(f"debía rechazar {bad!r}")
        except ValueError as error:
            assert str(error) == INVALID_TEXTS["direction"]
    print("3. Dirección: rumbos, abreviaturas y grados de 0 a 360")

    # 4. Por campo del inspector: las columnas de cada caja
    assert parse_numeric("gps", "42.5, -3") == {"latitude": 42.5, "longitude": -3.0}
    assert parse_numeric("gps", "") == {"latitude": None, "longitude": None}
    assert parse_numeric("altitude", "-12,5 m") == {"altitude": -12.5}
    assert parse_numeric("direction", "Sur") == {"gps_direction": 180.0}
    for key, sample in (("gps", "1, 2"), ("altitude", "1"), ("direction", "1")):
        assert tuple(parse_numeric(key, sample)) == NUMERIC_COLUMNS[key]
    print("4. Cada caja, con sus columnas")

    print("Autoprueba finalizada correctamente.")
