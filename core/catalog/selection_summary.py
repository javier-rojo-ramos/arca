"""Resumen de una selección de la cuadrícula (o de lo que se está viendo), para el inspector.

El panel derecho (inspector) muestra la sección «Selección» con los datos básicos de lo
seleccionado: nombre o número de archivos, carpeta, tamaño, fecha, biblioteca y estado.
Este módulo calcula ese resumen en la base de datos, sin Qt:

    - 'fetch_selection_summary(conn, ids)': de los elementos seleccionados (uno o varios).
    - 'fetch_source_summary(conn, source, filters)': de un origen entero (sin selección:
      lo que se está viendo, p. ej. una carpeta o una colección), con el filtro de la barra
      de filtros si lo hay. Usa la MISMA condición que la cuadrícula
      ('media_queries.source_condition'), así que cuenta lo mismo que se ve.

Las dos devuelven un 'SelectionSummary'. Como el resto de 'core/catalog', reciben la
conexión como primer parámetro y se lanzan con 'CatalogDatabaseManager.execute_async'.

Cómo se calcula (rápido aunque se seleccionen decenas de miles de archivos):
    - Una consulta AGRUPADA por (tipo de medio, biblioteca) con recuentos, sumas, mínimos y
      máximos; las selecciones grandes se consultan por trozos y se juntan en Python.
    - Carpeta común: la ruta relativa menor y la mayor (por orden alfabético) comparten el
      mismo comienzo que TODAS las demás, así que la carpeta común de esas dos es la de
      todas. No hace falta leer cada ruta.
    - Si es un solo elemento, una consulta más con sus datos propios (nombre, ruta, origen y
      zona horaria de la fecha).

1.2.0 'fetch_source_summary' con el filtro de la barra de filtros ('filters'; paso A.3).
1.1.0 'single_library': la biblioteca común de lo resumido (el inspector decide con ella
      qué secciones aparecen; paso A.2).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.selection_summary
"""

