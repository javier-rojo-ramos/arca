"""Botones de vista de la barra inferior: [▦] [▢] (cuadrícula, individual...).

Van a la izquierda de la barra inferior, antes del orden. Son botones exclusivos (solo
uno marcado), uno por cada vista que ofrece el módulo activo: quien los usa los rehace con
'set_views' al cambiar de módulo, así que cuando lleguen la lista y el mapa no hay que
tocar este widget ni el .ui.

Solo muestra y avisa: no sabe qué es una vista ni qué hace. Cada botón lleva una clave
(texto) y, al pulsarlo, emite 'view_requested(clave)'; lo marcado es siempre lo que le
confirman con otro 'set_views'. Con una sola vista (o ninguna) se oculta: un botón suelto
no sirve de nada.

Iconos: SVG monocromos teñidos con 'tinted_icon' (el del botón marcado, en el color de
acento, como los de la toolbar). Sin icono, la inicial del texto emergente. No cogen el
foco: tras pulsarlos, el teclado sigue en la vista.

Uso (en el .ui es un widget promocionado, 'widget_view_buttons'):
    buttons.set_views([("grid", "Cuadrícula (G)", AppIcons.VIEW_GRID), ...], "grid")
    buttons.view_requested.connect(...)

1.1.0 Botones de 22 px con icono de 16 (antes, 26 y 18): la barra inferior pasa a medir
      lo mismo que la franja de «Atributos».
1.0.0 Primera versión (paso A.1, subpaso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.view_buttons
"""

__version__ = "1.1.0"
__all__ = ["ViewButtons"]

# Librerías estándar
from collections.abc import Sequence

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile, QSize, Qt, Signal
from qtpy.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

# Módulos del proyecto
from ui_helpers.helpers.ui_icons import tinted_icon

# Medidas (px lógicos). La barra inferior mide 30 px bajo su raya, como la franja de
# «Atributos» de la barra de filtros: los botones, del alto de los desplegables («Orden» al
# lado, «≥» en «Atributos»), quedan a 4 px de las rayas; el icono, el del candado de la
# barra de filtros (pedido por el autor el 11/11/2026; antes, 26 y 18)
BUTTON_SIZE = 22  # lado de cada botón
ICON_SIZE = 16  # lado del icono
_SPACING = 4  # entre botones (como en la toolbar)

# Una vista para los botones: (clave, texto emergente, ruta del icono o "" sin icono)
ViewSpec = tuple[str, str, str]


class ViewButtons(QWidget):
    """Grupo exclusivo de botones de vista (ver el docstring del archivo).

    Signals:
        view_requested(str): el usuario ha pulsado el botón de otra vista (lleva su clave).
    """

    view_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(_SPACING)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        self._specs: list[ViewSpec] = []
        self.set_views((), None)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def current(self) -> str | None:
        """Clave de la vista marcada (None si no hay ninguna)."""
        button = self._group.checkedButton()
        return next((key for key, b in self._buttons.items() if b is button), None)

    def keys(self) -> list[str]:
        """Claves de los botones, en su orden."""
        return [key for key, _tooltip, _icon in self._specs]

    def set_views(self, views: Sequence[ViewSpec], current: str | None) -> None:
        """Pone un botón por vista y marca 'current' (no emite 'view_requested').

        Los botones solo se rehacen si cambian las vistas (al cambiar de módulo).
        """
        specs = list(views)
        if specs != self._specs:
            self._rebuild(specs)
        button = self._buttons.get(current or "")
        if button is not None:
            # 'setChecked' en un grupo exclusivo desmarca el anterior; no emite 'clicked'
            button.setChecked(True)
        else:
            checked = self._group.checkedButton()
            if checked is not None:
                self._group.setExclusive(False)  # para poder dejarlos todos sin marcar
                checked.setChecked(False)
                self._group.setExclusive(True)
        self.setVisible(len(specs) > 1)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _rebuild(self, specs: list[ViewSpec]) -> None:
        """Quita los botones de antes y crea uno por vista."""
        for button in self._buttons.values():
            self._group.removeButton(button)
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        self._specs = specs
        for key, tooltip, icon_path in specs:
            button = QToolButton(self)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
            button.setToolTip(tooltip)
            if icon_path and QFile.exists(icon_path):
                # Sin color fijo: el icono sigue la paleta y, marcado, toma el acento
                button.setIcon(tinted_icon(icon_path))
                button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            else:
                button.setText(tooltip[:1])  # sin SVG todavía: la inicial
            button.clicked.connect(lambda _checked=False, k=key: self._on_clicked(k))
            self._group.addButton(button)
            self._layout.addWidget(button)
            self._buttons[key] = button

    def _on_clicked(self, key: str) -> None:
        """Se pide la vista; lo marcado lo confirma quien la pone ('set_views')."""
        self.view_requested.emit(key)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica de los botones.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.view_buttons
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    # Con un padre que nunca se muestra: 'setVisible(True)' no crea una ventana
    holder = QWidget()
    buttons = ViewButtons(holder)
    requested: list[str] = []
    buttons.view_requested.connect(requested.append)

    # Sin vistas: oculto y sin nada marcado
    assert buttons.isHidden() and buttons.current is None

    views = [("grid", "Cuadrícula (G)", ""), ("single", "Vista individual (Intro)", "")]
    buttons.set_views(views, "grid")
    assert not buttons.isHidden() and buttons.keys() == ["grid", "single"]
    assert buttons.current == "grid" and requested == []  # 'set_views' no pide nada
    first = buttons._buttons["grid"]
    assert first.text() == "C" and first.toolTip() == "Cuadrícula (G)"  # sin SVG: la inicial
    assert first.focusPolicy() == Qt.FocusPolicy.NoFocus

    # Pulsar otro botón: se pide esa vista; se marca al confirmarla
    buttons._buttons["single"].click()
    assert requested == ["single"]
    buttons.set_views(views, "single")
    assert buttons.current == "single"
    # Las mismas vistas: no se rehacen los botones
    assert buttons._buttons["grid"] is first

    # Otro módulo con otras vistas: se rehacen; una sola vista, oculto
    buttons.set_views([("grid", "Cuadrícula (G)", "")], "grid")
    assert buttons.keys() == ["grid"] and buttons.isHidden()
    # Una vista marcada que no está entre los botones: ninguno marcado
    buttons.set_views(views, "map")
    assert buttons.current is None

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
