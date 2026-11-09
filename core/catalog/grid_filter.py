"""Filtro de la cuadrícula: lo que la barra de filtros añade al origen elegido a la izquierda.

Este módulo NO depende de Qt ni de la base de datos: describe el filtro, lo convierte en
conjuntos de reglas ('smart_rules.RuleSet') y lo guarda en un diccionario (settings.json).

El ORIGEN ('GridSource': una carpeta, una colección, una palabra clave...) dice qué se
muestra; el FILTRO acota ese origen sin cambiarlo, como la barra de filtros de Lightroom.
Son piezas separadas (como el orden): la consulta de la cuadrícula los junta con un AND
('media_queries.source_condition').

Qué guarda un 'GridFilter':
    - 'active': las pestañas encendidas de la barra («Texto», «Atributos», «Metadatos»;
      vacío = «Ninguno»). Son interruptores que se combinan: cada una aporta su propio
      'RuleSet' y entre ellos van con AND.
    - 'remembered': las pestañas que estaban encendidas al pasar a «Ninguno» (Ctrl+L
      vuelve a ellas).
    - 'locked': el candado. Abierto, al cambiar de origen la barra vuelve a «Ninguno»;
      cerrado, el filtro se mantiene. (Lo aplica quien cambia el origen, no este módulo.)
    - 'text': lo elegido en la fila de «Texto» (campo, operador y texto). Se conserva
      aunque la pestaña se apague: al volver a encenderla, sigue ahí.
    - 'attributes': lo elegido en la fila de «Atributos» ('AttributeFilter': marcas,
      valoración, colores, selección rápida y tipos). Se conserva igual que el texto.
    - 'metadata': las columnas de «Metadatos» ('MetadataFilter': de 1 a 6, cada una con su
      campo y los valores elegidos). Se conserva igual que el texto.

«Atributos»: cada GRUPO con algo elegido aporta su propio 'RuleSet' (AND entre grupos).
Dentro de un grupo, lo elegido vale con «alguna» (MATCH_ANY): marcadas O sin marca, rojo O
verde, fotos O vídeos. «Sin color» es 'color_label' vacío ('COLOR_NONE'). Valoración:
«≥ / ≤ / =» y de 1 a 5 estrellas; SIN estrellas, solo «=» filtra («sin valoración», la
valoración 0); «≥» y «≤» sin estrellas no filtran (decidido por el autor el 08/11/2026).

«Metadatos» (como el explorador de metadatos de Lightroom): cada COLUMNA con algo elegido
aporta su 'RuleSet' (AND entre columnas); dentro de una columna, cualquiera de sus valores
(MATCH_ANY). Los campos son los de 'smart_fields' con 'browse=True'. Cada columna cuenta
sus valores sobre lo que le llega: el origen, «Texto», «Atributos» y las columnas de su
izquierda ('metadata_column_filters'; los recuentos, en 'metadata_values.py'). El valor
de una fila se traduce en una regla con 'metadata_rule':
    None ('METADATA_UNKNOWN')   «Desconocido»: «está vacío» (si el campo lo admite)
    texto                       «es» (sin mayúsculas ni acentos)
    palabra clave               «es (sin sus hijas)»: la palabra tal como se asignó
    número, lista, valoración   «es»
    sí / no                     1 / 0: «sí» / «no»
    fecha                       'AAAA', 'AAAA-MM' o 'AAAA-MM-DD': ese año, mes o día

Ejemplo:

    GridFilter(active=frozenset({FILTER_TEXT}), text=TextFilter(TEXT_ALL_FIELDS, "contains", "boda"))
        .rule_sets()
    -> (RuleSet(MATCH_ANY, (Rule("file_name", "contains", "boda"), Rule("title", ...),
                           Rule("description", ...), Rule("keyword", ...))),)

«Todos los campos disponibles» con «No contiene» es «ningún campo lo contiene» (MATCH_ALL
de «no contiene»); con los demás operadores, «alguno» (MATCH_ANY).

Todo es inmutable ('frozen'): un filtro se compara con '==' y se cambia creando otro
('with_panel', 'cleared', 'toggled', 'dataclasses.replace').

1.3.0 Columnas de «Metadatos» ('MetadataColumn', 'MetadataFilter', 'metadata_rule',
      'GridFilter.metadata' y 'metadata_column_filters'; paso A.3, «Metadatos»).
1.2.0 «Sin valoración»: «=» sin estrellas filtra la valoración 0.
1.1.0 Fila de «Atributos» ('AttributeFilter', 'GridFilter.attributes'); paso A.3.
1.0.0 Primera versión (paso A.3, subpaso 1): pestañas, candado y fila de «Texto».

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.grid_filter
"""

