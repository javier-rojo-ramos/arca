"""Ventana «Cambiar nombre» de un archivo (menú de la tarjeta y F2; CAT 4.2) o de una carpeta.

    ┌ Cambiar nombre ──────────────────────────────────────────────┐
    │ Cambiar el nombre de «IMG_0001.CR3»                           │
    │                                                               │
    │ [IMG_0001                                       ]  .CR3       │
    │ El nombre no puede acabar en un espacio ni en un punto.       │  (solo si no vale)
    │                                                               │
    │ El nombre cambia también en el disco, y el de su .xmp. La     │
    │ valoración, las palabras clave y las colecciones se conservan.│
    │                                  [Cambiar nombre]  [Cancelar] │
    └───────────────────────────────────────────────────────────────┘

Es una ventana sencilla, hecha en código (sin .ui). No toca el disco ni la base de datos:
devuelve el nombre nuevo SIN la extensión (que no cambia) y quien la abre
('controllers/file_actions.py') calcula el plan y lanza el trabajo. La explicación es el
aviso de que la operación es en el disco (docs/DECISIONES.md, 19/11/2026).

Reglas:
    - Se abre con el nombre actual, sin la extensión, seleccionado (como el Explorador).
    - El nombre se comprueba al escribir ('core/file_ops/naming.name_problem': que valga en
      Windows, macOS y Linux); si no vale, el motivo sale debajo y el botón se desactiva. Su
      línea está siempre (vacía si vale): al aparecer el motivo no se mueve nada.
      También se desactiva si no ha cambiado (cambiar solo mayúsculas sí vale).
    - Lo que solo se sabe mirando el disco (que ya exista un archivo con ese nombre) lo dice
      quien la abre, después; para corregirlo, vuelve a abrirla con lo escrito
      ('initial_stem').
    - «Cambiar nombre» es el botón por defecto (Intro); Esc = «Cancelar».

Carpetas (CAT 4.3; menú de una carpeta del Catálogo): con 'folder_files' (cuántos archivos
del catálogo tiene). El título dice «la carpeta», el nombre se edita entero (una carpeta no
tiene extensión: «Viaje.2024» es todo nombre) y el aviso cuenta sus archivos.

Uso:
    stem = RenameDialog.ask(parent, "IMG_0001.CR3")       # None si se cancela
    name = RenameDialog.ask(parent, "Viaje", folder_files=12)

1.1.0 También para carpetas ('folder_files', 'folder_explanation_text'; CAT 4.3).
1.0.1 La línea del motivo está siempre, vacía si el nombre vale: al aparecer el motivo, la
      explicación y los botones ya no se mueven (lo pidió el autor al probarla).
1.0.0 Primera versión (CAT 4.2).

Prueba rápida (sin abrir ninguna ventana; desde la raíz del proyecto):
    python -m ui_helpers.dialogs.rename_dialog
"""

__version__ = "1.1.0"
__all__ = ["RenameDialog", "explanation_text", "folder_explanation_text"]

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
from core.file_ops.naming import clean_name, name_problem, split_extension
from core.userdata.policy import UserDataDestination, destination_for
from ui_helpers.helpers.ui_theme import ACCENT_COLOR

# Textos de los botones
RENAME_BUTTON_TEXT = "Cambiar nombre"
CANCEL_BUTTON_TEXT = "Cancelar"

# El título va algo más grande que el texto normal (puntos de diferencia), como en «Eliminar»
_TITLE_EXTRA_POINTS = 3


def explanation_text(file_name: str) -> str:
    """El aviso de la ventana: el nombre cambia también en el disco (y el de su .xmp si es un RAW).

    Está fuera de la clase para poder probarlo sin abrir ninguna ventana.
    """
    sidecar = destination_for(file_name) == UserDataDestination.XMP_SIDECAR
    disk = (
        "El nombre cambia también en el disco, y el de su .xmp."
        if sidecar
        else "El nombre cambia también en el disco."
    )
    return f"{disk} La valoración, las palabras clave y las colecciones se conservan."


