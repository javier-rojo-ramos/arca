"""Las cajas de la sección «Audio» del inspector: qué muestran y qué guarda lo escrito.

Este módulo NO depende de Qt ni de la base de datos: la sección («audio_section.py») le pide
el texto de cada caja a partir de los datos de las canciones ('core/catalog/audio_stats') y
le pasa lo que escribe el usuario, que vuelve como las columnas del catálogo que hay que
cambiar ('media_queries.update_metadata_fields'). Si no vale, 'ValueError' con el aviso que
se ve junto a la caja ('INVALID_TEXTS').

    editor_text("track", stats.value("track"))     -> ("03/12", False)
    parse_audio_value("track", "3/12")             -> {"track_number": 3, "track_total": 12}
    parse_audio_value("genre", "Rock;Pop")         -> {"genre": "Rock; Pop"}

Las reglas (acordadas con el autor el 28/11/2026, docs/MOD_MUSICA.md, plan de MUS 7.1):
    - Cada caja, sus columnas ('FIELD_COLUMNS'): el artista es 'creator', el comentario es
      'description' y el año, 'content_created_at'; la pista y el disco, el número y el total.
    - El AÑO, como un año: la caja enseña sus cuatro cifras («2001») y admite cuatro cifras
      (de 1000 a 9999); vacía, sin año.
    - La PISTA y el DISCO, en una caja con su total, como se escriben en los archivos y los
      enseña Mp3tag («03/12»; el autor, al probarlo: no «03 / 12»), el número con dos
      cifras al menos ('tag_map.pair_number_text'). Se admite «3»,
      «03», «3/12» o «3 / 12»; vacía, sin número ni total; el total sin número no vale
      (ID3 no lo admite: «3/12» o «3»), ni el 0, ni más de 65 535 (lo que cabe en un M4A).
    - VARIOS VALORES (el artista, el artista del álbum, el compositor y el género), con el
      separador de siempre: «Rock;Pop» -> «Rock; Pop» ('tag_map.normalize_values'), así el
      catálogo guarda lo mismo que acaba en el archivo.
    - Los demás textos, tal cual: los limpia 'update_metadata_fields' (espacios a los lados,
      vacío = sin valor; el comentario admite saltos de línea).
    - Con valores distintos en la selección, la caja enseña «Varios» (lo pone la caja).

1.1.0 La pista y el disco, «03/12», sin espacios (pedido por el autor al probar MUS 7.1c).
1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 7.1c).

Prueba rápida (sin Qt):
    python -m ui_helpers.inspector.audio_values
"""

__version__ = "1.1.0"
__all__ = [
    "FIELD_COLUMNS",
    "INVALID_TEXTS",
    "LIST_KEYS",
    "editor_text",
    "parse_audio_value",
]

# Librerías estándar
import re

# Módulos del proyecto
from core.audio.tag_map import normalize_values, pair_number_text
from core.catalog.selection_metadata import MIXED, VALUE, FieldValue

# Las columnas del catálogo de cada caja (las claves son las de 'audio_stats')
FIELD_COLUMNS: dict[str, tuple[str, ...]] = {
    "title": ("title",),
    "artist": ("creator",),
    "album": ("album",),
    "year": ("content_created_at",),
    "track": ("track_number", "track_total"),
    "disc": ("disc_number", "disc_total"),
    "genre": ("genre",),
    "album_artist": ("album_artist",),
    "composer": ("composer",),
    "comment": ("description",),
}

# Las cajas con varios valores («Rock; Pop»)
LIST_KEYS: frozenset[str] = frozenset({"artist", "album_artist", "composer", "genre"})

# Aviso junto a la caja cuando lo escrito no vale (textos decididos por el autor el
# 28/11/2026)
INVALID_TEXTS: dict[str, str] = {
    "year": "No es un año válido. Escribe, por ejemplo, 1999.",
    "track": "No es una pista válida. Escribe, por ejemplo, 3 o 3/12.",
    "disc": "No es un disco válido. Escribe, por ejemplo, 1 o 1/2.",
}

# El año: cuatro cifras; la pista y el disco: el número y, si se quiere, el total
_YEAR = re.compile(r"\d{4}")
_FIRST_YEAR = 1000
_PAIR = re.compile(r"(\d+)\s*(?:/\s*(\d+))?")
# Lo más alto que cabe en una pista o un disco (en un M4A son números de 16 bits)
_MAX_PAIR_NUMBER = 65535
# Separador entre el número y el total en la caja: como en el archivo y en Mp3tag
_PAIR_SEPARATOR = "/"


def editor_text(key: str, value: FieldValue) -> tuple[str, bool]:
    """Lo que enseña la caja de un campo: (texto, hay valores distintos en la selección).

    Args:
        key: La caja ('FIELD_COLUMNS').
        value: Su valor en 'audio_stats' (con VALUE, la tupla de sus columnas: el año, con
            su fecha y su precisión; la pista y el disco, con el número y el total).
    """
    if value.state == MIXED:
        return "", True
    if value.state != VALUE or not value.value or value.value[0] is None:
        return "", False
    if key == "year":
        return str(value.value[0])[:4], False
    if key in ("track", "disc"):
        number, total = (*value.value, None)[:2]
        text = pair_number_text(int(number))
        return (f"{text}{_PAIR_SEPARATOR}{total}" if total else text), False
    return str(value.value[0]), False


