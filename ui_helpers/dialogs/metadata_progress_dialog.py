"""Ventana "Leyendo metadatos": bloquea la aplicación mientras se leen los metadatos.

Mientras se leen, nada debe modificarse (docs/PENDIENTE.md, GEN 20; decidido por el
autor): esta ventana es MODAL respecto a la ventana principal, así que la bloquea entera
sin vigilar cada acción. La abre y la cierra 'controllers/metadata_progress.py'.

    ┌ [icono] Leyendo metadatos ─────────────────────────────────────── [x] ┐
    │ Se van a leer los metadatos de 22.012 archivos, la operación puede     │
    │ tardar varios minutos. Durante el proceso la edición está              │
    │ deshabilitada.                                                         │
    │                                                                        │
    │ [██████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] │
    │ 1.234 de 22.012                                           [Cancelar]   │
    └────────────────────────────────────────────────────────────────────────┘

Reglas:
    - Se muestra con 'show()' (no 'exec()'): el bucle de eventos sigue siendo el de
      siempre y quien la abre la cierra con 'finish()' al terminar el trabajo.
    - Solo se cierra así o con «Cancelar» (que pide parar la lectura: el trabajo termina
      el lote en curso y entonces se cierra). Esc y Alt+F4 no hacen nada, y el botón de
      cerrar sale desactivado ([x], en gris): una pulsación sin querer no debe cancelar
      una lectura de minutos.
    - No sabe nada de los trabajos: recibe el avance con 'set_progress' y avisa con
      'cancel_requested'.

Prueba (sin ventana; con '--ventana', la muestra con un avance simulado):
    python -m ui_helpers.dialogs.metadata_progress_dialog

1.1.1 Texto: «Se van a leer LOS metadatos de...» (cambiado por el autor); autoprueba al día.
1.1.0 Con el icono de la aplicación en la barra de título (el botón de cerrar, en gris) y
      sin la mención a las miniaturas en el texto (pedidos por el autor).
1.0.0 Primera versión (GEN 20.2). El texto es del autor.
"""

