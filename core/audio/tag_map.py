"""Tabla campo ↔ etiqueta de las canciones: qué etiqueta de cada formato guarda cada campo.

Este módulo NO depende de Qt, de la base de datos ni de mutagen: es una lista declarativa.

Tres familias de etiquetas:

    ID3      MP3 (y WAV y AIFF, que lo llevan dentro)   marcos de 4 letras ('TIT2')
    Vorbis   FLAC, Ogg Vorbis y Opus                     nombres libres ('TITLE'), sin
                                                         distinguir mayúsculas
    MP4      M4A                                         átomos ('©nam')

Es la MISMA tabla para leer ('tag_reader.py') y, desde MUS 6, para escribir: así los dos
entienden lo mismo (docs/MOD_MUSICA.md §3.3). En Vorbis, la PRIMERA clave es la que se
escribe; las demás solo se leen (las usan otros programas: «ALBUM ARTIST», «TOTALTRACKS»,
«DESCRIPTION»...). Al leer vale la primera que tenga valor.

Los campos, en el orden de la sección «Audio» del inspector (docs/MOD_MUSICA.md §7.1):

    title          Título              TIT2    TITLE          ©nam
    artist         Artista             TPE1    ARTIST         ©ART
    album          Álbum               TALB    ALBUM          ©alb
    date           Año                 TDRC    DATE           ©day
    track          Pista (y total)     TRCK    TRACKNUMBER    trkn
    disc           Disco (y total)     TPOS    DISCNUMBER     disk
    genre          Género              TCON    GENRE          ©gen
    album_artist   Artista del álbum   TPE2    ALBUMARTIST    aART
    composer       Compositor          TCOM    COMPOSER       ©wrt
    comment        Comentario          COMM    COMMENT        ©cmt

Cada campo tiene un TIPO ('kind'), que dice cómo se traduce:
    - TEXT: un texto (varios valores, unidos con 'MULTI_VALUE_SEPARATOR').
    - DATE: la fecha, tal cual («2001», «2001-05-04»). En ID3v2.3 está en TYER (y TDAT):
      mutagen lo pasa a TDRC al leer y lo devuelve a TYER al escribir en v2.3.
    - PAIR: número y total. En ID3, juntos en un texto («3/12»); en Vorbis, en dos claves
      ('vorbis' y 'vorbis_total'; algunos programas escriben «3/12» en la primera); en MP4,
      un par de números.
    - GENRE: un texto; en ID3 puede venir como número de ID3v1 («(17)» es Rock) y en MP4
      como número en otro átomo ('MP4_GENRE_NUMBER', de iTunes antiguos; solo se lee).
    - COMMENT: un texto. En ID3 hay varios marcos COMM, con una descripción cada uno: el
      comentario es el que no tiene (el que muestra Mp3tag); los de iTunes («iTunNORM»...),
      no.

Varios valores (varios géneros o artistas): se unen en un texto con 'MULTI_VALUE_SEPARATOR'
(«; », no la coma de las palabras clave: en un artista la coma es normal, «Earth, Wind &
Fire»; docs/MOD_MUSICA.md §3.4).

Añadir un campo: una línea en 'TAG_FIELDS' (la clave no se cambia nunca después).

1.0.0 Primera versión (25/11/2026; docs/MOD_MUSICA.md, paso MUS 1.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.audio.tag_map
"""

__version__ = "1.0.0"
__all__ = [
    "COMMENT",
    "DATE",
    "GENRE",
    "MP4_GENRE_NUMBER",
    "MULTI_VALUE_SEPARATOR",
    "PAIR",
    "TAG_FIELDS",
    "TEXT",
    "TagField",
    "tag_field",
]

# Librerías estándar
from dataclasses import dataclass

# Tipos de campo (ver el docstring del archivo)
TEXT = "text"
DATE = "date"
PAIR = "pair"
GENRE = "genre"
COMMENT = "comment"

# Separador de varios valores en un texto (docs/MOD_MUSICA.md §3.4)
MULTI_VALUE_SEPARATOR = "; "

# Átomo de MP4 con el género como número de ID3v1 más uno (solo se lee)
MP4_GENRE_NUMBER = "gnre"


