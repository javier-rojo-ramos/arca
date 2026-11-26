"""La carátula de las canciones seleccionadas, para la sección «Carátula» del inspector.

Este módulo NO depende de Qt. Como todas las funciones que tocan la base de datos, recibe
la conexión como primer parámetro y no hace 'commit' (solo lee).

Los datos de la carátula de cada canción los lee el extractor
('core/metadata/audio/extractor.py') y están en 'audio_details': cuántas imágenes trae
el archivo ('picture_count'), y de la que hace de carátula, su tipo, su formato, su tamaño,
su peso y su huella ('cover_hash'; dos canciones con la misma huella tienen la misma
imagen). Aquí solo se LEEN y, si hay varias canciones, se juntan con las reglas de
'selection_metadata' (las de «Audio» y «Metadatos»; acordado con el autor el 26/11/2026):

    - 'cover_type' (la fila «Tipo»): EMPTY (ninguna tiene carátula), VALUE (todas el mismo
      tipo) o MIXED (tipos distintos, o unas con carátula y otras sin ella).
    - 'image' (la fila «Imagen»: formato, ancho, alto y peso): VALUE solo si TODAS tienen la
      MISMA carátula (la misma huella); MIXED si hay carátulas distintas, o unas con ella y
      otras sin ella. Dos carátulas distintas del mismo tamaño siguen siendo «Varios».
    - 'shown_id': la canción cuya miniatura se enseña (la primera, en el orden de los 'id'
      recibidos, con esa carátula común). None si no hay una común: el marcador.
    - 'covers': cuántas carátulas distintas hay (para «2 carátulas distintas»).
    - 'most_pictures': el mayor número de imágenes de una canción (para avisar de que el
      archivo trae más de una: se enseña la que hace de carátula).

Solo cuentan las canciones con sus datos ya leídos (una fila en 'audio_details'); los
demás 'id' se ignoran.

Uso (el inspector lo lanza con 'execute_async'):
    stats = fetch_cover_stats(conn, [12, 15])
    stats.shown_id                 # 12 (o None)
    stats.cover_type               # FieldValue(VALUE, ('cover_front',)), MIXED o EMPTY
    stats.image                    # FieldValue(VALUE, ('image/jpeg', 600, 600, 25000))...

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 9.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.cover_stats
"""

__version__ = "1.0.0"
__all__ = ["CoverStats", "fetch_cover_stats"]

# Librerías estándar
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.catalog.selection_metadata import EMPTY, MIXED, VALUE, FieldValue

# Cuántos 'id' van en cada consulta (SQLite limita los parámetros de una sentencia)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class CoverStats:
    """La carátula de una o varias canciones, junta (ver el docstring del archivo).

    Attributes:
        count: Canciones con datos.
        with_cover: Cuántas tienen carátula.
        covers: Cuántas carátulas distintas hay (por su huella).
        shown_id: La canción cuya miniatura se enseña (None: no hay una común).
        cover_type: El tipo de la carátula en la selección.
        image: Formato, ancho, alto y peso de la carátula común.
        most_pictures: El mayor número de imágenes que trae una de las canciones.
    """

    count: int = 0
    with_cover: int = 0
    covers: int = 0
    shown_id: int | None = None
    cover_type: FieldValue = field(default_factory=FieldValue)
    image: FieldValue = field(default_factory=FieldValue)
    most_pictures: int = 0


def _merged(values: Sequence[Any]) -> FieldValue:
    """Las reglas de 'selection_metadata' con los valores de cada canción (None = sin él):
    ninguno, EMPTY; todos el mismo, VALUE; si no, MIXED."""
    present = [value for value in values if value is not None]
    if not present:
        return FieldValue(EMPTY)
    if len(present) < len(values) or len(set(present)) > 1:
        return FieldValue(MIXED)
    first = present[0]
    return FieldValue(VALUE, first if isinstance(first, tuple) else (first,))