__version__ = "1.3.0"
__all__ = [
    "COLOR_NONE",
    "FILTER_ATTRIBUTES",
    "FILTER_METADATA",
    "FILTER_PANELS",
    "FILTER_TEXT",
    "MAX_METADATA_COLUMNS",
    "MAX_TEXT_LENGTH",
    "METADATA_UNKNOWN",
    "MIN_METADATA_COLUMNS",
    "NO_ATTRIBUTES",
    "NO_FILTER",
    "RATING_OPERATORS",
    "TEXT_ALL_FIELDS",
    "TEXT_FIELDS",
    "TEXT_FILE_NAME",
    "TEXT_OPERATORS",
    "AttributeFilter",
    "GridFilter",
    "MetadataColumn",
    "MetadataFilter",
    "TextFilter",
    "filter_from_dict",
    "filter_to_dict",
    "metadata_rule",
]

# Librerías estándar
import calendar
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

# Módulos del proyecto
from core.catalog.color_labels import COLOR_LABELS
from core.catalog.media_types import MediaType
from core.catalog.smart_fields import FIELDS, KIND_BOOL, KIND_DATE, KIND_KEYWORD
from core.catalog.smart_rules import MATCH_ALL, MATCH_ANY, Rule, RuleSet, validate_rule

# Pestañas de la barra (claves estables: se guardan en settings.json)
FILTER_TEXT = "text"
FILTER_ATTRIBUTES = "attributes"
FILTER_METADATA = "metadata"
FILTER_PANELS: tuple[str, ...] = (FILTER_TEXT, FILTER_ATTRIBUTES, FILTER_METADATA)

# Campos de la fila de «Texto» -> campos de 'smart_fields.FIELDS' en los que se busca
TEXT_ALL_FIELDS = "all"  # «Todos los campos disponibles»
TEXT_FILE_NAME = "file_name"  # «Nombre de archivo»
TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    TEXT_ALL_FIELDS: ("file_name", "title", "description", "keyword"),
    TEXT_FILE_NAME: ("file_name",),
}

# Operadores de la fila de «Texto» (claves de 'smart_fields.OPERATORS'), en su orden
TEXT_OPERATORS: tuple[str, ...] = ("contains", "not_contains", "starts_with", "ends_with")

# Lo más largo que se busca (el mismo límite que el motor de reglas pone a un texto)
MAX_TEXT_LENGTH = 500

# Fila de «Atributos»
RATING_OPERATORS: tuple[str, ...] = ("gte", "lte", "eq")  # ≥, ≤, = (claves de OPERATORS)
COLOR_NONE = "none"  # «sin color» (junto a los nombres de 'COLOR_LABELS')
_FLAGS = (1, 0, -1)  # marcada, sin marca, rechazada ('media_items.flag')
_MEDIA_TYPES = tuple(t.value for t in MediaType)

# Columnas de «Metadatos»
MIN_METADATA_COLUMNS = 1
MAX_METADATA_COLUMNS = 6
METADATA_UNKNOWN = None  # valor de la fila «Desconocido» (archivos sin ese dato)


@dataclass(frozen=True, slots=True)
class TextFilter:
    """Lo elegido en la fila de «Texto».

    Attributes:
        field: Clave de 'TEXT_FIELDS' (dónde se busca).
        operator: Clave de 'TEXT_OPERATORS'.
        text: Lo escrito ('' = no filtra aunque la pestaña esté encendida).
    """

    field: str = TEXT_ALL_FIELDS
    operator: str = "contains"
    text: str = ""

    def rule_set(self) -> RuleSet | None:
        """Las reglas de esta fila, o None si no filtra (caja vacía o solo espacios)."""
        text = self.text.strip()[:MAX_TEXT_LENGTH]
        fields = TEXT_FIELDS.get(self.field)
        if not text or fields is None or self.operator not in TEXT_OPERATORS:
            return None
        # «No contiene» en varios campos: que NINGUNO lo contenga; los demás, que alguno
        match = MATCH_ALL if self.operator == "not_contains" else MATCH_ANY
        return RuleSet(match, tuple(Rule(name, self.operator, text) for name in fields))


