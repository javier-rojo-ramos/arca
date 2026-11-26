"""Vista de álbumes de Música: una fila por álbum (la primera tarjeta agrupada, GEN 17).

Este módulo NO depende de Qt. 'fetch_album_rows' recibe la conexión SQLite como primer
parámetro (para 'CatalogDatabaseManager.execute_async') y solo lee.

Cada fila lleva las claves de 'media_queries.fetch_grid_rows' (lo que pinta una tarjeta) y
las de su grupo:

    id                 la canción de la carátula: la primera del álbum que tiene miniatura
                       (si ninguna la tiene, la primera)
    group_ids          las canciones del álbum, por disco y pista: seleccionar la tarjeta es
                       seleccionarlas, y lo que se haga sobre ella va a todas
    group_count        cuántas son
    group_source       lo que muestra la cuadrícula al entrar en el álbum: su fila de
                       «Artistas» ('music_browse.artist_album_source')
    album, artist      sus nombres, escritos como en «Artistas» (None = «Sin álbum», «Sin
                       artista»: los textos los pone la interfaz)
    year_min, year_max el año más antiguo y el más reciente de sus canciones (None sin año)
    duration           la suma de sus duraciones (None si ninguna la tiene)
    rating, flag, color_label, in_quick_selection
                       el valor común de sus canciones; si difieren, el de «ninguno» (0,
                       0, None y 0), como «Varios» en el inspector
    el resto           (tipo, biblioteca, disponibilidad, estado de la miniatura), los de la
                       canción de la carátula

Reglas (acordadas con el autor el 26/11/2026; docs/MOD_MUSICA.md §7.5):
    - Las canciones son las del origen y el filtro, como en la cuadrícula: un álbum cuenta
      solo las suyas que lo cumplen.
    - Se agrupan como en «Artistas»: por el artista del álbum (o, sin él, el artista) y el
      álbum, sin mayúsculas ni acentos. Las canciones sin álbum, en un «Sin álbum» por
      artista. Lo que no es una canción (no debería haberlo en Música), en su propia fila,
      tal cual.
    - Los álbumes, en el orden del desplegable: cada uno donde va su primera canción en ese
      orden (con «Artista», cada artista y sus discos por año).

Uso:
    rows = fetch_album_rows(conn, order, source, filters)   # en segundo plano
    rows[0]["album"], rows[0]["group_count"], rows[0]["group_ids"]

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 5.3).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.album_rows
"""

__version__ = "1.0.0"
__all__ = ["ALBUM_GROUPING", "fetch_album_rows"]

# Librerías estándar
import sqlite3
from collections import Counter
from collections.abc import Sequence
from typing import Any, NamedTuple

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.catalog.grid_orders import ARTIST_ORDER, GridOrder
from core.catalog.grid_source import ALL_ITEMS, GridSource
from core.catalog.libraries import Library
from core.catalog.media_queries import fetch_grid_rows, source_condition
from core.catalog.media_types import MediaType
from core.catalog.music_browse import (
    ALBUM_FIELD,
    ARTIST_FIELD,
    artist_album_source,
    fetch_artist_tree,
)
from core.catalog.smart_fields import FIELDS
from core.catalog.smart_rules import RuleSet

# La agrupación de la vista de álbumes (la clave que usan el modelo y las vistas)
ALBUM_GROUPING = "album"

# La biblioteca de la música: sus álbumes y los nombres, como en «Artistas»
_LIBRARY = Library.AUDIO.value

# Lo que vale una tarjeta cuyas canciones no coinciden en un dato («ninguno»)
_MIXED: dict[str, Any] = {"rating": 0, "flag": 0, "color_label": None, "in_quick_selection": 0}


class _Song(NamedTuple):
    """Lo que hace falta de cada canción para agruparla y ordenarla en su álbum."""

    artist: str | None
    album: str | None
    year: int | None
    disc: int | None
    track: int | None


def fetch_album_rows(
    conn: sqlite3.Connection,
    order: GridOrder = ARTIST_ORDER,
    source: GridSource = ALL_ITEMS,
    filters: Sequence[RuleSet] = (),
) -> list[dict[str, Any]]:
    """Una fila por álbum entre lo que mostraría la cuadrícula (ver el docstring del módulo).

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        order: El orden del desplegable (el de las canciones: decide el de los álbumes).
        source: El origen elegido a la izquierda.
        filters: El filtro de la barra de filtros ('GridFilter.rule_sets()').

    Raises:
        TypeError, ValueError: Como 'fetch_grid_rows'.
    """
    rows = fetch_grid_rows(conn, order, source, filters)
    if not rows:
        return []
    songs = _songs(conn, source, filters)
    artist_names, album_names = _library_names(conn)

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        song = songs.get(row["id"])
        if row["media_type"] != MediaType.AUDIO.value or song is None:
            key: tuple[Any, ...] = ("#", row["id"])  # no es una canción: su propia fila
        else:
            key = (_fold(song.artist), _fold(song.album))
        groups.setdefault(key, []).append(row)  # en el orden de su primera canción

    albums = []
    for key, members in groups.items():
        if key[0] == "#":
            albums.append(members[0])
        else:
            albums.append(_album_row(key, members, songs, artist_names, album_names))
    return albums


