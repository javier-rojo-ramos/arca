"""Reglas de las colecciones inteligentes: validación, traducción a SQL y guardado en JSON.

Este módulo NO depende de Qt ni de la base de datos: describe reglas, las comprueba y las
convierte en una condición WHERE (con parámetros) sobre 'media_items' (alias 'm').

Una colección inteligente es un CONJUNTO DE REGLAS, como en Lightroom:

    Coincidencia con [todas | alguna] de las siguientes reglas:
        Valoración      es mayor o igual que   ★★★
        Etiqueta        es                     Rojo
        Fecha de captura  está entre           01/06/2024 y 30/06/2024

    RuleSet(match="all", rules=(
        Rule("rating", "gte", 3),
        Rule("color_label", "eq", "red"),
        Rule("captured_at", "between", ("2024-06-01", "2024-06-30")),
    ))

GRUPOS (como las reglas anidadas de Lightroom): en lugar de una regla puede ir un grupo, que
es otro 'RuleSet' con su propio «todas» o «alguna de». Así se mezclan «y» y «o»:

    Valoración ≥ ★★★  Y  (País es España  O  País es Francia)

    RuleSet("all", (
        Rule("rating", "gte", 3),
        RuleSet("any", (Rule("country", "eq", "España"), Rule("country", "eq", "Francia"))),
    ))

Un solo nivel: un grupo no puede llevar otro grupo dentro, ni quedar vacío (con «alguna
de» dejaría pasar todo). Lo comprueba 'validate_rule_set'.

Los CAMPOS (qué se puede filtrar, su tipo, su columna SQL) están en 'smart_fields.py':
para añadir uno basta con una línea allí. Aquí está lo que no cambia al añadir campos:
    - el SQL de cada operador ('_condition'),
    - la validación de los valores ('validate_rule'),
    - el formato JSON de 'collections.rules_json' ('rules_to_json' / 'rules_from_json'),
    - el texto legible de una regla ('describe_rule'), para los tooltips.

Formato de los valores dentro de una regla (siempre en unidades de la BASE DE DATOS):
    texto     'str' (no vacío)
    número    'int' o 'float' (p. ej. metros aunque el usuario escriba kilómetros)
    fecha     'YYYY-MM-DD'; "en los últimos" lleva un número de días (int)
    lista     uno de los valores de 'choices' del campo
    entre     tupla de dos valores (se ordena: el menor primero)

Seguridad: las columnas salen SIEMPRE de 'smart_fields.FIELDS' (lista cerrada) y los
valores van siempre como parámetros ('?'): nunca se pone en el SQL un texto que venga
de fuera (tampoco de un 'rules_json' manipulado a mano).

Texto sin distinguir mayúsculas ni acentos: se usa la función SQL 'arca_fold', que
registra 'catalog_schema.configure_connection' en cada conexión.

Todo es inmutable ('frozen' y tuplas), así que un 'RuleSet' se puede comparar con '==' y
usar como clave de un diccionario (lo necesita 'GridSource').

2.3.0 Grupos de reglas (un nivel): validación, SQL con paréntesis por grupo, JSON versión 2
      (se sigue leyendo la 1) y texto legible con los grupos sangrados.
2.2.0 «termina con» en las reglas de palabras clave (la barra de filtros busca con él en
      «Todos los campos disponibles»; paso A.3).
2.1.1 Comentarios con el nombre nuevo de la función SQL ('arca_fold').
2.1.0 Reglas de palabras clave (KIND_KEYWORD): árbol recorrido con una CTE recursiva.
2.0.0 Campos en 'smart_fields.py' (texto, números, fechas, listas, sí/no), grupo por tipo
      de medio, guardado en JSON y descripción legible.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.smart_rules
"""

__version__ = "2.3.0"
# ruff: noqa: RUF022
__all__ = [
    "FIELDS",
    "MATCH_ALL",
    "MATCH_ANY",
    "RULES_JSON_VERSION",
    "Rule",
    "RuleSet",
    "describe_rule",
    "describe_rules",
    "format_value",
    "rules_from_json",
    "rules_to_json",
    "rules_to_sql",
    "validate_rule",
    "validate_rule_set",
]

# Librerías estándar
import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Any

# Módulos del proyecto
from core.catalog.catalog_schema import FOLD_SQL_FUNCTION, fold_text
from core.catalog.smart_fields import (
    FIELDS,
    KIND_BOOL,
    KIND_DATE,
    KIND_ENUM,
    KIND_KEYWORD,
    KIND_NUMBER,
    KIND_RATING,
    KIND_TEXT,
    OPERATORS,
    SmartField,
)

# Modos de coincidencia
MATCH_ALL = "all"  # todas las reglas (AND)
MATCH_ANY = "any"  # alguna regla (OR)

