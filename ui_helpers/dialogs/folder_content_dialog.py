"""Ventana "¿Qué contiene esta carpeta?" (al añadir una carpeta al catálogo).

    Carpeta: D:/Música
    Vale también para sus subcarpetas.

    (•) Detectar automáticamente
        Se cataloga todo lo soportado...
    ( ) Imágenes
        Fotos y vídeos de cámara o de móvil...
    ( ) Vídeos
    ( ) Música
    ( ) Libros
    ( ) Tracks GPS
                                        [Añadir] [Cancelar]

Es una ventana sencilla, hecha en código (sin .ui). No toca la base de datos: devuelve el
tipo de contenido elegido ('auto' o una biblioteca, ver core/catalog/libraries.py) y quien
la abre ('main_window_controller.py') añade la carpeta con él.

Prueba suelta (sin el resto de la aplicación):
    python -m ui_helpers.dialogs.folder_content_dialog

Los nombres de las bibliotecas salen de 'core/catalog/libraries.LIBRARY_NAMES'. Si alguno
lleva '&', en los botones y menús de Qt hay que escribirlo doble: 'qt_text()' lo hace.

1.2.0 Pulsar la explicación de una opción también la elige (antes solo el círculo y el
      título); la explicación sigue en gris, pero ya no es un texto desactivado.
1.1.0 Nombres de las bibliotecas desde 'LIBRARY_NAMES' y 'qt_text()' para mostrarlos en
      botones y menús (por si alguno lleva '&').

Uso:
    content = FolderContentDialog.ask(parent, folder, current="auto")
    if content is not None:
        ...  # 'auto', 'image', 'video', 'audio', 'ebook' o 'tracks'
"""

__version__ = "1.2.0"
__all__ = ["FOLDER_CONTENT_TEXTS", "FolderContentDialog", "qt_text"]

# Librerías estándar
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtGui import QMouseEvent, QPalette
from qtpy.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.libraries import FOLDER_AUTO, FOLDER_CONTENTS, LIBRARY_NAMES, Library

# Texto de cada opción: (título, explicación). Las claves son las de 'FOLDER_CONTENTS'
FOLDER_CONTENT_TEXTS: dict[str, tuple[str, str]] = {
    FOLDER_AUTO: (
        "Detectar automáticamente",
        (
            "Se cataloga todo lo soportado. Fotos, música, libros y tracks van a su "
            "biblioteca; los vídeos quedan sin clasificar (pueden ser clips o películas)."
        ),
    ),
    Library.IMAGE: (
        LIBRARY_NAMES[Library.IMAGE],
        "Fotos y vídeos de cámara o de móvil. Lo demás (música, documentos...) se ignora.",
    ),
    Library.VIDEO: (
        LIBRARY_NAMES[Library.VIDEO],
        "Solo vídeos. Pósters e imágenes sueltas se ignoran.",
    ),
    Library.AUDIO: (
        LIBRARY_NAMES[Library.AUDIO],
        (
            "Solo audio. Las carátulas sueltas (.jpg, .png) se ignoran: la carátula se "
            "tomará de las etiquetas de cada canción."
        ),
    ),
    Library.EBOOK: (LIBRARY_NAMES[Library.EBOOK], "Solo libros electrónicos."),
    Library.TRACKS: (LIBRARY_NAMES[Library.TRACKS], "Solo archivos GPX."),
}

assert set(FOLDER_CONTENT_TEXTS) == set(FOLDER_CONTENTS)  # no puede faltar ninguna opción


def qt_text(text: str) -> str:
    """Texto para un botón o un menú de Qt: '&' doble, para que se vea (y no subraye).

    En QAction, QRadioButton, QPushButton... un '&' marca la tecla de acceso (Alt + letra)
    y no se dibuja: «Fotos & Vídeos» saldría como «Fotos  Vídeos».
    """
    return text.replace("&", "&&")


class _OptionDescription(QLabel):
    """Explicación de una opción, en gris, que al pulsarla elige su botón de opción.

    No se usa 'setEnabled(False)' para el gris: un widget desactivado no recibe los
    clics. El color es el del texto desactivado de la paleta (el mismo de antes).
    """

    def __init__(self, text: str, button: QRadioButton, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._button = button
        self.setWordWrap(True)
        palette = self.palette()
        palette.setColor(
            QPalette.ColorRole.WindowText,
            palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText),
        )
        self.setPalette(palette)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Clic con el botón izquierdo: elige la opción y le pasa el foco (como el título)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._button.setChecked(True)
            self._button.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)


class FolderContentDialog(QDialog):
    """Ventana para elegir qué contiene una carpeta antes de añadirla."""

    def __init__(
        self, folder: str | Path, *, current: str = FOLDER_AUTO, parent: QWidget | None = None
    ) -> None:
        """Crea la ventana.

        Args:
            folder: Carpeta que se va a añadir (solo se muestra).
            current: Opción elegida al abrir: la que ya tiene la carpeta (declarada o
                heredada de la que la contiene), o 'auto'.
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle("¿Qué contiene esta carpeta?")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        # --- Carpeta (la ruta puede ser larga: se parte en varias líneas) ---
        label_folder = QLabel(f"<b>Carpeta:</b> {Path(folder)}")
        label_folder.setWordWrap(True)
        layout.addWidget(label_folder)
        label_hint = QLabel("Vale también para sus subcarpetas.")
        label_hint.setEnabled(False)  # texto atenuado
        layout.addWidget(label_hint)
        layout.addSpacing(6)

        # --- Una opción por tipo de contenido, con su explicación debajo ---
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QRadioButton] = {}
        for content in FOLDER_CONTENTS:
            title, explanation = FOLDER_CONTENT_TEXTS[content]
            button = QRadioButton(qt_text(title))
            self._group.addButton(button)
            self._buttons[content] = button
            layout.addWidget(button)

            label = _OptionDescription(explanation, button, self)
            label.setContentsMargins(22, 0, 0, 6)  # alineado con el texto del botón
            layout.addWidget(label)

        self._buttons.get(current, self._buttons[FOLDER_AUTO]).setChecked(True)

        # --- Botones ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Añadir")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def content(self) -> str:
        """Tipo de contenido elegido ('auto' o una biblioteca)."""
        return next(
            (content for content, button in self._buttons.items() if button.isChecked()),
            FOLDER_AUTO,
        )

    @classmethod
    def ask(
        cls, parent: QWidget | None, folder: str | Path, *, current: str = FOLDER_AUTO
    ) -> str | None:
        """Abre la ventana y devuelve el tipo de contenido elegido, o None si se canceló."""
        dialog = cls(folder, current=current, parent=parent)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.content()
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    # Prueba suelta: abre la ventana y muestra lo elegido (no toca ningún catálogo).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.folder_content_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    from ui_helpers.helpers.ui_theme import apply_theme

    app = QApplication(sys.argv)
    apply_theme()  # con el tema de la aplicación, como se ve dentro de ella
    chosen = FolderContentDialog.ask(None, Path.home() / "Música", current=Library.AUDIO)
    print(f"Elegido: {chosen!r}")