@dataclass(frozen=True, slots=True)
class AttributeFilter:
    """Lo elegido en la fila de «Atributos» (un grupo vacío no filtra).

    Attributes:
        flags: Marcas elegidas (1 marcada, 0 sin marca, -1 rechazada).
        rating: Estrellas (0 a 5).
        rating_operator: Clave de 'RATING_OPERATORS' (≥, ≤ o =). Con 0 estrellas, solo
            «=» filtra («sin valoración»); «≥» y «≤», no.
        colors: Colores elegidos (nombres de 'COLOR_LABELS' y 'COLOR_NONE').
        quick: Solo lo de la selección rápida.
        media_types: Tipos elegidos (valores de 'MediaType').
    """

    flags: frozenset[int] = frozenset()
    rating: int = 0
    rating_operator: str = "gte"
    colors: frozenset[str] = frozenset()
    quick: bool = False
    media_types: frozenset[str] = frozenset()

    def rule_sets(self) -> tuple[RuleSet, ...]:
        """Un conjunto por grupo con algo elegido (marca, valoración, color, selección
        rápida, tipo), en ese orden. Lo que no es válido se ignora."""
        sets: list[RuleSet] = []
        flags = [f for f in _FLAGS if f in self.flags]
        if flags:
            sets.append(RuleSet(MATCH_ANY, tuple(Rule("flag", "eq", f) for f in flags)))
        if self._rating_filters():
            sets.append(RuleSet(rules=(Rule("rating", self.rating_operator, self.rating),)))
        colors = [Rule("color_label", "eq", c) for c in COLOR_LABELS if c in self.colors]
        if COLOR_NONE in self.colors:
            colors.append(Rule("color_label", "is_not_set"))
        if colors:
            sets.append(RuleSet(MATCH_ANY, tuple(colors)))
        if self.quick:
            sets.append(RuleSet(rules=(Rule("in_quick_selection", "is_true"),)))
        types = [t for t in _MEDIA_TYPES if t in self.media_types]
        if types:
            sets.append(RuleSet(MATCH_ANY, tuple(Rule("media_type", "eq", t) for t in types)))
        return tuple(sets)


    def _rating_filters(self) -> bool:
        """Si la valoración filtra: de 1 a 5 estrellas con cualquier operador, o ninguna
        con «=» (sin valoración). Sin estrellas, «≥» y «≤» no filtran: solo hay una forma
        de pedir «sin valoración», la que explica el texto emergente del desplegable."""
        if self.rating_operator not in RATING_OPERATORS or not 0 <= self.rating <= 5:
            return False
        return self.rating > 0 or self.rating_operator == "eq"


# La fila de «Atributos» sin nada elegido
NO_ATTRIBUTES = AttributeFilter()


def metadata_rule(field_key: str, value: Any) -> Rule | None:
    """La regla de un valor de una columna de «Metadatos» (ver la cabecera), o None si el
    campo no se ofrece como columna o el valor no vale para él. Así, lo que llega de fuera
    (settings.json editado a mano) nunca produce una regla que el motor rechace."""
    spec = FIELDS.get(field_key)
    # Un booleano no vale como valor aunque en Python True == 1 (sí / no van con 1 / 0)
    if spec is None or not spec.browse or isinstance(value, bool):
        return None
    try:
        if value is METADATA_UNKNOWN:
            rule = Rule(field_key, "is_not_set")  # lo rechaza quien no admite «está vacío»
        elif spec.kind == KIND_BOOL:
            if not isinstance(value, int) or value not in (0, 1):
                return None
            rule = Rule(field_key, "is_true" if value == 1 else "is_false")
        elif spec.kind == KIND_KEYWORD:
            rule = Rule(field_key, "kw_is_only", value)
        elif spec.kind == KIND_DATE:
            rule = _date_rule(field_key, value)
        else:
            rule = Rule(field_key, "eq", value)
        return validate_rule(rule)
    except ValueError:
        return None


def _date_rule(field_key: str, value: object) -> Rule:
    """La regla de un año ('AAAA'), un mes ('AAAA-MM') o un día ('AAAA-MM-DD').

    Raises:
        ValueError: Si el valor no es ninguna de las tres cosas.
    """
    if isinstance(value, str) and len(value) == 10:
        return Rule(field_key, "on", value)  # 'validate_rule' comprueba que es un día real
    if isinstance(value, str) and len(value) == 7 and value[4] == "-":
        year, month = value[:4], value[5:]
        if year.isdigit() and month.isdigit() and 1 <= int(month) <= 12:
            last = calendar.monthrange(int(year), int(month))[1]
            return Rule(field_key, "between", (f"{value}-01", f"{value}-{last:02d}"))
    if isinstance(value, str) and len(value) == 4 and value.isdigit():
        return Rule(field_key, "between", (f"{value}-01-01", f"{value}-12-31"))
    raise ValueError(f"Fecha no válida en una columna de «Metadatos»: {value!r}")


def _value_order(value: Any) -> tuple[int, float, str]:
    """Orden estable de unos valores de tipos mezclados (para guardar y para las reglas)."""
    if value is None:
        return (0, 0.0, "")
    if isinstance(value, (int, float)):
        return (1, float(value), "")
    return (2, 0.0, str(value))


def _is_plain_value(value: object) -> bool:
    """Si un valor leído de settings.json puede ser de una columna (texto, número o None)."""
    return value is None or (isinstance(value, (str, int, float)) and not isinstance(value, bool))


