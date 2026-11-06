"""Ventana "Eliminar" (menú de las tarjetas y tecla Supr fuera de las colecciones).

Como la de Lightroom: un título, la explicación y un botón por acción.

    ┌ Confirmar ─────────────────────────────────────────────────────────────┐
    │ Eliminar 2 archivos del catálogo                                       │
    │                                                                        │
    │ Los archivos siguen en su carpeta y vuelven a aparecer si sincronizas  │
    │ la carpeta. Elige «Eliminar del disco» para enviarlos también a la     │
    │ Papelera de reciclaje (con el sidecar .xmp de los RAW).                │
    │                                                                        │
    │ ⚠ 1 archivo solo se quitará del catálogo: 1 porque está en una unidad  │
    │ de red (sin papelera).                                                 │
    │                                                                        │
    │        [Eliminar del disco]  [Eliminar del catálogo]  [Cancelar]       │
    └────────────────────────────────────────────────────────────────────────┘

Es una ventana sencilla, hecha en código (sin .ui). No toca la base de datos ni el disco:
devuelve lo elegido y quien la abre ('main_window_controller.py') lanza el trabajo
('core/catalog/media_removal.remove_media_items'). Lo que dice sobre la papelera sale de un
'RemovalPlan' ('media_removal.plan_removal'), calculado antes de abrirla.

Reglas:
    - "Eliminar del catálogo" es el botón por defecto (Intro) y tiene el foco (decidido
      por el autor: lo seguro). Esc = "Cancelar".
    - "Eliminar del disco" se desactiva si ningún archivo puede ir a la papelera (todos
      ausentes, desconectados o en una unidad de red); la explicación dice por qué.
    - Con una selección mixta, un aviso dice cuántos archivos solo se quitarán del
      catálogo aunque se pulse "Eliminar del disco", y por qué.

Prueba suelta (sin el resto de la aplicación):
    python -m ui_helpers.dialogs.remove_dialog

Uso:
    to_trash = RemoveDialog.ask(parent, plan)
    if to_trash is not None:
        ...  # False = eliminar del catálogo; True = también del disco (papelera)

1.1.1 Sin el icono de la aplicación junto al título (decidido por el autor; más adelante,
      quizá un icono de papelera: iría en '__init__', a la izquierda de 'texts').
1.1.0 Diseño como Lightroom: título, explicación y un botón por acción (antes, dos
      opciones y un botón de confirmar).
"""

__version__ = "1.1.1"
__all__ = ["RemoveDialog"]

# Librerías estándar
import sys

# Librerías de terceros (Qt)
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.media_removal import RemovalPlan
from ui_helpers.helpers.ui_theme import ACCENT_COLOR

# Nombre de la papelera del sistema, para la explicación
TRASH_NAME = "la Papelera de reciclaje" if sys.platform == "win32" else "la Papelera"

# Textos de los botones
DISK_BUTTON_TEXT = "Eliminar del disco"
CATALOG_BUTTON_TEXT = "Eliminar del catálogo"
CANCEL_BUTTON_TEXT = "Cancelar"

# El título va algo más grande que el texto normal (puntos de diferencia)
_TITLE_EXTRA_POINTS = 3


def explanation_text(plan: RemovalPlan) -> str:
    """Explicación de la ventana según cuántos archivos son y si pueden ir a la papelera.

    Está fuera de la clase para poder probarla sin abrir ninguna ventana.
    """
    single = plan.total == 1
    keep = (
        "El archivo sigue en su carpeta y vuelve a aparecer si sincronizas la carpeta."
        if single
        else "Los archivos siguen en su carpeta y vuelven a aparecer si sincronizas la carpeta."
    )
    if not plan.can_trash:
        # Ninguno puede ir a la papelera: se explica por qué (el botón sale desactivado)
        reason = plan.catalog_only_text().replace("solo se quitarán", "solo se pueden quitar")
        reason = reason.replace("solo se quitará", "solo se puede quitar")
        return f"{keep}\n\n{reason}" if reason else keep
    target = "enviarlo" if single else "enviarlos"
    sidecar = "si es un RAW" if single else "de los RAW"
    return (
        f"{keep} Elige «{DISK_BUTTON_TEXT}» para {target} también a {TRASH_NAME} "
        f"(con el sidecar .xmp {sidecar})."
    )


