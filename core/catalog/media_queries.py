"""Consultas SQL de la cuadrícula de miniaturas y escritura de los datos del usuario.

Este módulo NO depende de Qt. Todas las funciones reciben la conexión SQLite como primer
parámetro, así que se pueden enviar tal cual a 'CatalogDatabaseManager.execute_async'
(se ejecutan en un hilo secundario; el gestor hace el commit).

Tres responsabilidades:
    1. 'fetch_grid_rows': qué filas muestra la cuadrícula y en qué orden (por defecto, por
       hora de captura). QUÉ filas lo decide un 'GridSource' (core/catalog/grid_source.py):
       todo el catálogo, una carpeta, una colección... Es el único sitio con el SQL de la
       cuadrícula: '_source_condition' traduce cada origen a una condición WHERE.
    2. 'count_grid_items': cuántos elementos tiene cada origen (los contadores de la barra
       lateral). Usa la MISMA condición que 'fetch_grid_rows', así que el número que se ve
       en la barra lateral siempre coincide con lo que muestra la cuadrícula.
    3. 'update_user_field': guarda en el catálogo lo que el usuario decide en la cuadrícula
       (estrellas, marca, etiqueta de color: BLOQUE C del esquema).
    4. 'set_quick_selection' / 'clear_quick_selection': la "Selección rápida" (el círculo
       de la tarjeta). Vive SOLO en el catálogo: no se escribe en los archivos.

IMPORTANTE: la base de datos es una CACHÉ reconstruible. Escribir aquí rating/flag/color es
solo la mitad del trabajo: 'update_user_field' deja además el elemento PENDIENTE de escribir
(un bit por campo en 'user_data_pending') y el trabajo de 'core/userdata/sync.py' lo escribe en el
archivo, en su sidecar XMP o en el archivo de carpeta, para que sobreviva a recrear el
catálogo.

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

__version__ = "1.13.1"
# ruff: noqa: RUF022
__all__ = [
    "AVAILABLE",
    "DEFAULT_ORDER",
    "FLAG_NONE",
    "FLAG_PICKED",
    "FLAG_REJECTED",
    "GRID_ORDERS",
    "MISSING",
    "OFFLINE",
    "USER_FIELDS",
    "USER_FIELD_BITS",
    "clear_quick_selection",
    "count_grid_items",
    "fetch_grid_rows",
    "set_quick_selection",
    "source_condition",
    "update_user_field",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

# Módulos del proyecto
from core.catalog.color_labels import is_valid_color_label
from core.catalog.grid_source import ALL_ITEMS, GridSource, SourceKind
from core.catalog.keywords import KEYWORD_MEDIA_SQL
from core.catalog.smart_rules import rules_to_sql

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

# Órdenes disponibles para la cuadrícula: clave -> cláusula ORDER BY.
# Los NULL van siempre al final ('X IS NULL' vale 1 para NULL). El desempate por nombre
# e id hace el orden ESTABLE (varias fotos con la misma fecha no bailan entre consultas).
#
# 'content_created_at' es la hora de captura (EXIF; hora local) y equivale a la "Hora de
# captura" de Lightroom: es el orden por defecto. Los archivos sin esa fecha (aún sin leer
# sus metadatos, o sin EXIF) van al final.
# OJO con 'file_created_at': es la fecha de creación del ARCHIVO según el sistema (UTC) y
# puede ser NULL (p. ej. en Linux); NO es la hora de captura.
GRID_ORDERS: dict[str, str] = {
    "file_created_at": (
        "file_created_at IS NULL, file_created_at, file_name COLLATE NOCASE, id"
    ),
    "content_created_at": (
        "content_created_at IS NULL, content_created_at, file_name COLLATE NOCASE, id"
    ),
    "file_name": "file_name COLLATE NOCASE, id",
}
DEFAULT_ORDER = "content_created_at"  # hora de captura (EXIF): como la de Lightroom

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


def source_condition(source: GridSource) -> tuple[str, tuple[Any, ...]]:
    """Versión pública de '_source_condition' (para otras consultas sobre un origen).

    La usa 'selection_summary.fetch_source_summary' (el inspector sin selección): así el
    resumen cuenta exactamente lo que muestra la cuadrícula.
    """
    return _source_condition(source)


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
    order: str = DEFAULT_ORDER,
    source: GridSource = ALL_ITEMS,
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
        order: Clave de 'GRID_ORDERS'. Va en segundo lugar (antes que 'source') para
            no romper las llamadas que ya pasaban el orden como argumento posicional.
        source: Qué elementos mostrar (por defecto, todo el catálogo).

    Raises:
        ValueError: Si 'order' o 'source' no son conocidos (así nunca se interpola en
            el SQL un texto que venga de fuera).
    """
    try:
        order_by = GRID_ORDERS[order]
    except KeyError:
        raise ValueError(f"Orden desconocido: {order!r}") from None
    where_sql, where_params = _source_condition(source)

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
          ORDER BY {_qualified(order_by)}""",  # noqa: S608 - todo sale de listas cerradas
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
            f"SELECT COUNT(*) FROM media_items AS m WHERE {where_sql}",  # noqa: S608
            where_params,
        ).fetchone()
        counts[source] = int(row[0])
    return counts


def _qualified(order_by: str) -> str:
    """Antepone 'm.' a las columnas de un ORDER BY de 'GRID_ORDERS' (por el JOIN).

    'id' y otros nombres existen en las dos tablas; con el alias no hay ambigüedad.
    """
    words = []
    for part in order_by.split(","):
        part = part.strip()
        words.append(part if part.startswith("m.") else f"m.{part}")
    return ", ".join(words)


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
            f"UPDATE media_items SET {field} = ?, user_data_pending = user_data_pending | ?, "  # noqa: S608
            f"updated_at = CURRENT_TIMESTAMP WHERE id IN ({marks})",
            (value, bit, *chunk),
        )
        changed += cursor.rowcount
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
            f"UPDATE media_items SET in_quick_selection = ? "  # noqa: S608 - solo marcas '?'
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

    # El ausente se muestra (al final por no tener fecha de contenido), marcado como tal
    rows = fetch_grid_rows(db, "file_created_at")
    names = [r["file_name"] for r in rows]
    assert names == ["gone.jpg", "a.jpg", "c.jpg", "b.jpg", "B2.jpg"], names
    assert {r["file_name"]: r["availability"] for r in rows}["gone.jpg"] == MISSING
    assert all(r["availability"] == AVAILABLE for r in rows if r["file_name"] != "gone.jpg")
    rows = [r for r in rows if r["file_name"] != "gone.jpg"]
    assert DEFAULT_ORDER == "content_created_at"
    assert [r["file_name"] for r in fetch_grid_rows(db)] == [
        "c.jpg", "a.jpg", "b.jpg", "B2.jpg", "gone.jpg"
    ]  # fmt: skip
    # Ubicación desconectada: todo lo suyo sale como OFFLINE (también el ausente)
    db.execute("UPDATE storage_locations SET is_online = 0")
    assert {r["availability"] for r in fetch_grid_rows(db)} == {OFFLINE}
    db.execute("UPDATE storage_locations SET is_online = 1")
    assert rows[0]["rating"] == 3 and rows[0]["flag"] == 1 and rows[1]["color_label"] is None
    assert set(rows[0]) == {
        "id", "media_type", "file_name", "rating", "flag", "color_label", "thumbnail_status",
        "in_quick_selection", "library", "library_manual", "duration", "availability",
    }  # fmt: skip
    # Hora de captura (EXIF): el orden cambia
    by_content = [r["file_name"] for r in fetch_grid_rows(db, "content_created_at")]
    assert by_content == ["c.jpg", "a.jpg", "b.jpg", "B2.jpg", "gone.jpg"], by_content
    assert [r["file_name"] for r in fetch_grid_rows(db, "file_name")] == [
        "a.jpg", "b.jpg", "B2.jpg", "c.jpg", "gone.jpg",
    ]  # fmt: skip
    try:
        fetch_grid_rows(db, "id; DROP TABLE media_items")
        raise AssertionError("debía rechazar un orden desconocido")
    except ValueError:
        pass

    # Carpetas: con subcarpetas (por defecto) y sin ellas; 'ab' no está dentro de 'a'
    from core.catalog.grid_source import folder_source

    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Q', '/tmp/q')")
    for path in ("a/x.jpg", "a/sub/y.jpg", "ab/z.jpg", "a_b/w.jpg"):
        add(path, None, None, storage_location_id=2)

    def names(source: GridSource) -> list[str]:
        return sorted(r["file_name"] for r in fetch_grid_rows(db, "file_name", source))

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
    assert [r["file_name"] for r in fetch_grid_rows(db, "file_name", three)] == ["a.jpg"]
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
    assert len(fetch_grid_rows(db, DEFAULT_ORDER, ALL_ITEMS)) == 5

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
    print("Autoprueba finalizada correctamente.")