@dataclass(frozen=True, slots=True)
class MetadataColumn:
    """Una columna de «Metadatos».

    Attributes:
        field: Clave de 'smart_fields.FIELDS' (uno con 'browse=True').
        values: Valores elegidos (vacío = «Todo»: la columna no filtra).
    """

    field: str
    values: frozenset[Any] = frozenset()

    def rule_set(self) -> RuleSet | None:
        """Las reglas de la columna (cualquiera de sus valores), o None si no filtra."""
        rules = [metadata_rule(self.field, v) for v in sorted(self.values, key=_value_order)]
        valid = tuple(rule for rule in rules if rule is not None)
        return RuleSet(MATCH_ANY, valid) if valid else None


@dataclass(frozen=True, slots=True)
class MetadataFilter:
    """Las columnas de «Metadatos», de izquierda a derecha (vacío = aún sin elegir: el
    panel pone las de partida del módulo)."""

    columns: tuple[MetadataColumn, ...] = ()

    @staticmethod
    def from_fields(field_keys: Iterable[str]) -> "MetadataFilter":
        """Columnas sin nada elegido con esos campos (los que no valen se ignoran)."""
        keys = [k for k in field_keys if k in FIELDS and FIELDS[k].browse]
        return MetadataFilter(tuple(MetadataColumn(k) for k in keys[:MAX_METADATA_COLUMNS]))

    def rule_sets(self, before: int | None = None) -> tuple[RuleSet, ...]:
        """Un conjunto por columna con algo elegido, de izquierda a derecha; con 'before',
        solo los de las columnas a la izquierda de esa (la cascada)."""
        columns = self.columns if before is None else self.columns[: max(0, before)]
        return tuple(s for s in (c.rule_set() for c in columns) if s is not None)

    def with_field(self, index: int, field_key: str) -> "MetadataFilter":
        """Cambia el campo de una columna (lo elegido en ella se vacía).

        Raises:
            ValueError: Si el campo no se ofrece como columna.
            IndexError: Si la columna no existe.
        """
        _check_browse_field(field_key)
        return self._replaced(index, MetadataColumn(field_key))

    def with_values(self, index: int, values: Iterable[Any]) -> "MetadataFilter":
        """Cambia lo elegido en una columna (los valores que no valen se ignoran).

        Raises:
            IndexError: Si la columna no existe.
        """
        column = self.columns[index]
        valid = frozenset(v for v in values if metadata_rule(column.field, v) is not None)
        return self._replaced(index, MetadataColumn(column.field, valid))

    def with_column_added(self, after: int, field_key: str) -> "MetadataFilter":
        """Añade una columna sin nada elegido a la derecha de la columna 'after' (-1 = la
        primera por la izquierda).

        Raises:
            ValueError: Si ya hay 'MAX_METADATA_COLUMNS' o el campo no se ofrece.
        """
        _check_browse_field(field_key)
        if len(self.columns) >= MAX_METADATA_COLUMNS:
            raise ValueError(f"Como mucho, {MAX_METADATA_COLUMNS} columnas.")
        position = min(max(after + 1, 0), len(self.columns))
        columns = (*self.columns[:position], MetadataColumn(field_key), *self.columns[position:])
        return MetadataFilter(columns)

    def with_column_removed(self, index: int) -> "MetadataFilter":
        """Quita una columna (y lo elegido en ella).

        Raises:
            ValueError: Si solo quedan 'MIN_METADATA_COLUMNS'.
            IndexError: Si la columna no existe.
        """
        if len(self.columns) <= MIN_METADATA_COLUMNS:
            raise ValueError(f"Al menos, {MIN_METADATA_COLUMNS} columna.")
        columns = list(self.columns)
        del columns[index]  # IndexError si no existe
        return MetadataFilter(tuple(columns))

    def _replaced(self, index: int, column: MetadataColumn) -> "MetadataFilter":
        """Las mismas columnas con la de 'index' cambiada (IndexError si no existe)."""
        columns = list(self.columns)
        columns[index] = column  # IndexError si no existe
        return MetadataFilter(tuple(columns))


def _check_browse_field(field_key: str) -> None:
    """ValueError si el campo no se ofrece como columna de «Metadatos»."""
    if field_key not in FIELDS or not FIELDS[field_key].browse:
        raise ValueError(f"Campo no disponible en «Metadatos»: {field_key!r}")


