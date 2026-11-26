"""Secciones «Artistas» y «Años» de la barra de Música: sus árboles y el origen de cada fila.

Este módulo NO depende de Qt. Las funciones que leen reciben la conexión SQLite como primer
parámetro (para 'CatalogDatabaseManager.execute_async') y solo leen.

    «Artistas»: artista del álbum ▸ álbumes        «Años»: año ▸ artista y álbum
        0 Varios                     4                 2003                     13
          1994 · BSO Pulp Fiction    2                   Estopa - Estopa Gran... 13
          1999 · BSO The Matrix      2                 2001                     13
        Estopa                      26                   Estopa - Destrangis    13
          2001 · Destrangis         13                 Sin año                   1
          2003 · Estopa Grandes...  13                   Sin álbum               1

Reglas (acordadas con el autor el 26/11/2026; docs/MOD_MUSICA.md §7.2):
    - Se agrupa por el «Artista del álbum» y, si la canción no lo tiene, por su artista (el
      campo 'audio_album_artist' de 'smart_fields'): un recopilatorio sin artista del
      álbum se reparte entre sus artistas. Las canciones sin ninguno de los dos, en
      «Sin artista» (artista None), al final.
    - Los artistas, por orden alfabético; sus álbumes, por año (el más antiguo de sus
      canciones; los que no tienen año, al final) y después por nombre. Un álbum con
      canciones de varios años lleva los dos extremos ('year_min', 'year_max'; la interfaz
      pone «1974 – 2011 · Grandes Éxitos»).
    - Los años, del más reciente al más antiguo, con «Sin año» (None) al final. Dentro, un
      álbum es un artista y su álbum, como en «Artistas» ('artist'; la interfaz pone «Estopa
      - Destrangis»: pedido por el autor el 26/11/2026), por artista y después por álbum;
      los que no tienen artista, al final del año. Un recopilatorio sin artista del álbum se
      reparte entre sus artistas, como en «Artistas».
    - Las canciones sin álbum, en «Sin álbum» (álbum None), al final de su artista o año.
    - Los textos se comparan sin mayúsculas ni acentos ('fold_text', como las reglas):
      «Estopa» y «ESTOPA» son la misma fila, con el nombre escrito como en la mayoría.

Cada fila lleva su origen de la cuadrícula: una colección inteligente fija (la biblioteca y
las reglas del artista, del año y del álbum), como las filas de «Fechas»
('timeline.date_source'). Así, cada fila cuenta EXACTAMENTE lo que muestra la cuadrícula al
elegirla (lo comprueba la autoprueba), y los árboles se leen con las mismas expresiones SQL
que usan las reglas.

Uso:
    artists = fetch_artist_tree(conn, "audio")    # en segundo plano
    artists[0].name, artists[0].count, artists[0].albums[0].year_min
    artist_source("audio", "Estopa")               # todas sus canciones
    artist_album_source("audio", "Estopa", "Destrangis")
    years = fetch_year_tree(conn, "audio")
    year_source("audio", "2001"); year_album_source("audio", "2001", "Estopa", "Destrangis")
    is_artist_source(source, "audio"); is_year_source(source, "audio")   # al recuperar
                                                                          # la fila elegida

Los textos que ve el usuario («Sin artista», «Sin álbum», «Sin año», «2001 · Destrangis»)
no están aquí: los pone la interfaz.

1.1.0 En «Años», cada álbum con su artista ('AlbumNode.artist'; fuera 'several_artists') y
      agrupado por artista y álbum, como en «Artistas» (antes, solo por el nombre del
      álbum): 'year_album_source' lleva el artista (pedido por el autor al verlo).
1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 4.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.music_browse
"""

__version__ = "1.1.0"
__all__ = [
    "AlbumNode",
    "ArtistNode",
    "YearNode",
    "artist_album_source",
    "artist_source",
    "fetch_artist_tree",
    "fetch_year_tree",
    "is_artist_source",
    "is_year_source",
    "year_album_source",
    "year_source",
]

