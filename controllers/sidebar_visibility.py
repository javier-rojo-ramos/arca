"""Mostrar u ocultar las dos barras laterales: la izquierda (la de cada módulo) y la derecha
(el inspector).

Decidido por el autor el 15/11/2026:
    - Menú «Ver» de la ventana: «Mostrar barra izquierda» (F7) y «Mostrar barra derecha»
      (F8), que se marcan y desmarcan. Son acciones del .ui ('action_show_left_sidebar' y
      'action_show_right_sidebar'), con su atajo; este controlador las atiende.
    - Tab: las dos a la vez, como Lightroom. Si alguna se ve, se ocultan las dos (y se
      recuerda cuáles se veían); si no se ve ninguna, vuelven las que se veían (o las dos).
      Mientras se escribe en un campo de texto, Tab sigue pasando al campo siguiente.
    - «Ocultar barra», la primera opción del menú de las secciones de cada barra (clic
      derecho en una cabecera o en el hueco vacío: 'SectionStack.offer_hide').
    - Se recuerda para toda la aplicación, no por módulo (settings.json, 'sidebars_visible':
      {"left": bool, "right": bool}).

Las barras van en el divisor de la ventana ('splitter_main'): al ocultar una, la zona del
centro se queda con su sitio; al volver, recupera su ancho (Qt lo conserva, también al
guardar el estado del divisor con una barra oculta). Si se oculta la barra que tiene el
teclado (p. ej. escribiendo en el inspector), el teclado vuelve a la vista del centro.

Uso (en el controlador principal, que solo lo crea):
    self.sidebar_visibility = SidebarVisibility(
        left=self.widget_sidebar_catalog, right=self.widget_sidebar_metadata,
        left_action=self.action_show_left_sidebar, right_action=self.action_show_right_sidebar,
        config=self.config, focus_view=self.center_views.focus_view, parent=self,
    )

1.0.0 Primera versión (15/11/2026).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.sidebar_visibility
"""

__version__ = "1.0.0"
__all__ = ["HIDE_BAR_TEXT", "SidebarVisibility", "TabToggle", "sidebars_from_settings"]

# Librerías estándar
from collections.abc import Callable
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QObject, Qt
from qtpy.QtGui import QAction, QKeySequence, QShortcut
from qtpy.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QStackedWidget,
    QTextEdit,
    QWidget,
)

# Módulos del proyecto
from config.app_constants import SETTING_SIDEBARS_VISIBLE
from ui_helpers.widgets.section_stack import SectionStack

# Texto de la opción del menú de las secciones (el del autor, 15/11/2026)
HIDE_BAR_TEXT = "Ocultar barra"

_LEFT, _RIGHT = "left", "right"
_SIDES = (_LEFT, _RIGHT)

# Donde Tab tiene que seguir pasando al campo siguiente (no oculta las barras)
_TEXT_INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)


def sidebars_from_settings(value: object) -> dict[str, bool]:
    """Lo guardado en settings.json ('sidebars_visible'), comprobado: si se ve cada barra. Lo que
    falte o no sea un booleano, a la vista."""
    data = value if isinstance(value, dict) else {}
    return {side: data.get(side) is not False for side in _SIDES}


class TabToggle:
    """Lo que hace Tab con las dos barras (sin Qt, para probarlo solo).

    Si alguna se ve, se ocultan las dos y se recuerda cuáles se veían; si no se ve
    ninguna, vuelven esas (o las dos, si no hay nada recordado: p. ej. al arrancar con las
    dos ocultas).
    """

    def __init__(self) -> None:
        self._before: dict[str, bool] | None = None

    def next_state(self, current: dict[str, bool]) -> dict[str, bool]:
        """Cómo quedan las barras tras pulsar Tab, a partir de cómo están ('current')."""
        if any(current.values()):
            self._before = dict(current)
            return dict.fromkeys(_SIDES, False)
        restored = self._before or dict.fromkeys(_SIDES, True)
        self._before = None
        return dict(restored)


