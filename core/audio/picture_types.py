"""Tipos de las imágenes de una canción (portada, contraportada, folleto...): la lista y sus textos.

Este módulo NO depende de Qt, de la base de datos ni de mutagen: es una lista declarativa.

Una canción puede llevar varias imágenes, cada una con su TIPO. ID3 (MP3, WAV, AIFF) y
FLAC (también Ogg y Opus) usan los mismos 21 tipos, numerados del 0 al 20 (los del marco
APIC de ID3). MP4 (M4A) no tiene tipos: sus imágenes se quedan sin clave (None).

Como las actividades de los tracks ('core/tracks/activities.py'), el tipo se GUARDA como
una CLAVE en inglés (el nombre del tipo en mutagen, en minúsculas: 'cover_front') y se
MUESTRA en español (decidido por el autor el 25/11/2026). El número solo se usa al leer y
al escribir el archivo.

La lista va en el orden de Mp3tag (la portada, primero). «Otro icono» y «Pez de colores»
(sí, el estándar ID3 tiene un tipo «A bright coloured fish») se leen y se muestran si un
archivo los trae, pero no se ofrecen al elegir un tipo ('offered=False'; como Mp3tag,
decidido por el autor el 25/11/2026).

Uso:
    picture_type_key(3)              # 'cover_front' (el número de ID3 o FLAC -> la clave)
    picture_type_key(99)             # None (fuera de la lista)
    picture_type_label("cover_back") # 'Contraportada'
    picture_type_label("raro")       # 'raro' (no está en la lista: tal cual)
    picture_type_number("leaflet_page")  # 5 (para escribirlo, desde MUS 9)
    offered_picture_types()          # los que se pueden elegir, en su orden
    FRONT_COVER                      # 'cover_front'

Las claves no se cambian nunca: estarán en los catálogos.

1.0.0 Primera versión (25/11/2026; docs/MOD_MUSICA.md, paso MUS 1.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.audio.picture_types
"""

__version__ = "1.0.0"
__all__ = [
    "FRONT_COVER",
    "PICTURE_TYPES",
    "PictureType",
    "offered_picture_types",
    "picture_type_key",
    "picture_type_label",
    "picture_type_number",
]

# Librerías estándar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PictureType:
    """Un tipo de imagen.

    Attributes:
        key: Clave estable, en inglés (lo que se guarda).
        label: Texto para el usuario.
        number: El número que guardan ID3 (marco APIC) y FLAC (bloque PICTURE).
        offered: Si se ofrece al elegir el tipo de una imagen.
    """

    key: str
    label: str
    number: int
    offered: bool = True


# Clave de la portada: la imagen que hace de carátula
FRONT_COVER = "cover_front"

# La lista, en el orden de Mp3tag; al final, los dos que no se ofrecen
PICTURE_TYPES: tuple[PictureType, ...] = (
    PictureType(FRONT_COVER, "Portada", 3),
    PictureType("cover_back", "Contraportada", 4),
    PictureType("other", "Otra", 0),
    PictureType("file_icon", "Icono", 1),
    PictureType("leaflet_page", "Folleto", 5),
    PictureType("media", "Soporte", 6),  # el propio disco: la cara de un CD o un vinilo
    PictureType("lead_artist", "Solista", 7),
    PictureType("artist", "Artista", 8),
    PictureType("conductor", "Director", 9),
    PictureType("band", "Grupo", 10),
    PictureType("composer", "Compositor", 11),
    PictureType("lyricist", "Letrista", 12),
    PictureType("recording_location", "Lugar de la grabación", 13),
    PictureType("during_recording", "Durante la grabación", 14),
    PictureType("during_performance", "Durante la actuación", 15),
    PictureType("screen_capture", "Captura de vídeo", 16),
    PictureType("illustration", "Ilustración", 18),
    PictureType("band_logotype", "Logotipo del grupo", 19),
    PictureType("publisher_logotype", "Logotipo de la discográfica", 20),
    PictureType("other_file_icon", "Otro icono", 2, offered=False),
    PictureType("fish", "Pez de colores", 17, offered=False),
)

_BY_NUMBER: dict[int, PictureType] = {kind.number: kind for kind in PICTURE_TYPES}
_BY_KEY: dict[str, PictureType] = {kind.key: kind for kind in PICTURE_TYPES}


def picture_type_key(number: object) -> str | None:
    """La clave del tipo con ese número de ID3 o FLAC (None si no es ninguno)."""
    try:
        kind = _BY_NUMBER.get(int(number))  # el de mutagen es un IntEnum
    except (TypeError, ValueError):
        return None
    return kind.key if kind is not None else None


def picture_type_label(key: str | None) -> str:
    """El texto de un tipo; una clave que no está en la lista, tal cual; None, vacío."""
    if key is None:
        return ""
    kind = _BY_KEY.get(key)
    return kind.label if kind is not None else key


def picture_type_number(key: str | None) -> int | None:
    """El número de ID3 o FLAC de un tipo (None si la clave no está en la lista)."""
    kind = _BY_KEY.get(key) if key is not None else None
    return kind.number if kind is not None else None


def offered_picture_types() -> tuple[PictureType, ...]:
    """Los tipos que se pueden elegir, en el orden de la lista."""
    return tuple(kind for kind in PICTURE_TYPES if kind.offered)


if __name__ == "__main__":
    # Autoprueba (sin Qt ni mutagen). Desde la raíz del proyecto:
    #     python -m core.audio.picture_types

    # Los 21 tipos de ID3 y FLAC, cada número y cada clave una sola vez
    assert sorted(kind.number for kind in PICTURE_TYPES) == list(range(21))
    assert len(_BY_KEY) == len(PICTURE_TYPES) == 21
    # Las claves, en minúsculas y sin espacios (como las de las actividades)
    assert all(kind.key == kind.key.lower() and " " not in kind.key for kind in PICTURE_TYPES)
    assert PICTURE_TYPES[0].key == FRONT_COVER and picture_type_number(FRONT_COVER) == 3

    # Número -> clave -> texto, también con lo que no vale
    assert picture_type_key(3) == "cover_front" and picture_type_key("4") == "cover_back"
    assert picture_type_key(17) == "fish" and picture_type_label("fish") == "Pez de colores"
    for bad in (21, -1, None, "x", 3.5j):
        assert picture_type_key(bad) is None, bad
    assert picture_type_label("cover_back") == "Contraportada"
    assert picture_type_label("raro") == "raro" and picture_type_label(None) == ""
    assert picture_type_number("raro") is None and picture_type_number(None) is None

    # Los que se ofrecen: 19, como Mp3tag (sin «Otro icono» ni «Pez de colores»)
    offered = offered_picture_types()
    assert len(offered) == 19 and offered[0].key == FRONT_COVER
    assert {"other_file_icon", "fish"}.isdisjoint(kind.key for kind in offered)

    # Si mutagen está instalado: sus números y sus nombres son los nuestros
    try:
        from mutagen.id3 import PictureType as MutagenPictureType
    except ImportError:
        print("(mutagen no está instalado: no se comparan los números con los suyos)")
    else:
        # No es un Enum de Python: sus tipos son atributos de la clase (enteros)
        members = {
            name: value for name, value in vars(MutagenPictureType).items()
            if not name.startswith("_") and isinstance(value, int)
        }  # fmt: skip
        assert len(members) == 21, sorted(members)
        for name, value in members.items():
            assert picture_type_key(value) == name.lower(), name

    print("Autoprueba finalizada correctamente.")
