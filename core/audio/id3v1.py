"""La etiqueta ID3v1 de un MP3: leerla y componerla con sus límites, cambiando solo lo editado.

Este módulo NO depende de Qt, de la base de datos ni de los archivos: trabaja con los 128
bytes de la etiqueta. Lo usa el escritor de MP3 ('tag_writer.py', MUS 6.1c), que es quien
los lee del final del archivo y los escribe.

    tag = parse_id3v1(ultimos_128_bytes)              # None si el archivo no tiene ID3v1
    tag = apply_changes(tag, {"title": "Vino Tinto", "track": (3, 12)})
    datos = build_id3v1(tag)                           # los 128 bytes nuevos

Cómo es (el ID3v1.1, el que se escribe):

    bytes   campo
    0-2     «TAG»
    3-32    título          30 caracteres
    33-62   artista         30
    63-92   álbum           30
    93-96   año             4
    97-124  comentario      28 (30 si no hay pista: ID3v1.0)
    125     0               (marca de ID3v1.1: hay pista)
    126     pista           1 a 255
    127     género          el número de su lista (255 = sin género)

Los textos son Latin-1, rellenos con ceros. Disco, artista del álbum y compositor no existen.

CÓMO SE ADAPTA LO EDITADO (decidido con el autor el 27/11/2026; docs/MOD_MUSICA.md §5):
    - Los textos, a Latin-1 (caben los acentos, la ñ, «» y ¿¡): los caracteres que tienen un
      equivalente claro se cambian (’ → ', — → -, … → ..., ř → r: la letra sin su acento si
      Latin-1 no lo tiene) y el resto pasa a «?». Los saltos de línea y tabuladores, a un
      espacio. Después se recortan a su tamaño (sin espacios a los lados).
    - El año: las cuatro cifras del principio de la fecha («2001-05-04» -> «2001»); si no
      empieza por un año, vacío.
    - La pista: el número, de 1 a 255 (el total no cabe); si no, sin pista.
    - El género: su número en la lista de ID3v1 (la de Winamp, 192, la misma de mutagen que
      usa el lector), sin distinguir mayúsculas; con varios («Rock; Pop»), el primero. Si no
      está en la lista («Pop Folk», «BSO»), sin género.
SOLO CAMBIA LO EDITADO: lo demás se queda como estaba en el archivo, byte a byte en el
contenido (también un texto en otra codificación o un género fuera de la lista). La única
excepción la pone el formato: si se añade una pista a un ID3v1.0 con un comentario de más de
28 caracteres, el comentario se recorta (los dos últimos bytes pasan a ser la pista).

Un 'Id3v1Tag' siempre cabe en los 128 bytes (si no, 'ValueError' al crearlo): así
'parse_id3v1(build_id3v1(tag)) == tag', y el escritor comprueba lo escrito contra el valor
ya adaptado, no contra el editado.

No se lee ni se toca la etiqueta ampliada «TAG+» (227 bytes antes del ID3v1; muy rara).

1.0.0 Primera versión (27/11/2026; docs/MOD_MUSICA.md, paso MUS 6.1b).

Prueba rápida (desde la raíz del proyecto):
    python -m core.audio.id3v1
"""

__version__ = "1.0.0"
__all__ = [
    "ID3V1_FIELDS",
    "ID3V1_SIZE",
    "NOT_IN_ID3V1",
    "NO_GENRE",
    "Id3v1Tag",
    "apply_changes",
    "build_id3v1",
    "fit_text",
    "genre_index",
    "parse_id3v1",
]

# Librerías estándar
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

# Librerías de terceros
from mutagen._constants import GENRES

# Módulos del proyecto
from core.audio.tag_map import MULTI_VALUE_SEPARATOR

