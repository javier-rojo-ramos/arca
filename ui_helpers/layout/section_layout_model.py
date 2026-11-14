"""Modelo de la colocación de las secciones de las barras laterales (única fuente de verdad).

Todas las interfaces que muestran o cambian el orden, la visibilidad o lo plegado de las
secciones (las barras, el menú de sus cabeceras, el arrastre, la página de Opciones) leen
y escriben AQUÍ, y se enteran de los cambios por la señal 'layout_changed'. Nadie guarda
su propia copia del orden.

Qué hace:
    - Al crearse, lee lo guardado en settings.json ('SETTING_SECTION_LAYOUT') y lo fusiona
      con el registro (secciones nuevas, 'id' desconocidos...: ver 'section_layout.py').
    - La PRIMERA vez (aún no hay nada guardado) recoge lo plegado que se guardaba antes de
      existir este modelo, para que nadie pierda cómo lo tenía, y lo guarda ya con el
      formato nuevo (ver '_import_legacy_states').
    - Cada cambio se guarda al momento y se avisa con 'layout_changed(modo, barra)'.
      Un cambio que no cambia nada (ocultar lo que ya está oculto) ni guarda ni avisa.
    - Si no se puede guardar, se anota en el registro y se sigue: el cambio vale mientras
      la aplicación esté abierta.

Uso:
    model = SectionLayoutModel(SECTION_REGISTRY, config, parent=window)
    model.layout_changed.connect(on_changed)           # (modo: str, barra: str)
    model.entries("image", Sidebar.LEFT)               # tupla de 'SectionEntry'
    model.title("image", "library")                    # «Biblioteca - Imagen»
    model.move("image", "keywords", 0)
    model.set_visible("image", "dates", False)
    model.set_expanded("image", "dates", False)
    model.reset("image")                               # o 'reset()': todos los modos
    model.reset("image", Sidebar.LEFT)                 # solo una barra de un modo
    model.is_default("image", Sidebar.LEFT)            # ¿hay algo que restaurar?

    Para una interfaz que edita y solo aplica al aceptar (la página de Opciones):
    layout = model.working_copy()                      # un 'SectionLayout' suelto
    layout.move(...); layout.set_visible(...); layout.reset(...)
    model.apply(layout)                                # ahora sí: guarda y avisa

La barra de la señal llega como texto ('Sidebar' es un 'StrEnum': se puede comparar con
'Sidebar.LEFT' directamente).

'config' es cualquier objeto con 'get(clave, defecto)' y 'set(clave, valor)' (como
'config.app_config.config'): así la autoprueba no toca el settings.json de verdad.

1.3.0 'working_copy' y 'apply': editar una copia y aplicarla de una vez (fase 4, la página
      «Paneles» de Opciones).
1.2.0 'reset' de una sola barra de un modo e 'is_default' (fase 2).
1.1.0 La primera vez, recoge lo plegado guardado con el formato anterior (fase 1b).
1.0.0 Primera versión (14/11/2026).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m ui_helpers.layout.section_layout_model
"""

__version__ = "1.3.0"
__all__ = ["SectionLayoutModel"]

# Librerías estándar
import logging
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal

# Módulos del proyecto
from config.app_constants import (
    SETTING_INSPECTOR_SECTIONS,
    SETTING_SECTION_LAYOUT,
    SETTING_SIDEBAR_STATE,
)
from ui_helpers.layout.section_layout import SectionEntry, SectionLayout
from ui_helpers.layout.section_registry import ModeSpec, SectionRegistry, SectionSpec, Sidebar

logger = logging.getLogger(__name__)

# Clave de settings.json con la carpeta del catálogo abierto la última vez (así la escribe
# 'ConfigManager.DEFAULTS'; no tiene constante)
_SETTING_CATALOG_PATH = "catalogo_ruta"


