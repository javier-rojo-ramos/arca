"""Valores y recuentos de una columna de «Metadatos» de la barra de filtros.

Este módulo NO depende de Qt. La función recibe la conexión SQLite como primer parámetro,
así que se puede enviar tal cual a 'CatalogDatabaseManager.execute_async'.

Cada columna de «Metadatos» (como el explorador de metadatos de Lightroom) lista los
valores de un campo ('smart_fields', los de 'browse=True') entre los archivos que le
llegan y, con cada uno, cuántos archivos lo tienen. Le llegan el origen elegido a la
izquierda, «Texto», «Atributos» y lo elegido en las columnas de su izquierda: es la
CASCADA, y esos filtros los da 'GridFilter.metadata_column_filters(columna)'.

Uso:
    result = fetch_metadata_values(conn, source, "city",
                                   grid_filter.metadata_column_filters(2), chosen)
    result.total        # archivos que llegan a la columna (el número de la fila «Todo»)
    result.value_count  # valores distintos (el «8» de «Todo (8)»)
    result.values       # MetadataValue(valor, recuento, hijos), en el orden de la lista

Cada valor es el que entiende 'grid_filter.metadata_rule' (texto tal cual, número, 1 / 0
en sí / no, 'AAAA' > 'AAAA-MM' > 'AAAA-MM-DD' en las fechas; None = «Desconocido»). Así,
elegir una fila filtra exactamente los archivos que cuenta (lo comprueba la autoprueba).

Reglas:
    - Textos y palabras clave se agrupan sin mayúsculas ni acentos, como la regla «es»:
      «Huesca» y «huesca» son una sola fila (con la primera forma en orden alfabético).
    - Palabra clave: cada palabra asignada, sin contar las hijas; un archivo con varias
      cuenta en cada una.
    - Campos de un tipo de medio (Imagen, Tracks GPS): solo cuentan los archivos de ese
      tipo; los demás están en «Todo», pero en ninguna fila.
    - «Desconocido» (None), al final y solo si el campo admite «está vacío»: no en la
      fecha de importación, la marca, la valoración, el tipo, la orientación ni en sí / no
      (lo que no tiene dato cuenta como «no», igual que la regla).
    - Lo elegido que ya no aparece sigue en la lista, con 0: no se pierde y se ve por qué
      la cuadrícula se queda vacía.
    - Orden: textos alfabético (sin mayúsculas ni acentos); números de menor a mayor;
      listas en el orden de sus opciones (marcas y colores como en «Atributos»);
      valoración de 1 a 5 estrellas y después «sin valoración»; sí antes que no; fechas en
      árbol, los años del más reciente al más antiguo y, dentro, meses y días en el orden
      del calendario.
    - Un valor que no se podría elegir (p. ej. un color que no está en la lista) no sale.

Los textos que ve el usuario («Todo (8)», «Desconocido», «Junio»...) no están aquí: los
pone la interfaz.

1.0.0 Primera versión (paso A.3, «Metadatos», subpaso 1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.metadata_values
"""

__version__ = "1.0.0"
__all__ = ["MetadataValue", "MetadataValues", "fetch_metadata_values"]

# Librerías estándar
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

# Módulos del proyecto
from core.catalog.catalog_schema import FOLD_SQL_FUNCTION, fold_text
from core.catalog.grid_filter import METADATA_UNKNOWN, metadata_rule
from core.catalog.grid_source import ALL_ITEMS, GridSource
from core.catalog.media_queries import source_condition
from core.catalog.smart_fields import (
    FIELDS,
    KIND_BOOL,
    KIND_DATE,
    KIND_ENUM,
    KIND_KEYWORD,
    KIND_NUMBER,
    KIND_RATING,
    KIND_TEXT,
    SmartField,
)
from core.catalog.smart_rules import RuleSet


@dataclass(frozen=True, slots=True)
class MetadataValue:
    """Una fila de una columna de «Metadatos».

    Attributes:
        value: El valor (el que se guarda en 'MetadataColumn.values'; None = «Desconocido»).
        count: Archivos que lo tienen (0 si estaba elegido y ya no aparece).
        children: En las fechas, los meses de un año o los días de un mes.
    """

    value: Any
    count: int
    children: tuple["MetadataValue", ...] = ()


@dataclass(frozen=True, slots=True)
class MetadataValues:
    """El contenido de una columna de «Metadatos».

    Attributes:
        field: Clave del campo.
        total: Archivos que llegan a la columna (el número de la fila «Todo»).
        values: Sus filas, en orden («Desconocido», al final).
    """

    field: str
    total: int
    values: tuple[MetadataValue, ...]

    @property
    def value_count(self) -> int:
        """Valores distintos con algún archivo, sin «Desconocido» (el «8» de «Todo (8)»)."""
        return sum(1 for v in self.values if v.value is not METADATA_UNKNOWN and v.count)


