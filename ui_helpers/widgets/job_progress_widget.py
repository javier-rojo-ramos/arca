"""Widget de progreso de un trabajo en segundo plano, para la barra de estado.

Muestra el nombre del trabajo, una barra de progreso y un botón "Cancelar". No
sabe nada de los trabajos: el controlador le pasa el avance con 'set_progress' y
escucha la señal 'cancel_requested' para detener el trabajo.

La barra y el botón tienen la misma altura ('ROW_HEIGHT'), algo menor que la de la barra
de estado, para que el botón se vea entero (su estilo compacto, '#btn_job_cancel', está en
'ui_theme.py': el botón normal de los diálogos tiene relleno vertical y no cabía).

1.1.0 Botón «Cancelar» compacto y de la misma altura que la barra de progreso (antes se
      veía cortado por abajo); márgenes verticales iguales.
"""

__version__ = "1.1.0"
__all__ = ["JobProgressWidget"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget


class JobProgressWidget(QWidget):
    """Etiqueta + barra de progreso + botón Cancelar, en una sola fila.

    Signals:
        cancel_requested(): El usuario pulsó "Cancelar".
    """

    cancel_requested = Signal()

    # Altura de la barra de progreso y del botón (px lógicos)
    ROW_HEIGHT = 18

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        """Crea el widget.

        Args:
            title: Texto que describe el trabajo ("Leyendo metadatos").
            parent: Widget padre.
        """
        super().__init__(parent)
        self._title = title

        self._label = QLabel(title)

        self._bar = QProgressBar()
        self._bar.setFixedWidth(200)
        self._bar.setFixedHeight(self.ROW_HEIGHT)
        self._bar.setTextVisible(True)
        # %v = valor actual, %m = máximo
        self._bar.setFormat("%v / %m")

        self._cancel_button = QPushButton("Cancelar")
        self._cancel_button.setObjectName("btn_job_cancel")  # estilo compacto (ui_theme.py)
        self._cancel_button.setFixedHeight(self.ROW_HEIGHT)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)

        layout = QHBoxLayout(self)
        # Sin márgenes verticales: la barra de estado centra la fila en su altura
        layout.setContentsMargins(5, 0, 4, 0)
        layout.setSpacing(8)
        # Añade un espacio flexible al inicio para empujar todo lo demás a la derecha
        layout.addStretch()
        layout.addWidget(self._label)
        layout.addWidget(self._bar)
        layout.addWidget(self._cancel_button)

    def set_progress(self, done: int, total: int) -> None:
        """Actualiza la barra.

        Args:
            done: Elementos tratados.
            total: Elementos totales.
        """
        # Con total 0 se deja un rango válido para que no aparezca en modo "indeterminado"
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(min(done, max(total, 1)))

    def _on_cancel_clicked(self) -> None:
        """Desactiva el botón (para no pulsarlo dos veces) y avisa de la cancelación."""
        self._cancel_button.setEnabled(False)
        self._label.setText("Cancelando...")
        self.cancel_requested.emit()