__version__ = "1.1.1"
__all__ = ["MetadataProgressDialog", "message_text"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QCloseEvent
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from ui_helpers.inspector.formatting import format_count

WINDOW_TITLE = "Leyendo metadatos"
CANCEL_BUTTON_TEXT = "Cancelar"
CANCELLING_TEXT = "Cancelando..."


def message_text(total: int) -> str:
    """El texto de la ventana para 'total' archivos (redactado por el autor).

    Está fuera de la clase para poder probarlo sin abrir ninguna ventana.
    """
    files = "1 archivo" if total == 1 else f"{format_count(total)} archivos"
    return (
        f"Se van a leer los metadatos de {files}, la operación puede tardar varios minutos. "
        "Durante el proceso la edición está deshabilitada."
    )


def count_text(done: int, total: int) -> str:
    """El avance en palabras: '1.234 de 22.012'."""
    return f"{format_count(done)} de {format_count(total)}"


class MetadataProgressDialog(QDialog):
    """Texto, barra de progreso, recuento y «Cancelar». Modal respecto a su ventana.

    Signals:
        cancel_requested(): El usuario pulsó «Cancelar» (una sola vez: luego se desactiva).
    """

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Crea la ventana (sin mostrarla).

        Args:
            parent: Ventana principal: es la que queda bloqueada mientras se ve.
        """
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        # Modal solo respecto a su ventana (no a toda la aplicación). Con el menú del sistema,
        # que en Windows es lo que muestra el icono (heredado de la ventana principal), pero
        # SIN 'WindowCloseButtonHint': Qt deja el botón de cerrar desactivado, en gris (en
        # Windows, icono y botón van juntos; comprobado con la API de Windows). Sin botón de
        # ayuda. Solo se cierra con 'finish' o con «Cancelar»
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setMinimumWidth(480)
        self._finished = False  # True tras 'finish': entonces sí se puede cerrar

        layout = QVBoxLayout(self)

        self._message = QLabel(message_text(0))
        self._message.setWordWrap(True)
        layout.addWidget(self._message)
        layout.addSpacing(12)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)  # el recuento va debajo, en palabras
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        row = QHBoxLayout()
        self._count = QLabel(count_text(0, 0))
        row.addWidget(self._count)
        row.addStretch(1)
        self._cancel_button = QPushButton(CANCEL_BUTTON_TEXT)
        self._cancel_button.setAutoDefault(False)  # Intro no cancela
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        row.addWidget(self._cancel_button)
        layout.addLayout(row)

    # -------------------------------------------------------------------------
    # Lo que usa quien la abre
    # -------------------------------------------------------------------------

    def set_progress(self, done: int, total: int) -> None:
        """Actualiza el texto (cuántos archivos), la barra y el recuento."""
        # Con total 0 se deja un rango válido para que no salga en modo "indeterminado"
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(min(done, max(total, 1)))
        self._message.setText(message_text(total))
        if self._cancel_button.isEnabled():  # cancelando, el recuento dice que se cancela
            self._count.setText(count_text(done, total))

    def finish(self) -> None:
        """El trabajo ha terminado (o se ha cancelado): cierra la ventana."""
        self._finished = True
        self.done(QDialog.DialogCode.Accepted)

    # -------------------------------------------------------------------------
    # Cierres que no deben ocurrir: Esc y el botón de cerrar
    # -------------------------------------------------------------------------

    def reject(self) -> None:  # nombre de Qt (Esc lo llama)
        """Esc no cierra la ventana: la lectura sigue (solo «Cancelar» la detiene)."""

    def closeEvent(self, event: QCloseEvent) -> None:  # nombre de Qt
        """Solo se cierra tras 'finish' (Alt+F4 o el sistema no la cierran a medias)."""
        if self._finished:
            super().closeEvent(event)
        else:
            event.ignore()

    def _on_cancel_clicked(self) -> None:
        """Desactiva el botón (para no pulsarlo dos veces) y avisa de la cancelación."""
        self._cancel_button.setEnabled(False)
        self._count.setText(CANCELLING_TEXT)
        self.cancel_requested.emit()


if __name__ == "__main__":
    # Autoprueba sin ventana (el diálogo se crea pero no se muestra). Con '--ventana', se
    # muestra con un avance simulado hasta cerrarla con «Cancelar».
    # Ejecutar desde la raíz del proyecto:
    #     python -m ui_helpers.dialogs.metadata_progress_dialog [--ventana]
    import sys

    from qtpy.QtCore import QTimer
    from qtpy.QtWidgets import QApplication

    # 1. Textos (con el punto de miles del resto de la aplicación)
    assert message_text(22012).startswith(
        "Se van a leer los metadatos de 22.012 archivos, la operación puede tardar"
    ), message_text(22012)
    assert "miniaturas" not in message_text(22012)  # se generan después, sin bloquear
    assert message_text(22012).endswith("Durante el proceso la edición está deshabilitada.")
    assert "de 1 archivo," in message_text(1)
    assert count_text(1234, 22012) == "1.234 de 22.012"
    print("1. Textos: correctos")

    app = QApplication.instance() or QApplication(sys.argv)

    if "--ventana" in sys.argv:
        dialog = MetadataProgressDialog()
        state = {"done": 0}
        timer = QTimer()

        def tick() -> None:
            state["done"] = min(state["done"] + 137, 22012)
            dialog.set_progress(state["done"], 22012)
            if state["done"] >= 22012:
                timer.stop()
                dialog.finish()
                app.quit()

        def cancelled() -> None:
            timer.stop()
            QTimer.singleShot(800, lambda: (dialog.finish(), app.quit()))  # como un lote

        dialog.cancel_requested.connect(cancelled)
        timer.timeout.connect(tick)
        timer.start(50)
        dialog.show()
        app.exec()
        sys.exit(0)

    # 2. El avance se ve en el texto, la barra y el recuento
    dialog = MetadataProgressDialog()
    dialog.set_progress(1234, 22012)
    assert "22.012 archivos" in dialog._message.text()
    assert (dialog._bar.value(), dialog._bar.maximum()) == (1234, 22012)
    assert dialog._count.text() == "1.234 de 22.012"
    dialog.set_progress(0, 0)  # sin total: rango válido, no "indeterminado"
    assert dialog._bar.maximum() == 1
    print("2. Avance: correcto")

    # 3. Esc y cerrar no hacen nada; «Cancelar» avisa UNA vez y lo dice en el recuento
    cancels: list[bool] = []
    dialog.cancel_requested.connect(lambda: cancels.append(True))
    # (sin mostrarla, 'result()' ya vale Rejected: se fija otro y se mira que Esc no lo toca)
    dialog.setResult(QDialog.DialogCode.Accepted)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Accepted and not dialog._finished
    dialog._cancel_button.click()
    dialog._cancel_button.click()  # desactivado: no cuenta
    assert cancels == [True] and dialog._count.text() == CANCELLING_TEXT
    dialog.set_progress(2000, 22012)  # un aviso rezagado no borra el «Cancelando...»
    assert dialog._count.text() == CANCELLING_TEXT
    print("3. Esc no cierra; «Cancelar», una sola vez")

    # 4. 'finish' sí la cierra
    dialog.finish()
    assert dialog._finished and dialog.result() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    print("4. Cierre al terminar: correcto")

    print("Autoprueba finalizada correctamente.")