def _legacy_sections(entry: object, mode: str) -> dict | None:
    """Lo plegado de la barra izquierda de un modo, dentro de la entrada de un catálogo de
    'sidebar_state' ({id de la sección: desplegada}), o None si no consta.

    Entiende los dos formatos que ha tenido esa entrada: {"modules": {modo: {...}}} y el
    primero, que era directamente el estado de la barra del Catálogo.
    """
    if not isinstance(entry, dict):
        return None
    modules = entry.get("modules")
    if isinstance(modules, dict):
        state = modules.get(mode)
    else:
        state = entry if mode == "catalog" else None
    sections = state.get("sections") if isinstance(state, dict) else None
    return sections if isinstance(sections, dict) else None


def _import_legacy_states(layout: SectionLayout, registry: SectionRegistry, config: Any) -> None:
    """Pasa a 'layout' lo plegado que se guardaba antes de existir este modelo.

    - El inspector lo guardaba en 'inspector_sections', igual para todos los módulos: se
      copia a todos los modos (ahora es por modo).
    - Cada barra izquierda lo guardaba por catálogo, en 'sidebar_state': se toma lo del
      catálogo abierto la última vez y, si no tiene, lo del primero que lo tenga (ahora es
      común a todos los catálogos).

    Lo que no se entienda o nombre secciones que no existen se ignora. Las claves antiguas
    no se borran (en 'inspector_sections' hay además otras cosas), pero ya nadie las lee.
    """
    inspector = config.get(SETTING_INSPECTOR_SECTIONS, None)
    if isinstance(inspector, dict):
        for mode in registry.mode_keys():
            for section_id, expanded in inspector.items():
                if isinstance(expanded, bool) and layout.sidebar_of(mode, section_id) is Sidebar.RIGHT:
                    layout.set_expanded(mode, section_id, expanded)

    catalogs = config.get(SETTING_SIDEBAR_STATE, None)
    if not isinstance(catalogs, dict):
        return
    last = config.get(_SETTING_CATALOG_PATH, None)
    # El catálogo de la última vez, el primero; después, los demás
    entries = [catalogs[last]] if isinstance(last, str) and last in catalogs else []
    entries += [entry for key, entry in catalogs.items() if key != last]
    for mode in registry.mode_keys():
        sections = next(
            (found for entry in entries if (found := _legacy_sections(entry, mode)) is not None),
            None,
        )
        for section_id, expanded in (sections or {}).items():
            if isinstance(expanded, bool) and layout.sidebar_of(mode, section_id) is Sidebar.LEFT:
                layout.set_expanded(mode, section_id, expanded)