# Tamaño de la etiqueta y su marca
ID3V1_SIZE = 128
_HEADER = b"TAG"
# Tamaño de cada campo (en bytes, que en Latin-1 son caracteres)
_TEXT_SIZE = 30
_YEAR_SIZE = 4
_COMMENT_SIZE_V10 = 30
_COMMENT_SIZE_V11 = 28  # con pista
# Valores de la pista y del género
_MAX_TRACK = 255
NO_GENRE = 255
_MAX_BYTE = 255

# Los campos de 'tag_map.TAG_FIELDS' que tiene un ID3v1 y los que no: entre los dos, todos
# (la autoprueba lo comprueba: un campo nuevo obliga a decidir aquí)
ID3V1_FIELDS: tuple[str, ...] = ("title", "artist", "album", "date", "track", "genre", "comment")
NOT_IN_ID3V1: tuple[str, ...] = ("disc", "album_artist", "composer")

# Equivalencias de los caracteres que no están en Latin-1 y tienen una clara (las letras
# con un acento que Latin-1 no tiene se resuelven aparte, quitándoles el acento)
_EQUIVALENTS: dict[int, str] = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    "…": "...", "•": "·", "€": "EUR", "™": "TM", "œ": "oe", "Œ": "OE",
})  # fmt: skip
# Lo que no se puede escribir en Latin-1
_UNKNOWN = "?"
# El año al principio de una fecha
_YEAR_PATTERN = re.compile(r"\s*(\d{4})")
# El número de cada género de la lista, sin distinguir mayúsculas
_GENRE_NUMBERS: dict[str, int] = {name.casefold(): number for number, name in enumerate(GENRES)}


@dataclass(frozen=True, slots=True)
class Id3v1Tag:
    """El contenido de un ID3v1 (siempre cabe en sus 128 bytes: ver el docstring del archivo).

    Attributes:
        title, artist, album: Textos de hasta 30 caracteres de Latin-1.
        year: Hasta 4 caracteres (casi siempre, el año; tal como esté en el archivo).
        comment: Hasta 30 caracteres; 28 si hay pista.
        track: La pista (1 a 255), o None (ID3v1.0).
        genre: El byte del género: su número en la lista ('GENRES' de mutagen) o 255, sin
            género (un valor fuera de la lista se conserva tal cual).

    Raises:
        ValueError: Si algo no cabe en el formato.
    """

    title: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    comment: str = ""
    track: int | None = None
    genre: int = NO_GENRE

    def __post_init__(self) -> None:
        comment_size = _COMMENT_SIZE_V10 if self.track is None else _COMMENT_SIZE_V11
        for name, size in (
            ("title", _TEXT_SIZE), ("artist", _TEXT_SIZE), ("album", _TEXT_SIZE),
            ("year", _YEAR_SIZE), ("comment", comment_size),
        ):  # fmt: skip
            value = getattr(self, name)
            if len(value) > size or "\x00" in value or any(ord(c) > _MAX_BYTE for c in value):
                raise ValueError(f"El campo «{name}» no cabe en un ID3v1: {value!r}")
        if self.track is not None and not 1 <= self.track <= _MAX_TRACK:
            raise ValueError(f"Pista fuera del ID3v1: {self.track}")
        if not 0 <= self.genre <= _MAX_BYTE:
            raise ValueError(f"Género fuera del ID3v1: {self.genre}")

    @property
    def genre_name(self) -> str | None:
        """El nombre del género («Rock»); None si no tiene o no está en la lista."""
        return GENRES[self.genre] if self.genre < len(GENRES) else None


# -----------------------------------------------------------------------------
# Leer y componer los 128 bytes
# -----------------------------------------------------------------------------


def parse_id3v1(data: bytes) -> Id3v1Tag | None:
    """El ID3v1 de los últimos 128 bytes de un archivo; None si no lo son de un ID3v1."""
    if len(data) != ID3V1_SIZE or not data.startswith(_HEADER):
        return None
    comment_bytes = data[97:127]
    track: int | None = None
    if data[125] == 0 and data[126] != 0:  # ID3v1.1: los dos últimos bytes son la pista
        comment_bytes, track = data[97:125], data[126]
    return Id3v1Tag(
        title=_decode(data[3:33]),
        artist=_decode(data[33:63]),
        album=_decode(data[63:93]),
        year=_decode(data[93:97]),
        comment=_decode(comment_bytes),
        track=track,
        genre=data[127],
    )