def folder_explanation_text(count: int) -> str:
    """El aviso al renombrar una carpeta: cambia también en el disco; sus archivos, igual."""
    disk = "La carpeta cambia de nombre también en el disco."
    if count == 0:
        return disk
    files = "Su archivo conserva" if count == 1 else f"Sus {count} archivos conservan"
    return f"{disk} {files} la valoración, las palabras clave y las colecciones."


class RenameDialog(QDialog):
    """Ventana para escribir el nombre nuevo de un archivo (sin su extensión)."""

    def __init__(
        self,
        file_name: str,
        *,
        initial_stem: str | None = None,
        folder_files: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Crea la ventana.

        Args:
            file_name: Nombre actual del archivo, con su extensión (o de la carpeta).
            initial_stem: Lo que aparece escrito al abrirla (None = el nombre actual): al
                volver a abrirla tras un problema, lo que el usuario había escrito.
            folder_files: Si es una carpeta, cuántos archivos del catálogo tiene (None = es
                un archivo).
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle(RENAME_BUTTON_TEXT)
        self.setModal(True)
        self.setMinimumWidth(460)
        is_folder = folder_files is not None
        if is_folder:
            self._stem, self._extension = file_name, ""  # una carpeta no tiene extensión
        else:
            self._stem, self._extension = split_extension(file_name)

        layout = QVBoxLayout(self)

        # --- Título: "Cambiar el nombre de «...»", más grande y en color de acento ---
        what = "la carpeta " if is_folder else ""
        title = QLabel(f"Cambiar el nombre de {what}«{file_name}»")
        title.setWordWrap(True)
        font = title.font()
        font.setPointSize(font.pointSize() + _TITLE_EXTRA_POINTS)
        title.setFont(font)
        title.setStyleSheet(f"color: {ACCENT_COLOR};")
        layout.addWidget(title)
        layout.addSpacing(8)

        # --- El nombre (sin la extensión, que se ve al lado y no se puede cambiar) ---
        row = QHBoxLayout()
        self._edit = QLineEdit(self._stem if initial_stem is None else initial_stem)
        row.addWidget(self._edit, 1)
        if self._extension:
            row.addWidget(QLabel(self._extension))
        layout.addLayout(row)

        # --- Por qué no vale: la línea está siempre (vacía si vale), para que al aparecer
        #     el motivo no se mueva nada (lo pidió el autor) ---
        # Una sola línea, de alto fijo y sin ajuste (todos los motivos son cortos: ver
        # 'name_problem'); su ancho no cuenta para el de la ventana, que tampoco se mueve
        self._problem = QLabel("Á")  # un texto cualquiera, para medir el alto de una línea
        self._problem.setObjectName("lbl_dialog_error")  # en rojo (QSS de 'ui_theme')
        self._problem.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._problem.ensurePolished()
        self._problem.setFixedHeight(self._problem.sizeHint().height())
        self._problem.setText("")
        layout.addWidget(self._problem)
        layout.addSpacing(6)

        # --- El aviso: lo que pasa en el disco ---
        explanation = QLabel(
            folder_explanation_text(folder_files) if is_folder else explanation_text(file_name)
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addSpacing(12)

        # --- Botones ---
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._rename_button = QPushButton(RENAME_BUTTON_TEXT)
        self._rename_button.setDefault(True)  # Intro
        self._rename_button.clicked.connect(self.accept)
        cancel_button = QPushButton(CANCEL_BUTTON_TEXT)
        cancel_button.setAutoDefault(False)
        cancel_button.clicked.connect(self.reject)  # Esc también cierra con 'reject'
        buttons.addWidget(self._rename_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        self._edit.textChanged.connect(self._check)
        self._check()
        self._edit.selectAll()
        self._edit.setFocus()

    def _check(self) -> None:
        """Comprueba lo escrito: el motivo si no vale; el botón, solo si vale y ha cambiado."""
        stem = self.new_stem()
        problem = name_problem(stem + self._extension) if stem else name_problem(stem)
        self._problem.setText(problem or "")
        self._rename_button.setEnabled(problem is None and stem != self._stem)

    def new_stem(self) -> str:
        """El nombre escrito, sin espacios alrededor y sin la extensión."""
        return clean_name(self._edit.text())

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        file_name: str,
        initial_stem: str | None = None,
        *,
        folder_files: int | None = None,
    ) -> str | None:
        """Abre la ventana. Devuelve el nombre nuevo sin la extensión, o None si se cancela."""
        dialog = cls(
            file_name, initial_stem=initial_stem, folder_files=folder_files, parent=parent
        )
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.new_stem()
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    # Autoprueba SIN abrir ninguna ventana: la ventana se crea, pero no se muestra.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.rename_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    assert explanation_text("IMG_0001.CR3") == (
        "El nombre cambia también en el disco, y el de su .xmp. La valoración, las palabras "
        "clave y las colecciones se conservan."
    )
    assert explanation_text("foto.jpg").startswith("El nombre cambia también en el disco. La")
    print("1. El aviso: con el .xmp solo en los RAW")

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = RenameDialog("IMG_0001.CR3")
    assert dialog._edit.text() == "IMG_0001" and dialog._edit.selectedText() == "IMG_0001"
    assert not dialog._rename_button.isEnabled()  # sin cambiar, no hay nada que hacer
    dialog._edit.setText("  Boda en Ordesa ")
    assert dialog._rename_button.isEnabled() and dialog.new_stem() == "Boda en Ordesa"
    assert dialog._problem.text() == "" and not dialog._problem.isHidden()  # su línea, vacía
    reserved = dialog._problem.height()
    assert reserved > 0 and dialog._problem.maximumHeight() == reserved  # alto fijo
    for text, expected in (("", "vacío"), ("con:dos", "caracteres"), ("CON", "reservado")):
        dialog._edit.setText(text)
        assert not dialog._rename_button.isEnabled(), text
        assert expected in dialog._problem.text(), text
        assert dialog._problem.height() == reserved and not dialog._problem.wordWrap()
    dialog._edit.setText("final.")  # con la extensión, 'final..CR3': Windows lo admite
    assert dialog._rename_button.isEnabled()
    dialog._edit.setText("img_0001")  # solo mayúsculas: sí
    assert dialog._rename_button.isEnabled()
    dialog.deleteLater()
    bare = RenameDialog("LEEME")  # sin extensión, el punto final sí cuenta
    bare._edit.setText("final.")
    assert not bare._rename_button.isEnabled() and "acabar" in bare._problem.text()
    bare.deleteLater()
    again = RenameDialog("clip.mov", initial_stem="Lo que escribí")
    assert again._edit.text() == "Lo que escribí" and again._rename_button.isEnabled()
    again.deleteLater()
    print("2. La caja: el nombre seleccionado, el motivo si no vale y el botón")

    # 3. Una carpeta: el nombre entero (sin extensión), «la carpeta» y sus archivos
    assert folder_explanation_text(0) == "La carpeta cambia de nombre también en el disco."
    assert "Su archivo conserva la valoración" in folder_explanation_text(1)
    assert "Sus 12 archivos conservan la valoración" in folder_explanation_text(12)
    folder = RenameDialog("Viaje.2024", folder_files=12)
    assert folder._edit.text() == "Viaje.2024" and folder._extension == ""
    titles = [label.text() for label in folder.findChildren(QLabel)]
    assert "Cambiar el nombre de la carpeta «Viaje.2024»" in titles, titles
    folder._edit.setText("final.")  # sin extensión, el punto final cuenta
    assert not folder._rename_button.isEnabled() and "acabar" in folder._problem.text()
    folder.deleteLater()
    print("3. Una carpeta: el nombre entero, el título y el aviso con sus archivos")
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
