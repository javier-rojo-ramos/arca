"""Desplegable de los ajustes personalizados de la barra de filtros (antes del candado).

    Ubicación ▾
    ┌─────────────────────────────────────────────────────────┐
    │ Guardar filtro activo como nuevo ajuste personalizado…  │
    │ Gestionar ajustes personalizados…                       │
    │ Restaurar filtro activo a sus valores por defecto       │
    │ ─────────────────────────────────────────────────────── │
    │   Columnas de partida                                   │
    │ ✓ Ubicación                                             │
    │   ...                                                   │
    └─────────────────────────────────────────────────────────┘

Un botón de texto (como las pestañas de la barra): el nombre del ajuste con el que
coincide el filtro; si no coincide con ninguno, «Personalizado» o, con «Ninguno» (nada
encendido), «Sin filtro»; detrás, «▾». Al pulsarlo, el
menú: las acciones arriba y la lista de ajustes del módulo abajo (decidido por el autor el
09/11/2026), con ✓ en el que coincide.

Solo muestra y avisa: no sabe qué es un ajuste ni un filtro. Lo que se ve es siempre lo que
le dicen con 'set_state' (lo hace 'controllers/filter_preset_controller.py'):
    - «Guardar…»:    'save_requested()'.
    - «Gestionar…»:  'manage_requested()'.
    - «Restaurar…»:  'reset_requested()'.
    - Un ajuste:     'preset_chosen(posición)' (en la lista que se le pasó).

Lo crea la barra de filtros ('FilterBar.preset_button'). No coge el foco.

Uso:
    button.set_state(["Columnas de partida", "Ubicación"], current=1, filtering=True,
                     can_save=True, can_reset=True, can_manage=True)
    button.preset_chosen.connect(...)

1.1.0 Sin ajuste que coincida: «Personalizado» si hay algo encendido y «Sin filtro» con
      «Ninguno» ('set_state(..., filtering=)'); lo pidió el autor el 09/11/2026.
1.0.1 «Sin filtro» en lugar de «Ajustes» cuando no coincide ningún ajuste (lo pidió el
      autor el 09/11/2026).
1.0.0 Primera versión (paso A.3, filtros personalizados, subpaso 2).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.filter_preset_button
"""

__version__ = "1.1.0"
__all__ = [
    "CUSTOM_TEXT",
    "MANAGE_TEXT",
    "NO_FILTER_TEXT",
    "PRESET_OBJECT_NAME",
    "RESET_TEXT",
    "SAVE_TEXT",
    "TOOLTIP_TEXT",
    "FilterPresetButton",
]

# Librerías estándar
from collections.abc import Iterable

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QAction
from qtpy.QtWidgets import QMenu, QToolButton, QWidget

# Textos de la interfaz
SAVE_TEXT = "Guardar filtro activo como nuevo ajuste personalizado…"
MANAGE_TEXT = "Gestionar ajustes personalizados…"
RESET_TEXT = "Restaurar filtro activo a sus valores por defecto"
# En el botón, si el filtro no coincide con ningún ajuste: con algo encendido o con «Ninguno»
CUSTOM_TEXT = "Personalizado"
NO_FILTER_TEXT = "Sin filtro"
TOOLTIP_TEXT = "Ajustes personalizados del filtro"
_ARROW = " ▾"  # tras el nombre: se puede pulsar (sin la flecha de Fusion)

# Nombre de objeto (lo usa el QSS de 'ui_theme.py')
PRESET_OBJECT_NAME = "btn_filter_presets"