# Una fila contada: (clave para agrupar y comparar, valor, recuento)
# (En el SQL de este módulo solo se ponen columnas de 'smart_fields' y la condición de
# 'source_condition': listas cerradas. Los valores van siempre como parámetros.)
_Counted = tuple[Any, Any, int]


def fetch_metadata_values(
    conn: sqlite3.Connection,
    source: GridSource = ALL_ITEMS,
    field_key: str = "city",
    filters: Sequence[RuleSet] = (),
    chosen: Iterable[Any] = (),
) -> MetadataValues:
    """Valores de un campo, con sus recuentos, entre los archivos de un origen y un filtro.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        source: El origen elegido a la izquierda (el mismo que la cuadrícula).
        field_key: Campo de la columna (de 'smart_fields.FIELDS', con 'browse=True').
        filters: Lo que filtra antes de la columna
            ('GridFilter.metadata_column_filters(columna)').
        chosen: Lo elegido en la columna (lo que ya no aparezca sale con 0).

    Raises:
        ValueError: Si el campo no se ofrece como columna, o el origen o el filtro no
            son válidos.
    """
    spec = FIELDS.get(field_key)
    if spec is None or not spec.browse:
        raise ValueError(f"Campo no disponible en «Metadatos»: {field_key!r}")
    where_sql, params = source_condition(source, filters)
    total = conn.execute(
        f"SELECT COUNT(*) FROM media_items AS m WHERE {where_sql}",
        params,
    ).fetchone()[0]

    # Campos de un tipo de medio (p. ej. el objetivo, solo fotos): como hace su regla
    if spec.media_types:
        marks = ", ".join("?" * len(spec.media_types))
        where_sql = f"({where_sql}) AND m.media_type IN ({marks})"
        params = (*params, *spec.media_types)

    counter = _KEYWORD_COUNTER if spec.kind == KIND_KEYWORD else _COUNTERS[spec.kind]
    rows = [row for row in counter(conn, spec, where_sql, params) if row[2] > 0]
    unknown = sum(count for key, _value, count in rows if key is METADATA_UNKNOWN)
    # Solo lo que se puede elegir: lo demás no sale (no habría regla para filtrarlo)
    known = [row for row in rows if row[0] is not METADATA_UNKNOWN and _selectable(spec, row[1])]
    chosen_values = [v for v in chosen if metadata_rule(spec.key, v) is not None]

    if spec.kind == KIND_DATE:
        values = _date_tree(known, chosen_values)
    else:
        values = _flat_list(spec, known, chosen_values)
    show_unknown = metadata_rule(spec.key, METADATA_UNKNOWN) is not None
    if show_unknown and (unknown or METADATA_UNKNOWN in chosen_values):
        values.append(MetadataValue(METADATA_UNKNOWN, unknown))
    return MetadataValues(spec.key, total, tuple(values))


def _selectable(spec: SmartField, value: Any) -> bool:
    """Si un valor de la base de datos tiene regla (p. ej. no un color desconocido)."""
    return metadata_rule(spec.key, value) is not None


# -----------------------------------------------------------------------------
# Recuentos por tipo de campo (todas con el mismo WHERE que la cuadrícula)
# -----------------------------------------------------------------------------


def _count_text(conn: sqlite3.Connection, spec: SmartField, where: str, params: tuple) -> list[_Counted]:
    """Textos: agrupados sin mayúsculas ni acentos ('arca_fold', como la regla «es»).
    Vacío o NULL = «Desconocido» (como «está vacío»)."""
    rows = conn.execute(
        f"SELECT {FOLD_SQL_FUNCTION}({spec.column}), MIN({spec.column}), COUNT(*) "
        f"FROM media_items AS m WHERE {where} GROUP BY 1",
        params,
    ).fetchall()
    return [(folded if folded else METADATA_UNKNOWN, raw, count) for folded, raw, count in rows]


