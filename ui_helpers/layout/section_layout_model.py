"""Modelo de la colocación de las secciones de las barras laterales (única fuente de verdad).

Todas las interfaces que muestran o cambian el orden, la visibilidad o lo plegado de las
secciones (las barras, el menú de sus cabeceras, el arrastre, la página de Opciones) leen
y escriben AQUÍ, y se enteran de los cambios por la señal 'layout_changed'. Nadie guarda
su propia copia del orden.

Qué hace:
    - Al crearse, lee lo guardado en settings.json ('SETTING_SECTION_LAYOUT') y lo fusiona
      con el registro (secciones nuevas, 'id' desconocidos...: ver 'section_layout.py').
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

La barra de la señal llega como texto ('Sidebar' es un 'StrEnum': se puede comparar con
'Sidebar.LEFT' directamente).

'config' es cualquier objeto con 'get(clave, defecto)' y 'set(clave, valor)' (como
'config.app_config.config'): así la autoprueba no toca el settings.json de verdad.

1.0.0 Primera versión (14/11/2026).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m ui_helpers.layout.section_layout_model
"""

__version__ = "1.0.0"
__all__ = ["SectionLayoutModel"]

# Librerías estándar
import logging
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal

# Módulos del proyecto
from config.app_constants import SETTING_SECTION_LAYOUT
from ui_helpers.layout.section_layout import SectionEntry, SectionLayout
from ui_helpers.layout.section_registry import ModeSpec, SectionRegistry, SectionSpec, Sidebar

logger = logging.getLogger(__name__)


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
        self._layout = SectionLayout.from_state(config.get(SETTING_SECTION_LAYOUT, None), registry)

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

    def reset(self, mode: str | None = None) -> bool:
        """Restaura la colocación de partida de un modo (None = de todos). Avisa por cada
        barra de cada modo que cambia."""
        modes = self._layout.reset(mode)
        if not modes:
            return False
        self._save()
        for changed_mode in modes:
            for sidebar in Sidebar:
                self.layout_changed.emit(changed_mode, sidebar.value)
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

    # --- Sin nada guardado: la colocación de partida, y nada escrito todavía
    config = _FakeConfig()
    model = SectionLayoutModel(SECTION_REGISTRY, config)
    seen: list[tuple[str, str]] = []
    model.layout_changed.connect(lambda mode, sidebar: seen.append((mode, sidebar)))
    assert _ids(model, "image") == ["library", "folders", "dates", "keywords"]
    assert model.title("image", "library") == "Biblioteca - Imagen" and model.title("image", "x") == ""
    assert [mode.key for mode in model.modes()] == ["catalog", "image", "video", "audio"]
    assert config.writes == 0 and not seen

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
    assert model.reset() is True and seen == [("catalog", "left"), ("catalog", "right")]
    assert model.reset() is False

    # --- Lo guardado ilegible o de otra versión: de partida, sin error
    for bad in ("roto", {"version": 99, "modes": {}}, []):
        broken = SectionLayoutModel(SECTION_REGISTRY, _FakeConfig({SETTING_SECTION_LAYOUT: bad}))
        assert _ids(broken, "catalog") == ["catalog", "folders", "collections"], bad

    # --- Si no se puede guardar, el cambio vale igual y se avisa (queda en el registro)
    logging.disable(logging.CRITICAL)  # el error esperado no ensucia la salida
    failing = SectionLayoutModel(SECTION_REGISTRY, _FakeConfig(fail=True))
    failing.layout_changed.connect(lambda mode, sidebar: seen.append((mode, sidebar)))
    seen.clear()
    assert failing.move("catalog", "collections", 0) is True
    assert _ids(failing, "catalog") == ["collections", "catalog", "folders"] and len(seen) == 1
    logging.disable(logging.NOTSET)

    print("Autoprueba finalizada correctamente.")