class FilterPresetButton(QToolButton):
    """Botón con el menú de los ajustes personalizados (ver el docstring del archivo).

    Signals:
        save_requested(): «Guardar filtro activo como nuevo ajuste personalizado…».
        manage_requested(): «Gestionar ajustes personalizados…».
        reset_requested(): «Restaurar filtro activo a sus valores por defecto».
        preset_chosen(int): un ajuste de la lista (su posición en la de 'set_state').
    """

    save_requested = Signal()
    manage_requested = Signal()
    reset_requested = Signal()
    preset_chosen = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(PRESET_OBJECT_NAME)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(TOOLTIP_TEXT)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        # Lo que se ve (ver 'set_state'); None = aún sin estado
        self._state: tuple[object, ...] | None = None
        self._names: tuple[str, ...] = ()
        self._current: int | None = None
        self._filtering = False
        self.set_state((), None, can_save=False, can_reset=False, can_manage=False)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def current_name(self) -> str:
        """El nombre que se ve en el botón (sin la flecha)."""
        if self._current is not None:
            return self._names[self._current]
        return CUSTOM_TEXT if self._filtering else NO_FILTER_TEXT

    def set_state(
        self,
        names: Iterable[str],
        current: int | None,
        *,
        filtering: bool = False,
        can_save: bool,
        can_reset: bool,
        can_manage: bool,
    ) -> None:
        """Muestra los ajustes del módulo y cuál coincide con el filtro (no emite nada).

        Args:
            names: Nombres de los ajustes, en el orden del menú.
            current: Posición del que coincide con el filtro (None = ninguno).
            filtering: Si hay alguna pestaña encendida (sin ajuste que coincida, decide
                entre «Personalizado» y «Sin filtro»).
            can_save: Si se puede guardar (hay alguna pestaña encendida).
            can_reset: Si hay algo que restaurar.
            can_manage: Si se puede abrir «Gestionar…».
        """
        names = tuple(names)
        if current is not None and not 0 <= current < len(names):
            current = None
        state = (names, current, bool(filtering), bool(can_save), bool(can_reset),
                 bool(can_manage))  # fmt: skip
        if state == self._state:
            return  # se llama en cada cambio del filtro: el menú solo se rehace si cambia
        self._state = state
        self._names, self._current, self._filtering = names, current, bool(filtering)
        self.setText(self.current_name + _ARROW)
        self._rebuild_menu(can_save=can_save, can_reset=can_reset, can_manage=can_manage)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _rebuild_menu(self, *, can_save: bool, can_reset: bool, can_manage: bool) -> None:
        """Acciones arriba y, tras una raya, la lista con ✓ en la que coincide."""
        self._menu.clear()
        for text, enabled, signal in (
            (SAVE_TEXT, can_save, self.save_requested),
            (MANAGE_TEXT, can_manage, self.manage_requested),
            (RESET_TEXT, can_reset, self.reset_requested),
        ):
            action = self._menu.addAction(text)
            action.setEnabled(bool(enabled))
            action.triggered.connect(lambda _checked=False, s=signal: s.emit())
        if not self._names:
            return
        self._menu.addSeparator()
        for index, name in enumerate(self._names):
            action = self._menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(index == self._current)
            action.triggered.connect(lambda _checked=False, i=index: self._on_chosen(i))

    def _on_chosen(self, index: int) -> None:
        """Se pide el ajuste; la marca la confirma 'set_state' (el clic ya la cambió)."""
        action = self._preset_actions()[index]
        action.setChecked(index == self._current)
        self.preset_chosen.emit(index)

    def _preset_actions(self) -> list[QAction]:
        """Las acciones de la lista de ajustes (tras la raya)."""
        actions = self._menu.actions()
        return actions[actions.index(next(a for a in actions if a.isSeparator())) + 1:]


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica del botón.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.filter_preset_button
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    holder = QWidget()  # padre que nunca se muestra: no se crea ninguna ventana
    button = FilterPresetButton(holder)
    events: list[object] = []
    button.save_requested.connect(lambda: events.append("save"))
    button.manage_requested.connect(lambda: events.append("manage"))
    button.reset_requested.connect(lambda: events.append("reset"))
    button.preset_chosen.connect(events.append)

    def texts() -> list[str]:
        return ["—" if a.isSeparator() else a.text() for a in button.menu().actions()]

    # 1. Al principio: «Sin filtro», las tres acciones desactivadas y sin lista
    assert button.text() == "Sin filtro ▾" and button.current_name == NO_FILTER_TEXT
    assert texts() == [SAVE_TEXT, MANAGE_TEXT, RESET_TEXT], texts()
    assert not any(a.isEnabled() for a in button.menu().actions())
    assert button.focusPolicy() == Qt.FocusPolicy.NoFocus and button.toolTip() == TOOLTIP_TEXT

    # 2. Con ajustes: acciones arriba, raya y la lista con ✓ en el que coincide
    names = ["Columnas de partida", "Ubicación", "Valoradas"]
    button.set_state(names, 1, can_save=True, can_reset=False, can_manage=True)
    assert button.text() == "Ubicación ▾"
    assert texts() == [SAVE_TEXT, MANAGE_TEXT, RESET_TEXT, "—", *names], texts()
    save, manage, reset = button.menu().actions()[:3]
    assert save.isEnabled() and manage.isEnabled() and not reset.isEnabled()
    assert [a.isChecked() for a in button._preset_actions()] == [False, True, False]

    # 3. Pulsar: se avisa; la marca no cambia hasta que la confirmen
    save.trigger()
    manage.trigger()
    button._preset_actions()[2].trigger()
    assert events == ["save", "manage", 2], events
    assert [a.isChecked() for a in button._preset_actions()] == [False, True, False]
    button._preset_actions()[1].trigger()  # el que ya está marcado: sigue marcado
    assert events[-1] == 1 and button._preset_actions()[1].isChecked()
    button.set_state(names, 2, can_save=True, can_reset=True, can_manage=True)
    assert button.text() == "Valoradas ▾" and button.menu().actions()[2].isEnabled()
    button.menu().actions()[2].trigger()
    assert events[-1] == "reset"

    # 4. Ninguno coincide (o una posición que no existe): «Personalizado» con algo
    # encendido, «Sin filtro» con «Ninguno»; sin ✓
    button.set_state(names, None, filtering=True, can_save=True, can_reset=True, can_manage=True)
    assert button.text() == "Personalizado ▾"
    assert not any(a.isChecked() for a in button._preset_actions())
    button.set_state(names, 7, filtering=True, can_save=True, can_reset=True, can_manage=True)
    assert button.current_name == CUSTOM_TEXT
    button.set_state(names, None, can_save=True, can_reset=True, can_manage=True)
    assert button.text() == "Sin filtro ▾" and button.current_name == NO_FILTER_TEXT
    # Con un ajuste que coincide, su nombre (encendido o no)
    button.set_state(names, 0, can_save=True, can_reset=True, can_manage=True)
    assert button.text() == "Columnas de partida ▾"

    # 5. El mismo estado otra vez: el menú no se rehace (las acciones son las mismas)
    before = button.menu().actions()
    button.set_state(names, 0, can_save=True, can_reset=True, can_manage=True)
    assert button.menu().actions() == before

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