def _count_keywords(conn: sqlite3.Connection, _spec: SmartField, where: str, params: tuple) -> list[_Counted]:
    """Palabras clave asignadas (sin las hijas), agrupadas por su nombre sin mayúsculas ni
    acentos ('name_folded', como «es (sin sus hijas)»); «Desconocido» = sin ninguna."""
    rows = conn.execute(
        "SELECT k.name_folded, MIN(k.name), COUNT(DISTINCT m.id) FROM media_items AS m "
        "JOIN media_keywords AS mk ON mk.media_id = m.id "
        f"JOIN keywords AS k ON k.id = mk.keyword_id WHERE {where} GROUP BY k.name_folded",
        params,
    ).fetchall()
    (without,) = conn.execute(
        f"SELECT COUNT(*) FROM media_items AS m WHERE ({where}) "
        "AND m.id NOT IN (SELECT media_id FROM media_keywords)",
        params,
    ).fetchone()
    return [*((folded, name, count) for folded, name, count in rows), (METADATA_UNKNOWN, None, without)]


def _count_bool(conn: sqlite3.Connection, spec: SmartField, where: str, params: tuple) -> list[_Counted]:
    """Sí / no: 1 si vale 1; si no (también sin dato), 0, como las reglas «sí» y «no»."""
    rows = conn.execute(
        f"SELECT CASE WHEN {spec.column} = 1 THEN 1 ELSE 0 END, COUNT(*) "
        f"FROM media_items AS m WHERE {where} GROUP BY 1",
        params,
    ).fetchall()
    return [(value, value, count) for value, count in rows]


def _count_dates(conn: sqlite3.Connection, spec: SmartField, where: str, params: tuple) -> list[_Counted]:
    """Fechas: por día ('AAAA-MM-DD', como compara la regla); el árbol se arma después."""
    rows = conn.execute(
        f"SELECT substr({spec.column}, 1, 10), COUNT(*) "
        f"FROM media_items AS m WHERE {where} GROUP BY 1",
        params,
    ).fetchall()
    return [(day if day else METADATA_UNKNOWN, day, count) for day, count in rows]


def _count_values(conn: sqlite3.Connection, spec: SmartField, where: str, params: tuple) -> list[_Counted]:
    """Números, listas y valoración: el valor tal cual (NULL = «Desconocido»)."""
    rows = conn.execute(
        f"SELECT {spec.column}, COUNT(*) FROM media_items AS m WHERE {where} GROUP BY 1",
        params,
    ).fetchall()
    return [(value if value is not None else METADATA_UNKNOWN, value, count) for value, count in rows]


_Counter = Callable[[sqlite3.Connection, SmartField, str, tuple], list[_Counted]]
_KEYWORD_COUNTER: _Counter = _count_keywords
_COUNTERS: dict[str, _Counter] = {
    KIND_TEXT: _count_text,
    KIND_BOOL: _count_bool,
    KIND_DATE: _count_dates,
    KIND_NUMBER: _count_values,
    KIND_ENUM: _count_values,
    KIND_RATING: _count_values,
}


# -----------------------------------------------------------------------------
# Orden y lo elegido que ya no aparece
# -----------------------------------------------------------------------------


def _match_key(spec: SmartField, value: Any) -> Any:
    """Con qué se compara un valor elegido con las filas contadas (textos y palabras clave,
    sin mayúsculas ni acentos, como sus reglas)."""
    if spec.kind in (KIND_TEXT, KIND_KEYWORD):
        return fold_text(value)
    return value


def _flat_list(spec: SmartField, known: list[_Counted], chosen: list[Any]) -> list[MetadataValue]:
    """Las filas de un campo que no es fecha, en su orden, con lo elegido que falte a 0.

    Si lo elegido coincide con una fila escrita de otra forma («huesca» y «Huesca»), la
    fila lleva el valor elegido: así la interfaz la ve elegida.
    """
    rows: dict[Any, list[Any]] = {key: [value, count] for key, value, count in known}
    for value in chosen:
        if value is METADATA_UNKNOWN:
            continue  # va al final, aparte
        key = _match_key(spec, value)
        if key in rows:
            rows[key][0] = value
        else:
            rows[key] = [value, 0]
    ordered = sorted(rows.items(), key=lambda item: _sort_key(spec, item[0]))
    return [MetadataValue(value, count) for _key, (value, count) in ordered]


def _sort_key(spec: SmartField, key: Any) -> tuple[Any, ...]:
    """Orden de las filas (ver la cabecera). 'key' es la clave de '_match_key'."""
    if spec.kind == KIND_ENUM:
        options = [value for value, _text in spec.choices]
        return (options.index(key) if key in options else len(options),)
    if spec.kind == KIND_RATING:
        return (key == 0, key)  # de 1 a 5 estrellas y después «sin valoración» (0)
    if spec.kind == KIND_BOOL:
        return (-key,)  # sí (1) antes que no (0)
    if spec.kind == KIND_NUMBER:
        return (float(key),)
    return (str(key),)  # textos y palabras clave: ya sin mayúsculas ni acentos