# Versión del formato de 'collections.rules_json' (subirla si cambia de forma incompatible).
# 2: con grupos. Se siguen leyendo las anteriores (la 1 es la 2 sin grupos).
RULES_JSON_VERSION = 2

# Niveles de grupos: 1 = grupos dentro de la lista principal, pero no grupos en un grupo
_MAX_GROUP_DEPTH = 1

# Longitud máxima de un texto en una regla (de sobra para un nombre o una ruta)
_MAX_TEXT = 500
# Máximo de días en "en los últimos N días" (unos 100 años)
_MAX_DAYS = 36500


@dataclass(frozen=True, slots=True)
class Rule:
    """Una regla: campo, operador y valor.

    Attributes:
        field: Clave de 'smart_fields.FIELDS' ('rating', 'captured_at'...).
        operator: Clave de 'smart_fields.OPERATORS' ('eq', 'between'...).
        value: Valor (None en los operadores sin valor; tupla de dos en "entre").
    """

    field: str
    operator: str
    value: Any = None


@dataclass(frozen=True, slots=True)
class RuleSet:
    """Conjunto de reglas de una colección inteligente (o un grupo dentro de otro conjunto).

    Attributes:
        match: MATCH_ALL (todas) o MATCH_ANY (alguna).
        rules: Las reglas y los grupos (una tupla, para que el conjunto sea inmutable).
    """

    match: str = MATCH_ALL
    rules: "tuple[Rule | RuleSet, ...]" = ()


# -----------------------------------------------------------------------------
# Validación
# -----------------------------------------------------------------------------


def validate_rule(rule: Rule) -> Rule:
    """Comprueba una regla y la devuelve normalizada (p. ej. "entre" con el menor primero).

    Raises:
        ValueError: Si el campo, el operador o el valor no son válidos (con un mensaje que
            se puede mostrar al usuario).
    """
    spec = FIELDS.get(rule.field)
    if spec is None:
        raise ValueError(f"Campo desconocido en una regla: {rule.field!r}")
    if rule.operator not in spec.allowed_operators:
        raise ValueError(f"«{spec.label}» no admite el operador {rule.operator!r}.")
    arity = OPERATORS[rule.operator].arity

    if arity == 0:
        return Rule(rule.field, rule.operator, None)
    if arity == 2:
        if not isinstance(rule.value, (tuple, list)) or len(rule.value) != 2:
            raise ValueError(f"«{spec.label}»: «está entre» necesita dos valores.")
        low = _validate_value(spec, rule.operator, rule.value[0])
        high = _validate_value(spec, rule.operator, rule.value[1])
        return Rule(rule.field, rule.operator, (low, high) if low <= high else (high, low))
    return Rule(rule.field, rule.operator, _validate_value(spec, rule.operator, rule.value))


def validate_rule_set(rule_set: RuleSet) -> RuleSet:
    """Comprueba todas las reglas (también las de los grupos) y devuelve el conjunto normalizado.

    Raises:
        ValueError: Si el modo o alguna regla no son válidos, o si un grupo está vacío o
            lleva otro grupo dentro.
    """
    return _validate_set(rule_set, depth=0)


def _validate_set(rule_set: RuleSet, *, depth: int) -> RuleSet:
    """'validate_rule_set' de un conjunto que está a 'depth' niveles de la lista principal."""
    if rule_set.match not in (MATCH_ALL, MATCH_ANY):
        raise ValueError(f"Modo de coincidencia no válido: {rule_set.match!r}")
    items: list[Rule | RuleSet] = []
    for item in rule_set.rules:
        if isinstance(item, Rule):
            items.append(validate_rule(item))
        elif isinstance(item, RuleSet):
            if depth >= _MAX_GROUP_DEPTH:
                raise ValueError("Un grupo de reglas no puede llevar otro grupo dentro.")
            # Vacío no filtraría nada: con «alguna de» arriba dejaría pasar todo
            if not item.rules:
                raise ValueError("Un grupo de reglas no puede quedar vacío.")
            items.append(_validate_set(item, depth=depth + 1))
        else:
            # ValueError (no TypeError): es lo que esperan quienes validan (p. ej. un JSON
            # manipulado a mano llega aquí y se muestra como «reglas no válidas»)
            raise ValueError(f"Regla no válida: {item!r}")  # noqa: TRY004
    return RuleSet(rule_set.match, tuple(items))


