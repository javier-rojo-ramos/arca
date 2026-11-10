"""Valores comunes de unos campos para una selección de elementos (para el inspector).

Este módulo NO depende de Qt. Su función recibe la conexión como primer parámetro (para
'CatalogDatabaseManager.execute_async') y solo lee.

Para cada campo pedido dice qué valor tiene la selección:
    EMPTY   ningún elemento tiene valor        -> la fila se ve en blanco
    VALUE   todos tienen el MISMO valor        -> se muestra ese valor
    MIXED   hay valores distintos, o unos tienen valor y otros no -> «Varios»

Qué es un campo lo decide quien llama, con 'FieldSource': su clave y, para cada tipo de
medio, de qué columnas sale. Así este módulo no sabe nada de etiquetas ni de formatos (lo
pone la interfaz: 'ui_helpers/inspector/metadata_fields.py') y sirve para cualquier
sección. Un campo puede salir de varias columnas a la vez (la exposición: tiempo y
apertura; el GPS: latitud y longitud): su valor es la tupla de todas.

Columnas: 'tabla.columna', con estas tablas:
    m       media_items (la del propio elemento)
    photo   photo_details        video   video_details        track   track_details
Para cada tipo de medio se dan sus columnas; '*' vale para cualquier tipo. Un tipo sin
columnas no tiene ese campo (cuenta como "sin valor"): p. ej. la ISO de un vídeo.

Columnas calculadas (no existen en la tabla; se escriben igual):
    m.file_title   el título PROPIO: NULL si 'title' es el nombre del archivo sin extensión
                   (función SQL 'arca_file_title'). Así varias fotos sin título salen en
                   blanco, no «Varios» (cada una tiene su nombre como título).

    FieldSource("camera_model", {"photo": ("photo.camera_model",),
                                 "video": ("video.camera_model",)})
    FieldSource("dimensions", {"*": ("m.width", "m.height")})

Rendimiento: una sola consulta por trozo de 500 'id', con 'COUNT(DISTINCT ...)' en SQL:
seleccionar miles de fotos (Ctrl+A) no trae miles de filas a Python.

1.1.0 Columna calculada 'm.file_title' (título propio; paso C.5).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.selection_metadata
"""

__version__ = "1.1.0"
__all__ = ["EMPTY", "MIXED", "VALUE", "FieldSource", "FieldValue", "fetch_field_values"]

# Librerías estándar
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Módulos del proyecto
from core.catalog.catalog_schema import FILE_TITLE_SQL_FUNCTION

# Estados del valor de un campo en la selección
EMPTY, VALUE, MIXED = "empty", "value", "mixed"

# Tablas que se pueden usar en las columnas y cómo se unen al elemento
_TABLES: dict[str, str] = {
    "photo": "photo_details",
    "video": "video_details",
    "track": "track_details",
}

# Una referencia de columna válida ('m.width', 'photo.iso'): evita SQL inyectado por error
_COLUMN_REF = re.compile(r"^(m|photo|video|track)\.([a-z_][a-z0-9_]*)$")

# Columnas calculadas (ver el docstring del módulo): referencia -> expresión SQL
_COMPUTED_COLUMNS: dict[str, str] = {
    "m.file_title": f"{FILE_TITLE_SQL_FUNCTION}(m.title, m.file_name)",
}

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


@dataclass(frozen=True, slots=True)
class FieldSource:
    """De dónde sale un campo para cada tipo de medio (ver el docstring del módulo).

    Attributes:
        key: Clave del campo ('camera_model', 'exposure'...).
        columns: Tipo de medio ('photo', 'video'... o '*' para todos) -> columnas.
    """

    key: str
    columns: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class FieldValue:
    """Valor de un campo en la selección.

    Attributes:
        state: EMPTY, VALUE o MIXED.
        value: Con VALUE, la tupla de valores de sus columnas (en el orden de
            'FieldSource.columns'); si no, None.
    """

    state: str = EMPTY
    value: tuple[Any, ...] | None = None


def _column_sql(ref: str) -> str:
    """SQL de una referencia de columna: 'm.width', una subconsulta a su tabla de detalles
    o una columna calculada."""
    if ref in _COMPUTED_COLUMNS:
        return _COMPUTED_COLUMNS[ref]
    match = _COLUMN_REF.match(ref)
    if match is None:
        raise ValueError(f"Columna no válida: {ref!r} (se espera 'tabla.columna')")
    table, column = match.groups()
    if table == "m":
        return f"m.{column}"
    return f"(SELECT d.{column} FROM {_TABLES[table]} AS d WHERE d.media_id = m.id)"


