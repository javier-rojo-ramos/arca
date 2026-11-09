"""Ventana «Gestionar ajustes personalizados» de la barra de filtros.

    ┌ Gestionar ajustes personalizados ──────────────────────────┐
    │ ┌──────────────────────────────┐  [ Subir                ] │
    │ │ Columnas de partida          │  [ Bajar                ] │
    │ │ Ubicación                    │  [ Cambiar nombre       ] │
    │ │ ...                          │  [ Eliminar             ] │
    │ └──────────────────────────────┘                           │
    │ Arrastra para cambiar el orden...  [ Restaurar los de fábrica ] │
    │                                      [ Aceptar ] [ Cancelar ] │
    └────────────────────────────────────────────────────────────┘

La lista tiene TODOS los ajustes (los de todos los módulos), en el orden del desplegable:
    - Ordenar: arrastrando, o con «Subir» y «Bajar».
    - Cambiar el nombre: doble clic (o F2) en la lista, o «Cambiar nombre». Un nombre vacío
      o repetido (sin distinguir mayúsculas) no se acepta: vuelve el que tenía y se avisa
      debajo de la lista.
    - Eliminar: sin preguntar (nada cambia hasta «Aceptar»).
    - «Restaurar los de fábrica»: añade al final los de fábrica que falten, sin tocar los
      demás ('filter_presets.with_factory_restored'). Desactivado si no falta ninguno.

Es una ventana hecha en código (sin .ui). No toca settings.json: devuelve la lista nueva y
quien la abre ('controllers/filter_preset_controller.py') la guarda.

Uso:
    result = FilterPresetsDialog.ask(parent, presets)
    if result is not None:
        presets, renamed = result   # 'renamed': nombre de antes -> nombre nuevo

1.0.0 Primera versión (paso A.3, filtros personalizados, subpaso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.dialogs.filter_presets_dialog
Para verla (abre la ventana y espera a que se cierre):
    python -m ui_helpers.dialogs.filter_presets_dialog --ventana
"""

__version__ = "1.0.0"
__all__ = [
    "DUPLICATE_TEXT",
    "EMPTY_NAME_TEXT",
    "ERROR_OBJECT_NAME",
    "HINT_OBJECT_NAME",
    "HINT_TEXT",
    "TITLE_TEXT",
    "FilterPresetsDialog",
]

# Librerías estándar
from collections.abc import Sequence

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.filter_presets import (
    MAX_PRESET_NAME,
    FilterPreset,
    clean_name,
    find_preset,
    with_factory_restored,
)

# Textos de la interfaz
TITLE_TEXT = "Gestionar ajustes personalizados"
HINT_TEXT = "Arrastra para cambiar el orden; doble clic para cambiar el nombre."
UP_TEXT = "Subir"
DOWN_TEXT = "Bajar"
RENAME_TEXT = "Cambiar nombre"
DELETE_TEXT = "Eliminar"
FACTORY_TEXT = "Restaurar los de fábrica"
EMPTY_NAME_TEXT = "El nombre no puede quedar vacío."
DUPLICATE_TEXT = "Ya hay un ajuste llamado «{name}»."

# Nombres de objeto (los usa el QSS de 'ui_theme.py': texto secundario y aviso en rojo)
HINT_OBJECT_NAME = "lbl_dialog_hint"
ERROR_OBJECT_NAME = "lbl_dialog_error"

# Datos de cada fila de la lista
_ORIGINAL_ROLE = Qt.ItemDataRole.UserRole  # posición en '_originals' (su filtro)
_NAME_ROLE = Qt.ItemDataRole.UserRole + 1  # el último nombre aceptado (para volver a él)

# Medidas (px lógicos)
_MIN_WIDTH = 460
_LIST_MIN_HEIGHT = 260