def parse_audio_value(key: str, text: str | None) -> dict[str, object]:
    """Lo escrito en una caja, como las columnas del catálogo que cambian (None = vaciar).

    Raises:
        ValueError: Si no vale (el año, la pista o el disco), con el aviso de la caja
            ('INVALID_TEXTS'). También si la caja no es de la sección.
    """
    columns = FIELD_COLUMNS.get(key)
    if columns is None:
        raise ValueError(f"Caja desconocida: {key!r}")
    text = (text or "").strip()
    if key == "year":
        return {columns[0]: _parse_year(text)}
    if key in ("track", "disc"):
        number, total = _parse_pair(key, text)
        return {columns[0]: number, columns[1]: total}
    if key in LIST_KEYS:
        return {columns[0]: normalize_values(text)}
    return {columns[0]: text or None}


def _parse_year(text: str) -> int | None:
    """Un año de cuatro cifras («1999»); vacío, None.

    Raises:
        ValueError: Si no lo es.
    """
    if not text:
        return None
    if not _YEAR.fullmatch(text) or int(text) < _FIRST_YEAR:
        raise ValueError(INVALID_TEXTS["year"])
    return int(text)


def _parse_pair(key: str, text: str) -> tuple[int | None, int | None]:
    """La pista o el disco: «3», «03», «3/12» o «3 / 12»; vacío, (None, None).

    Raises:
        ValueError: Si no vale (el total sin número, un 0, letras, demasiado grande).
    """
    if not text:
        return None, None
    match = _PAIR.fullmatch(text)
    if not match:
        raise ValueError(INVALID_TEXTS[key])
    number = int(match[1])
    total = int(match[2]) if match[2] is not None else None
    for item in (number, total):
        if item is not None and not 0 < item <= _MAX_PAIR_NUMBER:
            raise ValueError(INVALID_TEXTS[key])
    return number, total


if __name__ == "__main__":
    # Autoprueba (sin Qt ni base de datos). Desde la raíz del proyecto:
    #     python -m ui_helpers.inspector.audio_values
    from core.catalog.audio_stats import FIELD_KEYS
    from core.catalog.selection_metadata import EMPTY
    from core.userdata.editable_fields import field_for

    # --- Las cajas son las de los campos de la canción, y sus columnas, editables
    assert set(FIELD_COLUMNS) <= set(FIELD_KEYS), set(FIELD_COLUMNS) - set(FIELD_KEYS)
    for columns in FIELD_COLUMNS.values():
        for column in columns:
            field_for(column)  # si no es editable, ValueError

    # --- Lo que enseña cada caja
    def shown(key: str, *columns: object) -> str:
        return editor_text(key, FieldValue(VALUE, tuple(columns)))[0]

    assert shown("title", "Vino Tinto") == "Vino Tinto"
    assert shown("year", "2001-01-01 00:00:00", "year") == "2001"
    assert shown("year", "2001-05-04 00:00:00", "day") == "2001"  # solo el año
    assert shown("track", 3, 12) == "03/12" and shown("track", 3, None) == "03"
    assert shown("disc", 1, 2) == "01/2" and shown("track", 100, None) == "100"
    assert shown("track", None, 12) == ""  # el total sin número no se enseña (no se escribe)
    assert shown("comment", "Una\nDos") == "Una\nDos"
    assert editor_text("genre", FieldValue(MIXED)) == ("", True)
    assert editor_text("album", FieldValue(EMPTY)) == ("", False)
    print("Lo que enseñan las cajas: correcto")

    # --- Lo escrito, como columnas del catálogo
    assert parse_audio_value("title", "  Vino Tinto ") == {"title": "Vino Tinto"}
    assert parse_audio_value("title", "") == {"title": None}
    assert parse_audio_value("comment", "Una\nDos") == {"description": "Una\nDos"}
    assert parse_audio_value("artist", "Estopa;Rosendo;") == {"creator": "Estopa; Rosendo"}
    assert parse_audio_value("genre", " ; ") == {"genre": None}
    assert parse_audio_value("title", "A;B") == {"title": "A;B"}  # un título no se separa
    assert parse_audio_value("year", " 1999 ") == {"content_created_at": 1999}
    assert parse_audio_value("year", "") == {"content_created_at": None}
    for written, expected in (
        ("3", (3, None)), ("03", (3, None)), ("3/12", (3, 12)), (" 03 / 12 ", (3, 12)),
        ("", (None, None)), ("65535", (65535, None)),
    ):  # fmt: skip
        assert parse_audio_value("track", written) == {
            "track_number": expected[0], "track_total": expected[1]
        }, written  # fmt: skip
    assert parse_audio_value("disc", "1/2") == {"disc_number": 1, "disc_total": 2}
    for key, bad in (
        ("year", "99"), ("year", "0999"), ("year", "2001-05"), ("year", "dos mil"),
        ("track", "/12"), ("track", "0"), ("track", "3/0"), ("track", "tres"),
        ("track", "3-12"), ("track", "65536"), ("disc", "1/2/3"),
    ):  # fmt: skip
        try:
            parse_audio_value(key, bad)
            raise AssertionError(f"debía rechazar {bad!r} en {key}")
        except ValueError as error:
            assert str(error) == INVALID_TEXTS[key], (key, bad, error)
    print("Lo escrito: interpretado; lo que no vale, con su aviso")

    print("Autoprueba finalizada correctamente.")