def _songs(
    conn: sqlite3.Connection, source: GridSource, filters: Sequence[RuleSet]
) -> dict[int, _Song]:
    """El artista del álbum, el álbum, el año, el disco y la pista de cada fila (con las
    mismas expresiones SQL que las reglas de «Artistas»)."""
    where_sql, params = source_condition(source, filters)
    result = conn.execute(
        f"""SELECT m.id, {FIELDS[ARTIST_FIELD].column}, {FIELDS[ALBUM_FIELD].column},
                   substr(m.content_created_at, 1, 4),
                   (SELECT d.disc_number FROM audio_details AS d WHERE d.media_id = m.id),
                   (SELECT d.track_number FROM audio_details AS d WHERE d.media_id = m.id)
              FROM media_items AS m
             WHERE {where_sql}""",  # columnas de una lista cerrada; los valores, parámetros
        params,
    )
    songs = {}
    for media_id, artist, album, year, disc, track in result:
        year_number = int(year) if isinstance(year, str) and year.isdigit() else None
        songs[media_id] = _Song(artist, album, year_number, disc, track)
    return songs


def _library_names(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str]]:
    """Cómo se escriben los artistas y los álbumes: como en «Artistas» (el más escrito de
    la biblioteca). Así el origen de cada álbum es el de su fila de la barra, que se elige
    al entrar en él."""
    artists: dict[str, str] = {}
    albums: dict[str, str] = {}
    for artist in fetch_artist_tree(conn, _LIBRARY):
        if artist.name is not None:
            artists[fold_text(artist.name)] = artist.name
        for album in artist.albums:
            if album.name is not None:
                albums[fold_text(album.name)] = album.name
    return artists, albums


def _album_row(
    key: tuple[str | None, str | None],
    members: list[dict[str, Any]],
    songs: dict[int, _Song],
    artist_names: dict[str, str],
    album_names: dict[str, str],
) -> dict[str, Any]:
    """La fila de un álbum: la de la canción de la carátula, con los datos del grupo."""
    ordered = sorted(members, key=lambda row: _track_order(row, songs[row["id"]]))
    cover = next((row for row in ordered if row.get("thumbnail_status") == 1), ordered[0])
    artist_key, album_key = key
    artist = _name(artist_key, artist_names, [songs[row["id"]].artist for row in ordered])
    album = _name(album_key, album_names, [songs[row["id"]].album for row in ordered])
    years = [songs[row["id"]].year for row in ordered if songs[row["id"]].year is not None]
    durations = [row["duration"] for row in ordered if row.get("duration") is not None]

    album_row = dict(cover)
    album_row.update(
        group_ids=tuple(row["id"] for row in ordered),
        group_count=len(ordered),
        group_source=artist_album_source(_LIBRARY, artist, album),
        album=album,
        artist=artist,
        year_min=min(years) if years else None,
        year_max=max(years) if years else None,
        duration=sum(durations) if durations else None,
        has_location=False,
        track_overview=None,
    )
    for field, mixed in _MIXED.items():
        values = {row.get(field) for row in ordered}
        album_row[field] = values.pop() if len(values) == 1 else mixed
    return album_row


def _track_order(row: dict[str, Any], song: _Song) -> tuple[Any, ...]:
    """El orden de las canciones dentro de su álbum: disco, pista y nombre (lo que falta, al
    final)."""
    return (
        song.disc is None, song.disc or 0, song.track is None, song.track or 0,
        fold_text(row["file_name"]), row["id"],
    )  # fmt: skip


def _fold(value: str | None) -> str | None:
    """La clave de un texto, sin mayúsculas ni acentos (None si está vacío, como «está
    vacío» en las reglas)."""
    return fold_text(value) if value else None