@dataclass(frozen=True, slots=True)
class GridFilter:
    """Estado de la barra de filtros de un módulo (ver la cabecera).

    Attributes:
        active: Pestañas encendidas (claves de 'FILTER_PANELS'; vacío = «Ninguno»).
        remembered: Las que estaban encendidas al pasar a «Ninguno» (para Ctrl+L).
        locked: Candado cerrado: el filtro se mantiene al cambiar de origen.
        text: Fila de «Texto» (se conserva aunque su pestaña esté apagada).
        attributes: Fila de «Atributos» (igual).
        metadata: Columnas de «Metadatos» (igual).
    """

    active: frozenset[str] = frozenset()
    remembered: frozenset[str] = frozenset()
    locked: bool = False
    text: TextFilter = field(default_factory=TextFilter)
    attributes: AttributeFilter = field(default_factory=AttributeFilter)
    metadata: MetadataFilter = field(default_factory=MetadataFilter)

    @property
    def is_none(self) -> bool:
        """True si está en «Ninguno» (ninguna pestaña encendida)."""
        return not self.active

    def rule_sets(self) -> tuple[RuleSet, ...]:
        """Los conjuntos de reglas que aplican AHORA (de las pestañas encendidas que tienen
        algo que filtrar), en el orden de las pestañas. Vacío = no filtra nada."""
        if FILTER_METADATA not in self.active:
            return self._row_sets()
        return (*self._row_sets(), *self.metadata.rule_sets())

    def metadata_column_filters(self, index: int) -> tuple[RuleSet, ...]:
        """Lo que filtra ANTES de la columna 'index' de «Metadatos»: «Texto» y «Atributos»
        (si están encendidas) y las columnas de su izquierda. Sobre eso se cuentan los
        valores de la columna (la cascada; ver 'metadata_values.py')."""
        return (*self._row_sets(), *self.metadata.rule_sets(before=index))

    def _row_sets(self) -> tuple[RuleSet, ...]:
        """Los conjuntos de las filas de «Texto» y «Atributos» encendidas."""
        sets: list[RuleSet] = []
        if FILTER_TEXT in self.active:
            text_rules = self.text.rule_set()
            if text_rules is not None:
                sets.append(text_rules)
        if FILTER_ATTRIBUTES in self.active:
            sets.extend(self.attributes.rule_sets())
        return tuple(sets)

    def with_panel(self, panel: str, on: bool) -> "GridFilter":
        """Enciende o apaga una pestaña (las demás no cambian)."""
        if panel not in FILTER_PANELS:
            raise ValueError(f"Pestaña de filtro desconocida: {panel!r}")
        active = self.active | {panel} if on else self.active - {panel}
        return replace(self, active=frozenset(active))

    def cleared(self) -> "GridFilter":
        """«Ninguno»: apaga todas las pestañas, recuerda cuáles eran y no borra lo escrito."""
        if not self.active:
            return self
        return replace(self, active=frozenset(), remembered=self.active)

    def toggled(self) -> "GridFilter":
        """Ctrl+L: de encendido a «Ninguno» y de «Ninguno» a lo último que estuvo encendido."""
        if self.active:
            return self.cleared()
        return replace(self, active=self.remembered)


# El filtro de partida: «Ninguno», candado abierto, nada escrito
NO_FILTER = GridFilter()


# -----------------------------------------------------------------------------
# Guardado (settings.json)
# -----------------------------------------------------------------------------


def filter_to_dict(grid_filter: GridFilter) -> dict[str, Any]:
    """El filtro como diccionario para settings.json (pestañas en el orden de la barra)."""
    return {
        "active": [p for p in FILTER_PANELS if p in grid_filter.active],
        "remembered": [p for p in FILTER_PANELS if p in grid_filter.remembered],
        "locked": grid_filter.locked,
        "text": {
            "field": grid_filter.text.field,
            "operator": grid_filter.text.operator,
            "text": grid_filter.text.text,
        },
        "attributes": _attributes_to_dict(grid_filter.attributes),
        "metadata": {
            "columns": [
                {"field": c.field, "values": sorted(c.values, key=_value_order)}
                for c in grid_filter.metadata.columns
            ]
        },
    }


def _attributes_to_dict(attributes: AttributeFilter) -> dict[str, Any]:
    """La fila de «Atributos» como diccionario (listas en el orden de la fila)."""
    return {
        "flags": [f for f in _FLAGS if f in attributes.flags],
        "rating": attributes.rating,
        "rating_operator": attributes.rating_operator,
        "colors": [c for c in (*COLOR_LABELS, COLOR_NONE) if c in attributes.colors],
        "quick": attributes.quick,
        "media_types": [t for t in _MEDIA_TYPES if t in attributes.media_types],
    }


def _attributes_from_dict(data: object) -> AttributeFilter:
    """Lee la fila de «Atributos» (lo que no se entienda, con su valor de partida)."""
    if not isinstance(data, dict):
        return NO_ATTRIBUTES

    def chosen(key: str, valid: tuple[Any, ...]) -> frozenset[Any]:
        value = data.get(key)
        if not isinstance(value, list):
            return frozenset()
        # Un booleano no vale como marca aunque en Python True == 1
        return frozenset(v for v in value if not isinstance(v, bool) and v in valid)

    rating = data.get("rating")
    valid_rating = isinstance(rating, int) and not isinstance(rating, bool) and 0 <= rating <= 5
    operator = data.get("rating_operator")
    return AttributeFilter(
        flags=chosen("flags", _FLAGS),
        rating=rating if valid_rating else 0,
        rating_operator=operator if operator in RATING_OPERATORS else "gte",
        colors=chosen("colors", (*COLOR_LABELS, COLOR_NONE)),
        quick=data.get("quick") is True,
        media_types=chosen("media_types", _MEDIA_TYPES),
    )


