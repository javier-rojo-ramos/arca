"""Ventana «Nueva carpeta» («Crear nueva carpeta...» en el menú de una carpeta del árbol del
Catálogo; CAT 4.4a).

    ┌ Nueva carpeta ────────────────────────────────────────────────┐
    │ Nueva carpeta dentro de «Viaje»                               │
    │                                                               │
    │ [Nueva carpeta                                              ] │
    │ El nombre no puede llevar estos caracteres: < > : " / \\ | ? *│  (solo si no vale)
    │ [x] Incluir los 3 archivos seleccionados                      │
    │                                                               │
    │ La carpeta se crea también en el disco y se mueven a ella los │
    │ 3 archivos seleccionados. Conservan la valoración, las        │
    │ palabras clave y las colecciones.                             │
    │                                           [Crear]  [Cancelar] │
    └───────────────────────────────────────────────────────────────┘

Como en Lightroom («Crear carpeta» con «Incluir las fotos seleccionadas»). La casilla sale
marcada si hay algo elegido; sin nada elegido, desmarcada y desactivada, y la carpeta se crea
vacía (se ve en el árbol con 0: CAT 5, el árbol replica las carpetas del disco). El aviso
cambia con la casilla. No toca el disco: devuelve el nombre y si se incluye lo elegido, y
quien la abre ('controllers/file_actions.py') calcula el plan y lanza el trabajo.

Reglas, las de «Cambiar nombre» ('rename_dialog.py'): el nombre se comprueba al escribir
('name_problem') y su motivo ocupa siempre su línea (al aparecer no se mueve nada); «Crear»
es el botón por defecto (Intro) y se desactiva si el nombre no vale; Esc = «Cancelar».

Uso:
    answer = NewFolderDialog.ask(parent, "Viaje", 3)     # (nombre, incluir) o None

1.2.2 El título, con el tamaño de 'theme_fonts' (16 px), en lugar de sumar 3 puntos a la fuente
      normal: con la fuente en px, 'pointSize()' es -1 (GEN 21.1).
1.2.1 El aviso ya no menciona el .xmp de los RAW (se entiende que va con su archivo; lo
      pidió el autor).
1.2.0 Otra vez con la casilla «Incluir los N archivos seleccionados» (marcada si hay algo
      elegido): sin ella, la carpeta se crea vacía, que ya se ve en el árbol (CAT 5).
      'ask' devuelve (nombre, incluir).
1.1.0 Sin la casilla «Incluir los archivos seleccionados»: siempre con lo elegido (una
      carpeta vacía no se vería en el árbol; lo pidió el autor al probarla).
1.0.0 Primera versión (CAT 4.4a).

Prueba rápida (sin abrir ninguna ventana; desde la raíz del proyecto):
    python -m ui_helpers.dialogs.new_folder_dialog
"""

__version__ = "1.2.2"
__all__ = ["DEFAULT_NAME", "NewFolderDialog", "explanation_text"]