class FilterPresetsDialog(QDialog):
    """Ventana para ordenar, renombrar, eliminar y restaurar los ajustes personalizados."""

    def __init__(self, presets: Sequence[FilterPreset], parent: QWidget | None = None) -> None:
        """Crea la ventana con la lista de ajustes.

        Args:
            presets: Todos los ajustes, en su orden.
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle(TITLE_TEXT)
        self.setModal(True)
        self.setMinimumWidth(_MIN_WIDTH)
        # Los ajustes de los que salen las filas (los de fábrica restaurados se añaden)
        self._originals: list[FilterPreset] = []
        self._reverting = False  # al devolver un nombre no válido, 'itemChanged' no cuenta

        # --- Lista: ordenar arrastrando, renombrar con doble clic o F2 ---
        self.list_presets = QListWidget(self)
        self.list_presets.setMinimumHeight(_LIST_MIN_HEIGHT)
        self.list_presets.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_presets.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_presets.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_presets.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        for preset in presets:
            self._add_item(preset)

        # --- Botones de la derecha ---
        self.button_up = QPushButton(UP_TEXT, self)
        self.button_down = QPushButton(DOWN_TEXT, self)
        self.button_rename = QPushButton(RENAME_TEXT, self)
        self.button_delete = QPushButton(DELETE_TEXT, self)
        self.button_factory = QPushButton(FACTORY_TEXT, self)
        side = QVBoxLayout()
        for button in (self.button_up, self.button_down, self.button_rename, self.button_delete):
            side.addWidget(button)
        side.addStretch(1)
        side.addWidget(self.button_factory)

        middle = QHBoxLayout()
        middle.addWidget(self.list_presets, 1)
        middle.addLayout(side)

        # --- Debajo: cómo se usa y, si hace falta, el aviso de un nombre no válido ---
        self.label_hint = QLabel(HINT_TEXT, self)
        self.label_hint.setObjectName(HINT_OBJECT_NAME)
        self.label_hint.setWordWrap(True)
        self.label_error = QLabel(self)
        self.label_error.setObjectName(ERROR_OBJECT_NAME)
        self.label_error.setWordWrap(True)
        self.label_error.setVisible(False)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(middle)
        layout.addWidget(self.label_hint)
        layout.addWidget(self.label_error)
        layout.addWidget(self.buttons)

        self.button_up.clicked.connect(lambda: self._move_current(-1))
        self.button_down.clicked.connect(lambda: self._move_current(1))
        self.button_rename.clicked.connect(self._rename_current)
        self.button_delete.clicked.connect(self._delete_current)
        self.button_factory.clicked.connect(self._restore_factory)
        self.list_presets.currentRowChanged.connect(self._update_buttons)
        self.list_presets.itemChanged.connect(self._on_item_changed)
        # Tras arrastrar una fila, «Subir» y «Bajar» según su nuevo sitio
        self.list_presets.model().rowsMoved.connect(self._update_buttons)

        if self.list_presets.count():
            self.list_presets.setCurrentRow(0)
        self._update_buttons()

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def presets(self) -> list[FilterPreset]:
        """Los ajustes como han quedado: en el orden de la lista y con sus nombres."""
        return [
            FilterPreset(item.text(), self._original(item).grid_filter) for item in self._items()
        ]

    def renamed(self) -> dict[str, str]:
        """Los que han cambiado de nombre y siguen en la lista: nombre de antes -> nuevo."""
        result: dict[str, str] = {}
        for item in self._items():
            before = self._original(item).name
            if item.text() != before:
                result[before] = item.text()
        return result

    @classmethod
    def ask(
        cls, parent: QWidget | None, presets: Sequence[FilterPreset]
    ) -> tuple[list[FilterPreset], dict[str, str]] | None:
        """Abre la ventana y devuelve (la lista nueva, los renombrados), o None si se canceló."""
        dialog = cls(presets, parent)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.presets(), dialog.renamed()
        finally:
            dialog.deleteLater()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _items(self) -> list[QListWidgetItem]:
        """Las filas, en su orden."""
        return [self.list_presets.item(row) for row in range(self.list_presets.count())]

    def _original(self, item: QListWidgetItem) -> FilterPreset:
        """El ajuste del que salió la fila (su filtro no cambia aquí)."""
        return self._originals[item.data(_ORIGINAL_ROLE)]

    def _add_item(self, preset: FilterPreset) -> QListWidgetItem:
        """Añade una fila al final (se puede arrastrar y renombrar, no soltar encima)."""
        self._originals.append(preset)
        item = QListWidgetItem(preset.name)
        item.setData(_ORIGINAL_ROLE, len(self._originals) - 1)
        item.setData(_NAME_ROLE, preset.name)
        item.setFlags(
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        self.list_presets.addItem(item)
        return item

    def _update_buttons(self, *_args: object) -> None:
        """Qué se puede pulsar según la fila elegida y lo que falte de fábrica."""
        row = self.list_presets.currentRow()
        count = self.list_presets.count()
        selected = 0 <= row < count
        self.button_up.setEnabled(selected and row > 0)
        self.button_down.setEnabled(selected and row < count - 1)
        self.button_rename.setEnabled(selected)
        self.button_delete.setEnabled(selected)
        missing = len(with_factory_restored(self.presets())) > count
        self.button_factory.setEnabled(missing)

    def _move_current(self, step: int) -> None:
        """«Subir» (-1) o «Bajar» (+1) la fila elegida, que sigue elegida."""
        row = self.list_presets.currentRow()
        target = row + step
        if not (0 <= row < self.list_presets.count() and 0 <= target < self.list_presets.count()):
            return
        item = self.list_presets.takeItem(row)
        self.list_presets.insertItem(target, item)
        self.list_presets.setCurrentRow(target)
        self._update_buttons()

    def _rename_current(self) -> None:
        """«Cambiar nombre»: edita la fila elegida en la propia lista."""
        item = self.list_presets.currentItem()
        if item is not None:
            self.list_presets.editItem(item)

    def _delete_current(self) -> None:
        """«Eliminar» la fila elegida; queda elegida la siguiente (o la anterior)."""
        row = self.list_presets.currentRow()
        if not 0 <= row < self.list_presets.count():
            return
        self.list_presets.takeItem(row)
        if self.list_presets.count():
            self.list_presets.setCurrentRow(min(row, self.list_presets.count() - 1))
        self._show_error("")
        self._update_buttons()

    def _restore_factory(self) -> None:
        """«Restaurar los de fábrica»: los que falten, al final; queda elegido el primero."""
        current = self.presets()
        restored = with_factory_restored(current)
        added = restored[len(current):]
        for preset in added:
            self._add_item(preset)
        if added:
            self.list_presets.setCurrentRow(len(current))
        self._update_buttons()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Un nombre cambiado en la lista: se limpia o, si no vale, vuelve el de antes."""
        if self._reverting:
            return
        previous = item.data(_NAME_ROLE)
        others = [p for other, p in zip(self._items(), self.presets()) if other is not item]
        error = ""
        try:
            name = clean_name(item.text())
        except ValueError:
            name, error = previous, EMPTY_NAME_TEXT
        found = None if error else find_preset(others, name)
        if found is not None:
            error = DUPLICATE_TEXT.format(name=others[found].name)  # como se llama el otro
            name = previous
        self._reverting = True
        try:
            item.setText(name)  # limpio (sin espacios de sobra) o el de antes
            item.setData(_NAME_ROLE, name)
        finally:
            self._reverting = False
        self._show_error(error)

    def _show_error(self, text: str) -> None:
        """El aviso debajo de la lista (vacío = sin aviso)."""
        self.label_error.setText(text)
        self.label_error.setVisible(bool(text))


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica de la lista.
    # Con '--ventana', la abre de verdad (y espera a que se cierre).
    import os
    import sys

    show_window = "--ventana" in sys.argv
    if not show_window:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import QModelIndex
    from qtpy.QtWidgets import QApplication

    from core.catalog.filter_presets import factory_presets, preset_from_filter
    from core.catalog.grid_filter import FILTER_TEXT, GridFilter, TextFilter

    app = QApplication([])
    weddings = GridFilter(active=frozenset({FILTER_TEXT}), text=TextFilter(text="boda"))
    start = [*factory_presets(), preset_from_filter("Bodas", weddings, ())]

    if show_window:
        from ui_helpers.helpers.ui_theme import apply_theme

        apply_theme()
        print(FilterPresetsDialog.ask(None, start))
        sys.exit(0)

    dialog = FilterPresetsDialog(start)

    def names() -> list[str]:
        return [p.name for p in dialog.presets()]

    # 1. Al abrir: todos, en su orden; la primera elegida; nada de fábrica que restaurar
    assert names() == [p.name for p in start] and dialog.presets() == start
    assert dialog.list_presets.currentRow() == 0 and dialog.renamed() == {}
    assert not dialog.button_up.isEnabled() and dialog.button_down.isEnabled()
    assert not dialog.button_factory.isEnabled() and dialog.label_error.isHidden()
    assert dialog.windowTitle() == TITLE_TEXT

    # 2. «Bajar» y «Subir»: la fila se mueve y sigue elegida
    dialog.button_down.click()
    assert names()[:2] == ["Ubicación", "Columnas de partida"]
    assert dialog.list_presets.currentRow() == 1
    dialog.button_up.click()
    assert names()[:2] == ["Columnas de partida", "Ubicación"]
    dialog.list_presets.setCurrentRow(5)  # la última: no se puede bajar
    assert dialog.button_up.isEnabled() and not dialog.button_down.isEnabled()

    # 3. Arrastrar (lo que hace la lista al soltar): la fila 0, al final
    model = dialog.list_presets.model()
    assert model.moveRow(QModelIndex(), 0, QModelIndex(), model.rowCount())
    assert names()[-1] == "Columnas de partida" and names()[0] == "Ubicación"

    # 4. Cambiar el nombre: se limpia; vacío o repetido (otras mayúsculas), vuelve el de antes
    item = dialog.list_presets.item(0)
    item.setText("  Sitios   y lugares ")
    assert item.text() == "Sitios y lugares" and dialog.label_error.isHidden()
    item.setText("   ")
    assert item.text() == "Sitios y lugares" and dialog.label_error.text() == EMPTY_NAME_TEXT
    item.setText("BODAS")
    assert item.text() == "Sitios y lugares"
    assert dialog.label_error.text() == "Ya hay un ajuste llamado «Bodas»."
    item.setText("Sitios")  # uno válido quita el aviso
    assert dialog.label_error.isHidden()
    assert dialog.renamed() == {"Ubicación": "Sitios"}
    # El filtro de un ajuste renombrado es el mismo
    assert dialog.presets()[0].grid_filter == start[1].grid_filter
    assert len(item.text()) <= MAX_PRESET_NAME

    # 5. Eliminar: sin preguntar; queda elegida la siguiente
    dialog.list_presets.setCurrentRow(1)  # «Datos de exposición»
    dialog.button_delete.click()
    assert "Datos de exposición" not in names() and dialog.list_presets.currentRow() == 1

    # 6. Restaurar los de fábrica: los que falten («Ubicación», renombrado; «Datos de
    # exposición», eliminado), al final; después, ya no se puede
    assert dialog.button_factory.isEnabled()
    dialog.button_factory.click()
    assert names()[-2:] == ["Ubicación", "Datos de exposición"], names()
    assert not dialog.button_factory.isEnabled()
    assert dialog.renamed() == {"Ubicación": "Sitios"}  # el restaurado no cuenta

    # 7. Sin filas: nada que mover, renombrar ni eliminar
    empty = FilterPresetsDialog([])
    assert empty.presets() == [] and not empty.button_delete.isEnabled()
    assert empty.button_factory.isEnabled()
    empty.button_factory.click()
    assert [p.name for p in empty.presets()] == [p.name for p in factory_presets()]

    dialog.deleteLater()
    empty.deleteLater()
    print("Autoprueba finalizada correctamente.")