def _metadata_from_dict(data: object) -> MetadataFilter:
    """Lee las columnas de «Metadatos» (las que no se entiendan se saltan; los valores que
    no valgan para su campo, también)."""
    columns_data = data.get("columns") if isinstance(data, dict) else None
    if not isinstance(columns_data, list):
        return MetadataFilter()
    columns: list[MetadataColumn] = []
    for item in columns_data:
        key = item.get("field") if isinstance(item, dict) else None
        if not isinstance(key, str) or key not in FIELDS or not FIELDS[key].browse:
            continue
        values = item.get("values")
        chosen = frozenset(
            v for v in (values if isinstance(values, list) else ())
            if _is_plain_value(v) and metadata_rule(key, v) is not None
        )
        columns.append(MetadataColumn(key, chosen))
    return MetadataFilter(tuple(columns[:MAX_METADATA_COLUMNS]))


def filter_from_dict(data: object) -> GridFilter:
    """Lee un filtro guardado. Lo que no se entienda (otra versión, editado a mano) se
    ignora y se queda con su valor de partida: nunca falla."""
    if not isinstance(data, dict):
        return NO_FILTER

    def panels(value: object) -> frozenset[str]:
        if not isinstance(value, list):
            return frozenset()
        return frozenset(p for p in value if isinstance(p, str) and p in FILTER_PANELS)

    text_data = data.get("text")
    text = TextFilter()
    if isinstance(text_data, dict):
        field_key = text_data.get("field")
        operator = text_data.get("operator")
        value = text_data.get("text")
        text = TextFilter(
            field_key if field_key in TEXT_FIELDS else text.field,
            operator if operator in TEXT_OPERATORS else text.operator,
            value[:MAX_TEXT_LENGTH] if isinstance(value, str) else "",
        )
    return GridFilter(
        active=panels(data.get("active")),
        remembered=panels(data.get("remembered")),
        locked=data.get("locked") is True,
        text=text,
        attributes=_attributes_from_dict(data.get("attributes")),
        metadata=_metadata_from_dict(data.get("metadata")),
    )