def fetch_cover_stats(conn: sqlite3.Connection, media_ids: Sequence[int]) -> CoverStats:
    """La carátula, junta, de las canciones que haya entre esos 'id' (ver el docstring del
    archivo). Sin ninguna, un 'CoverStats' vacío ('count' = 0)."""
    ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))  # sin repetidos
    rows: dict[int, tuple[Any, ...]] = {}
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        for row in conn.execute(
            f"""SELECT m.id, d.picture_count, d.cover_type, d.cover_mime, d.cover_width,
                       d.cover_height, d.cover_bytes, d.cover_hash
                  FROM media_items AS m
                  JOIN audio_details AS d ON d.media_id = m.id
                 WHERE m.media_type = ? AND m.id IN ({marks})""",  # solo se interpolan '?'
            (MediaType.AUDIO.value, *chunk),
        ):
            rows[row[0]] = row[1:]
    if not rows:
        return CoverStats()

    # En el orden recibido (el de la cuadrícula): la primera con la carátula común se enseña
    songs = [(media_id, rows[media_id]) for media_id in ids if media_id in rows]
    hashes = [values[6] for _media_id, values in songs]
    # Sin huella no hay carátula, aunque las otras columnas trajeran algo
    types = [values[1] if values[6] is not None else None for _media_id, values in songs]
    image = _merged(hashes)
    shown_id: int | None = None
    image_value = FieldValue(image.state)
    if image.state == VALUE:
        shown_id, values = songs[0]
        image_value = FieldValue(VALUE, (values[2], values[3], values[4], values[5]))
    present = [digest for digest in hashes if digest is not None]
    return CoverStats(
        count=len(songs),
        with_cover=len(present),
        covers=len(set(present)),
        shown_id=shown_id,
        cover_type=_merged(types),
        image=image_value,
        most_pictures=max((values[0] or 0 for _media_id, values in songs), default=0),
    )


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.cover_stats
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('L', '/l')")

    def add(name: str, media_type: str = "audio", cover: tuple[Any, ...] | None = None,
            pictures: int | None = None) -> int:
        """Crea un elemento; las canciones, con su fila de 'audio_details' y su carátula
        (tipo, formato, ancho, alto, peso y huella) o sin ella."""
        media_id = int(db.execute(
            """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                   media_type, mime_type, file_size, file_mtime_ns, title)
               VALUES (1, ?, ?, ?, 'x', 1, 0, 't')""",
            (name, name, media_type),
        ).lastrowid)  # fmt: skip
        if media_type == "audio":
            columns = cover or (None,) * 6
            count = pictures if pictures is not None else (1 if cover else 0)
            db.execute(
                """INSERT INTO audio_details(media_id, picture_count, cover_type, cover_mime,
                       cover_width, cover_height, cover_bytes, cover_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (media_id, count, *columns),
            )  # fmt: skip
        return media_id

    front = ("cover_front", "image/jpeg", 600, 600, 25_000, "a" * 32)
    other = ("cover_front", "image/png", 600, 600, 31_000, "b" * 32)
    back = ("cover_back", *front[1:])  # la misma imagen con otro tipo
    first = add("1.mp3", cover=front)
    second = add("2.mp3", cover=front, pictures=3)
    distinct = add("3.mp3", cover=other)
    bare = add("4.mp3")
    same_back = add("5.mp3", cover=back)
    photo = add("6.jpg", "photo")
    pending = int(db.execute(  # una canción sin sus datos leídos todavía
        """INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
               mime_type, file_size, file_mtime_ns, title)
           VALUES (1, '7.mp3', '7.mp3', 'audio', 'x', 1, 0, 't')"""
    ).lastrowid)

    # 1. Una canción: su carátula, su tipo y la que se enseña
    one = fetch_cover_stats(db, [first])
    assert (one.count, one.with_cover, one.covers, one.shown_id) == (1, 1, 1, first)
    assert one.cover_type == FieldValue(VALUE, ("cover_front",))
    assert one.image == FieldValue(VALUE, ("image/jpeg", 600, 600, 25_000))
    assert one.most_pictures == 1

    # 2. Un álbum (la misma carátula): la primera en el orden recibido; las imágenes de más
    album = fetch_cover_stats(db, [second, first, first])  # los repetidos no cuentan dos veces
    assert (album.count, album.covers, album.shown_id, album.most_pictures) == (2, 1, second, 3)
    assert album.image.state == VALUE and album.cover_type.state == VALUE

    # 3. Carátulas distintas del mismo tipo: el tipo común, la imagen «Varios», ninguna se enseña
    mixed = fetch_cover_stats(db, [first, distinct])
    assert mixed.cover_type == FieldValue(VALUE, ("cover_front",))
    assert mixed.image == FieldValue(MIXED) and mixed.shown_id is None and mixed.covers == 2

    # 4. Unas con carátula y otras sin ella: «Varios» en las dos filas
    partly = fetch_cover_stats(db, [first, bare])
    assert partly.cover_type.state == MIXED and partly.image.state == MIXED
    assert (partly.with_cover, partly.covers, partly.shown_id) == (1, 1, None)

    # 5. Ninguna con carátula: vacío (la fila «Imagen» dirá «Sin carátula»)
    none = fetch_cover_stats(db, [bare])
    assert none.count == 1 and none.with_cover == 0 and none.shown_id is None
    assert none.cover_type == FieldValue(EMPTY) and none.image == FieldValue(EMPTY)

    # 6. La misma imagen con otro tipo: se enseña, pero el tipo es «Varios»
    retyped = fetch_cover_stats(db, [first, same_back])
    assert retyped.image.state == VALUE and retyped.shown_id == first
    assert retyped.cover_type.state == MIXED

    # 7. Lo que no son canciones con sus datos, fuera; sin canciones, vacío
    assert fetch_cover_stats(db, [first, photo, pending, 999]) == one
    assert fetch_cover_stats(db, [photo, pending]) == CoverStats()
    assert fetch_cover_stats(db, []) == CoverStats()

    # 8. Más de 500 'id' (en trozos): el mismo resultado
    assert fetch_cover_stats(db, [*range(1000, 2500), second, first]) == album

    print("Autoprueba finalizada correctamente.")
