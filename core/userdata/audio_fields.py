"""Los campos de las canciones que van a sus etiquetas: columna del catálogo ↔ campo.

Este módulo NO depende de Qt, de la base de datos ni de mutagen: es una tabla y una
traducción. Lo usan 'policy.py' (lo que se queda en el '.arca.json' de un MP3 es lo que NO
está aquí) y el escritor de las canciones ('audio_writer.py'), que pasa lo pendiente de una
canción a «lo editado» del motor de escritura ('core/audio/tag_writer.write_tags').

    AUDIO_TAG_COLUMNS               las columnas editables que van a las etiquetas
    tag_changes(wanted, metadata)   lo pendiente de una canción, para 'write_tags'

La tabla (docs/MOD_MUSICA.md §3 y §5; acordada con el autor el 16 y el 28/11/2026):

    columna del catálogo        campo de 'tag_map'   en ID3
    title                       title                TIT2 (igual al nombre del archivo:
                                                     «sin título», y se borra)
    creator                     artist               TPE1
    description                 comment              COMM sin descripción
    album                       album                TALB
    album_artist                album_artist         TPE2
    track_number, track_total   track                TRCK («3/12»; sin número, nada)
    disc_number, disc_total     disc                 TPOS
    genre                       genre                TCON
    composer                    composer             TCOM
    content_created_at          date                 TDRC (v2.4) o TYER (v2.3): el año,
                                                     «1999» (MUS 7.1a)

Es la misma correspondencia con la que el extractor guarda lo leído
('core/metadata/audio/extractor.py'). El año ('content_created_at', la fecha de su 1 de
enero) se escribe como un año (el autor, 28/11/2026): «1999».

Una PAREJA (la pista y su total, el disco y el suyo) va siempre entera: si está pendiente
una de las dos columnas, se escribe la pareja con los valores del catálogo de las dos. Sin
número no se guarda el total (ID3 solo admite «3/12» o «3»; decidido el 28/11/2026).

1.1.0 El año ('content_created_at' -> 'date', como «1999»; MUS 7.1a).
1.0.0 Primera versión (28/11/2026; docs/MOD_MUSICA.md, paso MUS 6.2b).

Prueba rápida (desde la raíz del proyecto):
    python -m core.userdata.audio_fields
"""

__version__ = "1.1.0"
__all__ = ["AUDIO_TAG_COLUMNS", "tag_changes"]

# Librerías estándar
from collections.abc import Mapping
from typing import Any

# Columna del catálogo -> campo de 'tag_map.TAG_FIELDS' (las de una pareja, aparte)
_SINGLE_COLUMNS: dict[str, str] = {
    "title": "title",
    "creator": "artist",
    "description": "comment",
    "album": "album",
    "album_artist": "album_artist",
    "genre": "genre",
    "composer": "composer",
}
# Campo de pareja de 'tag_map' -> (columna del número, columna del total)
_PAIR_COLUMNS: dict[str, tuple[str, str]] = {
    "track": ("track_number", "track_total"),
    "disc": ("disc_number", "disc_total"),
}
# Columna de fecha -> su campo (el año de una canción: se escribe como un año)
_YEAR_COLUMNS: dict[str, str] = {"content_created_at": "date"}
# Columna de una pareja -> su campo
_PAIR_OF: dict[str, str] = {
    column: key for key, columns in _PAIR_COLUMNS.items() for column in columns
}

# Las columnas editables que van a las etiquetas de una canción
AUDIO_TAG_COLUMNS: frozenset[str] = (
    frozenset(_SINGLE_COLUMNS) | frozenset(_PAIR_OF) | frozenset(_YEAR_COLUMNS)
)


def tag_changes(wanted: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Lo pendiente de una canción como «lo editado» de 'write_tags' (ver el docstring del
    archivo). Lo que no va a las etiquetas (la valoración, una columna sin campo) se pasa
    por alto.

    Args:
        wanted: Columna -> valor a escribir ('WriteItem.wanted': el título, ya con la regla
            del nombre del archivo).
        metadata: Columna -> valor del catálogo de las columnas editables
            ('WriteItem.metadata'): de ahí sale la otra mitad de una pareja.
    """
    changes: dict[str, Any] = {}
    for column, value in wanted.items():
        if column in _SINGLE_COLUMNS:
            changes[_SINGLE_COLUMNS[column]] = value
        elif column in _YEAR_COLUMNS:
            # La fecha de su 1 de enero («1999-01-01 00:00:00»), como un año: «1999»
            changes[_YEAR_COLUMNS[column]] = None if value is None else str(value)[:4]
        elif column in _PAIR_OF:
            key = _PAIR_OF[column]
            number_column, total_column = _PAIR_COLUMNS[key]
            number = wanted.get(number_column, metadata.get(number_column))
            total = wanted.get(total_column, metadata.get(total_column))
            changes[key] = None if number is None else (number, total)
    return changes


if __name__ == "__main__":
    # Autoprueba (sin Qt, sin mutagen y sin archivos). Desde la raíz del proyecto:
    #     python -m core.userdata.audio_fields
    from core.audio.tag_map import PAIR, TAG_FIELDS, tag_field
    from core.userdata.editable_fields import field_for

    # --- La tabla: columnas editables de las canciones (o comunes) y campos de 'tag_map'
    for column in AUDIO_TAG_COLUMNS:
        spec = field_for(column)  # editable (si no, ValueError)
        assert not spec.media_types or spec.media_types == ("audio",), column
    for key in _SINGLE_COLUMNS.values():
        assert tag_field(key).kind != PAIR, key
    for key in _PAIR_COLUMNS:
        assert tag_field(key).kind == PAIR, key
    # Todos los campos de las etiquetas tienen su columna (el año, desde MUS 7.1a)
    covered = set(_SINGLE_COLUMNS.values()) | set(_PAIR_COLUMNS) | set(_YEAR_COLUMNS.values())
    assert covered == {field.key for field in TAG_FIELDS}, covered
    assert len(AUDIO_TAG_COLUMNS) == 12

    # --- Lo pendiente, como «lo editado»
    metadata = {
        "title": "Vino Tinto", "creator": "Estopa", "album": "Destrangis",
        "track_number": 3, "track_total": 12, "disc_number": None, "disc_total": 2,
        "city": "León",
    }  # fmt: skip
    assert tag_changes({"title": None, "creator": "Estopa; Rosendo"}, metadata) == {
        "title": None, "artist": "Estopa; Rosendo",
    }  # fmt: skip
    # Una mitad de la pareja pendiente: la pareja entera, con la otra mitad del catálogo
    assert tag_changes({"track_number": 4}, metadata) == {"track": (4, 12)}
    assert tag_changes({"track_total": None}, metadata) == {"track": (3, None)}
    # Sin número, no se guarda el total
    assert tag_changes({"disc_total": 2}, metadata) == {"disc": None}
    assert tag_changes({"track_number": None}, metadata) == {"track": None}
    # Lo que no va a las etiquetas, fuera
    assert tag_changes({"rating": 4, "keywords": (), "city": "Soria"}, metadata) == {}
    assert tag_changes({"description": "Primer disco", "genre": None}, metadata) == {
        "comment": "Primer disco", "genre": None,
    }  # fmt: skip
    # El año, como un año; vaciado, None
    assert tag_changes({"content_created_at": "1999-01-01 00:00:00"}, metadata) == {"date": "1999"}
    assert tag_changes({"content_created_at": None}, metadata) == {"date": None}

    print("Autoprueba finalizada correctamente.")