def _validate_value(spec: SmartField, operator: str, value: Any) -> Any:
    """Comprueba UN valor según el tipo del campo; ValueError si no vale."""
    kind = spec.kind
    if kind == KIND_DATE and operator == "in_last":
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_DAYS:
            raise ValueError(f"«{spec.label}»: el número de días no es válido ({value!r}).")
        return value
    if kind in (KIND_TEXT, KIND_KEYWORD):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"«{spec.label}»: falta el texto.")
        if len(value) > _MAX_TEXT:
            raise ValueError(f"«{spec.label}»: el texto es demasiado largo.")
        return value.strip()
    if kind == KIND_NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"«{spec.label}»: el número no es válido ({value!r}).")
        return value
    if kind == KIND_DATE:
        # Solo 'YYYY-MM-DD' (10 caracteres): es lo que se compara con el día de la columna
        try:
            if not isinstance(value, str) or len(value) != 10:
                raise ValueError
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError(f"«{spec.label}»: la fecha no es válida ({value!r}).") from None
    if kind == KIND_RATING:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
            raise ValueError(f"«{spec.label}»: valoración no válida ({value!r}).")
        return value
    if kind == KIND_ENUM:
        # bool es subclase de int: True no puede pasar por 1 (Marcada)
        if isinstance(value, bool) or value not in [choice for choice, _text in spec.choices]:
            raise ValueError(f"«{spec.label}»: valor no válido ({value!r}).")
        return value
    raise ValueError(f"Tipo de campo desconocido: {kind!r}")


# -----------------------------------------------------------------------------
# SQL
# -----------------------------------------------------------------------------


def rules_to_sql(rule_set: RuleSet) -> tuple[str, tuple[Any, ...]]:
    """Traduce un conjunto de reglas a una condición WHERE sobre 'media_items' (alias 'm').

    Un conjunto vacío no filtra nada ("1 = 1").

    Returns:
        Fragmento SQL (sin la palabra WHERE) y sus parámetros.

    Raises:
        ValueError: Si el modo, un campo, un operador o un valor no son válidos (así nunca
            se genera SQL a partir de algo que no esté en las listas cerradas).
    """
    rule_set = validate_rule_set(rule_set)
    if not rule_set.rules:
        return "1 = 1", ()
    return _set_sql(rule_set)


def _set_sql(rule_set: RuleSet) -> tuple[str, tuple[Any, ...]]:
    """SQL de un conjunto ya validado y no vacío: cada grupo, entre sus propios paréntesis."""
    parts: list[str] = []
    params: list[Any] = []
    for item in rule_set.rules:
        sql, item_params = _set_sql(item) if isinstance(item, RuleSet) else _rule_sql(item)
        parts.append(sql)
        params.extend(item_params)
    joiner = " AND " if rule_set.match == MATCH_ALL else " OR "
    return "(" + joiner.join(f"({part})" for part in parts) + ")", tuple(params)


def _rule_sql(rule: Rule) -> tuple[str, tuple[Any, ...]]:
    """SQL de UNA regla ya validada, con la restricción de tipo de medio de su campo."""
    spec = FIELDS[rule.field]
    sql, params = _condition(spec, rule)
    # Campos de un tipo de medio (p. ej. ISO): solo coinciden archivos de ese tipo
    if spec.media_types:
        marks = ", ".join("?" * len(spec.media_types))
        sql = f"m.media_type IN ({marks}) AND ({sql})"
        params = (*spec.media_types, *params)
    return sql, params