__version__ = "1.2.0"
__all__ = [
    "SelectionItem",
    "SelectionSummary",
    "fetch_selection_summary",
    "fetch_source_summary",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Módulos del proyecto
from core.catalog.grid_source import GridSource
from core.catalog.media_queries import source_condition
from core.catalog.smart_rules import RuleSet

# Tamaño de cada trozo de 'id' en una consulta (por debajo del límite de parámetros de
# SQLite, que en versiones antiguas es 999)
_CHUNK = 500

# SELECT agrupado: lo mismo para una selección que para un origen (cambia el WHERE).
# El orden de las columnas es el de '_Group' (más abajo)
_GROUPED_SQL = """
    SELECT m.media_type, m.library, COUNT(*), COALESCE(SUM(m.file_size), 0),
           MIN(m.content_created_at), MAX(m.content_created_at),
           SUM(CASE WHEN l.is_online = 1 AND m.is_missing = 1 THEN 1 ELSE 0 END),
           SUM(CASE WHEN l.is_online = 0 THEN 1 ELSE 0 END),
           MIN(m.storage_location_id), MAX(m.storage_location_id),
           MIN(m.relative_path), MAX(m.relative_path),
           MIN(m.file_extension), MAX(m.file_extension)
      FROM media_items AS m
      JOIN storage_locations AS l ON l.id = m.storage_location_id
     WHERE {where}
  GROUP BY m.media_type, m.library
"""


@dataclass(frozen=True, slots=True)
class SelectionItem:
    """Datos propios de un único elemento seleccionado.

    Attributes:
        media_id: 'media_items.id'.
        file_name: Nombre con extensión ('IMG_0001.MOV').
        path: Ruta completa del archivo.
        date_precision: 'year', 'month', 'day' o 'second' (None si no hay fecha).
        date_source: De dónde salió la fecha ('exif', 'xmp', 'file_mtime'...).
        timezone_offset: Zona horaria de la fecha ('+02:00'), si se conoce.
    """

    media_id: int
    file_name: str
    path: Path
    date_precision: str | None
    date_source: str | None
    timezone_offset: str | None


@dataclass(frozen=True, slots=True)
class SelectionSummary:
    """Resumen de lo seleccionado (o de lo que se está viendo) para el inspector.

    Attributes:
        scope: 'selection' (elementos seleccionados) o 'source' (sin selección: el origen
            que se está viendo).
        count: Número de elementos.
        total_size: Suma de los tamaños, en bytes.
        date_min: Fecha más antigua ('YYYY-MM-DD HH:MM:SS', hora local), o None.
        date_max: Fecha más reciente, o None.
        missing: Elementos ausentes (en una ubicación conectada).
        offline: Elementos en una ubicación desconectada.
        libraries: Bibliotecas distintas (None = sin clasificar), en orden estable.
        media_types: (tipo de medio, número de elementos), de más a menos.
        extension: Extensión común (minúsculas, sin punto), o None si hay varias.
        folder: Carpeta común a todos (la del archivo si es uno solo), o None si están
            en ubicaciones distintas.
        item: Datos propios si es UN solo elemento; None si son varios o ninguno.
    """

    scope: str
    count: int = 0
    total_size: int = 0
    date_min: str | None = None
    date_max: str | None = None
    missing: int = 0
    offline: int = 0
    libraries: tuple[str | None, ...] = ()
    media_types: tuple[tuple[str, int], ...] = ()
    extension: str | None = None
    folder: Path | None = None
    item: SelectionItem | None = None

    @property
    def is_empty(self) -> bool:
        """True si no hay ningún elemento."""
        return self.count == 0

    @property
    def single_library(self) -> str | None:
        """La biblioteca de TODO lo resumido, o None si hay varias, alguno sin clasificar o
        nada (el inspector muestra las secciones propias de una biblioteca solo entonces)."""
        if len(self.libraries) == 1 and self.libraries[0] is not None:
            return self.libraries[0]
        return None


@dataclass(slots=True)
class _Totals:
    """Acumulador de las filas agrupadas (de uno o varios trozos)."""

    count: int = 0
    total_size: int = 0
    date_min: str | None = None
    date_max: str | None = None
    missing: int = 0
    offline: int = 0
    location_min: int | None = None
    location_max: int | None = None
    path_min: str | None = None
    path_max: str | None = None
    extension_min: str | None = None
    extension_max: str | None = None
    # Bibliotecas vistas (un dict como conjunto que conserva el orden) y elementos por tipo
    libraries: dict[str | None, None] = field(default_factory=dict)
    media_types: dict[str, int] = field(default_factory=dict)

    def add(self, row: Sequence[Any]) -> None:
        """Suma una fila de '_GROUPED_SQL'."""
        (media_type, library, count, size, d_min, d_max, missing, offline,
         loc_min, loc_max, p_min, p_max, e_min, e_max) = row  # fmt: skip
        self.count += count
        self.total_size += size
        self.missing += missing or 0
        self.offline += offline or 0
        self.media_types[media_type] = self.media_types.get(media_type, 0) + count
        self.libraries[library] = None
        self.date_min = _min(self.date_min, d_min)
        self.date_max = _max(self.date_max, d_max)
        self.location_min = _min(self.location_min, loc_min)
        self.location_max = _max(self.location_max, loc_max)
        self.path_min = _min(self.path_min, p_min)
        self.path_max = _max(self.path_max, p_max)
        self.extension_min = _min(self.extension_min, e_min)
        self.extension_max = _max(self.extension_max, e_max)


def _min(a: Any, b: Any) -> Any:
    """Mínimo que ignora los None."""
    return b if a is None else a if b is None else min(a, b)


def _max(a: Any, b: Any) -> Any:
    """Máximo que ignora los None."""
    return b if a is None else a if b is None else max(a, b)


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------


def fetch_selection_summary(
    conn: sqlite3.Connection, media_ids: Iterable[int]
) -> SelectionSummary:
    """Resumen de los elementos seleccionados.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        media_ids: 'id' de los elementos (los repetidos se cuentan una vez; los que ya
            no existan en el catálogo se ignoran).
    """
    ids = list(dict.fromkeys(media_ids))
    totals = _Totals()
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        sql = _GROUPED_SQL.format(where=f"m.id IN ({marks})")
        for row in conn.execute(sql, chunk):
            totals.add(row)
    item = _fetch_item(conn, ids[0]) if totals.count == 1 else None
    return _build("selection", conn, totals, item)


def fetch_source_summary(
    conn: sqlite3.Connection, source: GridSource, filters: Sequence[RuleSet] = ()
) -> SelectionSummary:
    """Resumen de un origen entero (lo que muestra la cuadrícula cuando no hay selección).

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        source: El origen que se ve.
        filters: Filtro de la barra de filtros ('GridFilter.rule_sets()'; vacío = sin
            filtro): se resume solo lo filtrado, lo mismo que muestra la cuadrícula.

    Raises:
        ValueError: Si el origen no se conoce o una regla no es válida (como en la
            cuadrícula).
    """
    where_sql, where_params = source_condition(source, filters)
    totals = _Totals()
    # 'where_sql' sale de 'source_condition' (listas cerradas); los valores van en los
    # parámetros
    for row in conn.execute(_GROUPED_SQL.format(where=where_sql), where_params):
        totals.add(row)
    item = None
    if totals.count == 1:
        row = conn.execute(
            f"SELECT m.id FROM media_items AS m WHERE {where_sql}",
            where_params,
        ).fetchone()
        item = _fetch_item(conn, row[0]) if row else None
    return _build("source", conn, totals, item)


# -----------------------------------------------------------------------------
# Interno
# -----------------------------------------------------------------------------


def _fetch_item(conn: sqlite3.Connection, media_id: int) -> SelectionItem | None:
    """Datos propios de un elemento (None si ya no está en el catálogo)."""
    row = conn.execute(
        """SELECT m.id, m.file_name, l.absolute_path, m.relative_path,
                  m.content_date_precision, m.content_date_source, m.timezone_offset
             FROM media_items AS m
             JOIN storage_locations AS l ON l.id = m.storage_location_id
            WHERE m.id = ?""",
        (media_id,),
    ).fetchone()
    if row is None:
        return None
    media_id, file_name, root, relative, precision, source, offset = row
    return SelectionItem(
        media_id=media_id,
        file_name=file_name,
        path=Path(root) / relative,
        date_precision=precision,
        date_source=source,
        timezone_offset=offset,
    )


def _common_folder(path_min: str, path_max: str) -> str:
    """Carpeta (relativa) común a dos rutas relativas de archivo ('' = la raíz).

    Se toma el comienzo común de las dos y se corta en la última '/': así 'a/b/x.jpg' y
    'a/bc/y.jpg' dan 'a' (y no 'a/b').
    """
    length = 0
    for char_a, char_b in zip(path_min, path_max, strict=False):
        if char_a != char_b:
            break
        length += 1
    common = path_min[:length]
    if path_min == path_max:
        common = path_min  # un solo archivo: su carpeta es la de su ruta
    return common.rpartition("/")[0]


def _build(
    scope: str, conn: sqlite3.Connection, totals: _Totals, item: SelectionItem | None
) -> SelectionSummary:
    """Convierte el acumulador en el resumen (y busca la carpeta común)."""
    if totals.count == 0:
        return SelectionSummary(scope=scope)

    folder: Path | None = None
    same_location = totals.location_min == totals.location_max
    if same_location and totals.path_min is not None and totals.path_max is not None:
        row = conn.execute(
            "SELECT absolute_path FROM storage_locations WHERE id = ?", (totals.location_min,)
        ).fetchone()
        if row is not None:
            relative = _common_folder(totals.path_min, totals.path_max)
            folder = Path(row[0]) / relative if relative else Path(row[0])

    # Bibliotecas: las conocidas en orden alfabético y "sin clasificar" (None) al final
    libraries = sorted(lib for lib in totals.libraries if lib is not None)
    if None in totals.libraries:
        libraries.append(None)

    extension = totals.extension_min if totals.extension_min == totals.extension_max else None
    return SelectionSummary(
        scope=scope,
        count=totals.count,
        total_size=totals.total_size,
        date_min=totals.date_min,
        date_max=totals.date_max,
        missing=totals.missing,
        offline=totals.offline,
        libraries=tuple(libraries),
        media_types=tuple(sorted(totals.media_types.items(), key=lambda kv: (-kv[1], kv[0]))),
        extension=extension,
        folder=folder,
        item=item,
    )


if __name__ == "__main__":
    # Autoprueba con un catálogo en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.selection_summary
    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_source import ALL_ITEMS, folder_source

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations (id, name, absolute_path) VALUES (1, 'A', '/fotos')")
    db.execute(
        "INSERT INTO storage_locations (id, name, absolute_path, is_online) "
        "VALUES (2, 'B', '/disco', 0)"
    )

    def add(media_id: int, location: int, path: str, media_type: str, size: int,
            date: str | None, library: str | None, missing: int = 0) -> None:  # fmt: skip
        """Inserta un elemento con lo justo para el resumen."""
        name = path.rpartition("/")[2]
        db.execute(
            """INSERT INTO media_items (id, storage_location_id, relative_path, file_name,
                   file_extension, media_type, mime_type, file_size, file_mtime_ns, title,
                   content_created_at, content_date_precision, content_date_source,
                   timezone_offset, library, is_missing)
               VALUES (?, ?, ?, ?, ?, ?, 'x/x', ?, 0, ?, ?, ?, ?, ?, ?, ?)""",
            (media_id, location, path, name, name.rpartition(".")[2].lower(), media_type,
             size, name, date, "second" if date else None, "exif" if date else None,
             "+02:00" if date else None, library, missing),
        )  # fmt: skip

    add(1, 1, "2024/viaje/a.jpg", "photo", 1000, "2024-06-01 12:00:00", "image")
    add(2, 1, "2024/viaje/b.mov", "video", 5000, "2024-06-02 09:30:00", "image")
    add(3, 1, "2024/vb/c.jpg", "photo", 2000, "2023-05-12 08:00:00", "image", missing=1)
    add(4, 1, "2024/otro.mkv", "video", 9000, None, None)
    add(5, 2, "musica/d.mp3", "audio", 300, None, "audio")

    # 1. Un solo elemento: sus datos propios y su carpeta
    one = fetch_selection_summary(db, [2])
    assert one.count == 1 and one.item is not None and one.item.file_name == "b.mov"
    assert one.item.path == Path("/fotos/2024/viaje/b.mov") and one.item.timezone_offset == "+02:00"
    assert one.folder == Path("/fotos/2024/viaje") and one.extension == "mov"
    assert one.libraries == ("image",) and one.missing == 0 and one.offline == 0

    # 2. Varios de la misma ubicación: carpeta común por la ruta (no 'viaje' ni 'v')
    several = fetch_selection_summary(db, [1, 2, 3, 3])
    assert several.count == 3 and several.item is None and several.total_size == 8000
    assert several.folder == Path("/fotos/2024"), several.folder
    assert (several.date_min, several.date_max) == ("2023-05-12 08:00:00", "2024-06-02 09:30:00")
    assert several.missing == 1 and several.extension is None
    assert several.media_types == (("photo", 2), ("video", 1))

    # 3. Dos ubicaciones: sin carpeta común; sin clasificar al final; desconectados
    mixed = fetch_selection_summary(db, [4, 5, 1])
    assert mixed.folder is None and mixed.offline == 1 and mixed.missing == 0
    assert mixed.libraries == ("audio", "image", None), mixed.libraries

    # 4. Sin fechas: None; ids desconocidos se ignoran; vacío
    assert fetch_selection_summary(db, [5]).date_min is None
    assert fetch_selection_summary(db, [999]).is_empty
    assert fetch_selection_summary(db, []).is_empty

    # 5. Selección grande (varios trozos): mismos totales que de una vez
    many = fetch_selection_summary(db, [1, 2, 3, 4, 5] * 300 + list(range(1000, 1700)))
    assert many.count == 5 and many.total_size == 17300

    # 6. Origen entero: lo mismo que contaría la cuadrícula
    everything = fetch_source_summary(db, ALL_ITEMS)
    assert everything.scope == "source" and everything.count == 5
    trip = fetch_source_summary(db, folder_source(1, "2024/viaje", include_subfolders=False))
    assert trip.count == 2 and trip.folder == Path("/fotos/2024/viaje")
    single = fetch_source_summary(db, folder_source(2, "musica", include_subfolders=True))
    assert single.count == 1 and single.item is not None and single.item.file_name == "d.mp3"
    # Con el filtro de la barra: solo lo filtrado (aquí, los nombres que empiezan por «b»)
    from core.catalog.smart_rules import Rule

    only_b = (RuleSet(rules=(Rule("file_name", "starts_with", "b"),)),)
    filtered = fetch_source_summary(db, ALL_ITEMS, only_b)
    assert filtered.count == 1 and filtered.item is not None and filtered.item.file_name == "b.mov"

    # 7. Carpeta común: casos límite
    assert _common_folder("a/b/x.jpg", "a/bc/y.jpg") == "a"
    assert _common_folder("x.jpg", "y.jpg") == ""
    assert _common_folder("a/x.jpg", "a/x.jpg") == "a"
    # Biblioteca común: una sola; varias, sin clasificar o nada -> None
    assert SelectionSummary("selection", count=2, libraries=("image",)).single_library == "image"
    assert SelectionSummary("selection", count=2, libraries=("image", "tracks")).single_library is None
    assert SelectionSummary("selection", count=1, libraries=(None,)).single_library is None
    assert SelectionSummary("selection").single_library is None
    db.close()
    print("Autoprueba finalizada correctamente.")
