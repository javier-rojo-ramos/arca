"""Ventana «Nueva carpeta» (menú de una carpeta del árbol del Catálogo; CAT 4.4a).

    ┌ Nueva carpeta ────────────────────────────────────────────────┐
    │ Nueva carpeta dentro de «Viaje»                               │
    │                                                               │
    │ [Nueva carpeta                                              ] │
    │ El nombre no puede llevar estos caracteres: < > : " / \\ | ? *│  (solo si no vale)
    │                                                               │
    │ La carpeta se crea también en el disco y se mueven a ella los │
    │ 3 archivos seleccionados (con su .xmp, si son RAW). Conservan │
    │ la valoración, las palabras clave y las colecciones.          │
    │                                           [Crear]  [Cancelar] │
    └───────────────────────────────────────────────────────────────┘

Como en Lightroom («Crear carpeta» con «Incluir las fotos seleccionadas»), pero siempre con
lo elegido dentro: el árbol de «Carpetas» solo muestra carpetas con archivos y lo que se
hace en el disco desde la aplicación tiene que verse en ella (regla del autor, 19/11/2026).
Quien la abre ('controllers/file_actions.py') comprueba antes que haya algo elegido. No
toca el disco: devuelve el nombre, y quien la abre calcula el plan y lanza el trabajo.

Reglas, las de «Cambiar nombre» ('rename_dialog.py'): el nombre se comprueba al escribir
('name_problem') y su motivo ocupa siempre su línea (al aparecer no se mueve nada); «Crear»
es el botón por defecto (Intro) y se desactiva si el nombre no vale; Esc = «Cancelar».

Uso:
    name = NewFolderDialog.ask(parent, "Viaje", 3)       # el nombre, o None si se cancela

1.1.0 Sin la casilla «Incluir los archivos seleccionados»: siempre con lo elegido (una
      carpeta vacía no se vería en el árbol; lo pidió el autor al probarla).
1.0.0 Primera versión (CAT 4.4a).

Prueba rápida (sin abrir ninguna ventana; desde la raíz del proyecto):
    python -m ui_helpers.dialogs.new_folder_dialog
"""

__version__ = "1.1.0"
__all__ = ["DEFAULT_NAME", "NewFolderDialog", "explanation_text"]

# Librerías de terceros (Qt)
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.file_ops.naming import clean_name, name_problem
from ui_helpers.helpers.ui_theme import ACCENT_COLOR

# El nombre que se propone (como el Explorador)
DEFAULT_NAME = "Nueva carpeta"

CREATE_BUTTON_TEXT = "Crear"
CANCEL_BUTTON_TEXT = "Cancelar"

# El título va algo más grande que el texto normal (puntos de diferencia), como en «Eliminar»
_TITLE_EXTRA_POINTS = 3


def explanation_text(selected: int) -> str:
    """El aviso: se crea en el disco y se mueve a ella lo elegido, que conserva lo suyo.

    Está fuera de la clase para poder probarlo sin abrir ninguna ventana.
    """
    if selected == 1:
        return (
            "La carpeta se crea también en el disco y se mueve a ella el archivo seleccionado "
            "(con su .xmp, si es un RAW). Conserva la valoración, las palabras clave y las "
            "colecciones."
        )
    return (
        f"La carpeta se crea también en el disco y se mueven a ella los {selected} archivos "
        "seleccionados (con su .xmp, si son RAW). Conservan la valoración, las palabras clave "
        "y las colecciones."
    )


