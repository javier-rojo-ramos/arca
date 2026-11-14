"""Colocación de las secciones de las barras laterales: orden, visibles y desplegadas.

Este módulo NO depende de Qt: es Python puro. La interfaz no lo usa directamente, sino a
través de 'section_layout_model.py' (que guarda y avisa de los cambios).

Para cada MODO y cada BARRA guarda una lista ordenada de secciones, cada una con si se ve y
si está desplegada:

    modo ─▶ barra ─▶ [SectionEntry(id, visible, expanded), ...]   (de arriba abajo)

Qué secciones existen y cuál es su colocación de partida lo dice el registro
('section_registry.py'). Aquí está lo que el usuario cambia sobre eso.

Cómo se guarda (para JSON; siempre por 'id', nunca por posición numérica):

    {"version": 1,
     "modes": {"image": {"left":  [{"id": "library", "visible": true, "expanded": true},
                                   {"id": "dates", "visible": false, "expanded": true}],
                         "right": [...]}}}

Al cargar ('SectionLayout.from_state') lo guardado se FUSIONA con el registro:
    - Las secciones guardadas que siguen existiendo conservan su orden y su estado.
    - Una sección nueva (registrada después de guardar) entra en su posición de partida:
      justo detrás de la sección que la precede en el orden de partida (la más cercana que
      esté en la lista); si no hay ninguna, la primera.
    - Lo desconocido se ignora sin error: un 'id' que ya no existe o que no es de ese modo o
      de esa barra, un 'id' repetido (vale el primero), un modo que no existe, un dato mal
      formado (un 'visible' que no es booleano toma su valor de partida).
    - Otra versión del formato (o ninguna): la colocación de partida. Si el formato cambia,
      se sube 'LAYOUT_VERSION' y se escribe aquí la conversión desde la anterior.

Uso:
    layout = SectionLayout.from_state(saved, SECTION_REGISTRY)
    layout.entries("image", Sidebar.LEFT)          # tupla de 'SectionEntry'
    layout.move("image", "keywords", 0)            # True si cambia
    layout.set_visible("image", "dates", False)
    layout.set_expanded("image", "dates", False)
    layout.reset("image")                          # o 'reset()' para todos los modos
    layout.reset("image", Sidebar.LEFT)            # solo una barra de un modo
    layout.is_default("image", Sidebar.LEFT)       # True si está como de partida
    saved = layout.to_state()

1.1.0 'reset' de una sola barra de un modo (devuelve los pares (modo, barra) que cambian) e
      'is_default' (fase 2: «Restaurar por defecto» del menú de las cabeceras).
1.0.0 Primera versión (14/11/2026).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.layout.section_layout
"""

__version__ = "1.1.0"
__all__ = ["LAYOUT_VERSION", "SectionEntry", "SectionLayout"]

# Librerías estándar
from dataclasses import dataclass, replace
from typing import Any

# Módulos del proyecto
from ui_helpers.layout.section_registry import SectionRegistry, Sidebar

# Versión del formato guardado (ver el docstring del archivo)
LAYOUT_VERSION = 1

# Claves del formato guardado
_VERSION_KEY = "version"
_MODES_KEY = "modes"
_ID_KEY = "id"
_VISIBLE_KEY = "visible"
_EXPANDED_KEY = "expanded"


@dataclass(frozen=True, slots=True)
class SectionEntry:
    """Una sección colocada en una barra.

    Attributes:
        id: El 'id' de la sección en el registro.
        visible: Si el usuario la tiene a la vista (otra cosa es que tenga algo que
            mostrar: una sección del inspector puede no aplicarse a lo seleccionado).
        expanded: Si está desplegada.
    """

    id: str
    visible: bool = True
    expanded: bool = True