# Librerías estándar
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.catalog.grid_source import GridSource, SourceKind, library_source, smart_source
from core.catalog.media_queries import source_condition
from core.catalog.media_types import MediaType
from core.catalog.smart_fields import FIELDS
from core.catalog.smart_rules import MATCH_ALL, Rule
from core.catalog.timeline import DATE_FIELD, NO_DATE, date_source

# Los campos de las reglas (los de 'smart_fields': sus expresiones SQL leen los árboles)
ARTIST_FIELD = "audio_album_artist"
ALBUM_FIELD = "audio_album"


@dataclass(frozen=True, slots=True)
class AlbumNode:
    """Un álbum de un artista o de un año.

    Attributes:
        name: Su nombre; None = «Sin álbum».
        count: Canciones.
        year_min: El año más antiguo de sus canciones (None si ninguna lo tiene).
        year_max: El más reciente (igual a 'year_min' si son todas del mismo).
        artist: En «Años», su artista (el del álbum o, sin él, el de las canciones); None =
            sin artista. En «Artistas», None (el artista es la fila de arriba).
    """

    name: str | None
    count: int
    year_min: int | None = None
    year_max: int | None = None
    artist: str | None = None


@dataclass(frozen=True, slots=True)
class ArtistNode:
    """Un artista de «Artistas», con sus álbumes.

    Attributes:
        name: Su nombre; None = «Sin artista».
        count: Canciones.
        albums: Sus álbumes, en el orden de la sección.
    """

    name: str | None
    count: int
    albums: tuple[AlbumNode, ...] = ()


@dataclass(frozen=True, slots=True)
class YearNode:
    """Un año de «Años», con sus álbumes.

    Attributes:
        year: 'AAAA'; None = «Sin año».
        count: Canciones.
        albums: Sus álbumes, por artista y después por nombre.
    """

    year: str | None
    count: int
    albums: tuple[AlbumNode, ...] = ()


# -----------------------------------------------------------------------------
# Orígenes de las filas
# -----------------------------------------------------------------------------


def _text_rule(field_key: str, value: str | None) -> Rule:
    """La regla de un texto: «es» ese valor o, sin él (None), «está vacío»."""
    if value is None:
        return Rule(field_key, "is_not_set")
    return Rule(field_key, "eq", value)


def artist_source(library: str, artist: str | None) -> GridSource:
    """Las canciones de un artista (o, con None, las de «Sin artista»)."""
    return smart_source(Rule("library", "eq", library), _text_rule(ARTIST_FIELD, artist))


def artist_album_source(library: str, artist: str | None, album: str | None) -> GridSource:
    """Las canciones de un álbum de un artista (álbum None = «Sin álbum»)."""
    return smart_source(
        Rule("library", "eq", library),
        _text_rule(ARTIST_FIELD, artist),
        _text_rule(ALBUM_FIELD, album),
    )


def year_source(library: str, year: str | None) -> GridSource:
    """Las canciones de un año (None = «Sin año»): la misma fila de un año de «Fechas»."""
    return date_source(library, NO_DATE if year is None else year)


def year_album_source(
    library: str, year: str | None, artist: str | None, album: str | None
) -> GridSource:
    """Las canciones de un álbum de un artista en un año (álbum None = «Sin álbum»)."""
    library_rule, date_rule = year_source(library, year).rules.rules
    return smart_source(
        library_rule,
        date_rule,
        _text_rule(ARTIST_FIELD, artist),
        _text_rule(ALBUM_FIELD, album),
    )


def _rule_fields(source: GridSource, library: str) -> tuple[str, ...] | None:
    """Los campos de las reglas de un origen de la barra, detrás de la de la biblioteca
    (None si no es una colección fija de esa biblioteca con solo reglas sueltas)."""
    rules = source.rules
    if source.kind != SourceKind.SMART or source.collection_id is not None or rules is None:
        return None
    if rules.match != MATCH_ALL or not rules.rules:
        return None
    if rules.rules[0] != Rule("library", "eq", library):
        return None
    if not all(isinstance(rule, Rule) for rule in rules.rules[1:]):
        return None
    return tuple(rule.field for rule in rules.rules[1:])