if __name__ == "__main__":
    # Autoprueba (sin base de datos). Ejecutar desde la raíz:  python -m core.catalog.grid_filter
    from core.catalog.smart_rules import rules_to_sql

    # 1. «Ninguno» no filtra, aunque haya algo escrito
    written = replace(NO_FILTER, text=TextFilter(TEXT_ALL_FIELDS, "contains", "boda"))
    assert NO_FILTER.is_none and NO_FILTER.rule_sets() == () and written.rule_sets() == ()

    # 2. «Texto» encendido: todos los campos con «alguna»; «no contiene» con «todas»
    on = written.with_panel(FILTER_TEXT, True)
    (rules,) = on.rule_sets()
    assert rules.match == MATCH_ANY and [r.field for r in rules.rules] == list(TEXT_FIELDS["all"])
    assert all(r.operator == "contains" and r.value == "boda" for r in rules.rules)
    not_on = replace(on, text=TextFilter(TEXT_ALL_FIELDS, "not_contains", "boda"))
    assert not_on.rule_sets()[0].match == MATCH_ALL
    only_name = replace(on, text=TextFilter(TEXT_FILE_NAME, "ends_with", " .JPG "))
    assert only_name.rule_sets() == (RuleSet(MATCH_ANY, (Rule("file_name", "ends_with", ".JPG"),)),)
    for operator in TEXT_OPERATORS:  # todas las combinaciones son reglas válidas
        for key in TEXT_FIELDS:
            rules_to_sql(replace(on, text=TextFilter(key, operator, "x")).rule_sets()[0])
    # Caja vacía o solo espacios: no filtra; texto larguísimo: se recorta
    assert replace(on, text=TextFilter(text="   ")).rule_sets() == ()
    long_rules = replace(on, text=TextFilter(text="a" * 900)).rule_sets()[0]
    assert len(long_rules.rules[0].value) == MAX_TEXT_LENGTH
    # Pestañas encendidas sin nada elegido: no filtran
    assert NO_FILTER.with_panel(FILTER_ATTRIBUTES, True).rule_sets() == ()
    assert NO_FILTER.with_panel(FILTER_METADATA, True).rule_sets() == ()

    # 3. «Ninguno» y Ctrl+L: recuerda las pestañas y lo escrito
    both = on.with_panel(FILTER_ATTRIBUTES, True)
    none = both.cleared()
    assert none.is_none and none.remembered == {FILTER_TEXT, FILTER_ATTRIBUTES}
    assert none.text == both.text and none.cleared() is none
    assert none.toggled().active == both.active and both.toggled() == none
    assert on.with_panel(FILTER_TEXT, False).active == frozenset()
    try:
        on.with_panel("otra", True)
        raise AssertionError("debía rechazar una pestaña desconocida")
    except ValueError:
        pass

    # 4. Guardado: ida y vuelta idéntica; lo estropeado se ignora sin fallar
    locked = replace(none, locked=True)
    assert filter_from_dict(filter_to_dict(locked)) == locked
    assert filter_to_dict(both)["active"] == ["text", "attributes"]  # orden de la barra
    assert filter_from_dict(None) == NO_FILTER and filter_from_dict([1]) == NO_FILTER
    broken = filter_from_dict({
        "active": ["text", "otra", 3], "locked": "sí",
        "text": {"field": "ruta", "operator": "eq", "text": 5},
    })  # fmt: skip
    assert broken.active == {FILTER_TEXT} and broken.locked is False
    assert broken.text == TextFilter()

    # 5. «Atributos»: un conjunto por grupo, con «alguna» dentro del grupo
    attrs = AttributeFilter(
        flags=frozenset({1, 0}), rating=3, colors=frozenset({"red", COLOR_NONE}),
        quick=True, media_types=frozenset({"video", "photo"}),
    )
    sets = attrs.rule_sets()
    fields_in_order = [r.rules[0].field for r in sets]
    assert fields_in_order == ["flag", "rating", "color_label", "in_quick_selection", "media_type"]
    assert sets[0] == RuleSet(MATCH_ANY, (Rule("flag", "eq", 1), Rule("flag", "eq", 0)))
    assert sets[1] == RuleSet(rules=(Rule("rating", "gte", 3),))
    assert sets[2].rules == (Rule("color_label", "eq", "red"), Rule("color_label", "is_not_set"))
    assert [r.value for r in sets[4].rules] == ["photo", "video"]
    for rule_set in sets:
        rules_to_sql(rule_set)  # todas son reglas válidas
    assert NO_ATTRIBUTES.rule_sets() == () and AttributeFilter(rating=9).rule_sets() == ()
    # Sin estrellas: solo «=» es «sin valoración»; «≥» y «≤», nada
    unrated = RuleSet(rules=(Rule("rating", "eq", 0),))
    assert AttributeFilter(rating_operator="eq").rule_sets() == (unrated,)
    assert AttributeFilter(rating_operator="lte").rule_sets() == ()
    assert AttributeFilter(rating_operator="gte").rule_sets() == ()
    rules_to_sql(unrated)
    # Solo filtran con la pestaña encendida, y se suman al texto
    with_attrs = replace(on, attributes=attrs)
    assert replace(written, attributes=attrs).rule_sets() == ()
    assert len(with_attrs.with_panel(FILTER_ATTRIBUTES, True).rule_sets()) == 6
    # Guardado: ida y vuelta; lo estropeado se ignora
    assert filter_from_dict(filter_to_dict(with_attrs)) == with_attrs
    broken = filter_from_dict({"attributes": {
        "flags": [1, True, 7], "rating": 8, "rating_operator": "gt",
        "colors": ["red", "orange"], "quick": 1, "media_types": ["photo", "x"],
    }})  # fmt: skip
    expected = AttributeFilter(
        flags=frozenset({1}), colors=frozenset({"red"}), media_types=frozenset({"photo"})
    )
    assert broken.attributes == expected, broken.attributes

    # 6. «Metadatos»: el valor de cada fila es una regla válida (o None si no vale)
    assert metadata_rule("city", "Huesca") == Rule("city", "eq", "Huesca")
    assert metadata_rule("keyword", "Coche") == Rule("keyword", "kw_is_only", "Coche")
    assert metadata_rule("iso", 100) == Rule("iso", "eq", 100)
    assert metadata_rule("rating", 0) == Rule("rating", "eq", 0)
    assert metadata_rule("flag", -1) == Rule("flag", "eq", -1)
    assert metadata_rule("has_gps", 1) == Rule("has_gps", "is_true")
    assert metadata_rule("has_gps", 0) == Rule("has_gps", "is_false")
    assert metadata_rule("captured_at", "2024") == Rule(
        "captured_at", "between", ("2024-01-01", "2024-12-31"))
    assert metadata_rule("captured_at", "2024-02") == Rule(
        "captured_at", "between", ("2024-02-01", "2024-02-29"))  # bisiesto
    assert metadata_rule("captured_at", "2024-06-15") == Rule("captured_at", "on", "2024-06-15")
    # «Desconocido»: solo en los campos que admiten «está vacío»
    assert metadata_rule("city", METADATA_UNKNOWN) == Rule("city", "is_not_set")
    assert metadata_rule("keyword", None) == Rule("keyword", "is_not_set")
    assert metadata_rule("captured_at", None) == Rule("captured_at", "is_not_set")
    for key in ("flag", "rating", "media_type", "added_at", "has_gps", "orientation"):
        assert metadata_rule(key, None) is None, key
    # Lo que no vale: campo que no es columna, tipo equivocado, fecha imposible...
    for key, bad in (("file_name", "a.jpg"), ("city", 3), ("city", "  "), ("has_gps", True),
                     ("has_gps", 2), ("iso", float("nan")), ("iso", "100"), ("flag", 7),
                     ("captured_at", "2024-13"), ("captured_at", "2024-02-30"),
                     ("captured_at", "24"), ("captured_at", 2024), ("otro", 1)):
        assert metadata_rule(key, bad) is None, (key, bad)

    # 7. Columnas: añadir, quitar, cambiar de campo (se vacía) y elegir valores
    meta = MetadataFilter.from_fields(["country", "file_name", "city", "keyword"])
    assert [c.field for c in meta.columns] == ["country", "city", "keyword"]
    meta = meta.with_values(0, ["España", 5]).with_values(1, ["Huesca", "Torla", None])
    assert meta.columns[0].values == {"España"}  # el 5 no vale para un texto
    sets = meta.rule_sets()
    assert sets[0] == RuleSet(MATCH_ANY, (Rule("country", "eq", "España"),))
    assert sets[1].rules == (Rule("city", "is_not_set"), Rule("city", "eq", "Huesca"),
                             Rule("city", "eq", "Torla"))
    assert meta.rule_sets(before=1) == sets[:1] and meta.rule_sets(before=0) == ()
    assert meta.with_field(1, "region").columns[1] == MetadataColumn("region")
    added = meta.with_column_added(0, "lens_model")
    assert [c.field for c in added.columns] == ["country", "lens_model", "city", "keyword"]
    assert added.with_column_added(-1, "iso").columns[0].field == "iso"
    assert [c.field for c in meta.with_column_removed(0).columns] == ["city", "keyword"]
    for bad_call in (lambda: meta.with_field(0, "file_name"),
                     lambda: meta.with_column_added(0, "title"),
                     lambda: MetadataFilter.from_fields(["city"]).with_column_removed(0),
                     lambda: MetadataFilter.from_fields(["iso"] * 9).with_column_added(0, "iso")):
        try:
            bad_call()
            raise AssertionError("debía rechazarlo")
        except ValueError:
            pass
    assert len(MetadataFilter.from_fields(["iso"] * 9).columns) == MAX_METADATA_COLUMNS
    try:
        meta.with_values(7, ["x"])
        raise AssertionError("debía rechazar una columna que no existe")
    except IndexError:
        pass
    for rule_set in sets:
        rules_to_sql(rule_set)

    # 8. En el filtro: solo con «Metadatos» encendida; la cascada lleva texto y atributos
    grid = replace(with_attrs, metadata=meta).with_panel(FILTER_ATTRIBUTES, True)
    assert grid.rule_sets() == with_attrs.with_panel(FILTER_ATTRIBUTES, True).rule_sets()
    grid = grid.with_panel(FILTER_METADATA, True)
    assert grid.rule_sets()[-2:] == sets and len(grid.rule_sets()) == 8
    assert grid.metadata_column_filters(1) == (*grid.rule_sets()[:6], sets[0])
    assert grid.metadata_column_filters(0) == grid.rule_sets()[:6]
    # Guardado: ida y vuelta; lo estropeado se salta
    assert filter_from_dict(filter_to_dict(grid)) == grid
    assert filter_to_dict(grid)["metadata"]["columns"][1]["values"] == [None, "Huesca", "Torla"]
    broken = filter_from_dict({"metadata": {"columns": [
        {"field": "city", "values": ["Huesca", True, [1], {"a": 1}, None, 3]},
        {"field": "file_name", "values": []}, "x", {"values": []},
        {"field": "captured_at", "values": ["2024-06", "2024-99", "2023"]},
        *({"field": "iso"} for _ in range(9)),
    ]}})  # fmt: skip
    assert broken.metadata.columns[:2] == (
        MetadataColumn("city", frozenset({"Huesca", None})),
        MetadataColumn("captured_at", frozenset({"2024-06", "2023"})),
    )
    assert len(broken.metadata.columns) == MAX_METADATA_COLUMNS
    assert filter_from_dict({"metadata": 3}).metadata == MetadataFilter()
    print("Autoprueba finalizada correctamente.")