def build_id3v1(tag: Id3v1Tag) -> bytes:
    """Los 128 bytes de un ID3v1 (ID3v1.1 si tiene pista)."""
    if tag.track is None:
        tail = _encode(tag.comment, _COMMENT_SIZE_V10)
    else:
        tail = _encode(tag.comment, _COMMENT_SIZE_V11) + b"\x00" + bytes([tag.track])
    data = (
        _HEADER
        + _encode(tag.title, _TEXT_SIZE)
        + _encode(tag.artist, _TEXT_SIZE)
        + _encode(tag.album, _TEXT_SIZE)
        + _encode(tag.year, _YEAR_SIZE)
        + tail
        + bytes([tag.genre])
    )
    assert len(data) == ID3V1_SIZE  # lo garantiza 'Id3v1Tag'
    return data


def _decode(field: bytes) -> str:
    """Un campo de texto: hasta el primer cero, en Latin-1, sin espacios a los lados."""
    return field.split(b"\x00", 1)[0].decode("latin-1").strip()


def _encode(text: str, size: int) -> bytes:
    """Un campo de texto en Latin-1, relleno con ceros hasta su tamaño."""
    return text.encode("latin-1").ljust(size, b"\x00")


# -----------------------------------------------------------------------------
# Lo editado
# -----------------------------------------------------------------------------


def apply_changes(tag: Id3v1Tag | None, changes: Mapping[str, Any]) -> Id3v1Tag:
    """El ID3v1 con lo editado, adaptado a sus límites (ver el docstring del archivo).

    Args:
        tag: El que tiene el archivo; None para crear uno.
        changes: Lo editado, con las claves de 'tag_map.TAG_FIELDS' y None para vaciar: los
            textos y la fecha, como texto; la pista y el disco, como la pareja (número,
            total). Los que no existen en un ID3v1 ('NOT_IN_ID3V1') se pasan por alto.

    Raises:
        ValueError: Si una clave no es de 'TAG_FIELDS'.
    """
    values: dict[str, Any] = {}
    for key, value in changes.items():
        if key in ("title", "artist", "album"):
            values[key] = fit_text(value, _TEXT_SIZE)
        elif key == "comment":
            values[key] = fit_text(value, _COMMENT_SIZE_V10)  # a 28, abajo, si hay pista
        elif key == "date":
            values["year"] = _year(value)
        elif key == "track":
            values["track"] = _track(value)
        elif key == "genre":
            values["genre"] = genre_index(value)
        elif key not in NOT_IN_ID3V1:
            raise ValueError(f"Campo desconocido: «{key}»")
    base = tag if tag is not None else Id3v1Tag()
    track = values.get("track", base.track)
    comment = values.get("comment", base.comment)
    if track is not None and len(comment) > _COMMENT_SIZE_V11:
        # Lo pone el formato: con pista, el comentario tiene 28 caracteres (aunque no se
        # haya editado: ver el docstring del archivo)
        values["comment"] = comment[:_COMMENT_SIZE_V11].rstrip()
    return replace(base, **values)


def fit_text(value: object, size: int) -> str:
    """Un texto editado, adaptado a un campo de ID3v1: en Latin-1 (con las equivalencias y
    «?»), sin saltos de línea ni espacios a los lados y recortado a 'size' caracteres. None
    o vacío, ''."""
    if value is None:
        return ""
    # Compuesto (una «é» escrita como «e» + acento pasa a ser una letra de Latin-1)
    text = unicodedata.normalize("NFC", str(value)).translate(_EQUIVALENTS)
    characters: list[str] = []
    for character in text:
        if character in "\t\n\r":
            characters.append(" ")
        elif unicodedata.category(character) == "Cc":
            continue  # los demás caracteres de control (el cero, entre ellos) no son texto
        elif ord(character) <= _MAX_BYTE:
            characters.append(character)
        else:
            characters.append(_without_accent(character))
    return "".join(characters).strip()[:size].rstrip()