def is_artist_source(source: GridSource, library: str) -> bool:
    """Si un origen es el de una fila de «Artistas» de esa biblioteca."""
    return _rule_fields(source, library) in ((ARTIST_FIELD,), (ARTIST_FIELD, ALBUM_FIELD))


def is_year_source(source: GridSource, library: str) -> bool:
    """Si un origen es el de una fila de «Años» de esa biblioteca."""
    return _rule_fields(source, library) in (
        (DATE_FIELD,),
        (DATE_FIELD, ARTIST_FIELD, ALBUM_FIELD),
    )


# -----------------------------------------------------------------------------
# Árboles
# -----------------------------------------------------------------------------


class _Names:
    """Los valores de un texto agrupados sin mayúsculas ni acentos: la clave de cada grupo
    y el nombre que se enseña (el más escrito; si empatan, el primero por orden)."""

    def __init__(self) -> None:
        self._spellings: dict[str, Counter[str]] = defaultdict(Counter)

    def key(self, value: str | None) -> str | None:
        """La clave de un valor (None si está vacío: lo mismo que «está vacío»)."""
        if value is None or value == "":
            return None
        key = fold_text(value)
        self._spellings[key][value] += 1
        return key

    def name(self, key: str | None) -> str | None:
        if key is None:
            return None
        spellings = self._spellings[key]
        best = max(spellings.values())
        return min(text for text, count in spellings.items() if count == best)


def _songs(conn: sqlite3.Connection, library: str) -> list[tuple[str | None, str | None, int | None]]:
    """(artista del álbum, álbum, año) de cada canción de la biblioteca, con las mismas
    expresiones SQL que las reglas de sus filas."""
    where, params = source_condition(library_source(library))
    rows = conn.execute(
        f"""SELECT {FIELDS[ARTIST_FIELD].column}, {FIELDS[ALBUM_FIELD].column},
                   substr(m.content_created_at, 1, 4)
              FROM media_items AS m
             WHERE ({where}) AND m.media_type = ?""",  # columnas de una lista cerrada
        (*params, MediaType.AUDIO.value),
    )
    songs = []
    for artist, album, year in rows:
        year_number = int(year) if isinstance(year, str) and year.isdigit() else None
        songs.append((artist, album, year_number))
    return songs


def _album_sort(albums: list[AlbumNode], *, by_year: bool) -> tuple[AlbumNode, ...]:
    """Los álbumes en su orden: en «Artistas» ('by_year'), por año y nombre, con «Sin
    álbum» al final; en «Años», por artista (sin artista, al final) y nombre, con el «Sin
    álbum» de cada artista detrás de sus álbumes."""

    def sort_key(album: AlbumNode) -> tuple:
        missing = album.name is None
        name = fold_text(album.name) if album.name is not None else ""
        if by_year:
            return (missing, album.year_min is None, album.year_min or 0, name)
        artist = fold_text(album.artist) if album.artist is not None else ""
        return (album.artist is None, artist, missing, name)

    return tuple(sorted(albums, key=sort_key))


def fetch_artist_tree(conn: sqlite3.Connection, library: str) -> tuple[ArtistNode, ...]:
    """«Artistas»: los artistas con sus álbumes (ver el docstring del módulo)."""
    artists, albums = _Names(), _Names()
    counts: Counter[str | None] = Counter()
    album_years: dict[tuple[str | None, str | None], list[int]] = defaultdict(list)
    album_counts: Counter[tuple[str | None, str | None]] = Counter()
    for artist, album, year in _songs(conn, library):
        artist_key, album_key = artists.key(artist), albums.key(album)
        counts[artist_key] += 1
        album_counts[artist_key, album_key] += 1
        if year is not None:
            album_years[artist_key, album_key].append(year)

    nodes = []
    for artist_key, count in counts.items():
        artist_albums = []
        for (owner, album_key), album_count in album_counts.items():
            if owner != artist_key:
                continue
            years = album_years.get((owner, album_key), [])
            artist_albums.append(AlbumNode(
                albums.name(album_key), album_count,
                min(years) if years else None, max(years) if years else None,
            ))  # fmt: skip
        nodes.append(ArtistNode(
            artists.name(artist_key), count, _album_sort(artist_albums, by_year=True)
        ))  # fmt: skip
    return tuple(sorted(nodes, key=lambda node: (node.name is None, fold_text(node.name) or "")))


