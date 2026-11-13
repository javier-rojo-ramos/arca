"""Ventana «Añadir capa» / «Cambiar capa»: una capa propia del mapa.

La abre la sección «Mapa» de la ventana de opciones. Pide el nombre, la dirección de las
teselas, la atribución y el zoom máximo; lo comprueba con 'core/maps/tile_layers.user_layer'
(los textos de lo que no vale salen de allí) y, si algo no vale, lo dice debajo sin
cerrarse. No guarda nada: quien la abre recoge la capa con 'layer()'.

    Nombre        [Mapa de mi empresa                ]
    Dirección     [https://.../{z}/{x}/{y}.png       ]
    Atribución    [© ...                             ]
    Zoom máximo   [19]
    (ayuda)
    (aviso en rojo si algo no vale)
                                   [Aceptar] [Cancelar]

1.0.0 Primera versión (docs/MAPA.md, paso 2.4).

Prueba rápida (desde la raíz del proyecto; abre la ventana):
    python -m ui_helpers.dialogs.map_layer_dialog
"""

__version__ = "1.0.0"
__all__ = ["MapLayerDialog"]

# Librerías de terceros (Qt)
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.maps.tile_layers import MAX_ZOOM_LIMIT, TileLayer, user_layer

# Zoom máximo que se propone para una capa nueva (el de casi todos los servicios)
_DEFAULT_MAX_ZOOM = 19

_HELP = (
    "La dirección de una tesela del servicio, con <b>{z}</b> (el zoom), <b>{x}</b> (la "
    "columna) e <b>{y}</b> (la fila) donde van esos números; si reparte la carga entre "
    "servidores a, b y c, con <b>{s}</b>. Por ejemplo:<br>"
    "<i>https://tile.openstreetmap.org/{z}/{x}/{y}.png</i><br>"
    "Antes de añadirla, lee las condiciones de uso del servicio y copia su atribución: "
    "se verá siempre en una esquina del mapa."
)


class MapLayerDialog(QDialog):
    """Pide los datos de una capa propia (ver el docstring del archivo)."""

    def __init__(
        self, key: str, layer: TileLayer | None = None, parent: QWidget | None = None
    ) -> None:
        """
        Args:
            key: Clave de la capa (una nueva, de 'new_user_key', o la de la que se cambia).
            layer: La capa que se cambia (None = una nueva).
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle("Cambiar capa" if layer is not None else "Añadir capa")
        self.setModal(True)
        self.resize(560, 0)
        self._key = key
        self._layer: TileLayer | None = None

        self.edit_name = QLineEdit(layer.name if layer else "")
        self.edit_url = QLineEdit(layer.url_template if layer else "")
        self.edit_url.setPlaceholderText("https://.../{z}/{x}/{y}.png")
        self.edit_attribution = QLineEdit(layer.attribution if layer else "")
        self.spin_max_zoom = QSpinBox()
        self.spin_max_zoom.setRange(1, MAX_ZOOM_LIMIT)
        self.spin_max_zoom.setValue(layer.max_zoom if layer else _DEFAULT_MAX_ZOOM)

        form = QFormLayout()
        form.addRow("Nombre", self.edit_name)
        form.addRow("Dirección", self.edit_url)
        form.addRow("Atribución", self.edit_attribution)
        form.addRow("Zoom máximo", self.spin_max_zoom)

        hint = QLabel(_HELP)
        hint.setObjectName("lbl_dialog_hint")  # en gris (ui_theme.py)
        hint.setWordWrap(True)
        self.label_error = QLabel()
        self.label_error.setObjectName("lbl_dialog_error")  # en rojo (ui_theme.py)
        self.label_error.setWordWrap(True)
        self.label_error.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.label_error)
        layout.addWidget(buttons)
        self.edit_name.setFocus()

    def layer(self) -> TileLayer | None:
        """La capa escrita (None si se canceló)."""
        return self._layer

    def accept(self) -> None:
        """Comprueba lo escrito: si vale, se cierra; si no, lo dice y se queda abierta."""
        try:
            self._layer = user_layer(
                self._key,
                self.edit_name.text(),
                self.edit_url.text(),
                self.edit_attribution.text(),
                self.spin_max_zoom.value(),
            )
        except ValueError as error:
            self.label_error.setText(str(error))
            self.label_error.show()
            return
        super().accept()


if __name__ == "__main__":
    # Prueba visual: abre la ventana (se queda abierta hasta que se cierra).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.map_layer_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    from ui_helpers.helpers.ui_theme import apply_theme

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme()
    dialog = MapLayerDialog("user_1")
    result = dialog.exec()
    print("Aceptado:" if result else "Cancelado", dialog.layer())