# Librerías de terceros (Qt)
from qtpy.QtWidgets import (
    QCheckBox,
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
from ui_helpers.helpers.theme_fonts import FONT_SIZES, ui_font
from ui_helpers.helpers.ui_theme import ACCENT_COLOR

# El nombre que se propone (como el Explorador)
DEFAULT_NAME = "Nueva carpeta"

CREATE_BUTTON_TEXT = "Crear"
CANCEL_BUTTON_TEXT = "Cancelar"


def explanation_text(selected: int, include: bool = True) -> str:
    """El aviso: se crea en el disco y, si se incluye, se mueve a ella lo elegido.

    Está fuera de la clase para poder probarlo sin abrir ninguna ventana.
    """
    if not (include and selected):
        return (
            "La carpeta se crea también en el disco, vacía. Para llenarla, arrastra a ella "
            "tarjetas de la cuadrícula."
        )
    # Sin mencionar el .xmp de los RAW: se entiende que va con su archivo (el autor)
    if selected == 1:
        return (
            "La carpeta se crea también en el disco y se mueve a ella el archivo seleccionado. "
            "Conserva la valoración, las palabras clave y las colecciones."
        )
    return (
        f"La carpeta se crea también en el disco y se mueven a ella los {selected} archivos "
        "seleccionados. Conservan la valoración, las palabras clave y las colecciones."
    )


class NewFolderDialog(QDialog):
    """Ventana para el nombre de una carpeta nueva y si se mueve a ella lo elegido."""

    def __init__(
        self,
        parent_name: str,
        selected: int,
        *,
        initial_name: str | None = None,
        include: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Crea la ventana.

        Args:
            parent_name: Nombre de la carpeta (o ubicación) dentro de la que se crea.
            selected: Cuántos archivos hay elegidos (0 = la casilla, desactivada).
            initial_name: Lo que aparece escrito (None = «Nueva carpeta»): al volver a
                abrirla tras un problema, lo que el usuario había escrito.
            include: Cómo empieza la casilla si hay algo elegido (al volver a abrirla,
                como estaba).
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle("Nueva carpeta")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._selected = selected

        layout = QVBoxLayout(self)

        # --- Título, más grande y en color de acento ---
        title = QLabel(f"Nueva carpeta dentro de «{parent_name}»")
        title.setWordWrap(True)
        title.setFont(ui_font(FONT_SIZES.dialog_title))
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

        # --- Incluir lo elegido (desactivada si no hay nada) ---
        if selected == 1:
            files = "el archivo seleccionado"
        elif selected:
            files = f"los {selected} archivos seleccionados"
        else:
            files = "los archivos seleccionados"
        self._include = QCheckBox(f"Incluir {files}")
        self._include.setChecked(include and selected > 0)
        self._include.setEnabled(selected > 0)
        layout.addWidget(self._include)
        layout.addSpacing(6)

        # --- El aviso: lo que pasa en el disco (cambia con la casilla) ---
        self._explanation = QLabel(explanation_text(selected, self.include()))
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
        self._include.toggled.connect(
            lambda _checked: self._explanation.setText(
                explanation_text(self._selected, self.include())
            )
        )
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

    def include(self) -> bool:
        """Si se mueve a ella lo elegido."""
        return self._include.isChecked() and self._selected > 0

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        parent_name: str,
        selected: int,
        initial_name: str | None = None,
        include: bool = True,
    ) -> tuple[str, bool] | None:
        """Abre la ventana. Devuelve (nombre, si se incluye lo elegido), o None si se cancela."""
        dialog = cls(
            parent_name, selected, initial_name=initial_name, include=include, parent=parent
        )
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.name(), dialog.include()
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    # Autoprueba SIN abrir ninguna ventana: la ventana se crea, pero no se muestra.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.new_folder_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    assert "se mueven a ella los 3 archivos seleccionados. Conservan" in explanation_text(3)
    assert ".xmp" not in explanation_text(1) + explanation_text(3)
    assert "se mueve a ella el archivo seleccionado" in explanation_text(1)
    assert explanation_text(3, False).startswith("La carpeta se crea también en el disco, vacía")
    assert explanation_text(0) == explanation_text(3, False)
    print("1. El aviso: lo elegido se mueve a ella; si no, vacía")

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = NewFolderDialog("Viaje", 3)
    assert dialog.name() == DEFAULT_NAME and dialog._edit.selectedText() == DEFAULT_NAME
    assert dialog._create_button.isEnabled()
    assert dialog.include() and dialog._include.text() == "Incluir los 3 archivos seleccionados"
    dialog._include.setChecked(False)
    assert not dialog.include() and "vacía" in dialog._explanation.text()
    dialog._include.setChecked(True)
    assert "se mueven a ella los 3" in dialog._explanation.text()
    reserved = dialog._problem.height()
    dialog._edit.setText("mal:nombre")
    assert not dialog._create_button.isEnabled() and "caracteres" in dialog._problem.text()
    assert dialog._problem.height() == reserved  # la línea del motivo no cambia de alto
    dialog._edit.setText("  Selección ")
    assert dialog._create_button.isEnabled() and dialog.name() == "Selección"
    dialog.deleteLater()
    again = NewFolderDialog("Viaje", 1, initial_name="Lo escrito", include=False)
    assert again.name() == "Lo escrito" and not again.include()
    assert again._include.text() == "Incluir el archivo seleccionado"
    again.deleteLater()
    nothing = NewFolderDialog("Viaje", 0)
    assert not nothing._include.isEnabled() and not nothing.include()
    assert "vacía" in nothing._explanation.text()
    nothing.deleteLater()
    app.processEvents()
    print("2. La caja, la línea del motivo y la casilla; otra vez, con lo escrito")
    print("Autoprueba finalizada correctamente.")