def fetch_year_tree(conn: sqlite3.Connection, library: str) -> tuple[YearNode, ...]:
    """«Años»: los años con sus álbumes (ver el docstring del módulo)."""
    artists, albums = _Names(), _Names()
    counts: Counter[int | None] = Counter()
    # (año, artista, álbum) -> canciones: cada álbum, con su artista
    album_counts: Counter[tuple[int | None, str | None, str | None]] = Counter()
    for artist, album, year in _songs(conn, library):
        counts[year] += 1
        album_counts[year, artists.key(artist), albums.key(album)] += 1

    nodes = []
    for year, count in counts.items():
        year_albums = []
        for (owner, artist_key, album_key), album_count in album_counts.items():
            if owner != year:
                continue
            year_albums.append(AlbumNode(
                albums.name(album_key), album_count, year, year, artist=artists.name(artist_key)
            ))  # fmt: skip
        nodes.append(YearNode(
            None if year is None else f"{year:04d}", count,
            _album_sort(year_albums, by_year=False),
        ))  # fmt: skip
    return tuple(sorted(nodes, key=lambda node: (node.year is None, -(int(node.year or 0)))))


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.music_browse
    import json
    from typing import Any

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_source import source_from_dict, source_to_dict

    db = sqlite3.connect(":memory:")
    configure_connection(db)  # 'arca_fold', que usan las reglas de texto
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('M', '/m')")
    next_id = iter(range(1, 1000))

    def song(artist: str | None, album: str | None, year: int | None,
             album_artist: str | None = None, library: str = "audio",
             media_type: str = "audio") -> None:  # fmt: skip
        """Una canción (o lo que se diga) con su fila de 'audio_details'."""
        media_id = next(next_id)
        created = f"{year}-01-01 00:00:00" if year else None
        columns: dict[str, Any] = {
            "id": media_id, "storage_location_id": 1, "relative_path": f"s{media_id}",
            "file_name": f"s{media_id}.mp3", "media_type": media_type, "mime_type": "x/y",
            "file_size": 1, "file_mtime_ns": 0, "title": f"s{media_id}", "library": library,
            "creator": artist, "content_created_at": created,
            "content_date_precision": "year" if year else None,
        }  # fmt: skip
        db.execute(
            f"INSERT INTO media_items({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            tuple(columns.values()),
        )
        if media_type == "audio":
            db.execute(
                "INSERT INTO audio_details(media_id, album, album_artist) VALUES (?, ?, ?)",
                (media_id, album, album_artist),
            )

    for _ in range(2):
        song("Estopa", "Destrangis", 2001)
    song("ESTOPA", "Destrangis", 2001)  # otra forma de escribirlo: la misma fila
    song("Estopa", "Grandes Éxitos", 1999)
    song("Estopa", "grandes exitos", 2003)  # sin mayúsculas ni acentos: el mismo álbum
    song("Estopa", None, 2003)  # sin álbum
    # Recopilatorio con artista del álbum: bajo «0 Varios», aunque sean de otros artistas
    song("Dick Dale", "BSO Pulp Fiction", 1994, album_artist="0 Varios")
    song("Kool & The Gang", "BSO Pulp Fiction", 1994, album_artist="0 Varios")
    # Recopilatorio SIN artista del álbum: se reparte entre sus artistas
    song("Ana", "Mezclas", 2010)
    song("Bea", "Mezclas", 2010)
    song("Álvaro", "Raro", None)  # sin año (y con acento: se ordena como «alvaro»)
    song(None, None, None)  # sin artista, sin álbum y sin año
    song("", "Vacío", 2010, album_artist="")  # textos vacíos: «sin artista»
    song("Estopa", "Destrangis", 2001, library="image")  # de otra biblioteca: no cuenta
    # (La biblioteca Música solo tiene canciones: core/catalog/libraries.py)

    # --- «Artistas»: el árbol
    tree = fetch_artist_tree(db, "audio")
    assert [(a.name, a.count) for a in tree] == [
        ("0 Varios", 2), ("Álvaro", 1), ("Ana", 1), ("Bea", 1), ("Estopa", 6), (None, 2),
    ], [(a.name, a.count) for a in tree]
    estopa = tree[4]
    assert [(b.name, b.count, b.year_min, b.year_max) for b in estopa.albums] == [
        ("Grandes Éxitos", 2, 1999, 2003),  # el más antiguo primero; con los dos extremos
        ("Destrangis", 3, 2001, 2001),
        (None, 1, 2003, 2003),  # «Sin álbum», al final
    ], estopa.albums
    assert tree[0].albums == (AlbumNode("BSO Pulp Fiction", 2, 1994, 1994),)
    assert tree[1].albums == (AlbumNode("Raro", 1, None, None),)
    assert [b.name for b in tree[5].albums] == ["Vacío", None]

    # --- «Años»: el árbol
    years = fetch_year_tree(db, "audio")
    assert [(y.year, y.count) for y in years] == [
        ("2010", 3), ("2003", 2), ("2001", 3), ("1999", 1), ("1994", 2), (None, 2),
    ], [(y.year, y.count) for y in years]
    mix = years[0].albums
    assert [(b.artist, b.name, b.count) for b in mix] == [
        ("Ana", "Mezclas", 1), ("Bea", "Mezclas", 1),  # sin artista del álbum: repartido
        (None, "Vacío", 1),  # sin artista, al final del año
    ], mix
    # El nombre, el más escrito (aquí empatan: el primero por orden)
    assert [(b.name, b.artist) for b in years[1].albums] == [("Grandes Éxitos", "Estopa"), (None, "Estopa")]
    # Un recopilatorio con artista del álbum, en una sola fila
    assert [(b.name, b.artist, b.count) for b in years[4].albums] == [
        ("BSO Pulp Fiction", "0 Varios", 2),
    ]
    assert [(b.name, b.artist) for b in years[5].albums] == [("Raro", "Álvaro"), (None, None)]

    # --- Lo importante: elegir una fila muestra EXACTAMENTE las canciones que cuenta
    def found(source: GridSource) -> int:
        where, params = source_condition(source)
        return db.execute(f"SELECT COUNT(*) FROM media_items AS m WHERE {where}", params).fetchone()[0]

    for artist in tree:
        assert found(artist_source("audio", artist.name)) == artist.count, artist.name
        for album in artist.albums:
            source = artist_album_source("audio", artist.name, album.name)
            assert found(source) == album.count, (artist.name, album.name)
    for year in years:
        assert found(year_source("audio", year.year)) == year.count, year.year
        for album in year.albums:
            source = year_album_source("audio", year.year, album.artist, album.name)
            assert found(source) == album.count, (year.year, album.artist, album.name)

    # --- Los orígenes se guardan en JSON y se reconocen al recuperarlos. Una fila de «Años»
    # de antes del 26/11/2026 (año y álbum, sin artista) ya no es de la sección: al abrir
    # el catálogo se vuelve a «Toda la música»
    old_year_album = smart_source(
        *year_source("audio", "2001").rules.rules, Rule(ALBUM_FIELD, "eq", "Destrangis")
    )
    samples = (
        (artist_source("audio", "Estopa"), True, False),
        (artist_source("audio", None), True, False),
        (artist_album_source("audio", "Estopa", None), True, False),
        (year_source("audio", "2001"), False, True),
        (year_source("audio", None), False, True),
        (year_album_source("audio", "2001", "Estopa", "Destrangis"), False, True),
        (old_year_album, False, False),
        (library_source("audio"), False, False),
    )
    for source, is_artist, is_year in samples:
        restored = source_from_dict(json.loads(json.dumps(source_to_dict(source))))
        assert restored == source, source
        assert is_artist_source(restored, "audio") is is_artist, source
        assert is_year_source(restored, "audio") is is_year, source
        assert not is_artist_source(restored, "video") and not is_year_source(restored, "video")

    # --- Una biblioteca sin canciones: sin filas
    assert fetch_artist_tree(db, "video") == () and fetch_year_tree(db, "video") == ()
    db.close()
    print("Autoprueba finalizada correctamente.")