def _without_accent(character: str) -> str:
    """Una letra que Latin-1 no tiene, sin su acento («ř» -> «r»); si no es eso, «?»."""
    base = "".join(
        part
        for part in unicodedata.normalize("NFKD", character)
        if not unicodedata.combining(part)
    )
    fits = all(ord(part) <= _MAX_BYTE and unicodedata.category(part) != "Cc" for part in base)
    return base if base and fits else _UNKNOWN


def genre_index(value: object) -> int:
    """El byte del género de un texto: su número en la lista de ID3v1 (con varios, el
    primero), sin distinguir mayúsculas; 'NO_GENRE' si no está o no hay."""
    if value is None:
        return NO_GENRE
    first = str(value).split(MULTI_VALUE_SEPARATOR, 1)[0].strip()
    return _GENRE_NUMBERS.get(first.casefold(), NO_GENRE)


def _year(value: object) -> str:
    """Las cuatro cifras del año del principio de una fecha; '' si no empieza por un año."""
    match = _YEAR_PATTERN.match(str(value)) if value is not None else None
    return match.group(1) if match else ""


def _track(value: object) -> int | None:
    """El número de la pareja (número, total) si cabe en un ID3v1 (1 a 255); si no, None."""
    if value is None:
        return None
    number = value[0] if isinstance(value, tuple) else value
    return number if isinstance(number, int) and 1 <= number <= _MAX_TRACK else None