class SectionLayout:
    """La colocación de las secciones de todos los modos (ver el docstring del archivo)."""

    def __init__(self, registry: SectionRegistry) -> None:
        """Crea la colocación de partida de ese registro."""
        self._registry = registry
        self._modes: dict[str, dict[Sidebar, list[SectionEntry]]] = {}
        self.reset()

    # -------------------------------------------------------------------------
    # Consultas
    # -------------------------------------------------------------------------

    def entries(self, mode: str, sidebar: Sidebar) -> tuple[SectionEntry, ...]:
        """Las secciones de esa barra en ese modo, de arriba abajo (vacío si el modo no
        existe)."""
        return tuple(self._modes.get(mode, {}).get(sidebar, ()))

    def sidebar_of(self, mode: str, section_id: str) -> Sidebar | None:
        """La barra en la que está una sección en ese modo (None si no está en él)."""
        found = self._find(mode, section_id)
        return found[0] if found is not None else None

    def entry(self, mode: str, section_id: str) -> SectionEntry | None:
        """La sección colocada, con su estado (None si no está en ese modo)."""
        found = self._find(mode, section_id)
        return found[2] if found is not None else None

    # -------------------------------------------------------------------------
    # Cambios (devuelven True si cambia algo)
    # -------------------------------------------------------------------------

    def move(self, mode: str, section_id: str, index: int) -> bool:
        """Mueve una sección dentro de su barra para que quede en la posición 'index' (0 =
        la primera; si se pasa, la última)."""
        found = self._find(mode, section_id)
        if found is None:
            return False
        sidebar, current, entry = found
        entries = self._modes[mode][sidebar]
        index = max(0, min(index, len(entries) - 1))
        if index == current:
            return False
        entries.pop(current)
        entries.insert(index, entry)
        return True

    def set_visible(self, mode: str, section_id: str, visible: bool) -> bool:
        """Muestra u oculta una sección en ese modo."""
        return self._replace(mode, section_id, visible=bool(visible))

    def set_expanded(self, mode: str, section_id: str, expanded: bool) -> bool:
        """Despliega o pliega una sección en ese modo."""
        return self._replace(mode, section_id, expanded=bool(expanded))

    def reset(
        self, mode: str | None = None, sidebar: Sidebar | None = None
    ) -> tuple[tuple[str, Sidebar], ...]:
        """Vuelve a la colocación de partida del registro.

        Args:
            mode: El modo que se restaura; None = todos.
            sidebar: La barra que se restaura; None = las dos. (Vale mientras cada sección
                sea de una sola barra, como hoy: si un día se mueven entre barras, restaurar
                solo una tendría que recoger también las suyas que estén en la otra.)

        Returns:
            Los pares (modo, barra) que han cambiado.
        """
        keys = self._registry.mode_keys()
        changed = []
        for key in keys if mode is None else (mode,):
            if key not in keys:
                continue
            default = self._default_mode(key)
            current = self._modes.setdefault(key, {side: [] for side in Sidebar})
            for side in Sidebar if sidebar is None else (sidebar,):
                if current[side] != default[side]:
                    current[side] = default[side]
                    changed.append((key, side))
        return tuple(changed)

    def is_default(self, mode: str, sidebar: Sidebar) -> bool:
        """True si esa barra de ese modo está como de partida (orden, visibles y
        desplegadas): no hay nada que restaurar."""
        return list(self.entries(mode, sidebar)) == self._default_mode(mode)[sidebar]

    # -------------------------------------------------------------------------
    # Guardar y cargar
    # -------------------------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        """La colocación de todos los modos, para JSON (ver el docstring del archivo)."""
        return {
            _VERSION_KEY: LAYOUT_VERSION,
            _MODES_KEY: {
                mode: {
                    sidebar.value: [
                        {_ID_KEY: e.id, _VISIBLE_KEY: e.visible, _EXPANDED_KEY: e.expanded}
                        for e in sidebars[sidebar]
                    ]
                    for sidebar in Sidebar
                }
                for mode, sidebars in self._modes.items()
            },
        }

    @classmethod
    def from_state(cls, state: object, registry: SectionRegistry) -> "SectionLayout":
        """Recupera lo guardado con 'to_state', fusionado con el registro (ver el
        docstring del archivo). Nunca falla: lo que no se entiende se ignora."""
        layout = cls(registry)  # la de partida: lo que no esté guardado se queda así
        if not isinstance(state, dict):
            return layout
        version = state.get(_VERSION_KEY)
        # 'type(...) is int': True también es un 'int' en Python
        if type(version) is not int or version != LAYOUT_VERSION:
            return layout
        saved_modes = state.get(_MODES_KEY)
        if not isinstance(saved_modes, dict):
            return layout
        for mode in registry.mode_keys():
            saved = saved_modes.get(mode)
            if isinstance(saved, dict):
                layout._modes[mode] = layout._merged_mode(mode, saved)
        return layout

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _find(self, mode: str, section_id: str) -> tuple[Sidebar, int, SectionEntry] | None:
        """(barra, posición, sección) de una sección en un modo, o None."""
        for sidebar, entries in self._modes.get(mode, {}).items():
            for index, entry in enumerate(entries):
                if entry.id == section_id:
                    return sidebar, index, entry
        return None

    def _replace(self, mode: str, section_id: str, **changes: bool) -> bool:
        """Cambia campos de una sección colocada; True si queda distinta."""
        found = self._find(mode, section_id)
        if found is None:
            return False
        sidebar, index, entry = found
        updated = replace(entry, **changes)
        if updated == entry:
            return False
        self._modes[mode][sidebar][index] = updated
        return True

    def _default_mode(self, mode: str) -> dict[Sidebar, list[SectionEntry]]:
        """La colocación de partida de un modo."""
        return {
            sidebar: [
                SectionEntry(spec.id, spec.visible, spec.expanded)
                for spec in self._registry.defaults(mode, sidebar)
            ]
            for sidebar in Sidebar
        }

    def _merged_mode(self, mode: str, saved: dict) -> dict[Sidebar, list[SectionEntry]]:
        """Lo guardado de un modo, fusionado con el registro."""
        result: dict[Sidebar, list[SectionEntry]] = {sidebar: [] for sidebar in Sidebar}
        placed: set[str] = set()

        # 1. Lo guardado que sigue valiendo, en su orden
        for sidebar in Sidebar:
            items = saved.get(sidebar.value)
            if not isinstance(items, list):
                continue
            for item in items:
                section_id = item.get(_ID_KEY) if isinstance(item, dict) else None
                if (
                    not isinstance(section_id, str)
                    or section_id in placed
                    or not self._registry.allowed(mode, sidebar, section_id)
                ):
                    continue
                spec = self._registry.get(section_id)
                result[sidebar].append(
                    SectionEntry(
                        section_id,
                        _as_bool(item.get(_VISIBLE_KEY), spec.visible),
                        _as_bool(item.get(_EXPANDED_KEY), spec.expanded),
                    )
                )
                placed.add(section_id)

        # 2. Las secciones nuevas, cada una detrás de la que la precede en el orden de
        #    partida. Se recorren en ese orden: así varias nuevas seguidas quedan en fila
        for sidebar in Sidebar:
            default_ids = [spec.id for spec in self._registry.defaults(mode, sidebar)]
            for position, section_id in enumerate(default_ids):
                if section_id in placed:
                    continue
                current_ids = [entry.id for entry in result[sidebar]]
                index = 0  # sin ninguna anterior en la lista: la primera
                for previous in reversed(default_ids[:position]):
                    if previous in current_ids:
                        index = current_ids.index(previous) + 1
                        break
                spec = self._registry.get(section_id)
                result[sidebar].insert(index, SectionEntry(section_id, spec.visible, spec.expanded))
                placed.add(section_id)
        return result


