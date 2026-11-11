"""Consultas SQL de la cuadrícula de miniaturas y escritura de los datos del usuario.

Este módulo NO depende de Qt. Todas las funciones reciben la conexión SQLite como primer
parámetro, así que se pueden enviar tal cual a 'CatalogDatabaseManager.execute_async'
(se ejecutan en un hilo secundario; el gestor hace el commit).

Tres responsabilidades:
    1. 'fetch_grid_rows': qué filas muestra la cuadrícula y en qué orden (un 'GridOrder' de
       core/catalog/grid_orders.py; por defecto, por nombre). QUÉ filas lo decide un 'GridSource' (core/catalog/grid_source.py):
       todo el catálogo, una carpeta, una colección... Es el único sitio con el SQL de la
       cuadrícula: '_source_condition' traduce cada origen a una condición WHERE. El
       FILTRO de la barra de filtros (conjuntos de reglas de 'grid_filter.py') se añade con
       un AND ('source_condition(origen, filtros)').
    2. 'count_grid_items': cuántos elementos tiene cada origen (los contadores de la barra
       lateral). Usa la MISMA condición que 'fetch_grid_rows', así que el número que se ve
       en la barra lateral siempre coincide con lo que muestra la cuadrícula.
    3. 'update_user_field': guarda en el catálogo lo que el usuario decide en la cuadrícula
       (estrellas, marca, etiqueta de color: BLOQUE C del esquema).
       'update_metadata_fields': lo mismo con los metadatos descriptivos que edita el
       usuario (título, pie de ilustración, ubicación...; ver
       core/userdata/editable_fields.py), con su bit en 'metadata_edit_pending'.
    4. 'set_quick_selection' / 'clear_quick_selection': la "Selección rápida" (el círculo
       de la tarjeta). Vive SOLO en el catálogo: no se escribe en los archivos.

IMPORTANTE: la base de datos es una CACHÉ reconstruible. Escribir aquí rating/flag/color es
solo la mitad del trabajo: 'update_user_field' deja además el elemento PENDIENTE de escribir
(un bit por campo en 'user_data_pending') y el trabajo de 'core/userdata/sync.py' lo escribe en el
archivo, en su sidecar XMP o en el archivo de carpeta, para que sobreviva a recrear el
catálogo.

2.2.0 'update_metadata_fields': metadatos descriptivos editados, pendientes de escribir
      (paso C.5).
2.1.0 Filtro de la barra de filtros: 'fetch_grid_rows(..., filters)' y
      'source_condition(source, filters)' (paso A.3).
2.0.0 El orden es un 'GridOrder' (campo y dirección, de 'grid_orders.py'); se quitan
      'GRID_ORDERS', 'DEFAULT_ORDER' y el orden por 'file_created_at'. Por defecto, por nombre.
1.13.1 Comentarios sin números de migración (esquema consolidado en la v1).
1.13.0 Selección rápida limitada a una biblioteca ('GridSource.library' en QUICK).
1.12.0 Carpeta limitada a una biblioteca ('GridSource.library' en el origen FOLDER).
1.11.0 Origen KEYWORD: una palabra clave y sus hijas (en una biblioteca).
1.10.0 'source_condition': nombre público de '_source_condition' (lo usa también el resumen
      del inspector, 'selection_summary.py', para contar lo mismo que la cuadrícula).
1.9.0 'fetch_grid_rows' trae también 'duration' (insignia de duración de la tarjeta).
1.8.0 'fetch_grid_rows' trae también 'library' y 'library_manual' (submenú «Biblioteca»).
1.7.0 Selección rápida: origen QUICK, columna 'in_quick_selection' en 'fetch_grid_rows',
      'set_quick_selection' y 'clear_quick_selection'.
1.6.0 Origen COLLECTION: los archivos de una colección estática.
1.5.0 Origen SMART: colecciones inteligentes (reglas de 'smart_rules.py').
1.4.0 Origen FOLDER: una carpeta de una ubicación, con o sin sus subcarpetas.
1.3.0 'fetch_grid_rows' acepta un 'GridSource' (qué mostrar) y se añade 'count_grid_items'
      (contadores de la barra lateral del catálogo).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.media_queries
"""