def _date_tree(known: list[_Counted], chosen: list[Any]) -> list[MetadataValue]:
    """Años > meses > días, con lo elegido que falte a 0 (ver el orden en la cabecera)."""
    years: dict[str, dict[str, dict[str, int]]] = {}
    for _key, day, count in known:
        if _is_day(day):  # una fecha mal escrita no tiene regla: no sale
            years.setdefault(day[:4], {}).setdefault(day[:7], {})[day] = count
    for value in chosen:
        if not isinstance(value, str):
            continue  # «Desconocido»: va al final, aparte
        months = years.setdefault(value[:4], {})
        if len(value) >= 7:
            days = months.setdefault(value[:7], {})
            if len(value) == 10:
                days.setdefault(value, 0)

    tree: list[MetadataValue] = []
    for year in sorted(years, reverse=True):
        month_nodes: list[MetadataValue] = []
        for month in sorted(years[year]):
            day_nodes = tuple(MetadataValue(d, n) for d, n in sorted(years[year][month].items()))
            month_nodes.append(MetadataValue(month, sum(d.count for d in day_nodes), day_nodes))
        tree.append(MetadataValue(year, sum(m.count for m in month_nodes), tuple(month_nodes)))
    return tree


def _is_day(text: object) -> bool:
    """Si es un día real 'AAAA-MM-DD'."""
    try:
        return isinstance(text, str) and len(text) == 10 and bool(date.fromisoformat(text))
    except ValueError:
        return False


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.metadata_values
    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_filter import MetadataColumn
    from core.catalog.smart_fields import browse_fields
    from core.catalog.smart_rules import MATCH_ANY, Rule

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")

    def add(name: str, media_type: str = "photo", **extra: Any) -> int:
        columns = {
            "storage_location_id": 1, "relative_path": name, "file_name": name,
            "media_type": media_type, "mime_type": "x/y", "file_size": 1, "file_mtime_ns": 0,
            "title": name,
            **extra,
        }  # fmt: skip
        cursor = db.execute(
            f"INSERT INTO media_items({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            tuple(columns.values()),
        )
        return cursor.lastrowid

    a = add("a.jpg", country="España", city="Huesca", rating=3, flag=1, color_label="red",
            content_created_at="2024-06-15 10:00:00", latitude=42.0, longitude=0.1)
    b = add("b.jpg", country="España", city="huesca", rating=0, flag=-1,
            content_created_at="2024-06-20 08:00:00")
    c = add("c.jpg", country="Francia", city="Pau", rating=5, color_label="blue",
            content_created_at="2023-01-02 09:00:00", in_quick_selection=1)
    d = add("d.jpg", country="España", city="", content_created_at="2024-07-01 00:00:00")
    e = add("e.mov", "video", country="España", city="Boltaña", rating=3, is_missing=1)
    f = add("f.gpx", "track", city=None, color_label="morado")  # color que no es de la lista
    for media_id, make, model, lens, iso, f_number, flash in (
        (a, "Canon", "EOS R5", "RF 24-70", 100, 2.8, 1),
        (b, "Canon", "EOS R5", None, 200, 2.8, 0),
        (c, "Apple", "iPhone 15", "iPhone 15 back camera", 100, 1.78, None),
    ):
        db.execute(
            "INSERT INTO photo_details(media_id, camera_make, camera_model, lens_model, iso, "
            "f_number, flash_fired) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (media_id, make, model, lens, iso, f_number, flash),
        )
    db.execute("INSERT INTO track_details(media_id, activity_type) VALUES (?, 'Senderismo')", (f,))
    db.execute("INSERT INTO keywords(id, name, name_folded) VALUES (1, 'Montaña', 'montana')")
    db.execute("INSERT INTO keywords(id, parent_id, name, name_folded) VALUES (2, 1, 'Pico', 'pico')")
    # La misma palabra en otra rama del árbol: se cuenta junto a la primera (como su regla)
    db.execute("INSERT INTO keywords(id, name, name_folded) VALUES (4, 'Lugares', 'lugares')")
    db.execute("INSERT INTO keywords(id, parent_id, name, name_folded) VALUES (3, 4, 'montaña', 'montana')")
    for media_id, keyword_id in ((a, 1), (a, 2), (b, 3), (c, 2), (e, 1)):
        db.execute("INSERT INTO media_keywords(media_id, keyword_id) VALUES (?, ?)", (media_id, keyword_id))

    def rows(key: str, filters: Sequence[RuleSet] = (), chosen: Iterable[Any] = ()) -> list:
        result = fetch_metadata_values(db, ALL_ITEMS, key, filters, chosen)
        return [(v.value, v.count) for v in result.values]

    # 1. Textos: sin mayúsculas ni acentos; vacío y NULL son «Desconocido», al final
    result = fetch_metadata_values(db, ALL_ITEMS, "city")
    assert result.total == 6 and result.value_count == 3
    assert rows("city") == [("Boltaña", 1), ("Huesca", 2), ("Pau", 1), (None, 2)], rows("city")
    # La cascada: con «País es España» delante, solo sus ciudades
    spain = (RuleSet(MATCH_ANY, (Rule("country", "eq", "España"),)),)
    assert rows("city", spain) == [("Boltaña", 1), ("Huesca", 2), (None, 1)]
    assert fetch_metadata_values(db, ALL_ITEMS, "city", spain).total == 4
    # Lo elegido que ya no aparece sale con 0; escrito de otra forma, con la forma elegida
    assert rows("city", spain, ["Pau", "HUESCA"]) == [
        ("Boltaña", 1), ("HUESCA", 2), ("Pau", 0), (None, 1)]

    # 2. Campos de las fotos: los vídeos y los tracks están en «Todo», pero en ninguna fila
    lens = fetch_metadata_values(db, ALL_ITEMS, "lens_model")
    assert lens.total == 6 and [(v.value, v.count) for v in lens.values] == [
        ("iPhone 15 back camera", 1), ("RF 24-70", 1), (None, 2)]  # b.jpg y d.jpg
    assert rows("iso") == [(100, 2), (200, 1), (None, 1)]  # d.jpg no tiene detalles
    assert rows("f_number") == [(1.78, 1), (2.8, 2), (None, 1)]
    assert rows("flash_fired") == [(1, 1), (0, 3)]  # sin dato = no
    assert rows("track_activity") == [("Senderismo", 1)]

    # 3. Listas, valoración y sí / no: en su orden; sin «Desconocido» si no hay regla
    assert rows("flag") == [(1, 1), (0, 4), (-1, 1)]
    assert rows("rating") == [(3, 2), (5, 1), (0, 3)]
    assert rows("color_label") == [("red", 1), ("blue", 1), (None, 3)]  # «morado» no sale
    assert rows("media_type") == [("photo", 4), ("video", 1), ("track", 1)]
    assert rows("has_gps") == [(1, 1), (0, 5)]
    assert rows("is_missing") == [(1, 1), (0, 5)]
    assert rows("in_quick_selection", chosen=[0]) == [(1, 1), (0, 5)]

    # 4. Palabras clave: cada palabra asignada (sin las hijas), sin mayúsculas ni acentos
    assert rows("keyword") == [("Montaña", 3), ("Pico", 2), (None, 2)], rows("keyword")

    # 5. Fechas: años (el más reciente arriba) > meses > días; lo elegido que falta, a 0
    dates = fetch_metadata_values(db, ALL_ITEMS, "captured_at", chosen=["2019-07-04", "2023"])
    years = [(v.value, v.count) for v in dates.values]
    assert years == [("2024", 3), ("2023", 1), ("2019", 0), (None, 2)], years
    june, july = dates.values[0].children
    assert (june.value, june.count, july.value, july.count) == ("2024-06", 2, "2024-07", 1)
    assert [(v.value, v.count) for v in june.children] == [("2024-06-15", 1), ("2024-06-20", 1)]
    assert dates.values[2].children[0].children[0] == MetadataValue("2019-07-04", 0)
    assert dates.value_count == 2
    # La fecha de importación siempre tiene valor: sin «Desconocido»
    assert [v.value for v in fetch_metadata_values(db, ALL_ITEMS, "added_at").values][-1] is not None

    # 6. Lo importante: elegir una fila filtra EXACTAMENTE los archivos que cuenta
    def check(spec_key: str, value: MetadataValue) -> None:
        column = MetadataColumn(spec_key, frozenset({value.value}))
        where, params = source_condition(ALL_ITEMS, (column.rule_set(),))
        (found,) = db.execute(f"SELECT COUNT(*) FROM media_items AS m WHERE {where}", params).fetchone()
        assert found == value.count, (spec_key, value.value, found, value.count)
        for child in value.children:
            check(spec_key, child)

    for spec in browse_fields():
        for value in fetch_metadata_values(db, ALL_ITEMS, spec.key).values:
            check(spec.key, value)

    # 7. Un campo que no es columna, rechazado
    try:
        fetch_metadata_values(db, ALL_ITEMS, "file_name")
        raise AssertionError("debía rechazar un campo que no es columna")
    except ValueError:
        pass
    print(f"{len(browse_fields())} campos comprobados.")
    print("Autoprueba finalizada correctamente.")