class NewFolderDialog(QDialog):
    """Ventana para el nombre de una carpeta nueva, a la que se mueve lo elegido."""

    def __init__(
        self,
        parent_name: str,
        selected: int,
        *,
        initial_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Crea la ventana.

        Args:
            parent_name: Nombre de la carpeta (o ubicación) dentro de la que se crea.
            selected: Cuántos archivos hay elegidos (se mueven a ella).
            initial_name: Lo que aparece escrito (None = «Nueva carpeta»): al volver a
                abrirla tras un problema, lo que el usuario había escrito.
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle("Nueva carpeta")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        # --- Título, más grande y en color de acento ---
        title = QLabel(f"Nueva carpeta dentro de «{parent_name}»")
        title.setWordWrap(True)
        font = title.font()
        font.setPointSize(font.pointSize() + _TITLE_EXTRA_POINTS)
        title.setFont(font)
        title.setStyleSheet(f"color: {ACCENT_COLOR};")
        layout.addWidget(title)
        layout.addSpacing(8)

        # --- El nombre ---
        self._edit = QLineEdit(DEFAULT_NAME if initial_name is None else initial_name)
        layout.addWidget(self._edit)

        # --- Por qué no vale: una línea fija, vacía si vale (como en «Cambiar nombre») ---
        self._problem = QLabel("Á")  # un texto cualquiera, para medir el alto de una línea
        self._problem.setObjectName("lbl_dialog_error")  # en rojo (QSS de 'ui_theme')
        self._problem.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._problem.ensurePolished()
        self._problem.setFixedHeight(self._problem.sizeHint().height())
        self._problem.setText("")
        layout.addWidget(self._problem)
        layout.addSpacing(6)

        # --- El aviso: lo que pasa en el disco ---
        self._explanation = QLabel(explanation_text(selected))
        self._explanation.setWordWrap(True)
        layout.addWidget(self._explanation)
        layout.addSpacing(12)

        # --- Botones ---
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._create_button = QPushButton(CREATE_BUTTON_TEXT)
        self._create_button.setDefault(True)  # Intro
        self._create_button.clicked.connect(self.accept)
        cancel_button = QPushButton(CANCEL_BUTTON_TEXT)
        cancel_button.setAutoDefault(False)
        cancel_button.clicked.connect(self.reject)  # Esc también cierra con 'reject'
        buttons.addWidget(self._create_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        self._edit.textChanged.connect(self._check)
        self._check()
        self._edit.selectAll()
        self._edit.setFocus()

    def _check(self) -> None:
        """Comprueba el nombre: el motivo si no vale; «Crear», solo si vale."""
        problem = name_problem(self.name())
        self._problem.setText(problem or "")
        self._create_button.setEnabled(problem is None)

    def name(self) -> str:
        """El nombre escrito, sin espacios alrededor."""
        return clean_name(self._edit.text())

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        parent_name: str,
        selected: int,
        initial_name: str | None = None,
    ) -> str | None:
        """Abre la ventana. Devuelve el nombre, o None si se cancela."""
        dialog = cls(parent_name, selected, initial_name=initial_name, parent=parent)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.name()
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    # Autoprueba SIN abrir ninguna ventana: la ventana se crea, pero no se muestra.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.new_folder_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    assert "se mueven a ella los 3 archivos seleccionados (con su .xmp, si son RAW)" in (
        explanation_text(3)
    )
    assert "se mueve a ella el archivo seleccionado" in explanation_text(1)
    print("1. El aviso: lo elegido se mueve a ella")

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = NewFolderDialog("Viaje", 3)
    assert dialog.name() == DEFAULT_NAME and dialog._edit.selectedText() == DEFAULT_NAME
    assert dialog._create_button.isEnabled()
    reserved = dialog._problem.height()
    dialog._edit.setText("mal:nombre")
    assert not dialog._create_button.isEnabled() and "caracteres" in dialog._problem.text()
    assert dialog._problem.height() == reserved  # la línea del motivo no cambia de alto
    dialog._edit.setText("  Selección ")
    assert dialog._create_button.isEnabled() and dialog.name() == "Selección"
    dialog.deleteLater()
    again = NewFolderDialog("Viaje", 1, initial_name="Lo escrito")
    assert again.name() == "Lo escrito"
    again.deleteLater()
    app.processEvents()
    print("2. La caja y la línea del motivo; otra vez, con lo escrito")
    print("Autoprueba finalizada correctamente.")
