"""Datos de las canciones seleccionadas, para la sección «Audio» del inspector.

Este módulo NO depende de Qt. Como todas las funciones que tocan la base de datos, recibe
la conexión como primer parámetro y no hace 'commit' (solo lee).

Los datos de cada canción los lee el extractor ('core/metadata/audio/extractor.py') y están
en 'media_items' (título, artista, año, comentario, duración) y en 'audio_details' (álbum,
pista, género... y los datos técnicos): aquí solo se LEEN y, si hay varias canciones, se
juntan:

    - Los CAMPOS (los diez de la canción y los técnicos que se comparan: formato, modo de
      la tasa de bits, frecuencia, bits, canales y tipo de etiqueta), con las reglas de
      'selection_metadata.fetch_field_values': EMPTY (ninguna tiene valor), VALUE (todas
      el mismo) o MIXED (valores distintos, o unas con valor y otras sin él: «Varios»). Son
      las de «Metadatos», así que la edición ('MUS 7') funcionará igual. El título es el
      PROPIO ('m.file_title'): el nombre del archivo, que queda de título si la canción no
      lo tiene, no cuenta.
    - La DURACIÓN se SUMA ('with_duration' dice cuántas la tienen).
    - La TASA DE BITS: la mínima y la máxima (con varias canciones, la fila «Calidad»
      enseña el intervalo; con una, las dos son la misma).

Solo cuentan las canciones con sus datos ya leídos (una fila en 'audio_details'); los
demás 'id' se ignoran.

Claves de 'AudioStats.fields' ('FIELD_KEYS'): 'title', 'artist', 'album', 'year'
(fecha y precisión), 'track' y 'disc' (número y total), 'genre', 'album_artist',
'composer', 'comment', 'format' (códec y descripción), 'bitrate_mode', 'sample_rate',
'bit_depth', 'channels' y 'tag_type'. El valor de cada una, con VALUE, es la tupla de sus
columnas, en ese orden.

Uso (el inspector lo lanza con 'execute_async'):
    stats = fetch_audio_stats(conn, [12, 15])
    stats.count, stats.duration_s, stats.bitrate_min, stats.bitrate_max
    stats.value("album")          # FieldValue(VALUE, ('Destrangis',)) o MIXED o EMPTY

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 2.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.audio_stats
"""

__version__ = "1.0.0"
__all__ = ["FIELD_KEYS", "AudioStats", "fetch_audio_stats"]

# Librerías estándar
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.catalog.selection_metadata import FieldSource, FieldValue, fetch_field_values

# De dónde sale cada campo (ver 'selection_metadata': 'm.' es 'media_items' y 'audio.',
# 'audio_details'). Solo de las canciones: cualquier otro tipo no tiene estos campos
_AUDIO = MediaType.AUDIO.value
_SOURCES: tuple[FieldSource, ...] = (
    FieldSource("title", {_AUDIO: ("m.file_title",)}),
    FieldSource("artist", {_AUDIO: ("m.creator",)}),
    FieldSource("album", {_AUDIO: ("audio.album",)}),
    FieldSource("year", {_AUDIO: ("m.content_created_at", "m.content_date_precision")}),
    FieldSource("track", {_AUDIO: ("audio.track_number", "audio.track_total")}),
    FieldSource("disc", {_AUDIO: ("audio.disc_number", "audio.disc_total")}),
    FieldSource("genre", {_AUDIO: ("audio.genre",)}),
    FieldSource("album_artist", {_AUDIO: ("audio.album_artist",)}),
    FieldSource("composer", {_AUDIO: ("audio.composer",)}),
    FieldSource("comment", {_AUDIO: ("m.description",)}),
    FieldSource("format", {_AUDIO: ("audio.codec", "audio.codec_detail")}),
    FieldSource("bitrate_mode", {_AUDIO: ("audio.bitrate_mode",)}),
    FieldSource("sample_rate", {_AUDIO: ("audio.sample_rate",)}),
    FieldSource("bit_depth", {_AUDIO: ("audio.bit_depth",)}),
    FieldSource("channels", {_AUDIO: ("audio.channels",)}),
    FieldSource("tag_type", {_AUDIO: ("audio.tag_type",)}),
)
FIELD_KEYS: tuple[str, ...] = tuple(source.key for source in _SOURCES)