class SectionLayoutModel(QObject):
    """La colocación de las secciones, guardada y con aviso de cambios (ver el docstring
    del archivo).

    Signals:
        layout_changed(str, str): ha cambiado la colocación de una barra de un modo
            (modo, barra: el valor de 'Sidebar').
    """

    layout_changed = Signal(str, str)

    def __init__(
        self, registry: SectionRegistry, config: Any, parent: QObject | None = None
    ) -> None:
        """Lee lo guardado y lo fusiona con el registro.

        Args:
            registry: El registro de secciones (normalmente, 'SECTION_REGISTRY').
            config: La configuración de la aplicación ('get' y 'set').
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._registry = registry
        self._config = config
        saved = config.get(SETTING_SECTION_LAYOUT, None)
        self._layout = SectionLayout.from_state(saved, registry)
        if saved is None:
            # Primera vez: lo plegado que hubiera con el formato anterior, y se guarda ya
            # (así no se vuelve a importar)
            _import_legacy_states(self._layout, registry, config)
            self._save()

    # -------------------------------------------------------------------------
    # Consultas
    # -------------------------------------------------------------------------

    def modes(self) -> tuple[ModeSpec, ...]:
        """Los modos registrados, en su orden."""
        return self._registry.modes()

    def entries(self, mode: str, sidebar: Sidebar) -> tuple[SectionEntry, ...]:
        """Las secciones de esa barra en ese modo, de arriba abajo."""
        return self._layout.entries(mode, sidebar)

    def entry(self, mode: str, section_id: str) -> SectionEntry | None:
        """Una sección colocada, con su estado (None si no está en ese modo)."""
        return self._layout.entry(mode, section_id)

    def spec(self, section_id: str) -> SectionSpec | None:
        """Lo que declara una sección en el registro (None si no existe)."""
        return self._registry.get(section_id)

    def title(self, mode: str, section_id: str) -> str:
        """Título de una sección en ese modo ("" si no existe)."""
        spec = self._registry.get(section_id)
        return spec.title_for(mode) if spec is not None else ""

    # -------------------------------------------------------------------------
    # Cambios (guardan y avisan solo si cambia algo; devuelven True si cambia)
    # -------------------------------------------------------------------------

    def move(self, mode: str, section_id: str, index: int) -> bool:
        """Mueve una sección dentro de su barra a la posición 'index' (0 = la primera)."""
        return self._changed(mode, section_id, self._layout.move(mode, section_id, index))

    def set_visible(self, mode: str, section_id: str, visible: bool) -> bool:
        """Muestra u oculta una sección en ese modo."""
        changed = self._layout.set_visible(mode, section_id, visible)
        return self._changed(mode, section_id, changed)

    def set_expanded(self, mode: str, section_id: str, expanded: bool) -> bool:
        """Despliega o pliega una sección en ese modo."""
        changed = self._layout.set_expanded(mode, section_id, expanded)
        return self._changed(mode, section_id, changed)

    def reset(self, mode: str | None = None, sidebar: Sidebar | None = None) -> bool:
        """Restaura la colocación de partida de un modo (None = de todos) y de una barra
        (None = de las dos). Avisa por cada barra de cada modo que cambia."""
        changed = self._layout.reset(mode, sidebar)
        if not changed:
            return False
        self._save()
        for changed_mode, changed_sidebar in changed:
            self.layout_changed.emit(changed_mode, changed_sidebar.value)
        return True

    def is_default(self, mode: str, sidebar: Sidebar) -> bool:
        """True si esa barra de ese modo está como de partida (nada que restaurar)."""
        return self._layout.is_default(mode, sidebar)

    def working_copy(self) -> SectionLayout:
        """Una copia suelta de la colocación, para editarla sin que nada cambie hasta
        pasarla a 'apply' (así trabaja la página de Opciones, que solo aplica al aceptar)."""
        return SectionLayout.from_state(self._layout.to_state(), self._registry)

    def apply(self, layout: SectionLayout) -> bool:
        """Sustituye la colocación por la de 'layout' (una copia editada). Guarda una vez y
        avisa por cada barra de cada modo que queda distinta.

        Returns:
            True si cambia algo.
        """
        changed = [
            (mode, sidebar)
            for mode in self._registry.mode_keys()
            for sidebar in Sidebar
            if layout.entries(mode, sidebar) != self._layout.entries(mode, sidebar)
        ]
        if not changed:
            return False
        # Otra copia (pasada por el registro): lo que haga después quien la editaba no
        # toca la del modelo
        self._layout = SectionLayout.from_state(layout.to_state(), self._registry)
        self._save()
        for changed_mode, changed_sidebar in changed:
            self.layout_changed.emit(changed_mode, changed_sidebar.value)
        return True

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _changed(self, mode: str, section_id: str, changed: bool) -> bool:
        """Tras un cambio de una sección: si lo ha habido, guarda y avisa de su barra."""
        if not changed:
            return False
        self._save()
        sidebar = self._layout.sidebar_of(mode, section_id)
        if sidebar is not None:
            self.layout_changed.emit(mode, sidebar.value)
        return True

    def _save(self) -> None:
        """Escribe la colocación en settings.json (un fallo no interrumpe a la interfaz)."""
        try:
            # 'to_state' crea un diccionario nuevo cada vez: 'ConfigManager.set' compara
            # con el anterior para saber si hay que escribir
            self._config.set(SETTING_SECTION_LAYOUT, self._layout.to_state())
        except Exception:
            # No poder guardarlo no debe romper la interfaz: el cambio ya está hecho
            logger.exception("No se pudo guardar la colocación de las secciones.")


if __name__ == "__main__":
    # Autoprueba, sin ventana y sin tocar el settings.json de verdad (configuración de
    # mentira). Desde la raíz del proyecto:
    #     python -m ui_helpers.layout.section_layout_model
    import copy

    from ui_helpers.layout.section_registry import SECTION_REGISTRY

    class _FakeConfig:
        """Lo mínimo de 'ConfigManager': un diccionario, y cuántas veces se escribe."""

        def __init__(self, data: dict | None = None, *, fail: bool = False) -> None:
            self.data = data or {}
            self.writes = 0
            self.fail = fail

        def get(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            if self.fail:
                raise OSError("disco lleno")
            self.writes += 1
            self.data[key] = copy.deepcopy(value)

    def _ids(model: SectionLayoutModel, mode: str, sidebar: Sidebar = Sidebar.LEFT) -> list[str]:
        return [entry.id for entry in model.entries(mode, sidebar)]

    # --- Sin nada guardado: la colocación de partida, que se guarda ya (una vez)
    config = _FakeConfig()
    model = SectionLayoutModel(SECTION_REGISTRY, config)
    seen: list[tuple[str, str]] = []
    model.layout_changed.connect(lambda mode, sidebar: seen.append((mode, sidebar)))
    assert _ids(model, "image") == ["library", "folders", "dates", "keywords"]
    assert model.title("image", "library") == "Biblioteca - Imagen" and model.title("image", "x") == ""
    assert [mode.key for mode in model.modes()] == ["catalog", "image", "video", "audio", "tracks"]
    assert config.writes == 1 and not seen
    config.writes = 0

    # --- Cada cambio guarda y avisa una vez, con su modo y su barra
    assert model.move("image", "keywords", 0) is True
    assert seen == [("image", "left")] and config.writes == 1
    assert seen[0][1] == Sidebar.LEFT  # el texto de la señal se compara con el enumerado
    assert model.set_visible("image", "dates", False) is True
    assert model.set_expanded("image", "metadata", False) is True
    assert seen[1:] == [("image", "left"), ("image", "right")] and config.writes == 3
    # Lo que no cambia nada, ni guarda ni avisa
    assert model.move("image", "keywords", 0) is False
    assert model.set_visible("image", "dates", False) is False
    assert model.set_visible("image", "no_existe", False) is False
    assert model.set_expanded("no_existe", "dates", False) is False
    assert len(seen) == 3 and config.writes == 3

    # --- Otro modelo con la misma configuración (otra sesión) recupera lo mismo
    again = SectionLayoutModel(SECTION_REGISTRY, config)
    assert _ids(again, "image") == ["keywords", "library", "folders", "dates"]
    assert again.entry("image", "dates").visible is False
    assert again.entry("image", "metadata").expanded is False
    assert again.entry("catalog", "metadata").expanded is True  # por modo: el Catálogo, no
    assert config.writes == 3  # cargar no escribe

    # --- Restaurar un modo: avisa de sus dos barras; los demás, sin tocar
    model.set_visible("catalog", "folders", False)
    seen.clear()
    assert model.reset("image") is True
    assert seen == [("image", "left"), ("image", "right")]
    assert _ids(model, "image") == ["library", "folders", "dates", "keywords"]
    assert model.entry("catalog", "folders").visible is False
    assert model.reset("image") is False and len(seen) == 2
    # Restaurar todos: solo avisa de los que cambian
    seen.clear()
    assert model.reset() is True and seen == [("catalog", "left")]
    assert model.reset() is False
    # Restaurar una sola barra de un modo
    model.set_visible("image", "dates", False)
    model.set_expanded("image", "metadata", False)
    seen.clear()
    assert not model.is_default("image", Sidebar.LEFT)
    assert model.reset("image", Sidebar.LEFT) is True and seen == [("image", "left")]
    assert model.is_default("image", Sidebar.LEFT) and not model.is_default("image", Sidebar.RIGHT)
    assert model.entry("image", "metadata").expanded is False
    assert model.reset() is True

    # --- Editar una copia y aplicarla de una vez (la página de Opciones)
    writes = config.writes
    seen.clear()
    draft = model.working_copy()
    draft.move("image", "keywords", 0)
    draft.set_visible("catalog", "folders", False)
    assert _ids(model, "image")[0] == "library" and not seen and config.writes == writes
    assert model.apply(draft) is True and config.writes == writes + 1
    assert sorted(seen) == [("catalog", "left"), ("image", "left")], seen
    assert _ids(model, "image")[0] == "keywords" and not model.entry("catalog", "folders").visible
    assert model.apply(draft) is False and config.writes == writes + 1  # ya está igual
    draft.reset()  # lo que se haga después con la copia no toca el modelo
    assert _ids(model, "image")[0] == "keywords"
    assert model.apply(draft) is True and model.is_default("image", Sidebar.LEFT)

    # --- Lo guardado ilegible o de otra versión: de partida, sin error
    for bad in ("roto", {"version": 99, "modes": {}}, []):
        broken = SectionLayoutModel(SECTION_REGISTRY, _FakeConfig({SETTING_SECTION_LAYOUT: bad}))
        assert _ids(broken, "catalog") == ["catalog", "folders", "collections"], bad

    # --- La primera vez se recoge lo plegado guardado con el formato anterior
    legacy = _FakeConfig({
        "catalogo_ruta": "C:/cat2",
        SETTING_INSPECTOR_SECTIONS: {"metadata": False, "keyword_editor.recent": False, "selection": "x"},
        SETTING_SIDEBAR_STATE: {
            # el primer formato: el estado de la barra del Catálogo, sin "modules"
            "C:/viejo": {"sections": {"catalog": False}, "expanded_folders": []},
            "C:/cat1": {"modules": {"catalog": {"sections": {"folders": False}},
                                    "image": {"sections": {"dates": False, "no_existe": False}}}},
            # el de la última vez manda; no tiene nada de Imagen: se toma del primero que sí
            "C:/cat2": {"modules": {"catalog": {"sections": {"collections": False, "folders": 3}}}},
        },
    })  # fmt: skip
    imported = SectionLayoutModel(SECTION_REGISTRY, legacy)

    def _folded(mode: str, sidebar: Sidebar) -> list[str]:
        return [entry.id for entry in imported.entries(mode, sidebar) if not entry.expanded]

    assert _folded("catalog", Sidebar.LEFT) == ["collections"], _folded("catalog", Sidebar.LEFT)
    assert _folded("image", Sidebar.LEFT) == ["dates"]
    for mode_key in SECTION_REGISTRY.mode_keys():  # el inspector, a todos los modos
        assert _folded(mode_key, Sidebar.RIGHT) == ["metadata"], mode_key
    assert legacy.writes == 1 and SETTING_SECTION_LAYOUT in legacy.data
    # La segunda vez ya hay algo guardado: no se vuelve a importar
    legacy.data[SETTING_INSPECTOR_SECTIONS] = {"selection": False}
    assert SectionLayoutModel(SECTION_REGISTRY, legacy).entry("image", "selection").expanded is True
    # Con lo antiguo ilegible, la colocación de partida
    for bad_key in (SETTING_INSPECTOR_SECTIONS, SETTING_SIDEBAR_STATE):
        odd = SectionLayoutModel(SECTION_REGISTRY, _FakeConfig({bad_key: ["roto"], "catalogo_ruta": 7}))
        assert all(e.expanded for e in odd.entries("catalog", Sidebar.LEFT))
    odd = SectionLayoutModel(
        SECTION_REGISTRY, _FakeConfig({SETTING_SIDEBAR_STATE: {"a": "roto", "b": {"modules": []}}})
    )
    assert all(e.expanded for e in odd.entries("catalog", Sidebar.LEFT))

    # --- Si no se puede guardar, el cambio vale igual y se avisa (queda en el registro)
    logging.disable(logging.CRITICAL)  # el error esperado no ensucia la salida
    failing = SectionLayoutModel(SECTION_REGISTRY, _FakeConfig(fail=True))
    failing.layout_changed.connect(lambda mode, sidebar: seen.append((mode, sidebar)))
    seen.clear()
    assert failing.move("catalog", "collections", 0) is True
    assert _ids(failing, "catalog") == ["collections", "catalog", "folders"] and len(seen) == 1
    logging.disable(logging.NOTSET)

    print("Autoprueba finalizada correctamente.")
