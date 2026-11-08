"""Barra de filtros de la franja superior de la cuadrícula (como la de Lightroom).

    Filtro activo:        Texto   Atributos   Metadatos   [Ninguno]        [▾] [🔓]
    ───────────────────────────────────────────────────────────────────────────────
    (debajo, los paneles de las pestañas encendidas: la fila de «Texto»...)

De izquierda a derecha: el texto fijo «Filtro activo:», las pestañas en el centro, el
desplegable de filtros personalizados (aún oculto) y, siempre lo último, el candado. Las
pestañas «Texto», «Atributos» y «Metadatos» son INTERRUPTORES que se combinan; «Ninguno»
apaga todas. Las encendidas (o «Ninguno», si no hay ninguna) van en el color de acento.

Solo muestra y avisa: no sabe qué es un filtro. Lo que se ve es siempre lo que le
confirman con 'set_state' (lo hace 'controllers/filter_controller.py', que habla con el
'ModuleHost'):
    - Al pulsar una pestaña: 'panel_toggled(clave, encendida)'.
    - Al pulsar «Ninguno»: 'none_requested()'.
    - Al pulsar el candado: 'lock_toggled(cerrado)'.

Los paneles (la fila de «Texto»...) los pone quien la usa ('add_panel'): se ven, debajo
de la fila de pestañas y en el orden de estas, los de las pestañas encendidas. Las
pestañas sin panel todavía se pueden dejar sin pulsar ('set_available').

Nada coge el foco: tras pulsar, el teclado sigue en la cuadrícula.

Uso (en el .ui es un widget promocionado, 'widget_filter_bar', dentro de 'frame_main_top'):
    bar.add_panel("text", text_row)
    bar.set_available({"text"})
    bar.set_state(frozenset({"text"}), locked=False)

1.0.0 Primera versión (paso A.3, subpaso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.filter_bar
"""

__version__ = "1.0.0"
__all__ = ["LOCK_TOOLTIPS", "TAB_TEXTS", "TITLE_TEXT", "FilterBar"]

# Librerías estándar
from collections.abc import Iterable

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile, QSize, Qt, Signal
from qtpy.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.grid_filter import (
    FILTER_ATTRIBUTES,
    FILTER_METADATA,
    FILTER_PANELS,
    FILTER_TEXT,
)
from ui_helpers.helpers.ui_icons import tinted_icon

# Textos de la interfaz
TITLE_TEXT = "Filtro activo:"
TAB_TEXTS: dict[str, str] = {
    FILTER_TEXT: "Texto",
    FILTER_ATTRIBUTES: "Atributos",
    FILTER_METADATA: "Metadatos",
}
NONE_TEXT = "Ninguno"
# Texto emergente del candado (abierto, cerrado)
LOCK_TOOLTIPS: tuple[str, str] = (
    "Filtro sin bloquear: al cambiar de origen se vuelve a «Ninguno»",
    "Filtro bloqueado: se mantiene al cambiar de origen",
)

# Medidas (px lógicos)
HEADER_HEIGHT = 30  # fila de las pestañas
LOCK_BUTTON_SIZE = 24
LOCK_ICON_SIZE = 16
_TAB_SPACING = 14  # entre las palabras del centro
_SIDE_MARGIN = 10  # a izquierda y derecha de la fila

# Nombres de objeto (los usa el QSS de 'ui_theme.py')
TAB_OBJECT_NAME = "btn_filter_tab"
LOCK_OBJECT_NAME = "btn_filter_lock"
TITLE_OBJECT_NAME = "lbl_filter_title"
PANELS_OBJECT_NAME = "widget_filter_panels"