if __name__ == "__main__":
    # Autoprueba (sin Qt ni archivos). Desde la raíz del proyecto:
    #     python -m core.audio.id3v1
    from core.audio.tag_map import TAG_FIELDS

    # --- Los campos: entre los que tiene y los que no, todos los de la tabla
    assert sorted(ID3V1_FIELDS + NOT_IN_ID3V1) == sorted(field.key for field in TAG_FIELDS)
    assert not set(ID3V1_FIELDS) & set(NOT_IN_ID3V1)

    # --- Componer y leer: ida y vuelta, con y sin pista
    tag = Id3v1Tag("Vino Tinto", "Estopa", "Destrangis", "2001", "Primer disco", 3, 17)
    data = build_id3v1(tag)
    assert len(data) == ID3V1_SIZE and data.startswith(b"TAG")
    assert data[125] == 0 and data[126] == 3 and data[127] == 17  # ID3v1.1
    assert data[3:33] == b"Vino Tinto".ljust(30, b"\x00")
    assert parse_id3v1(data) == tag and tag.genre_name == "Rock"
    v10 = Id3v1Tag(title="Antigua", comment="c" * 30)  # sin pista: 30 de comentario
    assert parse_id3v1(build_id3v1(v10)) == v10
    assert parse_id3v1(build_id3v1(Id3v1Tag())) == Id3v1Tag()
    assert parse_id3v1(b"TAG" + bytes(100)) is None  # no son 128 bytes
    assert parse_id3v1(b"XYZ" + bytes(125)) is None  # no es un ID3v1
    # Rellenos con espacios (algunos programas) y textos con bytes de otra codificación
    spaced = bytearray(build_id3v1(Id3v1Tag()))
    spaced[3:33] = b"Hola".ljust(30, b" ")
    spaced[33:37] = b"Don\x92t"[:4]  # el «’» de Windows (cp1252), que en Latin-1 es otro
    parsed = parse_id3v1(bytes(spaced))
    assert parsed is not None and parsed.title == "Hola" and parsed.artist == "Don\x92"

    # --- Lo que no cabe, al crearlo
    for bad in (
        {"title": "x" * 31}, {"year": "20011"}, {"artist": "東京"}, {"album": "a\x00b"},
        {"comment": "c" * 29, "track": 1}, {"track": 0}, {"track": 256}, {"genre": 256},
    ):  # fmt: skip
        try:
            Id3v1Tag(**bad)
            raise AssertionError(f"debía fallar: {bad}")
        except ValueError:
            pass

    # --- Adaptar un texto
    assert fit_text("Mañana, ¿qué «tal»? Ü", 30) == "Mañana, ¿qué «tal»? Ü"  # Latin-1 cabe
    assert fit_text("Don’t Stop — Live…", 30) == "Don't Stop - Live..."
    assert fit_text("Dvořák: Ŝtar Œuvre", 30) == "Dvorák: Star OEuvre"  # sin el acento
    assert fit_text("東京 Łódź", 30) == "?? ?ódz"  # sin equivalente: «?»
    assert fit_text("café", 30) == "café"  # la «é» en dos partes, en una
    assert fit_text(" dos\nlíneas\t", 30) == "dos líneas"
    assert fit_text("a\x00b\x07c", 30) == "abc"
    assert fit_text("x" * 29 + " yz", 30) == "x" * 29  # recortado, sin el espacio final
    assert fit_text(None, 30) == "" and fit_text("   ", 30) == ""
    # El género, el año y la pista
    assert genre_index("rock") == 17 and genre_index("Rock; Pop") == 17
    assert genre_index("Pop Folk") == NO_GENRE and genre_index(None) == NO_GENRE
    assert genre_index("Hip-Hop") == 7 and genre_index("Psybient") == 191
    assert _year("2001-05-04") == "2001" and _year("1999") == "1999"
    assert _year("abc") == "" and _year(None) == "" and _year("01/02/2003") == ""
    assert _track((3, 12)) == 3 and _track((None, 12)) is None and _track((300, None)) is None
    assert _track(None) is None and _track((0, 5)) is None

    # --- Lo editado, y solo lo editado
    old = parse_id3v1(bytes(spaced))
    assert old is not None
    new = apply_changes(old, {"title": "Nuevo", "composer": "Nadie", "disc": (1, 2)})
    assert new == replace(old, title="Nuevo"), new  # el artista raro y lo demás, igual
    assert build_id3v1(new)[33:63] == bytes(spaced)[33:63]  # byte a byte
    odd_genre = replace(tag, genre=200)  # un género fuera de la lista se conserva
    assert apply_changes(odd_genre, {"album": "Otro"}).genre == 200
    # Vaciar
    cleared = apply_changes(tag, {"title": None, "date": None, "track": None, "genre": None})
    assert (cleared.title, cleared.year, cleared.track, cleared.genre) == ("", "", None, NO_GENRE)
    assert (cleared.artist, cleared.comment) == ("Estopa", "Primer disco")
    # Todo lo de la tabla, adaptado
    full = apply_changes(None, {
        "title": "Una canción con un título muy, muy largo",
        "artist": "Estopa; Rosendo", "album": "Destrangis", "date": "2001-05-04",
        "track": (3, 12), "disc": (1, 1), "genre": "Rock; Pop",
        "album_artist": "Varios", "composer": "J. Muñoz",
        "comment": "Un comentario que no cabe entero en el ID3v1",
    })  # fmt: skip
    assert full == Id3v1Tag(
        "Una canción con un título muy,", "Estopa; Rosendo", "Destrangis", "2001",
        "Un comentario que no cabe en", 3, 17,
    ), full  # fmt: skip
    assert parse_id3v1(build_id3v1(full)) == full
    # Añadir pista a un ID3v1.0 con comentario largo: el comentario, a 28
    with_track = apply_changes(v10, {"track": (5, None)})
    assert with_track.track == 5 and with_track.comment == "c" * 28
    # Sin pista, el comentario puede tener 30
    assert len(apply_changes(None, {"comment": "x" * 40}).comment) == 30
    try:
        apply_changes(tag, {"titulo": "x"})
        raise AssertionError("debía fallar: clave desconocida")
    except ValueError:
        pass

    print("Autoprueba finalizada correctamente.")