class _TabGuard(QObject):
    """Deja Tab a los campos de texto: si el que tiene el teclado es uno de ellos, acepta
    el aviso previo de Qt ('ShortcutOverride') y Tab le llega como siempre (pasa al campo
    siguiente) en lugar de ocultar las barras. Vigila la aplicación entera: los campos están
    repartidos por toda la ventana."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # nombre de Qt
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and event.key() == Qt.Key.Key_Tab
            and isinstance(watched, _TEXT_INPUTS)
        ):
            event.accept()
        return False


class SidebarVisibility(QObject):
    """Muestra u oculta las barras laterales (ver el docstring del archivo)."""

    def __init__(
        self,
        *,
        left: QWidget,
        right: QWidget,
        left_action: QAction,
        right_action: QAction,
        config: Any,
        focus_view: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            left: La barra izquierda (la parte del divisor que la contiene).
            right: La barra derecha (ídem).
            left_action: «Mostrar barra izquierda» del menú «Ver» (con su atajo, F7).
            right_action: «Mostrar barra derecha» (F8).
            config: Configuración de la aplicación (lo que se ve, en 'sidebars_visible').
            focus_view: Devuelve el teclado a la vista del centro (si se oculta la barra
                que lo tenía).
            parent: La ventana principal (Tab vale en toda ella).
        """
        super().__init__(parent)
        self._bars = {_LEFT: left, _RIGHT: right}
        self._actions = {_LEFT: left_action, _RIGHT: right_action}
        self._config = config
        self._focus_view = focus_view
        self._tab = TabToggle()

        for side, action in self._actions.items():
            action.setCheckable(True)
            action.toggled.connect(lambda visible, s=side: self.set_visible(s, visible))

        # Tab: las dos barras (los campos de texto se lo quedan: '_TabGuard')
        self._tab_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Tab), parent or left)
        self._tab_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._tab_shortcut.activated.connect(self.toggle_both)
        self._guard = _TabGuard(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._guard)

        # «Ocultar barra» en el menú de las secciones de cada barra (las de los módulos que
        # se añadan después, también)
        for side, bar in self._bars.items():
            self._offer_hide(side, bar)
            for stack in bar.findChildren(QStackedWidget):
                stack.widgetAdded.connect(lambda _index, s=side, b=bar: self._offer_hide(s, b))

        self._apply(sidebars_from_settings(config.get(SETTING_SIDEBARS_VISIBLE)), save=False)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def is_visible(self, side: str) -> bool:
        """True si la barra ('left' o 'right') se ve (la quiere ver el usuario)."""
        return not self._bars[side].isHidden()

    def set_visible(self, side: str, visible: bool) -> None:
        """Muestra u oculta una barra ('left' o 'right') y lo guarda."""
        state = {s: self.is_visible(s) for s in _SIDES}
        state[side] = visible
        self._apply(state)

    def toggle_both(self) -> None:
        """Tab: oculta las dos (si se ve alguna) o vuelve a mostrar las que se veían."""
        self._apply(self._tab.next_state({s: self.is_visible(s) for s in _SIDES}))

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _apply(self, state: dict[str, bool], *, save: bool = True) -> None:
        """Deja las barras como dice 'state', con el menú al día y, si se pide, guardado."""
        focus = QApplication.focusWidget()
        lost_focus = False
        for side, visible in state.items():
            bar = self._bars[side]
            if not visible and focus is not None and bar.isAncestorOf(focus):
                lost_focus = True
            bar.setVisible(visible)
            action = self._actions[side]
            if action.isChecked() != visible:
                action.blockSignals(True)  # ya está aplicado: sin volver a entrar
                action.setChecked(visible)
                action.blockSignals(False)
        if lost_focus and self._focus_view is not None:
            self._focus_view()
        if save and sidebars_from_settings(self._config.get(SETTING_SIDEBARS_VISIBLE)) != state:
            self._config.set(SETTING_SIDEBARS_VISIBLE, dict(state))

    def _offer_hide(self, side: str, bar: QWidget) -> None:
        """Pone «Ocultar barra» en el menú de las secciones de las pilas de esa barra."""
        for stack in bar.findChildren(SectionStack):
            if not stack.hide_offered():
                stack.offer_hide(HIDE_BAR_TEXT)
                stack.hide_requested.connect(lambda s=side: self.set_visible(s, False))


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): Tab, el menú, lo guardado, «Ocultar
    # barra» y el teclado al ocultar la barra que lo tiene.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.sidebar_visibility
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qtpy.QtTest import QTest
    from qtpy.QtWidgets import QHBoxLayout, QListView, QMainWindow, QSplitter, QVBoxLayout

    app = QApplication.instance() or QApplication([])

    # 1. Lo guardado, comprobado
    assert sidebars_from_settings(None) == {"left": True, "right": True}
    assert sidebars_from_settings({"left": False, "right": "no"}) == {"left": False, "right": True}

    # 2. Tab sin Qt: oculta las dos y vuelven las que se veían; sin nada recordado, las dos
    tab = TabToggle()
    assert tab.next_state({"left": True, "right": False}) == {"left": False, "right": False}
    assert tab.next_state({"left": False, "right": False}) == {"left": True, "right": False}
    fresh = TabToggle()
    assert fresh.next_state({"left": False, "right": False}) == {"left": True, "right": True}

    class _Config(dict):
        def set(self, key: str, value: object) -> None:
            self[key] = value

    # Una ventana como la de la aplicación: divisor con barra izquierda, centro y derecha;
    # en la izquierda, una pila de páginas con una pila de secciones y un campo de texto
    window = QMainWindow()
    splitter = QSplitter(Qt.Orientation.Horizontal)
    left_bar, center, right_bar = QWidget(), QListView(), QWidget()
    pages = QStackedWidget(left_bar)
    QVBoxLayout(left_bar).addWidget(pages)
    page = QWidget()
    page_layout = QVBoxLayout(page)
    sections = SectionStack(page)
    search = QLineEdit(page)
    page_layout.addWidget(sections)
    page_layout.addWidget(search)
    pages.addWidget(page)
    right_field = QLineEdit(right_bar)
    QHBoxLayout(right_bar).addWidget(right_field)
    for widget in (left_bar, center, right_bar):
        splitter.addWidget(widget)
    window.setCentralWidget(splitter)
    menu = window.menuBar().addMenu("Ver")
    show_left = menu.addAction("Mostrar barra izquierda")
    show_left.setShortcut(QKeySequence("F7"))
    show_right = menu.addAction("Mostrar barra derecha")
    show_right.setShortcut(QKeySequence("F8"))
    config = _Config(sidebars_visible={"left": True, "right": False})
    focused: list[str] = []

    def focus_center() -> None:
        focused.append("centro")
        center.setFocus()

    control = SidebarVisibility(
        left=left_bar, right=right_bar, left_action=show_left, right_action=show_right,
        config=config, focus_view=focus_center, parent=window,
    )
    window.resize(900, 500)
    window.show()  # offscreen: no se ve nada
    QTest.qWait(20)

    # 3. Al arrancar, como se guardó (sin volver a guardarlo); el menú, al día
    assert control.is_visible("left") and not control.is_visible("right")
    assert show_left.isChecked() and not show_right.isChecked()
    assert right_bar.isHidden()

    # 4. El menú (o su atajo) muestra y oculta, y se guarda
    show_right.trigger()
    assert control.is_visible("right") and config["sidebars_visible"] == {"left": True, "right": True}
    QTest.keyClick(window, Qt.Key.Key_F7)
    assert not control.is_visible("left") and not show_left.isChecked()
    assert config["sidebars_visible"] == {"left": False, "right": True}
    QTest.keyClick(window, Qt.Key.Key_F7)
    assert control.is_visible("left")

    # 5. Tab con el teclado en la vista del centro: las dos fuera; otra vez, vuelven
    center.setFocus()
    QTest.qWait(10)
    QTest.keyClick(center, Qt.Key.Key_Tab)
    assert not control.is_visible("left") and not control.is_visible("right")
    assert not show_left.isChecked() and config["sidebars_visible"] == {"left": False, "right": False}
    QTest.keyClick(center, Qt.Key.Key_Tab)
    assert control.is_visible("left") and control.is_visible("right")

    # 6. Tab escribiendo en un campo de texto: pasa al campo siguiente, no oculta nada
    search.setFocus()
    QTest.qWait(10)
    QTest.keyClick(search, Qt.Key.Key_Tab)
    assert control.is_visible("left") and control.is_visible("right")
    assert QApplication.focusWidget() is not search  # el teclado ha pasado a otro sitio

    # 7. Ocultar la barra que tiene el teclado: vuelve a la vista del centro
    right_field.setFocus()
    QTest.qWait(10)
    focused.clear()
    QTest.keyClick(window, Qt.Key.Key_F8)
    assert not control.is_visible("right") and focused == ["centro"]
    # ...y si no lo tenía, el teclado no se mueve
    focused.clear()
    QTest.keyClick(window, Qt.Key.Key_F8)
    QTest.keyClick(window, Qt.Key.Key_F7)
    assert focused == [] and not control.is_visible("left")
    QTest.keyClick(window, Qt.Key.Key_F7)

    # 8. «Ocultar barra» en el menú de las secciones, también en una página añadida después
    assert sections.hide_offered()
    sections.hide_requested.emit()
    assert not control.is_visible("left") and config["sidebars_visible"]["left"] is False
    show_left.trigger()
    later = QWidget()
    later_sections = SectionStack(later)
    pages.addWidget(later)
    assert later_sections.hide_offered()
    later_sections.hide_requested.emit()
    assert not control.is_visible("left")
    # Ofrecerla dos veces no la duplica en el menú (es su única opción: la pila no tiene
    # modelo en esta prueba)
    control._offer_hide("left", left_bar)
    later_menu = later_sections.build_menu()
    assert later_menu is not None
    assert [action.text() for action in later_menu.actions()] == [HIDE_BAR_TEXT]
    later_menu.deleteLater()

    print("Autoprueba finalizada correctamente.")