class FilterBar(QWidget):
    """Fila de pestañas de filtro, candado y paneles (ver el docstring del archivo).

    Signals:
        panel_toggled(str, bool): se ha pulsado una pestaña (su clave y si se enciende).
        none_requested(): se ha pulsado «Ninguno» con alguna pestaña encendida.
        lock_toggled(bool): se ha pulsado el candado (True = cerrarlo).
    """

    panel_toggled = Signal(str, bool)
    none_requested = Signal()
    lock_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active: frozenset[str] = frozenset()
        self._locked = False
        self._available: frozenset[str] = frozenset(FILTER_PANELS)
        self._panels: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Fila de arriba: tres zonas; la izquierda y la derecha con el mismo estiramiento,
        # así las pestañas quedan centradas en la barra aunque los lados midan distinto
        header = QWidget(self)
        header.setFixedHeight(HEADER_HEIGHT)
        row = QHBoxLayout(header)
        row.setContentsMargins(_SIDE_MARGIN, 0, _SIDE_MARGIN // 2, 0)
        row.setSpacing(0)

        left = QWidget(header)
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel(TITLE_TEXT, left)
        self._title.setObjectName(TITLE_OBJECT_NAME)
        left_layout.addWidget(self._title)
        left_layout.addStretch(1)

        center = QWidget(header)
        center_layout = QHBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(_TAB_SPACING)
        self._tabs: dict[str, QToolButton] = {}
        for key in FILTER_PANELS:
            button = self._make_tab(TAB_TEXTS[key], center)
            button.clicked.connect(lambda _checked=False, k=key: self._on_tab_clicked(k))
            center_layout.addWidget(button)
            self._tabs[key] = button
        self._none = self._make_tab(NONE_TEXT, center)
        self._none.clicked.connect(self._on_none_clicked)
        center_layout.addWidget(self._none)

        right = QWidget(header)
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addStretch(1)
        # Aquí irá el desplegable de filtros personalizados (antes del candado)
        self._lock = QToolButton(right)
        self._lock.setObjectName(LOCK_OBJECT_NAME)
        self._lock.setCheckable(True)
        self._lock.setAutoRaise(True)
        self._lock.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lock.setFixedSize(LOCK_BUTTON_SIZE, LOCK_BUTTON_SIZE)
        self._lock.setIconSize(QSize(LOCK_ICON_SIZE, LOCK_ICON_SIZE))
        self._lock.clicked.connect(self._on_lock_clicked)
        right_layout.addWidget(self._lock)

        row.addWidget(left, 1)
        row.addWidget(center, 0)
        row.addWidget(right, 1)
        layout.addWidget(header)

        # Debajo: los paneles de las pestañas encendidas (oculto si no hay ninguno)
        self._panel_area = QWidget(self)
        self._panel_area.setObjectName(PANELS_OBJECT_NAME)
        # Sin esto, el QSS de un QWidget simple (la raya de arriba) no se pinta
        self._panel_area.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._panel_layout = QVBoxLayout(self._panel_area)
        self._panel_layout.setContentsMargins(0, 0, 0, 0)
        self._panel_layout.setSpacing(0)
        layout.addWidget(self._panel_area)

        self._refresh()

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def active(self) -> frozenset[str]:
        """Pestañas encendidas, tal como se ven."""
        return self._active

    @property
    def locked(self) -> bool:
        """Si el candado se ve cerrado."""
        return self._locked

    def add_panel(self, key: str, panel: QWidget) -> None:
        """Pone el panel de una pestaña (se ve debajo cuando la pestaña está encendida).

        Raises:
            ValueError: Si la pestaña no existe o ya tiene panel.
        """
        if key not in self._tabs or key in self._panels:
            raise ValueError(f"Pestaña desconocida o con panel: {key!r}")
        self._panels[key] = panel
        # En el orden de las pestañas, aunque se añadan en otro
        position = sum(1 for k in FILTER_PANELS[: FILTER_PANELS.index(key)] if k in self._panels)
        self._panel_layout.insertWidget(position, panel)
        self._refresh()

    def set_available(self, keys: Iterable[str]) -> None:
        """Pestañas que se pueden pulsar (las demás, en gris: aún no tienen panel)."""
        self._available = frozenset(keys) & frozenset(FILTER_PANELS)
        self._refresh()

    def set_state(self, active: Iterable[str], *, locked: bool) -> None:
        """Muestra el filtro (no emite nada): pestañas encendidas y candado."""
        self._active = frozenset(active) & frozenset(FILTER_PANELS)
        self._locked = bool(locked)
        self._refresh()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _make_tab(self, text: str, parent: QWidget) -> QToolButton:
        """Una palabra del centro: botón de texto que se marca (color de acento)."""
        button = QToolButton(parent)
        button.setObjectName(TAB_OBJECT_NAME)
        button.setText(text)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _refresh(self) -> None:
        """Lo que se ve, a partir de '_active', '_locked' y '_available'."""
        for key, button in self._tabs.items():
            button.setEnabled(key in self._available)
            button.setChecked(key in self._active)
            # Con el puntero de mano solo las que se pueden pulsar
            hand = key in self._available
            button.setCursor(Qt.CursorShape.PointingHandCursor if hand else Qt.CursorShape.ArrowCursor)
        self._none.setChecked(not self._active)
        self._lock.setChecked(self._locked)
        icon_path = AppIcons.LOCK_CLOSED if self._locked else AppIcons.LOCK_OPEN
        if QFile.exists(icon_path):
            # Sin color fijo: sigue la paleta y, marcado (cerrado), toma el acento
            self._lock.setIcon(tinted_icon(icon_path))
        else:
            self._lock.setText("🔒" if self._locked else "🔓")
        self._lock.setToolTip(LOCK_TOOLTIPS[int(self._locked)])
        shown = False
        for key, panel in self._panels.items():
            visible = key in self._active
            panel.setVisible(visible)
            shown = shown or visible
        self._panel_area.setVisible(shown)

    def _on_tab_clicked(self, key: str) -> None:
        """Se pide encender o apagar la pestaña; lo que se ve lo confirma 'set_state'."""
        on = key not in self._active
        self._refresh()  # el clic ya cambió la marca: se deja como estaba hasta confirmar
        self.panel_toggled.emit(key, on)

    def _on_none_clicked(self) -> None:
        self._refresh()
        if self._active:
            self.none_requested.emit()

    def _on_lock_clicked(self) -> None:
        locked = not self._locked
        self._refresh()
        self.lock_toggled.emit(locked)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica de la barra.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.filter_bar
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    holder = QWidget()  # padre que nunca se muestra: no se crea ninguna ventana
    bar = FilterBar(holder)
    toggled: list[tuple[str, bool]] = []
    nones: list[bool] = []
    locks: list[bool] = []
    bar.panel_toggled.connect(lambda key, on: toggled.append((key, on)))
    bar.none_requested.connect(lambda: nones.append(True))
    bar.lock_toggled.connect(locks.append)

    # Al principio: «Ninguno» marcado, candado abierto, sin paneles
    assert bar._none.isChecked() and not any(b.isChecked() for b in bar._tabs.values())
    assert not bar._lock.isChecked() and bar._panel_area.isHidden()
    assert bar._title.text() == "Filtro activo:"
    assert [b.text() for b in bar._tabs.values()] == ["Texto", "Atributos", "Metadatos"]

    # Solo «Texto» se puede pulsar
    bar.set_available({FILTER_TEXT})
    assert bar._tabs[FILTER_TEXT].isEnabled() and not bar._tabs[FILTER_ATTRIBUTES].isEnabled()

    # Pulsar «Texto»: se pide, pero no se marca hasta confirmarlo
    panel = QWidget(holder)
    bar.add_panel(FILTER_TEXT, panel)
    bar._tabs[FILTER_TEXT].click()
    assert toggled == [(FILTER_TEXT, True)] and not bar._tabs[FILTER_TEXT].isChecked()
    bar.set_state({FILTER_TEXT}, locked=False)
    assert bar._tabs[FILTER_TEXT].isChecked() and not bar._none.isChecked()
    assert not panel.isHidden() and not bar._panel_area.isHidden()
    # Pulsarla otra vez: se pide apagarla
    bar._tabs[FILTER_TEXT].click()
    assert toggled[-1] == (FILTER_TEXT, False) and bar._tabs[FILTER_TEXT].isChecked()

    # «Ninguno»: se pide solo si hay algo encendido; nunca se desmarca con el clic
    bar._none.click()
    assert nones == [True]
    bar.set_state((), locked=False)
    assert bar._none.isChecked() and panel.isHidden() and bar._panel_area.isHidden()
    bar._none.click()
    assert nones == [True] and bar._none.isChecked()

    # Candado: se pide cerrarlo; cerrado cuando se confirma, con su texto emergente
    bar._lock.click()
    assert locks == [True] and not bar._lock.isChecked()
    bar.set_state((), locked=True)
    assert bar._lock.isChecked() and bar._lock.toolTip() == LOCK_TOOLTIPS[1]
    assert bar.locked and bar.active == frozenset()

    # Nada coge el foco; un panel repetido o de una pestaña desconocida, rechazado
    buttons = (*bar._tabs.values(), bar._none, bar._lock)
    assert all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in buttons)
    for bad in (FILTER_TEXT, "otra"):
        try:
            bar.add_panel(bad, QWidget(holder))
            raise AssertionError("debía rechazar el panel")
        except ValueError:
            pass

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
