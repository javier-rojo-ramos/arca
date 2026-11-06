"""Ventana "Crear colección" / "Crear conjunto de colecciones" (como la de Lightroom).

    Nombre:     [________________________]
    Ubicación:  [Ninguna (primer nivel)    ▾]   <- conjuntos donde se puede crear
    [x] Incluir los 12 elementos seleccionados  <- solo en colecciones, si hay selección

    Es una ventana sencilla, hecha en código (sin .ui). No toca la base de datos: devuelve
lo que ha elegido el usuario y quien la abre ('controllers/collection_actions.py') crea la
colección. Que el nombre no esté repetido se comprueba al crearla
('core/catalog/user_collections.py'), así vale también para otras formas de crearla.

Uso:
    choice = CollectionDialog.ask(parent, kind=KIND_STATIC, sets=[(3, "Álbumes")],
                                  parent_id=None, selection_count=12)
    if choice is not None:
        ...  # choice.name, choice.parent_id, choice.include_selection
"""

__version__ = "1.0.0"
__all__ = ["CollectionChoice", "CollectionDialog"]

# Librerías estándar
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.user_collections import KIND_SET, MAX_NAME_LENGTH


@dataclass(frozen=True, slots=True)
class CollectionChoice:
    """Lo que ha elegido el usuario.

    Attributes:
        name: Nombre escrito (sin espacios en los extremos).
        parent_id: Conjunto donde crearla (None = primer nivel).
        include_selection: Si hay que añadirle los elementos seleccionados.
    """

    name: str
    parent_id: int | None
    include_selection: bool


class CollectionDialog(QDialog):
    """Ventana para crear una colección o un conjunto de colecciones."""

    def __init__(
        self,
        *,
        kind: str,
        sets: list[tuple[int, str]],
        parent_id: int | None = None,
        selection_count: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        """Crea la ventana.

        Args:
            kind: KIND_STATIC (colección) o KIND_SET (conjunto).
            sets: Conjuntos donde se puede crear: (id, nombre con sus conjuntos delante).
            parent_id: Conjunto elegido al abrir (p. ej. si se pulsó "Crear aquí").
            selection_count: Elementos seleccionados en la cuadrícula (0 = ninguno).
            parent: Ventana padre.
        """
        super().__init__(parent)
        is_set = kind == KIND_SET
        self.setWindowTitle("Crear conjunto de colecciones" if is_set else "Crear colección")
        self.setModal(True)
        self.setMinimumWidth(380)

        # --- Nombre ---
        self.edit_name = QLineEdit()
        self.edit_name.setMaxLength(MAX_NAME_LENGTH)
        self.edit_name.setPlaceholderText("Nombre del conjunto" if is_set else "Nombre de la colección")

        # --- Ubicación: primer nivel o dentro de un conjunto ---
        self.combo_parent = QComboBox()
        self.combo_parent.addItem("Ninguna (primer nivel)", None)
        for set_id, set_name in sets:
            self.combo_parent.addItem(set_name, set_id)
        position = self.combo_parent.findData(parent_id) if parent_id is not None else 0
        self.combo_parent.setCurrentIndex(max(0, position))

        form = QFormLayout()
        form.addRow("Nombre:", self.edit_name)
        form.addRow("Dentro del conjunto:", self.combo_parent)

        # --- Incluir la selección (solo colecciones con algo seleccionado) ---
        self.check_include = QCheckBox()
        # (se guarda aparte: tras cerrar la ventana, 'isVisible()' devuelve siempre False)
        self._can_include = not is_set and selection_count > 0
        if self._can_include:
            text = (
                "Incluir el elemento seleccionado"
                if selection_count == 1
                else f"Incluir los {selection_count} elementos seleccionados"
            )
            self.check_include.setText(text)
            self.check_include.setChecked(True)  # como Lightroom
        else:
            self.check_include.setVisible(False)

        # --- Botones (Crear se activa al escribir un nombre) ---
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.button_ok.setText("Crear")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.edit_name.textChanged.connect(
            lambda text: self.button_ok.setEnabled(bool(text.strip()))
        )
        self.button_ok.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.check_include)
        layout.addWidget(self.buttons)

    def choice(self) -> CollectionChoice:
        """Lo elegido (llamar tras 'exec()' con resultado aceptado)."""
        return CollectionChoice(
            name=self.edit_name.text().strip(),
            parent_id=self.combo_parent.currentData(),
            include_selection=self._can_include and self.check_include.isChecked(),
        )

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        *,
        kind: str,
        sets: list[tuple[int, str]],
        parent_id: int | None = None,
        selection_count: int = 0,
    ) -> CollectionChoice | None:
        """Abre la ventana y devuelve lo elegido, o None si se canceló."""
        dialog = cls(
            kind=kind, sets=sets, parent_id=parent_id, selection_count=selection_count, parent=parent
        )
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.choice()
        finally:
            dialog.deleteLater()
