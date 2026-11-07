"""Control del orden de la cuadrícula: «Orden: [campo ▾] [↑]».

Va a la izquierda de la barra inferior de la ventana ('frame_main_bottom'). Solo muestra y
avisa: NO sabe nada de la base de datos ni de los módulos. Qué campos ofrece y cuál está
elegido se lo dice quien lo usa ('set_options'); cuando el usuario cambia algo, emite
'order_requested' con el orden nuevo y espera a que se lo confirmen con otro
'set_options' (así lo que se ve es siempre lo que manda el módulo activo).

    Orden: [Hora de captura ▾] [↑]
              │                 └─ dirección: ↑ ascendente, ↓ descendente (pulsar invierte)
              └─ campos del módulo activo (claves de 'core/catalog/grid_orders.SORT_FIELDS')

Sin campos (un módulo que no decide el orden, como los provisionales), el control se oculta.

No coge el foco (ni el desplegable ni el botón): tras usarlo, los atajos de teclado de la
cuadrícula siguen funcionando.

Uso (en el .ui es un widget promocionado, 'widget_sort_control'):
    sort = self.widget_sort_control
    sort.order_requested.connect(module_host.set_order)
    module_host.order_changed.connect(
        lambda _o: sort.set_options(module_host.active_sort_fields(), module_host.active_order)
    )

1.0.0 Primera versión (orden de la cuadrícula, paso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.sort_control
"""

__version__ = "1.0.0"
__all__ = ["SortControl"]

# Librerías estándar
from collections.abc import Sequence

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QComboBox, QHBoxLayout, QLabel, QToolButton, QWidget

# Módulos del proyecto
from core.catalog.grid_orders import SORT_FIELDS, GridOrder
from ui_helpers.helpers.signal_blocker import blocked_signals

# Textos de la interfaz
_LABEL = "Orden:"
_COMBO_TIP = "Campo por el que se ordenan las tarjetas"
_ARROW = {False: "↑", True: "↓"}  # descending -> flecha
_ARROW_TIP = {
    False: "Orden ascendente (pulsa para invertirlo)",
    True: "Orden descendente (pulsa para invertirlo)",
}

# Medidas (px lógicos)
_SPACING = 6  # entre la etiqueta, el desplegable y la flecha
_ARROW_SIZE = 24  # lado del botón de la flecha


class SortControl(QWidget):
    """«Orden:», el desplegable de campos y el botón de la dirección (ver el docstring
    del archivo).

    Signals:
        order_requested(object): el usuario ha elegido otro campo o ha invertido la
            dirección (lleva el 'GridOrder' pedido).
    """

    order_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Orden que se muestra (None = sin opciones: el control está oculto)
        self._order: GridOrder | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_SPACING)

        self._label = QLabel(_LABEL, self)
        layout.addWidget(self._label)

        self._combo = QComboBox(self)
        self._combo.setToolTip(_COMBO_TIP)
        self._combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Tan ancho como el campo más largo: no cambia de ancho al elegir otro
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._combo.activated.connect(self._on_field_activated)
        layout.addWidget(self._combo)

        self._arrow = QToolButton(self)
        self._arrow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._arrow.setAutoRaise(True)
        self._arrow.setFixedSize(_ARROW_SIZE, _ARROW_SIZE)
        self._arrow.clicked.connect(self._on_arrow_clicked)
        layout.addWidget(self._arrow)

        self.set_options((), None)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def order(self) -> GridOrder | None:
        """Orden que se muestra (None si el control está oculto)."""
        return self._order

    def set_options(self, fields: Sequence[str], order: GridOrder | None) -> None:
        """Muestra los campos de un módulo y su orden actual (no emite 'order_requested').

        Args:
            fields: Claves de 'SORT_FIELDS', en el orden del desplegable. Las que no
                existen se ignoran.
            order: Orden elegido. Si es None o su campo no está entre 'fields', el control
                se oculta (el módulo no decide el orden).
        """
        keys = [key for key in fields if key in SORT_FIELDS]
        if order is None or order.field not in keys:
            self._order = None
            self.setVisible(False)
            return

        self._order = order
        with blocked_signals(self._combo):
            # Solo se rehace la lista si cambia (al cambiar de módulo), no al cambiar de orden
            current = [self._combo.itemData(i) for i in range(self._combo.count())]
            if current != keys:
                self._combo.clear()
                for key in keys:
                    self._combo.addItem(SORT_FIELDS[key].label, key)
            self._combo.setCurrentIndex(keys.index(order.field))
        self._arrow.setText(_ARROW[order.descending])
        self._arrow.setToolTip(_ARROW_TIP[order.descending])
        self.setVisible(True)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_field_activated(self, index: int) -> None:
        """El usuario ha elegido un campo: se pide con la dirección que ya tenía."""
        key = self._combo.itemData(index)
        if self._order is None or key is None or key == self._order.field:
            return
        self.order_requested.emit(GridOrder(key, self._order.descending))

    def _on_arrow_clicked(self) -> None:
        """El usuario ha pulsado la flecha: se pide la dirección contraria."""
        if self._order is not None:
            self.order_requested.emit(self._order.reversed())


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica del control.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.sort_control
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    from core.catalog.grid_orders import CAPTURE_TIME_ORDER, NAME_ORDER

    app = QApplication([])
    # Con un padre que nunca se muestra: 'setVisible(True)' no crea una ventana
    holder = QWidget()
    control = SortControl(holder)
    requested: list[GridOrder] = []
    control.order_requested.connect(requested.append)

    # Sin opciones: oculto
    assert control.order is None and control.isHidden()

    # Opciones de un módulo: visible, con sus campos (los desconocidos se ignoran)
    fields = ("captured_at", "file_name", "no_existe", "file_size")
    control.set_options(fields, CAPTURE_TIME_ORDER)
    assert not control.isHidden() and control.order == CAPTURE_TIME_ORDER
    assert [control._combo.itemText(i) for i in range(control._combo.count())] == [
        "Hora de captura", "Nombre", "Tamaño",
    ]  # fmt: skip
    assert control._combo.currentText() == "Hora de captura" and control._arrow.text() == "↑"
    assert requested == []  # 'set_options' no pide nada

    # Elegir otro campo: pide ese campo con la misma dirección
    control._combo.setCurrentIndex(2)
    control._combo.activated.emit(2)
    assert requested == [GridOrder("file_size")], requested
    # Volver a elegir el mismo campo que se muestra: nada
    control._combo.setCurrentIndex(0)
    control._combo.activated.emit(0)
    assert len(requested) == 1

    # La flecha: pide la dirección contraria; se ve al confirmarlo
    control._arrow.click()
    assert requested[-1] == GridOrder("captured_at", descending=True)
    control.set_options(fields, requested[-1])
    assert control._arrow.text() == "↓" and "descendente" in control._arrow.toolTip()

    # Otro módulo con otros campos: la lista se rehace
    control.set_options(("file_name",), NAME_ORDER)
    assert control._combo.count() == 1 and control._combo.currentText() == "Nombre"

    # Orden cuyo campo no se ofrece, o sin orden: oculto
    control.set_options(("file_name",), CAPTURE_TIME_ORDER)
    assert control.isHidden() and control.order is None
    control.set_options((), None)
    assert control.isHidden()

    # Sin foco: los atajos de la cuadrícula siguen funcionando tras usarlo
    assert control._combo.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert control._arrow.focusPolicy() == Qt.FocusPolicy.NoFocus

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