@dataclass(frozen=True, slots=True)
class TagField:
    """Un campo de la canción y su etiqueta en cada formato.

    Attributes:
        key: Clave estable del campo (en inglés).
        label: Texto para el usuario (el de la sección «Audio» del inspector).
        kind: Cómo se traduce: TEXT, DATE, PAIR, GENRE o COMMENT.
        id3: Marco de ID3.
        vorbis: Claves de Vorbis, en mayúsculas; la primera es la que se escribe.
        mp4: Átomo de MP4.
        vorbis_total: Solo en las parejas: las claves de Vorbis del total.
    """

    key: str
    label: str
    kind: str
    id3: str
    vorbis: tuple[str, ...]
    mp4: str
    vorbis_total: tuple[str, ...] = ()


# La tabla, en el orden de la sección «Audio» del inspector
TAG_FIELDS: tuple[TagField, ...] = (
    TagField("title", "Título", TEXT, "TIT2", ("TITLE",), "©nam"),
    TagField("artist", "Artista", TEXT, "TPE1", ("ARTIST",), "©ART"),
    TagField("album", "Álbum", TEXT, "TALB", ("ALBUM",), "©alb"),
    TagField("date", "Año", DATE, "TDRC", ("DATE", "YEAR"), "©day"),
    TagField("track", "Pista", PAIR, "TRCK", ("TRACKNUMBER",), "trkn",
             ("TRACKTOTAL", "TOTALTRACKS")),
    TagField("disc", "Disco", PAIR, "TPOS", ("DISCNUMBER",), "disk",
             ("DISCTOTAL", "TOTALDISCS")),
    TagField("genre", "Género", GENRE, "TCON", ("GENRE",), "©gen"),
    TagField("album_artist", "Artista del álbum", TEXT, "TPE2", ("ALBUMARTIST", "ALBUM ARTIST"),
             "aART"),
    TagField("composer", "Compositor", TEXT, "TCOM", ("COMPOSER",), "©wrt"),
    TagField("comment", "Comentario", COMMENT, "COMM", ("COMMENT", "DESCRIPTION"), "©cmt"),
)  # fmt: skip

_BY_KEY: dict[str, TagField] = {field.key: field for field in TAG_FIELDS}


def tag_field(key: str) -> TagField:
    """El campo con esa clave.

    Raises:
        KeyError: Si no existe.
    """
    return _BY_KEY[key]


if __name__ == "__main__":
    # Autoprueba (sin Qt ni mutagen). Desde la raíz del proyecto:
    #     python -m core.audio.tag_map

    keys = [field.key for field in TAG_FIELDS]
    # Los diez campos de docs/MOD_MUSICA.md, en el orden del inspector (§7.1)
    assert keys == [
        "title", "artist", "album", "date", "track", "disc", "genre", "album_artist",
        "composer", "comment",
    ], keys  # fmt: skip
    assert len(set(keys)) == len(keys)
    assert tag_field("track").label == "Pista"
    try:
        tag_field("no_existe")
        raise AssertionError("debía fallar")
    except KeyError:
        pass

    for field in TAG_FIELDS:
        # Cada campo, en las tres familias
        assert field.id3 and field.vorbis and field.mp4, field.key
        assert field.kind in (TEXT, DATE, PAIR, GENRE, COMMENT), field.key
        # ID3: marcos de 4 letras o cifras, en mayúsculas
        assert len(field.id3) == 4 and field.id3 == field.id3.upper(), field.key
        # Vorbis: en mayúsculas (se comparan sin distinguirlas al leer)
        assert all(key == key.upper() for key in field.vorbis + field.vorbis_total), field.key
        # Las parejas, con las claves del total; los demás, sin ellas
        assert bool(field.vorbis_total) == (field.kind == PAIR), field.key

    # Ninguna etiqueta guarda dos campos
    for family in ("id3", "mp4"):
        tags = [getattr(field, family) for field in TAG_FIELDS]
        assert len(set(tags)) == len(tags), family
    vorbis = [key for field in TAG_FIELDS for key in field.vorbis + field.vorbis_total]
    assert len(set(vorbis)) == len(vorbis)
    assert MP4_GENRE_NUMBER not in {field.mp4 for field in TAG_FIELDS}
    assert "," not in MULTI_VALUE_SEPARATOR  # la coma es normal en un artista

    print("Autoprueba finalizada correctamente.")