def _as_bool(value: object, default: bool) -> bool:
    """'value' si es un booleano; si no, 'default'."""
    return value if isinstance(value, bool) else default


if __name__ == "__main__":
    # Autoprueba (sin Qt). Desde la raíz del proyecto:
    #     python -m ui_helpers.layout.section_layout
    import json

    from ui_helpers.layout.section_registry import LEFT, RIGHT, SECTION_REGISTRY, SectionSpec

    def _ids(layout: SectionLayout, mode: str, sidebar: Sidebar = Sidebar.LEFT) -> list[str]:
        return [entry.id for entry in layout.entries(mode, sidebar)]

    def _registry(*left_ids: str) -> SectionRegistry:
        """Un registro de prueba: modos 'a' y 'b'; en la izquierda, las secciones pedidas
        (de 100 en 100); en la derecha, 'info' (y 'closed', que empieza plegada y oculta)."""
        reg = SectionRegistry()
        reg.register_mode("a", "A")
        reg.register_mode("b", "B")
        for number, section_id in enumerate(left_ids, start=1):
            reg.register(SectionSpec(section_id, section_id.title(), LEFT, number * 100))
        reg.register(SectionSpec("info", "Info", RIGHT, 100))
        reg.register(SectionSpec("closed", "Cerrada", RIGHT, 200, visible=False, expanded=False))
        return reg

    # --- De partida: lo que dice el registro (con el de la aplicación, lo que hay hoy)
    app = SectionLayout(SECTION_REGISTRY)
    assert _ids(app, "catalog") == ["catalog", "folders", "collections"]
    assert _ids(app, "image") == ["library", "folders", "dates", "keywords"]
    assert _ids(app, "image", Sidebar.RIGHT) == ["selection", "keyword_editor", "keyword_list", "metadata"]
    assert all(e.visible and e.expanded for e in app.entries("image", Sidebar.LEFT))
    assert app.entries("no_existe", Sidebar.LEFT) == ()
    # Sin cambios, cargar lo guardado da lo mismo; y lo guardado cabe en JSON
    assert SectionLayout.from_state(json.loads(json.dumps(app.to_state())), SECTION_REGISTRY).to_state() == app.to_state()

    reg = _registry("one", "two", "three")
    layout = SectionLayout(reg)
    assert layout.entry("a", "closed") == SectionEntry("closed", visible=False, expanded=False)
    assert layout.sidebar_of("a", "info") is Sidebar.RIGHT and layout.sidebar_of("a", "zzz") is None

    # --- Mover: dentro de su barra, solo en ese modo; fuera de rango = al extremo
    assert layout.move("a", "three", 0) is True and _ids(layout, "a") == ["three", "one", "two"]
    assert layout.move("a", "three", 0) is False
    assert layout.move("a", "three", 99) is True and _ids(layout, "a") == ["one", "two", "three"]
    assert layout.move("a", "two", -5) is True and _ids(layout, "a") == ["two", "one", "three"]
    assert layout.move("a", "zzz", 0) is False and layout.move("zzz", "one", 0) is False
    assert _ids(layout, "b") == ["one", "two", "three"]  # el otro modo, sin tocar

    # --- Visible y desplegada
    assert layout.set_visible("a", "one", False) is True
    assert layout.set_visible("a", "one", False) is False
    assert layout.set_expanded("a", "info", False) is True
    assert layout.entry("a", "one") == SectionEntry("one", visible=False, expanded=True)
    assert layout.entry("b", "one") == SectionEntry("one")
    assert layout.set_visible("a", "zzz", False) is False

    # --- Guardar y cargar: igual
    saved = json.loads(json.dumps(layout.to_state()))
    assert saved["version"] == LAYOUT_VERSION
    assert saved["modes"]["a"]["left"][0] == {"id": "two", "visible": True, "expanded": True}
    again = SectionLayout.from_state(saved, reg)
    assert again.to_state() == layout.to_state()

    # --- Fusión: secciones nuevas en su posición de partida
    # Guardado: two, one, three ('one' oculta). Registro nuevo: zero, one, mid, two, three, last
    grown = SectionLayout.from_state(saved, _registry("zero", "one", "mid", "two", "three", "last"))
    #   zero: nadie antes -> la primera; mid: detrás de 'one'; last: detrás de 'three'
    assert _ids(grown, "a") == ["zero", "two", "one", "mid", "three", "last"], _ids(grown, "a")
    assert grown.entry("a", "one").visible is False  # lo guardado se conserva
    assert grown.entry("a", "mid") == SectionEntry("mid")
    # Varias nuevas seguidas quedan en fila, en su orden
    row = SectionLayout.from_state(saved, _registry("one", "n1", "n2", "two", "three"))
    assert _ids(row, "a") == ["two", "one", "n1", "n2", "three"], _ids(row, "a")

    # --- Fusión: lo desconocido se ignora
    shrunk = SectionLayout.from_state(saved, _registry("one", "three"))  # 'two' ya no existe
    assert _ids(shrunk, "a") == ["one", "three"]
    odd = {
        "version": 1,
        "modes": {
            "a": {
                "left": [
                    {"id": "three"},                      # sin estado: el de partida
                    {"id": "info"},                       # no es de esta barra
                    {"id": "ghost", "visible": False},    # no existe
                    {"id": "three", "visible": False},    # repetida: vale la primera
                    "roto", None, {"id": 7}, {"visible": True},
                    {"id": "one", "visible": "no", "expanded": 0},  # mal formado
                ],
                "right": "roto",
            },
            "b": [],           # mal formado: el modo, de partida
            "borrado": {"left": [{"id": "one"}]},  # modo que no existe
        },
    }
    merged = SectionLayout.from_state(odd, reg)
    # 'two' falta en lo guardado: entra detrás de 'one', que es quien la precede
    assert _ids(merged, "a") == ["three", "one", "two"], _ids(merged, "a")
    assert merged.entry("a", "three") == SectionEntry("three")
    assert merged.entry("a", "one") == SectionEntry("one")
    assert _ids(merged, "a", Sidebar.RIGHT) == ["info", "closed"]
    assert _ids(merged, "b") == ["one", "two", "three"]
    assert "borrado" not in merged.to_state()["modes"]

    # --- Otra versión, ninguna o algo ilegible: la colocación de partida
    default_state = SectionLayout(reg).to_state()
    for bad in (None, [], "x", {}, {"modes": saved["modes"]}, {**saved, "version": 2},
                {**saved, "version": True}, {**saved, "version": "1"}, {"version": 1, "modes": []}):  # fmt: skip
        assert SectionLayout.from_state(bad, reg).to_state() == default_state, bad

    # --- Una sección que vale en las dos barras se queda en la que se guardó
    both = _registry("one")
    both.register(SectionSpec("any", "Cualquiera", LEFT | RIGHT, 50))
    assert _ids(SectionLayout(both), "a") == ["any", "one"]
    moved = SectionLayout.from_state(
        {"version": 1, "modes": {"a": {"left": [{"id": "one"}], "right": [{"id": "any"}, {"id": "info"}]}}},
        both,
    )
    assert _ids(moved, "a") == ["one"] and _ids(moved, "a", Sidebar.RIGHT) == ["any", "info", "closed"]

    # --- Restaurar: un modo o todos
    layout.move("b", "three", 0)
    assert not layout.is_default("a", Sidebar.LEFT) and not layout.is_default("a", Sidebar.RIGHT)
    assert layout.is_default("b", Sidebar.RIGHT)
    # ...solo una barra: la otra se queda como estaba
    assert layout.reset("a", Sidebar.RIGHT) == (("a", Sidebar.RIGHT),)
    assert layout.entry("a", "info").expanded is True and _ids(layout, "a") == ["two", "one", "three"]
    assert layout.is_default("a", Sidebar.RIGHT) and layout.reset("a", Sidebar.RIGHT) == ()
    layout.set_expanded("a", "info", False)
    both_sides = (("a", Sidebar.LEFT), ("a", Sidebar.RIGHT))
    assert layout.reset("a") == both_sides and _ids(layout, "a") == ["one", "two", "three"]
    assert layout.is_default("a", Sidebar.LEFT)
    assert layout.entry("a", "one").visible is True and _ids(layout, "b") == ["three", "one", "two"]
    assert layout.reset("a") == () and layout.reset("zzz") == ()
    layout.set_expanded("a", "two", False)
    assert layout.reset() == (("a", Sidebar.LEFT), ("b", Sidebar.LEFT))
    assert layout.to_state() == default_state

    print("Autoprueba finalizada correctamente.")