class RemoveDialog(QDialog):
    """Ventana para elegir entre eliminar del catálogo o también del disco (papelera)."""

    def __init__(self, plan: RemovalPlan, *, parent: QWidget | None = None) -> None:
        """Crea la ventana.

        Args:
            plan: Qué se puede enviar a la papelera ('media_removal.plan_removal').
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle("Confirmar")
        self.setModal(True)
        self.setMinimumWidth(480)
        self._to_trash = False  # lo cambia el botón "Eliminar del disco"

        layout = QVBoxLayout(self)
        # Textos (título, explicación y aviso). Si más adelante se pone un icono (p. ej. una
        # papelera), iría en una fila horizontal: [icono | texts]
        texts = QVBoxLayout()
        layout.addLayout(texts)

        # --- Título: "Eliminar N archivos del catálogo", más grande y en color de acento ---
        what = "1 archivo" if plan.total == 1 else f"{plan.total} archivos"
        title = QLabel(f"Eliminar {what} del catálogo")
        font = title.font()
        font.setPointSize(font.pointSize() + _TITLE_EXTRA_POINTS)
        title.setFont(font)
        title.setStyleSheet(f"color: {ACCENT_COLOR};")
        texts.addWidget(title)
        texts.addSpacing(8)

        # --- Explicación ---
        explanation = QLabel(explanation_text(plan))
        explanation.setWordWrap(True)
        texts.addWidget(explanation)

        # --- Aviso: con una selección mixta, lo que no puede ir a la papelera ---
        warning = plan.catalog_only_text() if plan.can_trash else ""
        if warning:
            texts.addSpacing(6)
            warning_label = QLabel(f"⚠ {warning}")
            warning_label.setWordWrap(True)
            texts.addWidget(warning_label)
        texts.addStretch(1)
        layout.addSpacing(12)

        # --- Botones, en el orden de Lightroom: disco, catálogo (por defecto), cancelar ---
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        disk_button = QPushButton(DISK_BUTTON_TEXT)
        disk_button.setAutoDefault(False)
        disk_button.clicked.connect(self._accept_disk)
        if not plan.can_trash:
            disk_button.setEnabled(False)
            disk_button.setToolTip(plan.catalog_only_text() or "No hay archivos que enviar a la papelera.")
        catalog_button = QPushButton(CATALOG_BUTTON_TEXT)
        catalog_button.setDefault(True)  # Intro = lo seguro
        catalog_button.clicked.connect(self.accept)
        cancel_button = QPushButton(CANCEL_BUTTON_TEXT)
        cancel_button.setAutoDefault(False)
        cancel_button.clicked.connect(self.reject)  # Esc también cierra con 'reject'
        for button in (disk_button, catalog_button, cancel_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        catalog_button.setFocus()

    def _accept_disk(self) -> None:
        """«Eliminar del disco»: se acepta con la papelera elegida."""
        self._to_trash = True
        self.accept()

    def to_trash(self) -> bool:
        """True si se pulsó "Eliminar del disco"."""
        return self._to_trash

    @classmethod
    def ask(cls, parent: QWidget | None, plan: RemovalPlan) -> bool | None:
        """Abre la ventana. Devuelve True (disco), False (solo catálogo) o None (cancelar)."""
        dialog = cls(plan, parent=parent)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.to_trash()
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    # Prueba suelta: comprueba los textos y abre la ventana con selecciones inventadas
    # (no toca nada). Ejecutar desde la raíz del proyecto:
    #     python -m ui_helpers.dialogs.remove_dialog
    from qtpy.QtWidgets import QApplication

    from core.catalog.media_removal import REASON_MISSING, REASON_NETWORK

    one = RemovalPlan(total=1, trashable=1)
    assert explanation_text(one).startswith("El archivo sigue en su carpeta")
    assert "enviarlo también a" in explanation_text(one) and "si es un RAW" in explanation_text(one)
    mixed = RemovalPlan(total=5, trashable=2, catalog_only={REASON_NETWORK: 2, REASON_MISSING: 1})
    assert "enviarlos también a" in explanation_text(mixed)
    network_only = RemovalPlan(total=1, trashable=0, catalog_only={REASON_NETWORK: 1})
    assert "1 archivo solo se puede quitar del catálogo" in explanation_text(network_only)
    print("Textos: correctos")

    app = QApplication(sys.argv)
    print(f"Selección mixta: {RemoveDialog.ask(None, mixed)!r}")
    print(f"Solo en red: {RemoveDialog.ask(None, network_only)!r}")
    print("Autoprueba finalizada correctamente.")