# Cuántos 'id' van en cada consulta (SQLite limita los parámetros de una sentencia)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class AudioStats:
    """Los datos de una o varias canciones, juntos (ver el docstring del archivo).

    Attributes:
        count: Canciones con datos.
        fields: Clave del campo ('FIELD_KEYS') -> su valor en la selección.
        duration_s: Duración sumada, en segundos (None si ninguna la tiene).
        with_duration: Cuántas tienen duración.
        bitrate_min: Tasa de bits más baja, en bits por segundo (None si ninguna la tiene).
        bitrate_max: Tasa de bits más alta.
    """

    count: int = 0
    fields: Mapping[str, FieldValue] = field(default_factory=dict)
    duration_s: float | None = None
    with_duration: int = 0
    bitrate_min: int | None = None
    bitrate_max: int | None = None

    def value(self, key: str) -> FieldValue:
        """El valor de un campo (vacío si no se ha pedido o no hay canciones)."""
        return self.fields.get(key, FieldValue())


def fetch_audio_stats(conn: sqlite3.Connection, media_ids: Sequence[int]) -> AudioStats:
    """Los datos, juntos, de las canciones que haya entre esos 'id' (ver el docstring del
    archivo). Sin ninguna, un 'AudioStats' vacío ('count' = 0)."""
    ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))  # sin repetidos
    songs: list[int] = []  # las que tienen sus datos leídos
    duration: float | None = None
    with_duration = 0
    lowest: int | None = None
    highest: int | None = None
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT m.id, m.duration, d.bitrate
                  FROM media_items AS m
                  JOIN audio_details AS d ON d.media_id = m.id
                 WHERE m.media_type = ? AND m.id IN ({marks})""",  # solo se interpolan '?'
            (_AUDIO, *chunk),
        )
        for media_id, row_duration, row_bitrate in rows:
            songs.append(media_id)
            if row_duration is not None and row_duration > 0:
                with_duration += 1
                duration = row_duration if duration is None else duration + row_duration
            if row_bitrate is not None and row_bitrate > 0:
                lowest = row_bitrate if lowest is None else min(lowest, row_bitrate)
                highest = row_bitrate if highest is None else max(highest, row_bitrate)
    if not songs:
        return AudioStats()
    return AudioStats(
        count=len(songs),
        fields=fetch_field_values(conn, songs, _SOURCES),
        duration_s=duration,
        with_duration=with_duration,
        bitrate_min=lowest,
        bitrate_max=highest,
    )


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.audio_stats
    from typing import Any

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.selection_metadata import EMPTY, MIXED, VALUE

    db = sqlite3.connect(":memory:")
    configure_connection(db)  # 'm.file_title' necesita la función SQL de la aplicación
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('M', '/m')")

    def add(media_id: int, media_type: str, title: str, details: dict | None, **columns: Any) -> None:
        """Un elemento ('file_name' es el título con '.x') y, si se da, su fila de detalles."""
        names = "".join(f", {name}" for name in columns)
        marks = "".join(", ?" for _ in columns)
        db.execute(
            f"""INSERT INTO media_items(id, storage_location_id, relative_path, file_name,
                    title, file_extension, media_type, mime_type, file_size,
                    file_mtime_ns{names})
                VALUES (?, 1, ?, ?, ?, 'x', ?, 'x/x', 1, 1{marks})""",
            (media_id, f"f{media_id}", f"f{media_id}.x", title, media_type, *columns.values()),
        )
        if details is not None:
            keys = "".join(f", {name}" for name in details)
            values = "".join(", ?" for _ in details)
            db.execute(
                f"INSERT INTO audio_details(media_id{keys}) VALUES (?{values})",
                (media_id, *details.values()),
            )

    year_2001 = {"content_created_at": "2001-01-01 00:00:00", "content_date_precision": "year"}
    aac = {"codec": "aac", "codec_detail": "AAC LC", "sample_rate": 44100, "channels": 2,
           "tag_type": "MP4", "album": "Destrangis", "genre": "Pop Folk", "track_total": 12}  # fmt: skip
    # 1 y 2: dos canciones del mismo álbum; 3: un MP3 VBR de otro, sin título propio (se
    # quedó el nombre del archivo); 4: canción sin leer todavía; 5: una foto
    add(1, "audio", "Vino Tinto", {**aac, "track_number": 1, "bitrate": 138299},
        creator="Estopa", duration=198.6, **year_2001)  # fmt: skip
    add(2, "audio", "Partiendo la Pana", {**aac, "track_number": 2, "bitrate": 71479},
        creator="Estopa", duration=201.4, **year_2001)  # fmt: skip
    add(3, "audio", "f3", {"codec": "mp3", "bitrate_mode": "vbr", "bitrate": 277471,
                           "sample_rate": 44100, "channels": 2, "tag_type": "ID3v2.3",
                           "album": "Back To Black"},
        creator="Amy Winehouse", description="Primera línea\nSegunda")  # fmt: skip
    add(4, "audio", "Sin leer", None, duration=100.0)
    add(5, "photo", "Foto", None)

    # --- Una sola: sus valores, tal cual
    one = fetch_audio_stats(db, [1])
    assert one.count == 1 and one.duration_s == 198.6 and one.with_duration == 1
    assert (one.bitrate_min, one.bitrate_max) == (138299, 138299)
    assert one.value("title") == FieldValue(VALUE, ("Vino Tinto",))
    assert one.value("artist") == FieldValue(VALUE, ("Estopa",))
    assert one.value("year") == FieldValue(VALUE, ("2001-01-01 00:00:00", "year"))
    assert one.value("track") == FieldValue(VALUE, (1, 12))
    assert one.value("disc") == FieldValue(EMPTY) and one.value("composer") == FieldValue(EMPTY)
    assert one.value("format") == FieldValue(VALUE, ("aac", "AAC LC"))
    assert one.value("bit_depth") == FieldValue(EMPTY)
    assert set(one.fields) == set(FIELD_KEYS)

    # --- El álbum entero: lo común, «Varios» en la pista; la duración, sumada; la tasa,
    # el intervalo
    album = fetch_audio_stats(db, [2, 1, 1])  # los repetidos no cuentan dos veces
    assert album.count == 2 and round(album.duration_s, 1) == 400.0
    assert (album.bitrate_min, album.bitrate_max) == (71479, 138299)
    assert album.value("album") == FieldValue(VALUE, ("Destrangis",))
    assert album.value("track").state == MIXED and album.value("genre").state == VALUE
    assert album.value("sample_rate") == FieldValue(VALUE, (44100,))

    # --- De dos álbumes: lo que solo tienen unas es «Varios»; sin título propio no cuenta
    mixed = fetch_audio_stats(db, [1, 3])
    assert mixed.value("album").state == MIXED and mixed.value("format").state == MIXED
    assert mixed.value("bitrate_mode").state == MIXED  # el MP3 lo tiene; el M4A, no
    assert mixed.value("channels") == FieldValue(VALUE, (2,))
    assert mixed.duration_s == 198.6 and mixed.with_duration == 1  # el MP3 no tiene duración
    assert fetch_audio_stats(db, [3]).value("title") == FieldValue(EMPTY)  # el nombre del archivo
    assert fetch_audio_stats(db, [3]).value("comment") == FieldValue(VALUE, ("Primera línea\nSegunda",))

    # --- Lo que no es una canción leída se ignora; sin nada, vacío
    assert fetch_audio_stats(db, [1, 4, 5, 999]) == one
    for nothing in ([], [4], [5], [999]):
        empty = fetch_audio_stats(db, nothing)
        assert empty == AudioStats() and empty.value("album") == FieldValue(EMPTY), nothing

    # --- Muchos 'id' (más de los que caben en una consulta)
    assert fetch_audio_stats(db, [*range(1000, 2500), 1, 2]) == fetch_audio_stats(db, [1, 2])

    db.close()
    print("Autoprueba finalizada correctamente.")