def _like_pattern(text: str, *, prefix: bool, suffix: bool) -> str:
    """Patrón LIKE con los comodines del texto escapados (con '\\')."""
    escaped = fold_text(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return ("%" if prefix else "") + escaped + ("%" if suffix else "")


# Archivos que tienen asignada alguna palabra de un conjunto O ALGUNA DE SUS HIJAS (a
# cualquier profundidad). El conjunto se elige con '{base}' (una condición sobre
# 'keywords'); la CTE recursiva baja por el árbol. 'UNION' (no 'UNION ALL') evita bucles
# infinitos si el árbol tuviera un ciclo. Es una subconsulta NO correlacionada: SQLite la
# calcula una vez por consulta, no una vez por fila.
_KEYWORD_WITH_CHILDREN = (
    "WITH RECURSIVE kw(id) AS ("
    "SELECT id FROM keywords WHERE {base} "
    "UNION SELECT k.id FROM keywords AS k JOIN kw ON k.parent_id = kw.id) "
    "SELECT mk.media_id FROM media_keywords AS mk WHERE mk.keyword_id IN (SELECT id FROM kw)"
)


def _keyword_condition(op: str, value: Any) -> tuple[str, tuple[Any, ...]]:
    """SQL de una regla de palabra clave (los nombres se comparan sin mayúsculas ni acentos:
    'keywords.name_folded' ya está normalizado)."""
    if op == "is_set":
        return "m.id IN (SELECT media_id FROM media_keywords)", ()
    if op == "is_not_set":
        return "m.id NOT IN (SELECT media_id FROM media_keywords)", ()
    if op == "kw_is_only":
        return (
            "m.id IN (SELECT mk.media_id FROM media_keywords AS mk "
            "JOIN keywords AS k ON k.id = mk.keyword_id WHERE k.name_folded = ?)"
        ), (fold_text(value),)
    if op in ("kw_is", "kw_is_not"):
        base, params = "name_folded = ?", (fold_text(value),)
    else:
        prefix, suffix = {
            "contains": (True, True),
            "not_contains": (True, True),
            "starts_with": (False, True),
            "ends_with": (True, False),
        }[op]
        base, params = "name_folded LIKE ? ESCAPE '\\'", (_like_pattern(value, prefix=prefix, suffix=suffix),)
    negate = "NOT " if op in ("kw_is_not", "not_contains") else ""
    return f"m.id {negate}IN ({_KEYWORD_WITH_CHILDREN.format(base=base)})", params


def _condition(spec: SmartField, rule: Rule) -> tuple[str, tuple[Any, ...]]:
    """SQL de UNA regla ya validada (sin la restricción de tipo de medio)."""
    col = spec.column
    op = rule.operator
    value = rule.value

    # Palabras clave: van por sus tablas, no por una columna
    if spec.kind == KIND_KEYWORD:
        return _keyword_condition(op, value)

    # Sin valor
    if op == "is_set":
        return (f"{col} IS NOT NULL AND {col} <> ''" if spec.kind == KIND_TEXT else f"{col} IS NOT NULL"), ()
    if op == "is_not_set":
        return (f"{col} IS NULL OR {col} = ''" if spec.kind == KIND_TEXT else f"{col} IS NULL"), ()
    if op == "is_true":
        return f"{col} = 1", ()
    if op == "is_false":
        return f"({col} IS NULL OR {col} = 0)", ()

    # Texto: sin distinguir mayúsculas ni acentos ('arca_fold')
    if spec.kind == KIND_TEXT:
        folded = f"{FOLD_SQL_FUNCTION}({col})"
        if op == "eq":
            return f"{folded} = ?", (fold_text(value),)
        if op == "ne":
            return f"({col} IS NULL OR {folded} <> ?)", (fold_text(value),)
        patterns = {
            "contains": (True, True),
            "not_contains": (True, True),
            "starts_with": (False, True),
            "ends_with": (True, False),
        }
        prefix, suffix = patterns[op]
        pattern = _like_pattern(value, prefix=prefix, suffix=suffix)
        if op == "not_contains":
            return f"({col} IS NULL OR {folded} NOT LIKE ? ESCAPE '\\')", (pattern,)
        return f"{folded} LIKE ? ESCAPE '\\'", (pattern,)

    # Fechas: se compara el día ('YYYY-MM-DD'), salvo "en los últimos N días"
    if spec.kind == KIND_DATE:
        day = f"substr({col}, 1, 10)"
        if op == "on":
            return f"{day} = ?", (value,)
        if op == "before":
            return f"{day} < ?", (value,)
        if op == "after":
            return f"{day} > ?", (value,)
        if op == "between":
            return f"{day} BETWEEN ? AND ?", tuple(value)
        if op == "in_last":
            now = "datetime('now', 'localtime', ?)" if spec.clock == "local" else "datetime('now', ?)"
            return f"{col} >= {now}", (f"-{value} days",)

    # Números, valoración y listas
    simple = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if op in simple:
        return f"{col} {simple[op]} ?", (value,)
    if op == "ne":
        # "no es" incluye lo que no tiene valor (p. ej. "etiqueta no es roja": también sin color)
        return f"({col} IS NULL OR {col} <> ?)", (value,)
    if op == "between":
        return f"{col} BETWEEN ? AND ?", tuple(value)
    raise ValueError(f"Operador {op!r} sin traducción a SQL para «{spec.label}».")


# -----------------------------------------------------------------------------
# JSON ('collections.rules_json')
# -----------------------------------------------------------------------------


def rules_to_json(rule_set: RuleSet) -> str:
    """Convierte un conjunto de reglas (ya validado) en el texto de 'rules_json'.

    Formato (versión 2): {"version": 2, "match": "all", "rules": [...]}, donde cada
    elemento de "rules" es una regla, {"field", "op", "value"}, o un grupo,
    {"match", "rules"} (el grupo se reconoce por llevar "rules").
    """
    data = {"version": RULES_JSON_VERSION, **_set_to_data(validate_rule_set(rule_set))}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _set_to_data(rule_set: RuleSet) -> dict[str, Any]:
    """Un conjunto (o un grupo) como diccionario para el JSON."""
    items: list[dict[str, Any]] = []
    for item in rule_set.rules:
        if isinstance(item, RuleSet):
            items.append(_set_to_data(item))
        else:
            value = list(item.value) if isinstance(item.value, tuple) else item.value
            items.append({"field": item.field, "op": item.operator, "value": value})
    return {"match": rule_set.match, "rules": items}


def rules_from_json(text: str | None) -> RuleSet:
    """Lee el texto de 'rules_json' y devuelve el conjunto de reglas, validado.

    Raises:
        ValueError: Si el texto no es válido, es de una versión más nueva o alguna regla
            no se entiende (p. ej. un campo que ya no existe).
    """
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        raise ValueError("Las reglas guardadas no se pueden leer (JSON no válido).") from None
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ValueError("Las reglas guardadas no tienen el formato esperado.")
    version = data.get("version")
    if not isinstance(version, int) or version > RULES_JSON_VERSION:
        raise ValueError("Las reglas son de una versión más nueva de la aplicación.")
    # La versión 1 es la 2 sin grupos: se leen igual
    return validate_rule_set(_set_from_data(data, depth=0))


def _set_from_data(data: dict[str, Any], *, depth: int) -> RuleSet:
    """Un conjunto (o un grupo) leído del JSON, sin validar las reglas todavía."""
    items: list[Rule | RuleSet] = []
    for entry in data["rules"]:
        if not isinstance(entry, dict):
            raise ValueError("Una regla guardada no tiene el formato esperado.")
        if "rules" in entry:
            # Un grupo. La profundidad se corta aquí (no solo al validar): un JSON
            # manipulado con muchos niveles no llega a recorrerse entero
            if depth >= _MAX_GROUP_DEPTH or not isinstance(entry["rules"], list):
                raise ValueError("Un grupo de reglas guardado no tiene el formato esperado.")
            items.append(_set_from_data(entry, depth=depth + 1))
            continue
        value = entry.get("value")
        if isinstance(value, list):
            value = tuple(value)  # "entre": la tupla es inmutable (y comparable)
        items.append(Rule(str(entry.get("field")), str(entry.get("op")), value))
    return RuleSet(str(data.get("match", MATCH_ALL)), tuple(items))


# -----------------------------------------------------------------------------
# Texto legible (tooltips)
# -----------------------------------------------------------------------------


def format_value(spec: SmartField, operator: str, value: Any) -> str:
    """Un valor tal como lo ve el usuario (estrellas, km, dd/mm/aaaa, texto de la lista)."""
    if spec.kind == KIND_DATE:
        if operator == "in_last":
            return f"{value} días" if value != 1 else "1 día"
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    if spec.kind == KIND_RATING:
        return "★" * value if value else "sin estrellas"
    if spec.kind == KIND_ENUM:
        return spec.choice_label(value)
    if spec.kind == KIND_NUMBER:
        shown = value / spec.scale
        text = f"{shown:.{spec.decimals}f}" if spec.decimals else f"{shown:g}"
        text = text.replace(".", ",")  # coma decimal (español)
        return f"{text} {spec.unit}".strip()
    return f"«{value}»"


def describe_rule(rule: Rule) -> str:
    """Una regla en palabras: 'Valoración es mayor o igual que ★★★'."""
    spec = FIELDS.get(rule.field)
    if spec is None:
        return f"(campo desconocido: {rule.field})"
    operator = OPERATORS[rule.operator]
    if spec.kind == KIND_BOOL:
        return f"{spec.label}: {operator.label}"
    if operator.arity == 0:
        return f"{spec.label} {operator.label}"
    if operator.arity == 2:
        low, high = (format_value(spec, rule.operator, v) for v in rule.value)
        return f"{spec.label} {operator.label} {low} y {high}"
    if rule.operator == "in_last":
        return f"{spec.label} en los últimos {format_value(spec, rule.operator, rule.value)}"
    return f"{spec.label} {operator.label} {format_value(spec, rule.operator, rule.value)}"


def describe_rules(rule_set: RuleSet) -> str:
    """Todas las reglas en palabras, una por línea, con el modo de coincidencia delante.

    Los grupos, con su modo y sus reglas sangradas debajo:

        Cumple todas estas reglas:
        • Valoración es mayor o igual que ★★★
        • Cumple alguna de estas:
            – País es «España»
            – País es «Francia»
    """
    header = "Cumple todas estas reglas:" if rule_set.match == MATCH_ALL else "Cumple alguna de estas reglas:"
    return "\n".join([header, *_describe_items(rule_set, level=0)])


def _describe_items(rule_set: RuleSet, *, level: int) -> list[str]:
    """Las líneas de las reglas de un conjunto: «•» en la lista principal, «–» en un grupo."""
    bullet = "• " if level == 0 else "    " * level + "– "
    lines: list[str] = []
    for item in rule_set.rules:
        if isinstance(item, RuleSet):
            mode = "todas" if item.match == MATCH_ALL else "alguna de"
            lines.append(f"{bullet}Cumple {mode} estas:")
            lines.extend(_describe_items(item, level=level + 1))
        else:
            lines.append(f"{bullet}{describe_rule(item)}")
    return lines


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.smart_rules
    import sqlite3

    from core.catalog.catalog_schema import configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)  # registra 'arca_fold'
    db.executescript(
        """CREATE TABLE media_items(id INTEGER PRIMARY KEY, media_type TEXT, file_name TEXT,
               relative_path TEXT, rating INT, flag INT, color_label TEXT, title TEXT,
               content_created_at TEXT, added_at TEXT, file_size INT, latitude REAL,
               longitude REAL, width INT, height INT);
           CREATE TABLE photo_details(media_id INTEGER PRIMARY KEY, iso INT, camera_model TEXT);
           CREATE TABLE track_details(media_id INTEGER PRIMARY KEY, distance_m REAL);"""
    )
    rows = [
        # id, tipo, nombre, ruta, rating, flag, color, título, captura, importación, bytes, lat, lon, w, h
        (1, "photo", "a.jpg", "Viajes/Ordesa/a.jpg", 0, 0, None, "Cañón de Añisclo",
         "2024-06-10 10:00:00", "2026-10-01 08:00:00", 2_000_000, 42.6, 0.1, 4000, 3000),
        (2, "photo", "b.jpg", "Viajes/Pineta/b.jpg", 3, 1, "red", "Pineta 50%",
         "2024-06-30 23:59:59", "2026-10-01 08:00:00", 5_000_000, None, None, 3000, 4000),
        (3, "photo", "c.jpg", "Casa/c.jpg", 5, -1, "blue", None,
         "2023-01-01 00:00:00", "2026-10-01 08:00:00", 1_000_000, None, None, 1000, 1000),
        (4, "video", "d.mp4", "Viajes/d.mp4", 3, 0, None, "ordesa",
         None, "2026-10-01 08:00:00", 90_000_000, None, None, 1920, 1080),
        (5, "track", "ruta.gpx", "Tracks/ruta.gpx", 1, 1, "red", "Ruta",
         "2024-07-01 09:00:00", "2026-10-01 08:00:00", 50_000, 42.0, 0.0, None, None),
    ]  # fmt: skip
    db.executemany(f"INSERT INTO media_items VALUES ({','.join('?' * 15)})", rows)
    db.executemany("INSERT INTO photo_details VALUES (?, ?, ?)", [(1, 100, "Nikon Df"), (2, 800, "iPhone 8 Plus"), (3, 100, None)])
    db.execute("INSERT INTO track_details VALUES (5, 12345.6)")

    def ids(*rules: Rule | RuleSet, match: str = MATCH_ALL) -> list[int]:
        sql, params = rules_to_sql(RuleSet(match, rules))
        return [r[0] for r in db.execute(f"SELECT id FROM media_items AS m WHERE {sql} ORDER BY id", params)]

    # 1. Lo de antes (colecciones del sistema): mismo resultado
    assert ids() == [1, 2, 3, 4, 5]
    assert ids(Rule("rating", "eq", 3)) == [2, 4]
    assert ids(Rule("rating", "gte", 1)) == [2, 3, 4, 5]
    assert ids(Rule("flag", "eq", -1)) == [3]
    assert ids(Rule("color_label", "is_set")) == [2, 3, 5]
    assert ids(Rule("color_label", "ne", "red")) == [1, 3, 4]  # incluye sin color
    both = (Rule("rating", "eq", 3), Rule("color_label", "eq", "red"))
    assert ids(*both) == [2] and ids(*both, match=MATCH_ANY) == [2, 4, 5]

    # 2. Texto: sin mayúsculas ni acentos; comodines escapados
    assert ids(Rule("title", "contains", "anon")) == [1]  # "Cañón"
    assert ids(Rule("title", "contains", "ORDESA")) == [4]
    assert ids(Rule("title", "eq", "ruta")) == [5]
    assert ids(Rule("title", "contains", "50%")) == [2]
    assert ids(Rule("title", "contains", "%")) == [2]  # '%' literal, no comodín
    assert ids(Rule("title", "not_contains", "ruta")) == [1, 2, 3, 4]  # incluye sin título

    # 2b. Palabras clave: Coche > Toyota Corolla (foto 1, solo el modelo), Coche (foto 2,
    # asignada directamente), Familia > Papá (vídeo 4) y ninguna en las demás
    db.executescript(
        """CREATE TABLE keywords(id INTEGER PRIMARY KEY, parent_id INT, name TEXT, name_folded TEXT);
           CREATE TABLE media_keywords(media_id INT, keyword_id INT);
           INSERT INTO keywords VALUES (1, NULL, 'Coche', 'coche'), (2, 1, 'Toyota Corolla', 'toyota corolla'),
                                       (3, NULL, 'Familia', 'familia'), (4, 3, 'Papá', 'papa');
           INSERT INTO media_keywords VALUES (1, 2), (2, 1), (4, 4);"""
    )
    assert ids(Rule("keyword", "kw_is", "COCHE")) == [1, 2]  # con sus hijas
    assert ids(Rule("keyword", "kw_is_only", "coche")) == [2]  # solo la asignada
    assert ids(Rule("keyword", "kw_is_not", "Coche")) == [3, 4, 5]
    assert ids(Rule("keyword", "kw_is", "papa")) == [4]  # sin acentos
    assert ids(Rule("keyword", "contains", "fami")) == [4]  # el padre también cuenta
    assert ids(Rule("keyword", "contains", "corol")) == [1]
    assert ids(Rule("keyword", "not_contains", "o")) == [3, 4, 5]  # ni «Coche» ni sus hijas
    assert ids(Rule("keyword", "starts_with", "toy")) == [1]
    assert ids(Rule("keyword", "ends_with", "OLLA")) == [1]  # «Toyota Corolla»
    assert ids(Rule("keyword", "ends_with", "che")) == [1, 2]  # «Coche», con sus hijas
    assert ids(Rule("keyword", "is_set")) == [1, 2, 4] and ids(Rule("keyword", "is_not_set")) == [3, 5]
    assert ids(Rule("keyword", "contains", "%")) == []  # comodín literal
    assert describe_rule(Rule("keyword", "kw_is", "Coche")) == "Palabra clave es (con sus hijas) «Coche»"
    assert ids(Rule("title", "is_not_set")) == [3]
    assert ids(Rule("folder", "starts_with", "viajes/")) == [1, 2, 4]
    assert ids(Rule("file_name", "ends_with", ".JPG")) == [1, 2, 3]

    # 3. Fechas
    assert ids(Rule("captured_at", "on", "2024-06-30")) == [2]
    assert ids(Rule("captured_at", "between", ("2024-06-30", "2024-06-01"))) == [1, 2]  # se ordena
    assert ids(Rule("captured_at", "before", "2024-01-01")) == [3]
    assert ids(Rule("captured_at", "after", "2024-06-30")) == [5]
    assert ids(Rule("captured_at", "is_not_set")) == [4]
    assert ids(Rule("added_at", "in_last", 36500)) == [1, 2, 3, 4, 5]

    # 4. Números (con unidades: la regla guarda unidades de la BD)
    assert ids(Rule("file_size", "gt", 4 * 1024 * 1024)) == [2, 4]
    assert ids(Rule("file_size", "between", (1_000_000, 2_000_000))) == [1, 3]

    # 5. Campos de un tipo de medio: solo coinciden archivos de ese tipo
    assert ids(Rule("iso", "eq", 100)) == [1, 3]
    assert ids(Rule("iso", "ne", 100)) == [2]  # ni el vídeo ni el track
    assert ids(Rule("camera_model", "is_not_set")) == [3]  # solo fotos
    assert ids(Rule("orientation", "eq", "v")) == [2]
    assert ids(Rule("orientation", "eq", "s")) == [3]
    assert ids(Rule("track_distance", "gte", 10_000)) == [5]
    assert ids(Rule("has_gps", "is_true")) == [1, 5]
    assert ids(Rule("has_gps", "is_false")) == [2, 3, 4]
    assert ids(Rule("media_type", "eq", "video")) == [4]

    # 5b. Grupos: «y» y «o» mezclados, cada grupo entre sus paréntesis
    red_or_rejected = RuleSet(MATCH_ANY, (Rule("color_label", "eq", "red"), Rule("flag", "eq", -1)))
    assert ids(Rule("rating", "gte", 1), red_or_rejected) == [2, 3, 5]  # sin el 4 (sin color)
    rated_red = RuleSet(MATCH_ALL, (Rule("rating", "eq", 3), Rule("color_label", "eq", "red")))
    assert ids(Rule("media_type", "eq", "video"), rated_red, match=MATCH_ANY) == [2, 4]
    assert ids(RuleSet(MATCH_ANY, (Rule("iso", "eq", 100),))) == [1, 3]  # tipo de medio, dentro
    # Sin grupos, el mismo SQL que antes de existir los grupos
    assert rules_to_sql(RuleSet(rules=both)) == (
        "((m.rating = ?) AND (m.color_label = ?))", (3, "red")
    ), rules_to_sql(RuleSet(rules=both))

    # 6. JSON: ida y vuelta idéntica (comparable con '=='), también con grupos
    original = RuleSet(MATCH_ANY, (
        Rule("rating", "gte", 3),
        Rule("captured_at", "between", ("2024-06-01", "2024-06-30")),
        Rule("title", "contains", "Añisclo"),
        Rule("color_label", "is_set"),
        Rule("track_distance", "lt", 12345.6),
    ))  # fmt: skip
    text = rules_to_json(original)
    assert "Añisclo" in text  # sin escapar (legible en la BD)
    assert text.startswith('{"version":2,') and rules_from_json(text) == original
    grouped = RuleSet(MATCH_ALL, (Rule("rating", "gte", 1), red_or_rejected))
    text = rules_to_json(grouped)
    assert '{"match":"any","rules":[{"field":"color_label"' in text, text
    assert rules_from_json(text) == grouped
    # La versión 1 (las colecciones guardadas antes de los grupos) se sigue leyendo
    old = '{"version":1,"match":"any","rules":[{"field":"rating","op":"gte","value":3}]}'
    assert rules_from_json(old) == RuleSet(MATCH_ANY, (Rule("rating", "gte", 3),))
    deep = '{"match":"any","rules":[{"field":"rating","op":"eq","value":1}]}'
    for bad in (
        "",
        "{",
        "[]",
        '{"version": 99, "rules": []}',
        '{"version": 1, "rules": [{"field": "zzz", "op": "eq", "value": 1}]}',
        '{"version": 2, "rules": [{"match": "any", "rules": []}]}',  # grupo vacío
        '{"version": 2, "rules": [{"match": "any", "rules": "x"}]}',
        f'{{"version": 2, "rules": [{{"match": "all", "rules": [{deep}]}}]}}',  # grupo en grupo
    ):
        try:
            rules_from_json(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debía rechazar {bad!r}")

    # 7. Lo que no está en las listas cerradas se rechaza
    for bad_set in (
        RuleSet("xor", both),
        RuleSet(rules=(Rule("title; DROP TABLE x", "eq", 1),)),
        RuleSet(rules=(Rule("rating", "is_set"),)),
        RuleSet(rules=(Rule("rating", "eq", 9),)),
        RuleSet(rules=(Rule("rating", "eq", True),)),
        RuleSet(rules=(Rule("flag", "eq", True),)),
        RuleSet(rules=(Rule("flag", "eq", 2),)),
        RuleSet(rules=(Rule("color_label", "eq", "orange"),)),
        RuleSet(rules=(Rule("title", "contains", "   "),)),
        RuleSet(rules=(Rule("captured_at", "on", "30/06/2024"),)),
        RuleSet(rules=(Rule("captured_at", "between", ("2024-01-01",)),)),
        RuleSet(rules=(Rule("file_size", "gt", float("nan")),)),
        RuleSet(rules=(Rule("added_at", "in_last", 0),)),
        RuleSet(rules=(RuleSet(MATCH_ANY, ()),)),  # grupo vacío
        RuleSet(rules=(RuleSet(rules=(red_or_rejected,)),)),  # grupo dentro de un grupo
        RuleSet(rules=(RuleSet("xor", both),)),
        RuleSet(rules=(RuleSet(rules=(Rule("rating", "eq", 9),)),)),  # regla mala en un grupo
        RuleSet(rules=("rating",)),  # ni regla ni grupo
    ):
        try:
            rules_to_sql(bad_set)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debía rechazar {bad_set}")

    # 8. Texto legible
    assert describe_rule(Rule("rating", "gte", 3)) == "Valoración es mayor o igual que ★★★"
    assert describe_rule(Rule("track_distance", "gt", 12500)) == "Distancia es mayor que 12,5 km"
    assert describe_rule(Rule("captured_at", "between", ("2024-06-01", "2024-06-30"))) == (
        "Fecha de captura está entre 01/06/2024 y 30/06/2024"
    )
    assert describe_rule(Rule("added_at", "in_last", 7)) == "Fecha de importación en los últimos 7 días"
    assert describe_rule(Rule("color_label", "eq", "red")) == "Etiqueta de color es Rojo"
    assert describe_rule(Rule("has_gps", "is_true")) == "Tiene coordenadas GPS: sí"
    countries = RuleSet(MATCH_ANY, (Rule("country", "eq", "España"), Rule("country", "eq", "Francia")))
    assert describe_rules(RuleSet(MATCH_ALL, (Rule("rating", "gte", 3), countries))) == (
        "Cumple todas estas reglas:\n"
        "• Valoración es mayor o igual que ★★★\n"
        "• Cumple alguna de estas:\n"
        "    – País es «España»\n"
        "    – País es «Francia»"
    )
    assert describe_rules(RuleSet(MATCH_ANY, (rated_red,))).splitlines()[1] == "• Cumple todas estas:"
    print(describe_rules(original))
    print("Autoprueba finalizada correctamente.")