def _name(key: str | None, names: dict[str, str], spellings: list[str | None]) -> str | None:
    """El nombre de un artista o un álbum: el de «Artistas»; si no está (no debería), el más
    escrito entre sus canciones."""
    if key is None:
        return None
    if key in names:
        return names[key]
    counts = Counter(text for text in spellings if text)
    best = max(counts.values())
    return min(text for text, count in counts.items() if count == best)


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.album_rows
    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_orders import GridOrder as Order
    from core.catalog.grid_source import library_source
    from core.catalog.smart_rules import MATCH_ALL, Rule

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('M', '/tmp/m')")

    def song(name: str, artist: str | None, album: str | None, year: int | None, disc: int | None,
             track: int | None, *, album_artist: str | None = None, genre: str = "Rock",
             rating: int = 0, thumbnail: int = 1, duration: float = 200.0) -> int:  # fmt: skip
        media_id = db.execute(
            "INSERT INTO media_items(storage_location_id, relative_path, file_name, title, "
            "file_extension, media_type, mime_type, file_size, file_mtime_ns, creator, "
            "content_created_at, library, rating, thumbnail_status, duration) "
            "VALUES (1, ?, ?, ?, 'mp3', 'audio', 'audio/mpeg', 1, 1, ?, ?, 'audio', ?, ?, ?)",
            (name, name, name, artist, f"{year}-01-01 00:00:00" if year else None, rating,
             thumbnail, duration),
        ).lastrowid  # fmt: skip
        db.execute(
            "INSERT INTO audio_details(media_id, album, album_artist, disc_number, track_number, "
            "genre) VALUES (?, ?, ?, ?, ?, ?)",
            (media_id, album, album_artist, disc, track, genre),
        )
        return media_id

    # Destrangis: la pista 1 sin miniatura (la carátula, de la 2); una escrita en mayúsculas
    d1 = song("z1.mp3", "Estopa", "Destrangis", 2001, None, 1, thumbnail=0, rating=4)
    d2 = song("a2.mp3", "Estopa", "DESTRANGIS", 2001, None, 2, rating=4)
    d3 = song("m3.mp3", "estopa", "Destrangis", 2001, None, 3, rating=4, genre="Rumba")
    g1 = song("b1.mp3", "Estopa", "Estopa Grandes Éxitos", 2003, 2, 1, rating=5)  # disco 2
    g2 = song("c1.mp3", "Estopa", "Estopa Grandes Éxitos", 2003, 1, 1)
    p1 = song("k1.mp3", "Dick Dale", "BSO Pulp Fiction", 1994, None, 1, album_artist="0 Varios")
    p2 = song("k2.mp3", "Kool", "BSO Pulp Fiction", 1974, None, 2, album_artist="0 Varios")
    s1 = song("s1.mp3", "Estopa", None, None, None, None)  # sin álbum: el de Estopa
    n1 = song("n1.mp3", None, None, None, None, None)  # sin nada
    photo = db.execute(
        "INSERT INTO media_items(storage_location_id, relative_path, file_name, title, "
        "media_type, mime_type, file_size, file_mtime_ns) "
        "VALUES (1, 'f.jpg', 'f.jpg', 'f', 'photo', 'image/jpeg', 1, 1)"
    ).lastrowid
    music = library_source(_LIBRARY)

    rows = fetch_album_rows(db, ARTIST_ORDER, music)
    albums = [(r["artist"], r["album"], r["group_count"]) for r in rows]
    assert albums == [
        ("0 Varios", "BSO Pulp Fiction", 2),
        ("Estopa", "Destrangis", 3),
        ("Estopa", "Estopa Grandes Éxitos", 2),
        ("Estopa", None, 1),
        (None, None, 1),
    ], albums
    pulp, destrangis, hits, loose, nothing = rows
    # Las canciones, por disco y pista; la carátula, la primera con miniatura
    assert destrangis["group_ids"] == (d1, d2, d3) and destrangis["id"] == d2
    assert hits["group_ids"] == (g2, g1)  # el disco 1 delante
    assert pulp["group_ids"] == (p1, p2) and (pulp["year_min"], pulp["year_max"]) == (1974, 1994)
    # Los valores comunes; si difieren, «ninguno»
    assert destrangis["rating"] == 4 and hits["rating"] == 0
    assert destrangis["duration"] == 600.0 and destrangis["file_name"] == "a2.mp3"
    # El nombre, como en «Artistas»; y su origen, el de esa fila: cuenta lo mismo
    assert destrangis["album"] == "Destrangis" and loose["group_ids"] == (s1,)
    for row in rows:
        where, params = source_condition(row["group_source"])
        found = {i for (i,) in db.execute(f"SELECT m.id FROM media_items AS m WHERE {where}", params)}
        assert found == set(row["group_ids"]), (row["album"], found)
    assert nothing["artist"] is None and nothing["group_ids"] == (n1,)

    # El orden del desplegable: con «Año» hacia abajo, los álbumes más recientes primero
    newest = [r["album"] for r in fetch_album_rows(db, Order("audio_year", descending=True), music)]
    assert newest[:3] == ["Estopa Grandes Éxitos", "Destrangis", "BSO Pulp Fiction"], newest

    # Con un filtro, solo sus canciones: Destrangis con una (la de rumba)
    rumba = (RuleSet(MATCH_ALL, (Rule("audio_genre", "eq", "rumba"),)),)
    (only,) = fetch_album_rows(db, ARTIST_ORDER, music, rumba)
    assert only["group_ids"] == (d3,) and only["id"] == d3 and only["album"] == "Destrangis"

    # Lo que no es una canción, en su propia fila; sin nada, ninguna fila
    everything = fetch_album_rows(db, ARTIST_ORDER, ALL_ITEMS)
    assert any(r["id"] == photo and "group_ids" not in r for r in everything)
    none = (RuleSet(MATCH_ALL, (Rule("audio_genre", "eq", "jazz"),)),)
    assert fetch_album_rows(db, ARTIST_ORDER, music, none) == []
    print("Autoprueba finalizada correctamente.")