__version__ = "2.2.0"
# ruff: noqa: RUF022
__all__ = [
    "AVAILABLE",
    "FLAG_NONE",
    "FLAG_PICKED",
    "FLAG_REJECTED",
    "MISSING",
    "OFFLINE",
    "USER_FIELDS",
    "USER_FIELD_BITS",
    "clear_quick_selection",
    "count_grid_items",
    "fetch_grid_rows",
    "set_quick_selection",
    "source_condition",
    "update_metadata_fields",
    "update_user_field",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# Módulos del proyecto
from core.catalog.color_labels import is_valid_color_label
from core.catalog.grid_orders import NAME_ORDER, GridOrder, order_by_sql
from core.catalog.grid_source import ALL_ITEMS, GridSource, SourceKind
from core.catalog.keywords import KEYWORD_MEDIA_SQL
from core.catalog.smart_rules import RuleSet, rules_to_sql
from core.userdata.editable_fields import bits_for, default_title, normalize_value

# Valores de 'media_items.flag' (mismos que Lightroom: marcada / sin marca / rechazada)
FLAG_REJECTED = -1
FLAG_NONE = 0
FLAG_PICKED = 1

# Disponibilidad de un archivo en disco (clave 'availability' de 'fetch_grid_rows'):
#   AVAILABLE  está en disco (lo normal).
#   MISSING    su unidad está conectada pero el archivo no está: se borró, movió o
#              renombró fuera de la aplicación ('media_items.is_missing = 1').
#   OFFLINE    toda su ubicación está desconectada (disco externo, unidad de red):
#              no es un problema, volverá ('storage_locations.is_online = 0').
# Si se dan los dos casos, manda OFFLINE: con el disco desconectado no se sabe si el
# archivo sigue ahí.
AVAILABLE = 0
MISSING = 1
OFFLINE = 2

# Campos del usuario que se pueden escribir desde la cuadrícula
USER_FIELDS: tuple[str, ...] = ("rating", "flag", "color_label")

# Bit de cada campo en 'media_items.user_data_pending' (pendiente de escribir fuera del
# catálogo; ver la columna en catalog_schema.py)
USER_FIELD_BITS: dict[str, int] = {"rating": 1, "flag": 2, "color_label": 4}

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


# -----------------------------------------------------------------------------
# Origen de la cuadrícula -> SQL
# -----------------------------------------------------------------------------


def _source_condition(source: GridSource) -> tuple[str, tuple[Any, ...]]:
    """Traduce un 'GridSource' a una condición WHERE sobre 'media_items' (alias 'm').

    Es el ÚNICO sitio donde un origen se convierte en SQL: lo usan tanto la cuadrícula
    ('fetch_grid_rows') como los contadores ('count_grid_items'), así que nunca pueden
    discrepar. Al añadir un 'SourceKind' nuevo, se añade aquí su caso.

    Returns:
        Fragmento SQL (sin la palabra WHERE) y sus parámetros.

    Raises:
        ValueError: Si el tipo de origen no se conoce.
    """
    match source.kind:
        case SourceKind.ALL:
            # Todo el catálogo, también lo ausente o desconectado (como Lightroom)
            return "1 = 1", ()
        case SourceKind.FOLDER if source.location_id is not None:
            return _folder_condition(source)
        case SourceKind.SMART if source.rules is not None:
            # Las reglas ya validan campos, operadores y valores (ValueError si no)
            return rules_to_sql(source.rules)
        case SourceKind.QUICK:
            # Usa el índice parcial 'idx_media_items_quick_selection' (solo las filas marcadas)
            if source.library is not None:
                # La del módulo Imagen: solo lo de su biblioteca
                return "m.in_quick_selection = 1 AND m.library = ?", (source.library,)
            return "m.in_quick_selection = 1", ()
        case SourceKind.KEYWORD if source.keyword_id is not None:
            # La palabra y sus hijas (CTE recursiva, ver 'keywords.KEYWORD_MEDIA_SQL')
            sql, params = f"m.id IN ({KEYWORD_MEDIA_SQL})", (source.keyword_id,)
            if source.library is not None:
                sql, params = f"m.library = ? AND {sql}", (source.library, *params)
            return sql, params
        case SourceKind.COLLECTION if source.collection_id is not None:
            # Usa la clave primaria de 'collection_items' (collection_id, media_id)
            return (
                "m.id IN (SELECT media_id FROM collection_items WHERE collection_id = ?)",
                (source.collection_id,),
            )
        case _:
            raise ValueError(f"Origen de la cuadrícula desconocido: {source!r}")


def source_condition(
    source: GridSource, filters: Sequence[RuleSet] = ()
) -> tuple[str, tuple[Any, ...]]:
    """Condición WHERE de un origen y, si lo hay, del filtro de la barra de filtros.

    La usan la cuadrícula ('fetch_grid_rows') y 'selection_summary.fetch_source_summary'
    (el inspector sin selección): así el resumen cuenta exactamente lo que se ve. Los
    contadores de la barra lateral NO llevan filtro (como en Lightroom).

    Args:
        source: El origen elegido a la izquierda.
        filters: Conjuntos de reglas del filtro ('GridFilter.rule_sets()'), con AND entre
            ellos y con el origen. Vacío = solo el origen.

    Raises:
        ValueError: Si el origen no se conoce o una regla no es válida.
    """
    sql, params = _source_condition(source)
    if not filters:
        return sql, params
    parts, all_params = [f"({sql})"], list(params)
    for rule_set in filters:
        rule_sql, rule_params = rules_to_sql(rule_set)  # valida campos, operadores y valores
        parts.append(f"({rule_sql})")
        all_params.extend(rule_params)
    return " AND ".join(parts), tuple(all_params)


def _folder_condition(source: GridSource) -> tuple[str, tuple[Any, ...]]:
    """Condición de una carpeta: su ubicación y su ruta relativa (con o sin subcarpetas).

    Las rutas se comparan por RANGO ('carpeta/' <= ruta < 'carpeta0', porque '0' es el
    carácter que sigue a '/'), como en 'catalog_writer._under_prefix': LIKE no distingue
    mayúsculas y trata '%' y '_' (frecuentes en nombres de carpeta) como comodines, y el
    rango aprovecha el índice del UNIQUE (storage_location_id, relative_path). Así la
    carpeta 'ab' NO queda dentro de 'a'.

    Sin subcarpetas: además, lo que queda de la ruta tras 'carpeta/' no puede tener '/'.
    """
    params: list[Any] = [source.location_id]
    sql = "m.storage_location_id = ?"
    prefix = source.folder  # '' = la raíz de la ubicación

    if prefix:
        sql += " AND m.relative_path >= ? AND m.relative_path < ?"
        params += [prefix + "/", prefix + "0"]

    if not source.include_subfolders:
        # Posición donde empieza el nombre del archivo dentro de la ruta (1 = al principio)
        start = len(prefix) + 2 if prefix else 1
        sql += " AND instr(substr(m.relative_path, ?), '/') = 0"
        params.append(start)

    if source.library is not None:
        # Solo lo de una biblioteca (las «Carpetas» del módulo Imagen)
        sql += " AND m.library = ?"
        params.append(source.library)

    return sql, tuple(params)


def fetch_grid_rows(
    conn: sqlite3.Connection,
    order: GridOrder = NAME_ORDER,
    source: GridSource = ALL_ITEMS,
    filters: Sequence[RuleSet] = (),
) -> list[dict[str, Any]]:
    """Devuelve las filas que muestra la cuadrícula para un origen.

    Incluye los archivos que no están disponibles (ausentes o en una ubicación
    desconectada), con su estado en la clave 'availability' (AVAILABLE, MISSING u
    OFFLINE): se siguen viendo con su miniatura de la caché y sus datos, como en
    Lightroom, y la tarjeta indica que el archivo no está.

    Solo se piden las columnas que se pintan (nada de rutas ni metadatos pesados), así
    que incluso con cientos de miles de archivos la consulta y la lista en memoria son
    pequeñas.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        order: Orden (campo y dirección; ver 'grid_orders.py'). Va en segundo lugar (antes que 'source') para
            no romper las llamadas que ya pasaban el orden como argumento posicional.
        source: Qué elementos mostrar (por defecto, todo el catálogo).
        filters: Filtro de la barra de filtros ('GridFilter.rule_sets()'; vacío = sin
            filtro): solo las filas del origen que cumplen TODOS los conjuntos.

    Raises:
        TypeError: Si 'order' no es un 'GridOrder' (su campo ya se validó al crearlo:
            así nunca se interpola en el SQL un texto que venga de fuera).
        ValueError: Si 'source' no es conocido o alguna regla del filtro no es válida.
    """
    if not isinstance(order, GridOrder):
        raise TypeError(f"Orden no válido: {order!r} (se espera un GridOrder)")
    where_sql, where_params = source_condition(source, filters)

    rows = conn.execute(
        f"""SELECT m.id, m.media_type, m.file_name, m.rating, m.flag, m.color_label,
                   m.thumbnail_status, m.in_quick_selection, m.library, m.library_manual,
                   m.duration,
                   CASE WHEN l.is_online = 0 THEN {OFFLINE}
                        WHEN m.is_missing = 1 THEN {MISSING}
                        ELSE {AVAILABLE} END
              FROM media_items AS m
              JOIN storage_locations AS l ON l.id = m.storage_location_id
             WHERE {where_sql}
          ORDER BY {order_by_sql(order, "m")}""",  # todo sale de listas cerradas
        where_params,
    ).fetchall()
    keys = (
        "id", "media_type", "file_name", "rating", "flag", "color_label",
        "thumbnail_status", "in_quick_selection", "library", "library_manual", "duration",
        "availability",
    )  # fmt: skip
    return [dict(zip(keys, row, strict=True)) for row in rows]


def count_grid_items(
    conn: sqlite3.Connection, sources: Iterable[GridSource]
) -> dict[GridSource, int]:
    """Cuenta los elementos de cada origen (contadores de la barra lateral).

    Cuenta TODO lo que hay en el catálogo para ese origen, también lo ausente o
    desconectado: es lo mismo que mostrará la cuadrícula al pulsarlo.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        sources: Orígenes que hay que contar (los repetidos se cuentan una vez).

    Returns:
        Origen -> número de elementos.

    Raises:
        ValueError: Si algún origen no se conoce.
    """
    counts: dict[GridSource, int] = {}
    for source in dict.fromkeys(sources):  # sin repetidos y en el mismo orden
        where_sql, where_params = _source_condition(source)
        row = conn.execute(
            f"SELECT COUNT(*) FROM media_items AS m WHERE {where_sql}",
            where_params,
        ).fetchone()
        counts[source] = int(row[0])
    return counts


# -----------------------------------------------------------------------------
# Datos del usuario
# -----------------------------------------------------------------------------


def _validate(field: str, value: object) -> object:
    """Comprueba (y devuelve) un valor para un campo del usuario; ValueError si no vale."""
    if field == "rating":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
            raise ValueError(f"Rating no válido: {value!r} (0 a 5)")
    elif field == "flag":
        if value not in (FLAG_REJECTED, FLAG_NONE, FLAG_PICKED) or isinstance(value, bool):
            raise ValueError(f"Marca no válida: {value!r} (-1, 0 o 1)")
    elif field == "color_label":
        if value is not None and not is_valid_color_label(value):
            raise ValueError(f"Etiqueta de color no válida: {value!r}")
    else:
        raise ValueError(f"Campo no editable por el usuario: {field!r}")
    return value


def update_user_field(
    conn: sqlite3.Connection, media_ids: Sequence[int], field: str, value: object
) -> int:
    """Escribe un campo del usuario (rating, flag o color_label) en varios elementos.

    Deja además ESE campo pendiente de escribir fuera del catálogo (su bit en
    'user_data_pending'): hasta que el trabajo de escritura lo haga, lo que se lea de
    los archivos no pisa este cambio.

    Args:
        conn: Conexión (la pone el gestor; él hace el commit).
        media_ids: 'id' de los elementos a modificar.
        field: 'rating', 'flag' o 'color_label'.
        value: Nuevo valor (color_label admite None = sin etiqueta).

    Returns:
        Número de filas modificadas.

    Raises:
        ValueError: Si el campo o el valor no son válidos (no se modifica nada).
    """
    _validate(field, value)
    bit = USER_FIELD_BITS[field]
    ids = [int(i) for i in media_ids]
    changed = 0
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        # 'field' ya está validado contra una lista cerrada: es seguro ponerlo en el SQL
        cursor = conn.execute(
            f"UPDATE media_items SET {field} = ?, user_data_pending = user_data_pending | ?, "
            f"updated_at = CURRENT_TIMESTAMP WHERE id IN ({marks})",
            (value, bit, *chunk),
        )
        changed += cursor.rowcount
    return changed


def update_metadata_fields(
    conn: sqlite3.Connection, media_ids: Sequence[int], values: Mapping[str, object]
) -> int:
    """Escribe metadatos descriptivos editados (título, pie, ubicación...) en varios elementos.

    Como 'update_user_field', pero para los campos de 'EDITABLE_FIELDS'
    (core/userdata/editable_fields.py), varios a la vez: cada valor, limpio
    ('normalize_value'), va a su columna, y los bits de ESOS campos se ponen en
    'metadata_edit_pending'. Hasta que el trabajo de escritura los lleve al archivo, lo que
    se lea de él no pisa estas columnas.

    Un título vacío (None, '' o solo espacios) vuelve, en cada elemento, al nombre de su
    archivo sin extensión ('title' es NOT NULL), y queda pendiente igual: en el archivo se
    vacía.

    Args:
        conn: Conexión (la pone el gestor; él hace el commit).
        media_ids: 'id' de los elementos a modificar.
        values: Columna editable -> texto nuevo (None o vacío = vaciar el campo).

    Returns:
        Número de elementos modificados.

    Raises:
        ValueError: Si una columna no es editable (no se modifica nada).
        TypeError: Si un valor no es texto ni None (no se modifica nada).
    """
    # Se valida todo antes de tocar nada
    clean = {column: normalize_value(column, value) for column, value in values.items()}
    if not clean:
        return 0
    bits = bits_for(clean)
    reset_title = "title" in clean and clean["title"] is None
    assigned = {
        column: value
        for column, value in clean.items()
        if not (column == "title" and value is None)
    }
    # Las columnas ya están validadas contra una lista cerrada: es seguro ponerlas en el SQL
    assignments = "".join(f"{column} = ?, " for column in assigned)
    ids = [int(i) for i in media_ids]
    changed = 0
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        cursor = conn.execute(
            f"UPDATE media_items SET {assignments}"
            "metadata_edit_pending = metadata_edit_pending | ?, "
            f"updated_at = CURRENT_TIMESTAMP WHERE id IN ({marks})",
            (*assigned.values(), bits, *chunk),
        )
        changed += cursor.rowcount
        if reset_title:
            # El nombre sin extensión se calcula en Python, igual que lo hace el escáner
            rows = conn.execute(
                f"SELECT id, file_name FROM media_items WHERE id IN ({marks})", chunk
            ).fetchall()
            conn.executemany(
                "UPDATE media_items SET title = ? WHERE id = ?",
                [(default_title(file_name), media_id) for media_id, file_name in rows],
            )
    return changed


# -----------------------------------------------------------------------------
# Selección rápida
# -----------------------------------------------------------------------------


def set_quick_selection(
    conn: sqlite3.Connection, media_ids: Sequence[int], selected: bool
) -> int:
    """Mete o saca varios elementos de la selección rápida.

    No toca 'user_data_pending' ni 'updated_at': la selección rápida es una marca de
    trabajo que vive solo en el catálogo, no un dato del archivo.

    Args:
        conn: Conexión (la pone el gestor; él hace el commit).
        media_ids: 'id' de los elementos.
        selected: True para meterlos, False para sacarlos.

    Returns:
        Número de filas que han cambiado (las que ya estaban así no cuentan).
    """
    value = 1 if selected else 0
    ids = [int(i) for i in media_ids]
    changed = 0
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        cursor = conn.execute(
            f"UPDATE media_items SET in_quick_selection = ? "  # solo marcas '?'
            f"WHERE in_quick_selection <> ? AND id IN ({marks})",
            (value, value, *chunk),
        )
        changed += cursor.rowcount
    return changed


def clear_quick_selection(conn: sqlite3.Connection) -> int:
    """Vacía la selección rápida. Devuelve cuántos elementos tenía."""
    return conn.execute(
        "UPDATE media_items SET in_quick_selection = 0 WHERE in_quick_selection = 1"
    ).rowcount


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.media_queries
    from dataclasses import dataclass

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_orders import CAPTURE_TIME_ORDER

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")

    def add(name: str, created: str | None, content: str | None = None, **extra: Any) -> None:
        columns = {
            "storage_location_id": 1, "relative_path": name, "file_name": name,
            "media_type": "photo", "mime_type": "image/jpeg", "file_size": 1,
            "file_mtime_ns": 0, "title": name, "file_created_at": created,
            "content_created_at": content, **extra,
        }  # fmt: skip
        names = ",".join(columns)
        db.execute(
            f"INSERT INTO media_items({names}) VALUES ({','.join('?' * len(columns))})",
            tuple(columns.values()),
        )

    add("c.jpg", "2020-03-01 10:00:00", "2019-01-01 08:00:00")
    add("a.jpg", "2020-01-01 10:00:00", "2021-01-01 08:00:00", rating=3, flag=1)
    add("b.jpg", None, None)  # sin fecha de sistema (típico en Linux): va al final
    add("B2.jpg", None, None)  # empate de NULL: desempata por nombre, sin distinguir mayúsculas
    add("gone.jpg", "2019-01-01 00:00:00", is_missing=1)  # ausente: se muestra, marcado

    # Por defecto, por nombre (sin distinguir mayúsculas). El ausente se muestra, marcado
    rows = fetch_grid_rows(db)
    names = [r["file_name"] for r in rows]
    assert names == ["a.jpg", "b.jpg", "B2.jpg", "c.jpg", "gone.jpg"], names
    assert {r["file_name"]: r["availability"] for r in rows}["gone.jpg"] == MISSING
    assert all(r["availability"] == AVAILABLE for r in rows if r["file_name"] != "gone.jpg")
    rows = [r for r in rows if r["file_name"] != "gone.jpg"]
    # Ubicación desconectada: todo lo suyo sale como OFFLINE (también el ausente)
    db.execute("UPDATE storage_locations SET is_online = 0")
    assert {r["availability"] for r in fetch_grid_rows(db)} == {OFFLINE}
    db.execute("UPDATE storage_locations SET is_online = 1")
    assert rows[0]["rating"] == 3 and rows[0]["flag"] == 1 and rows[1]["color_label"] is None
    assert set(rows[0]) == {
        "id", "media_type", "file_name", "rating", "flag", "color_label", "thumbnail_status",
        "in_quick_selection", "library", "library_manual", "duration", "availability",
    }  # fmt: skip
    # Hora de captura (EXIF): el orden cambia; sin ella, al final (desempate por nombre)
    by_content = [r["file_name"] for r in fetch_grid_rows(db, CAPTURE_TIME_ORDER)]
    assert by_content == ["c.jpg", "a.jpg", "b.jpg", "B2.jpg", "gone.jpg"], by_content
    # Descendente: los que no tienen fecha siguen al final; el desempate también se invierte
    by_content = [r["file_name"] for r in fetch_grid_rows(db, CAPTURE_TIME_ORDER.reversed())]
    assert by_content == ["a.jpg", "c.jpg", "gone.jpg", "B2.jpg", "b.jpg"], by_content
    try:
        fetch_grid_rows(db, "id; DROP TABLE media_items")  # type: ignore[arg-type]
        raise AssertionError("debía rechazar un orden que no es un GridOrder")
    except TypeError:
        pass

    # Carpetas: con subcarpetas (por defecto) y sin ellas; 'ab' no está dentro de 'a'
    from core.catalog.grid_source import folder_source

    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Q', '/tmp/q')")
    for path in ("a/x.jpg", "a/sub/y.jpg", "ab/z.jpg", "a_b/w.jpg"):
        add(path, None, None, storage_location_id=2)

    def names(source: GridSource) -> list[str]:
        return sorted(r["file_name"] for r in fetch_grid_rows(db, NAME_ORDER, source))

    assert names(folder_source(2, "a")) == ["a/sub/y.jpg", "a/x.jpg"]
    assert names(folder_source(2, "a", include_subfolders=False)) == ["a/x.jpg"]
    assert names(folder_source(2, "a/sub")) == ["a/sub/y.jpg"]
    assert names(folder_source(2, "a_b")) == ["a_b/w.jpg"]  # '_' no es comodín
    assert len(names(folder_source(2))) == 4  # toda la ubicación
    assert names(folder_source(1, "", include_subfolders=False)) == [
        "B2.jpg", "a.jpg", "b.jpg", "c.jpg", "gone.jpg"
    ]  # fmt: skip
    assert names(folder_source(2, "", include_subfolders=False)) == []
    assert folder_source(2, "\\a\\sub\\") == folder_source(2, "a/sub")  # barras de Windows
    assert count_grid_items(db, [folder_source(2, "a"), folder_source(2)]) == {
        folder_source(2, "a"): 2, folder_source(2): 4
    }  # fmt: skip
    # Solo una biblioteca dentro de la carpeta (las «Carpetas» del módulo Imagen)
    db.execute("UPDATE media_items SET library = 'image' WHERE storage_location_id = 2")
    db.execute("UPDATE media_items SET library = 'document' WHERE file_name = 'a/x.jpg'")
    assert names(folder_source(2, "a", library="image")) == ["a/sub/y.jpg"]
    assert count_grid_items(db, [folder_source(2, "a", library="image")]) == {folder_source(2, "a", library="image"): 1}
    db.execute("DELETE FROM media_items WHERE storage_location_id = 2")

    # Colección inteligente: se cuenta y se muestra lo mismo
    from core.catalog.grid_source import smart_source
    from core.catalog.smart_rules import Rule

    three = smart_source(Rule("rating", "eq", 3))
    assert [r["file_name"] for r in fetch_grid_rows(db, NAME_ORDER, three)] == ["a.jpg"]
    assert count_grid_items(db, [three]) == {three: 1}
    picked = smart_source(Rule("flag", "eq", FLAG_PICKED))
    assert count_grid_items(db, [picked])[picked] == 1

    # Colección estática: solo sus archivos
    from core.catalog.grid_source import collection_source

    db.execute("INSERT INTO collections(id, kind, name) VALUES (7, 'static', 'Favoritas')")
    db.execute("INSERT INTO collection_items(collection_id, media_id) VALUES (7, ?)", (rows[0]["id"],))
    favorites = collection_source(7)
    assert [r["id"] for r in fetch_grid_rows(db, source=favorites)] == [rows[0]["id"]]
    assert count_grid_items(db, [favorites, collection_source(8)]) == {
        favorites: 1, collection_source(8): 0
    }  # fmt: skip

    # Origen de la cuadrícula: "todo el catálogo" (por defecto o explícito) da lo mismo
    assert fetch_grid_rows(db, source=ALL_ITEMS) == fetch_grid_rows(db)
    assert len(fetch_grid_rows(db, NAME_ORDER, ALL_ITEMS)) == 5

    # Contadores: cuentan lo mismo que muestra la cuadrícula (también el ausente)
    assert count_grid_items(db, [ALL_ITEMS]) == {ALL_ITEMS: 5}
    assert count_grid_items(db, [ALL_ITEMS, ALL_ITEMS]) == {ALL_ITEMS: 5}  # sin repetidos
    assert count_grid_items(db, []) == {}

    # Un origen desconocido se rechaza (nunca se genera SQL a partir de él)
    @dataclass(frozen=True)
    class _FakeSource:
        kind: str = "nope"

    for call in (lambda: fetch_grid_rows(db, source=_FakeSource()),
                 lambda: count_grid_items(db, [_FakeSource()])):  # fmt: skip
        try:
            call()
            raise AssertionError("debía rechazar un origen desconocido")
        except ValueError:
            pass

    ids = {r["file_name"]: r["id"] for r in rows}
    assert update_user_field(db, [ids["a.jpg"], ids["c.jpg"]], "rating", 5) == 2
    assert update_user_field(db, [ids["c.jpg"]], "flag", FLAG_REJECTED) == 1
    assert update_user_field(db, [ids["b.jpg"]], "color_label", "blue") == 1
    assert update_user_field(db, [ids["b.jpg"]], "color_label", None) == 1
    by_name = {r["file_name"]: r for r in fetch_grid_rows(db)}
    assert by_name["a.jpg"]["rating"] == 5 and by_name["c.jpg"]["flag"] == -1
    assert by_name["b.jpg"]["color_label"] is None
    # Cada cambio deja el elemento pendiente de escribir fuera del catálogo
    pending = dict(db.execute("SELECT file_name, user_data_pending FROM media_items"))
    # (un bit por campo: rating 1, flag 2, color 4)
    assert pending == {"c.jpg": 3, "a.jpg": 1, "b.jpg": 4, "B2.jpg": 0, "gone.jpg": 0}, pending

    for bad in (("rating", 6), ("rating", True), ("rating", "3"), ("flag", 2),
                ("color_label", "orange"), ("title", "x"), ("is_missing", 1)):  # fmt: skip
        try:
            update_user_field(db, [ids["a.jpg"]], *bad)
            raise AssertionError(f"debía rechazar {bad}")
        except ValueError:
            pass
    assert by_name["a.jpg"]["rating"] == 5  # nada se modificó con los valores rechazados

    # Más ids que el límite de variables de SQLite: se trocea sin problema
    many = list(range(1, 1500))
    assert update_user_field(db, many, "rating", 2) == 5  # solo existen 5 filas
    assert update_user_field(db, [], "rating", 1) == 0

    # Metadatos descriptivos editados: cada valor, limpio, a su columna, y su bit pendiente
    def edited(name: str) -> tuple[Any, ...]:
        return db.execute(
            "SELECT title, description, city, metadata_edit_pending FROM media_items "
            "WHERE file_name = ?",
            (name,),
        ).fetchone()

    user_pending = dict(db.execute("SELECT id, user_data_pending FROM media_items"))
    values = {"title": "  Atardecer ", "city": "León"}
    assert update_metadata_fields(db, [ids["a.jpg"], ids["b.jpg"]], values) == 2
    assert edited("a.jpg") == edited("b.jpg") == ("Atardecer", None, "León", 1 | 32)
    assert edited("c.jpg") == ("c.jpg", None, None, 0)  # los demás, sin tocar
    # Vaciar: el título vuelve al nombre sin extensión y la ciudad a NULL; los bits se suman
    values = {"title": "", "city": None, "description": "Uno\r\nDos"}
    assert update_metadata_fields(db, [ids["a.jpg"]], values) == 1
    assert edited("a.jpg") == ("a", "Uno\nDos", None, 1 | 2 | 32)
    assert edited("b.jpg") == ("Atardecer", None, "León", 1 | 32)
    # No toca los datos del usuario ni su pendiente
    assert dict(db.execute("SELECT id, user_data_pending FROM media_items")) == user_pending
    # Lo que no vale se rechaza entero, sin modificar nada
    for bad in ({"rating": "3"}, {"title": 3}, {"city": "x", "file_name": "y"}):
        try:
            update_metadata_fields(db, [ids["a.jpg"]], bad)
            raise AssertionError(f"debía rechazar {bad}")
        except (ValueError, TypeError):
            pass
    assert edited("a.jpg") == ("a", "Uno\nDos", None, 1 | 2 | 32)
    assert update_metadata_fields(db, [ids["a.jpg"]], {}) == 0
    assert update_metadata_fields(db, [], {"city": "León"}) == 0
    assert update_metadata_fields(db, many, {"title": None}) == 5  # troceado
    titles = dict(db.execute("SELECT file_name, title FROM media_items"))
    assert titles == {"c.jpg": "c", "a.jpg": "a", "b.jpg": "b", "B2.jpg": "B2", "gone.jpg": "gone"}

    # Selección rápida: se cuenta y se muestra lo mismo, y no deja nada pendiente de escribir
    from core.catalog.grid_source import QUICK_SELECTION

    before = dict(db.execute("SELECT id, user_data_pending FROM media_items"))
    assert count_grid_items(db, [QUICK_SELECTION]) == {QUICK_SELECTION: 0}
    assert set_quick_selection(db, [ids["a.jpg"], ids["b.jpg"]], True) == 2
    assert set_quick_selection(db, [ids["a.jpg"]], True) == 0  # ya estaba
    quick = sorted(r["file_name"] for r in fetch_grid_rows(db, source=QUICK_SELECTION))
    assert quick == ["a.jpg", "b.jpg"], quick
    assert all(r["in_quick_selection"] == 1 for r in fetch_grid_rows(db, source=QUICK_SELECTION))
    assert count_grid_items(db, [QUICK_SELECTION]) == {QUICK_SELECTION: 2}
    assert set_quick_selection(db, [ids["b.jpg"]], False) == 1
    assert count_grid_items(db, [QUICK_SELECTION]) == {QUICK_SELECTION: 1}
    # La del módulo Imagen: solo lo de su biblioteca (la selección es la misma)
    from core.catalog.grid_source import quick_source

    db.execute("UPDATE media_items SET library = CASE WHEN file_name = 'a.jpg' THEN 'document' ELSE 'image' END")
    assert count_grid_items(db, [quick_source("image")]) == {quick_source("image"): 0}  # solo 'a.jpg', documento
    db.execute("UPDATE media_items SET library = 'image'")
    assert count_grid_items(db, [quick_source("image")]) == {quick_source("image"): 1}
    assert set_quick_selection(db, many, True) == 4  # troceado; 'a.jpg' ya estaba
    assert clear_quick_selection(db) == 5
    assert count_grid_items(db, [QUICK_SELECTION]) == {QUICK_SELECTION: 0}
    assert dict(db.execute("SELECT id, user_data_pending FROM media_items")) == before
    try:
        db.execute("UPDATE media_items SET in_quick_selection = 2")
        raise AssertionError("el CHECK debía rechazar un valor distinto de 0 y 1")
    except sqlite3.IntegrityError:
        pass

    # Filtro de la barra de filtros: se suma al origen con AND; los contadores no lo llevan
    from dataclasses import replace

    from core.catalog.grid_filter import (
        FILTER_TEXT,
        NO_FILTER,
        TEXT_ALL_FIELDS,
        TEXT_FILE_NAME,
        TextFilter,
    )

    def filtered(source: GridSource, field: str, operator: str, text: str) -> list[str]:
        grid_filter = replace(NO_FILTER, active=frozenset({FILTER_TEXT}),
                              text=TextFilter(field, operator, text))  # fmt: skip
        rows = fetch_grid_rows(db, NAME_ORDER, source, grid_filter.rule_sets())
        return sorted(r["file_name"] for r in rows)

    db.execute("UPDATE media_items SET description = 'Boda de Ana' WHERE file_name = 'c.jpg'")
    assert filtered(ALL_ITEMS, TEXT_FILE_NAME, "starts_with", "B") == ["B2.jpg", "b.jpg"]
    assert filtered(ALL_ITEMS, TEXT_FILE_NAME, "contains", "boda") == []  # solo el nombre
    assert filtered(ALL_ITEMS, TEXT_ALL_FIELDS, "contains", "BODA") == ["c.jpg"]  # descripción
    assert filtered(ALL_ITEMS, TEXT_ALL_FIELDS, "not_contains", "boda") == [
        "B2.jpg", "a.jpg", "b.jpg", "gone.jpg"
    ]  # fmt: skip
    assert filtered(QUICK_SELECTION, TEXT_FILE_NAME, "contains", "jpg") == []  # origen vacío
    assert fetch_grid_rows(db, NAME_ORDER, ALL_ITEMS, NO_FILTER.rule_sets()) == fetch_grid_rows(db)
    assert source_condition(ALL_ITEMS) == ("1 = 1", ())

    # «Atributos»: marca, valoración, color (también «sin color»), selección rápida y tipo
    from core.catalog.grid_filter import COLOR_NONE, FILTER_ATTRIBUTES, AttributeFilter

    db.executescript("""
        UPDATE media_items SET rating = 0, flag = 0, color_label = NULL, in_quick_selection = 0;
        UPDATE media_items SET rating = 4, flag = 1, color_label = 'red' WHERE file_name = 'a.jpg';
        UPDATE media_items SET rating = 2, flag = -1 WHERE file_name = 'b.jpg';
        UPDATE media_items SET color_label = 'green', in_quick_selection = 1,
                               media_type = 'video' WHERE file_name = 'c.jpg';
    """)

    def by_attributes(**chosen: Any) -> list[str]:
        grid_filter = replace(NO_FILTER, active=frozenset({FILTER_ATTRIBUTES}),
                              attributes=AttributeFilter(**chosen))  # fmt: skip
        rows = fetch_grid_rows(db, NAME_ORDER, ALL_ITEMS, grid_filter.rule_sets())
        return sorted(r["file_name"] for r in rows)

    everything = sorted(r["file_name"] for r in fetch_grid_rows(db))
    assert by_attributes() == everything
    assert by_attributes(flags=frozenset({1, -1})) == ["a.jpg", "b.jpg"]
    assert by_attributes(rating=2) == ["a.jpg", "b.jpg"]  # 2 o más
    assert by_attributes(rating=2, rating_operator="lte") == ["B2.jpg", "b.jpg", "c.jpg", "gone.jpg"]
    assert by_attributes(rating=4, rating_operator="eq") == ["a.jpg"]
    # Sin estrellas: «=» es «sin valoración»; «≤», nada
    assert by_attributes(rating_operator="eq") == ["B2.jpg", "c.jpg", "gone.jpg"]
    assert by_attributes(rating_operator="lte") == everything
    assert by_attributes(colors=frozenset({"red", "green"})) == ["a.jpg", "c.jpg"]
    assert by_attributes(colors=frozenset({COLOR_NONE})) == ["B2.jpg", "b.jpg", "gone.jpg"]
    assert by_attributes(quick=True) == ["c.jpg"]
    assert by_attributes(media_types=frozenset({"video"})) == ["c.jpg"]
    # Entre grupos, todos a la vez
    assert by_attributes(flags=frozenset({0}), colors=frozenset({"green"})) == ["c.jpg"]
    assert by_attributes(flags=frozenset({1}), quick=True) == []
    print("Autoprueba finalizada correctamente.")