def _field_sql(source: FieldSource) -> str:
    """Expresión SQL con el valor del campo de cada elemento: un texto JSON o NULL.

    Se usa JSON ('json_array') para que un campo de varias columnas sea UN valor que se
    pueda comparar con 'COUNT(DISTINCT ...)'. Si todas sus columnas son NULL, el valor es
    NULL (sin valor), no '[null, null]'.
    """
    def one(refs: tuple[str, ...]) -> str:
        parts = [_column_sql(ref) for ref in refs]
        values = ", ".join(parts)
        return f"CASE WHEN COALESCE({values}, NULL) IS NULL THEN NULL ELSE json_array({values}) END"

    by_type = {media_type: refs for media_type, refs in source.columns.items() if refs}
    if "*" in by_type:
        return one(by_type["*"])
    if not by_type:
        return "NULL"
    cases = " ".join(
        f"WHEN '{media_type}' THEN {one(refs)}"
        for media_type, refs in by_type.items()
        if re.fullmatch(r"[a-z]+", media_type)  # solo nombres de tipo sencillos
    )
    return f"CASE m.media_type {cases} ELSE NULL END"


def fetch_field_values(
    conn: sqlite3.Connection, media_ids: Sequence[int], sources: Sequence[FieldSource]
) -> dict[str, FieldValue]:
    """Valor de cada campo en la selección: común, «Varios» o vacío.

    Solo lee. Los 'id' que no existen se ignoran.

    Args:
        conn: Conexión sqlite3.
        media_ids: Elementos seleccionados.
        sources: Campos que se quieren y de dónde sale cada uno.

    Returns:
        Clave del campo -> 'FieldValue'. Sin elementos, todos EMPTY.
    """
    ids = list(dict.fromkeys(int(media_id) for media_id in media_ids))
    if not sources:
        return {}
    expressions = [_field_sql(source) for source in sources]
    select = ", ".join(
        f"COUNT({expr}), COUNT(DISTINCT {expr}), MIN({expr})" for expr in expressions
    )

    total = 0
    with_value = [0] * len(sources)  # elementos con valor, por campo
    mixed = [False] * len(sources)  # algún trozo ya tenía valores distintos
    seen: list[set[str]] = [set() for _ in sources]  # valores distintos vistos (como mucho 2)
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        row = conn.execute(
            f"SELECT COUNT(*), {select} FROM media_items AS m WHERE m.id IN ({marks})", chunk
        ).fetchone()
        total += row[0]
        for index in range(len(sources)):
            count, distinct, minimum = row[1 + 3 * index : 4 + 3 * index]
            with_value[index] += count
            if distinct > 1:
                mixed[index] = True
            elif minimum is not None:
                seen[index].add(minimum)

    result: dict[str, FieldValue] = {}
    for index, source in enumerate(sources):
        if with_value[index] == 0:
            result[source.key] = FieldValue(EMPTY)
        elif mixed[index] or len(seen[index]) > 1 or with_value[index] < total:
            # Valores distintos, o unos elementos con valor y otros sin él
            result[source.key] = FieldValue(MIXED)
        else:
            result[source.key] = FieldValue(VALUE, tuple(json.loads(next(iter(seen[index])))))
    return result


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.selection_metadata
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('L', '/l')")

    def add(name: str, media_type: str, **columns: Any) -> int:
        """Crea un elemento con algunas columnas de 'media_items'."""
        names = ", ".join(columns)
        marks = ", ".join("?" * len(columns))
        extra = f", {names}" if columns else ""
        return int(db.execute(
            f"""INSERT INTO media_items(storage_location_id, relative_path, file_name,
                    media_type, mime_type, file_size, file_mtime_ns, title{extra})
                VALUES (1, ?, ?, ?, 'x', 1, 0, 't'{', ' + marks if columns else ''})""",
            (name, name, media_type, *columns.values()),
        ).lastrowid)  # fmt: skip

    a = add("a.jpg", "photo", width=6000, height=4000, city="Torla")
    b = add("b.jpg", "photo", width=6000, height=4000, city="Broto")
    c = add("c.mov", "video", width=1080, height=1920)
    db.execute("INSERT INTO photo_details(media_id, camera_model, iso, exposure_time_s, f_number) VALUES (?, 'NIKON Df', 100, 0.0008, 8.0)", (a,))
    db.execute("INSERT INTO photo_details(media_id, camera_model, iso, exposure_time_s, f_number) VALUES (?, 'NIKON Df', 100, 0.0008, 8.0)", (b,))
    db.execute("INSERT INTO video_details(media_id, camera_model, frame_rate) VALUES (?, 'iPhone 17 Pro', 30.0)", (c,))

    sources = [
        FieldSource("dimensions", {"*": ("m.width", "m.height")}),
        FieldSource("city", {"*": ("m.city",)}),
        FieldSource("camera_model", {"photo": ("photo.camera_model",), "video": ("video.camera_model",)}),
        FieldSource("iso", {"photo": ("photo.iso",)}),
        FieldSource("exposure", {"photo": ("photo.exposure_time_s", "photo.f_number")}),
        FieldSource("frame_rate", {"video": ("video.frame_rate",)}),
    ]

    # 1. Un elemento: sus valores (las columnas múltiples, como tupla)
    one = fetch_field_values(db, [a], sources)
    assert one["dimensions"] == FieldValue(VALUE, (6000, 4000))
    assert one["exposure"] == FieldValue(VALUE, (0.0008, 8.0))
    assert one["camera_model"] == FieldValue(VALUE, ("NIKON Df",))
    assert one["frame_rate"] == FieldValue(EMPTY)  # una foto no tiene fotogramas por segundo

    # 2. Dos fotos: comunes y distintos
    two = fetch_field_values(db, [a, b], sources)
    assert two["dimensions"].state == VALUE and two["iso"] == FieldValue(VALUE, (100,))
    assert two["city"] == FieldValue(MIXED)

    # 3. Foto y vídeo: cada uno de su tabla; lo que solo tiene uno de ellos es «Varios»
    mixed_types = fetch_field_values(db, [a, c], sources)
    assert mixed_types["camera_model"] == FieldValue(MIXED)  # 'NIKON Df' / 'iPhone 17 Pro'
    assert mixed_types["iso"] == FieldValue(MIXED)  # la foto la tiene; el vídeo, no
    assert mixed_types["dimensions"] == FieldValue(MIXED)
    video = fetch_field_values(db, [c], sources)
    assert video["frame_rate"] == FieldValue(VALUE, (30.0,)) and video["iso"] == FieldValue(EMPTY)

    # 4. Sin elementos (o 'id' que no existen): todo vacío
    assert all(v == FieldValue(EMPTY) for v in fetch_field_values(db, [], sources).values())
    assert fetch_field_values(db, [999], sources)["city"] == FieldValue(EMPTY)

    # 5. Muchos elementos (varios trozos): sigue funcionando
    many = [add(f"m{i}.jpg", "photo", width=6000, height=4000) for i in range(1200)]
    assert fetch_field_values(db, many, sources)["dimensions"] == FieldValue(VALUE, (6000, 4000))
    assert fetch_field_values(db, [*many, c], sources)["dimensions"] == FieldValue(MIXED)

    # 5b. Título propio: el nombre del archivo sin extensión no cuenta (vacío, no «Varios»)
    own = [FieldSource("title", {"*": ("m.file_title",)})]
    untitled = [add(f"IMG_{i}.jpg", "photo") for i in range(3)]
    db.executemany("UPDATE media_items SET title = ? WHERE id = ?",
                   [(f"IMG_{i}", media_id) for i, media_id in enumerate(untitled)])  # fmt: skip
    assert fetch_field_values(db, untitled, own)["title"] == FieldValue(EMPTY)
    db.execute("UPDATE media_items SET title = 'Atardecer' WHERE id = ?", (untitled[0],))
    assert fetch_field_values(db, untitled[:1], own)["title"] == FieldValue(VALUE, ("Atardecer",))
    assert fetch_field_values(db, untitled, own)["title"] == FieldValue(MIXED)

    # 6. Una columna mal escrita se rechaza (no se mete en el SQL)
    try:
        fetch_field_values(db, [a], [FieldSource("x", {"*": ("m.width; DROP TABLE x",)})])
    except ValueError:
        pass
    else:
        raise AssertionError("debería rechazar una columna no válida")
    db.close()
    print("Autoprueba finalizada correctamente.")
