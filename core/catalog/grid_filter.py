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

Ejemplo:

    GridFilter(active=frozenset({FILTER_TEXT}), text=TextFilter(TEXT_ALL_FIELDS, "contains", "boda"))
        .rule_sets()
    -> (RuleSet(MATCH_ANY, (Rule("file_name", "contains", "boda"), Rule("title", ...),
                           Rule("description", ...), Rule("keyword", ...))),)

«Todos los campos disponibles» con «No contiene» es «ningún campo lo contiene» (MATCH_ALL
de «no contiene»); con los demás operadores, «alguno» (MATCH_ANY).

Todo es inmutable ('frozen'): un filtro se compara con '==' y se cambia creando otro
('with_panel', 'cleared', 'toggled', 'dataclasses.replace').

1.0.0 Primera versión (paso A.3, subpaso 1): pestañas, candado y fila de «Texto».

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.grid_filter
"""

__version__ = "1.0.0"
__all__ = [
    "FILTER_ATTRIBUTES",
    "FILTER_METADATA",
    "FILTER_PANELS",
    "FILTER_TEXT",
    "MAX_TEXT_LENGTH",
    "NO_FILTER",
    "TEXT_ALL_FIELDS",
    "TEXT_FIELDS",
    "TEXT_FILE_NAME",
    "TEXT_OPERATORS",
    "GridFilter",
    "TextFilter",
    "filter_from_dict",
    "filter_to_dict",
]

# Librerías estándar
from dataclasses import dataclass, field, replace
from typing import Any

# Módulos del proyecto
from core.catalog.smart_rules import MATCH_ALL, MATCH_ANY, Rule, RuleSet

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
class GridFilter:
    """Estado de la barra de filtros de un módulo (ver la cabecera).

    Attributes:
        active: Pestañas encendidas (claves de 'FILTER_PANELS'; vacío = «Ninguno»).
        remembered: Las que estaban encendidas al pasar a «Ninguno» (para Ctrl+L).
        locked: Candado cerrado: el filtro se mantiene al cambiar de origen.
        text: Fila de «Texto» (se conserva aunque su pestaña esté apagada).
    """

    active: frozenset[str] = frozenset()
    remembered: frozenset[str] = frozenset()
    locked: bool = False
    text: TextFilter = field(default_factory=TextFilter)

    @property
    def is_none(self) -> bool:
        """True si está en «Ninguno» (ninguna pestaña encendida)."""
        return not self.active

    def rule_sets(self) -> tuple[RuleSet, ...]:
        """Los conjuntos de reglas que aplican AHORA (de las pestañas encendidas que tienen
        algo que filtrar), en el orden de las pestañas. Vacío = no filtra nada."""
        sets: list[RuleSet] = []
        if FILTER_TEXT in self.active:
            text_rules = self.text.rule_set()
            if text_rules is not None:
                sets.append(text_rules)
        # «Atributos» y «Metadatos» aún no tienen panel (siguientes pasos)
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
    }


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
    # Pestañas sin panel todavía: no filtran
    assert NO_FILTER.with_panel(FILTER_ATTRIBUTES, True).rule_sets() == ()

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
    print("Autoprueba finalizada correctamente.")
