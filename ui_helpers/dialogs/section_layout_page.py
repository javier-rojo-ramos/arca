"""Página «Paneles» de la ventana de opciones: las secciones de las barras, por módulo.

Permite ver y cambiar, para CUALQUIER módulo (no solo el activo) y para sus dos barras, qué
secciones se ven y en qué orden:

    Módulo: [ Imagen ▾ ]
    Barra izquierda                 Barra derecha (inspector)
    ┌─────────────────────────┐     ┌─────────────────────────┐
    │ ☑ Biblioteca - Imagen   │     │ ☑ Selección             │
    │ ☑ Carpetas              │     │ ☑ Palabras clave        │
    │ ☐ Fechas                │     │ ☑ Lista de palabras...  │
    │ ☑ Lista de palabras...  │     │ ☑ Metadatos             │
    └─────────────────────────┘     └─────────────────────────┘
      [↑] [↓]                         [↑] [↓]
    [Restaurar este módulo]  [Restaurar todos los módulos]

    - La casilla muestra u oculta la sección.
    - El orden se cambia arrastrando las filas o con las flechas de debajo de cada lista
      (subir y bajar la fila elegida).
    - «Restaurar...» devuelve la colocación de partida (orden, todas a la vista y
      desplegadas) al módulo elegido o a todos.

Es otra interfaz del MISMO modelo que el menú de las cabeceras y el arrastre
('SectionLayoutModel', la única fuente de verdad): como el resto de la ventana de opciones,
trabaja sobre una COPIA de la colocación y solo la pasa al modelo al pulsar «Aceptar»
('save'); entonces el modelo guarda y avisa, y las barras se recolocan solas. «Cancelar»
no cambia nada. Lo plegado de cada sección no se toca aquí (se conserva).

De dónde saca el modelo: de 'context["section_layout"]' (lo pone el controlador). El módulo
que se muestra al abrir es 'context["active_mode"]' (el activo). Sin modelo en el contexto
(la prueba suelta de la ventana), crea uno propio con la configuración recibida.

1.1.1 Los botones de subir y bajar, cuadrados (pedido por el autor).
1.1.0 «Subir» y «Bajar», con flechas en lugar de texto ('AppIcons.ARROW_UP' / 'ARROW_DOWN')
      y separados (pedido por el autor).
1.0.0 Primera versión (14/11/2026; fase 4 de las secciones personalizables).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.dialogs.section_layout_page
La página se ve en la prueba de la ventana de opciones ('settings_dialog', abre una ventana).
"""

__version__ = "1.1.1"
__all__ = ["SectionLayoutPage"]

# Librerías estándar
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QSize, Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
)

# Módulos del proyecto
from config.app_constants import SETTING_SECTION_LAYOUT, AppIcons
from ui_helpers.dialogs.settings_dialog import SettingsPage
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.layout.section_layout import SectionLayout
from ui_helpers.layout.section_layout_model import SectionLayoutModel
from ui_helpers.layout.section_registry import SECTION_REGISTRY, Sidebar

# Rol con el 'id' de la sección en cada fila de las listas
_ROLE_SECTION_ID = Qt.ItemDataRole.UserRole
# Alto de las dos listas (px lógicos): caben unas siete secciones sin desplazar
_LIST_HEIGHT = 150
# Botones de subir y bajar: lado del icono y separación entre los dos (px lógicos)
_MOVE_ICON_SIZE = 18
_MOVE_BUTTON_SPACING = 8
# Lado de esos botones, cuadrados (px lógicos): el alto de los demás botones de la ventana
_MOVE_BUTTON_SIDE = 28
# Título de cada lista
_SIDEBAR_TITLES = {
    Sidebar.LEFT: "Barra izquierda",
    Sidebar.RIGHT: "Barra derecha (inspector)",
}


class SectionLayoutPage(SettingsPage):
    """Sección «Paneles»: qué secciones se ven en cada barra de cada módulo y en qué orden
    (ver el docstring del archivo)."""

    title = "Paneles"
    icon = AppIcons.SETTINGS_APP

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)
        model = context.get("section_layout")
        if not isinstance(model, SectionLayoutModel):
            # Sin el modelo de la aplicación (prueba suelta de la ventana): uno propio
            model = SectionLayoutModel(SECTION_REGISTRY, config, parent=self)
        self._model: SectionLayoutModel = model
        # La copia sobre la que se trabaja hasta «Aceptar» (la pone 'load')
        self._layout: SectionLayout = model.working_copy()
        # True mientras se rellenan las listas (sus avisos no son cambios del usuario)
        self._filling = False

        # --- Módulo ---
        self.combo_mode = QComboBox()
        for mode in model.modes():
            self.combo_mode.addItem(mode.title, mode.key)
        self.combo_mode.currentIndexChanged.connect(lambda _index: self._fill_lists())
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Módulo"))
        mode_row.addWidget(self.combo_mode)
        mode_row.addStretch(1)
        self.body.addLayout(mode_row)

        # --- Las dos barras: título, lista y «Subir» / «Bajar» ---
        self.lists: dict[Sidebar, QListWidget] = {}
        self._move_buttons: dict[Sidebar, tuple[QPushButton, QPushButton]] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        for column, sidebar in enumerate(Sidebar):
            grid.addWidget(QLabel(f"<b>{_SIDEBAR_TITLES[sidebar]}</b>"), 0, column)
            section_list = QListWidget()
            section_list.setFixedHeight(_LIST_HEIGHT)
            # Reordenar arrastrando las filas (solo dentro de su lista: las secciones no
            # cambian de barra)
            section_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            section_list.setDefaultDropAction(Qt.DropAction.MoveAction)
            section_list.itemChanged.connect(lambda _item: self._on_lists_edited())
            section_list.model().rowsMoved.connect(lambda *_args: self._on_lists_edited())
            section_list.model().rowsInserted.connect(lambda *_args: self._on_lists_edited())
            section_list.currentRowChanged.connect(lambda _row: self._update_buttons())
            grid.addWidget(section_list, 1, column)
            self.lists[sidebar] = section_list

            # Con flechas (se tiñen con la paleta: apagadas si no se puede mover)
            button_up = self._make_move_button(AppIcons.ARROW_UP, "Subir")
            button_down = self._make_move_button(AppIcons.ARROW_DOWN, "Bajar")
            button_up.clicked.connect(lambda _checked=False, s=sidebar: self._move_current(s, -1))
            button_down.clicked.connect(lambda _checked=False, s=sidebar: self._move_current(s, 1))
            buttons = QHBoxLayout()
            buttons.setSpacing(_MOVE_BUTTON_SPACING)
            buttons.addWidget(button_up)
            buttons.addWidget(button_down)
            buttons.addStretch(1)
            grid.addLayout(buttons, 2, column)
            self._move_buttons[sidebar] = (button_up, button_down)
        self.body.addLayout(grid)

        # --- Restaurar ---
        self.button_reset_mode = QPushButton("Restaurar este módulo")
        self.button_reset_all = QPushButton("Restaurar todos los módulos")
        self.button_reset_mode.clicked.connect(lambda: self._reset(self.current_mode()))
        self.button_reset_all.clicked.connect(lambda: self._reset(None))
        reset_row = QHBoxLayout()
        reset_row.addWidget(self.button_reset_mode)
        reset_row.addWidget(self.button_reset_all)
        reset_row.addStretch(1)
        self.body.addSpacing(4)
        self.body.addLayout(reset_row)

        help_label = self.make_help_label(
            "Las secciones de las dos barras laterales de cada módulo: la casilla las muestra "
            "o las oculta y el orden se cambia arrastrando las filas o con las flechas de "
            "debajo de cada lista. Las del inspector se ven, además, solo cuando tienen algo "
            "que mostrar de lo seleccionado.<br>"
            "También se puede hacer en la propia barra: clic derecho en la cabecera de una "
            "sección para mostrarlas u ocultarlas, y arrastrar la cabecera para cambiarla de "
            "sitio."
        )
        help_label.setContentsMargins(0, 0, 0, 4)  # aquí no hay casilla con la que alinearse
        self.body.addWidget(help_label)

    @staticmethod
    def _make_move_button(icon: str, tooltip: str) -> QPushButton:
        """Un botón de subir o bajar la fila elegida: solo el icono, con su texto de ayuda."""
        button = QPushButton()
        button.setIcon(tinted_icon(icon))
        button.setIconSize(QSize(_MOVE_ICON_SIZE, _MOVE_ICON_SIZE))
        # Cuadrado: tan ancho como alto (el alto que el tema da a los botones)
        button.setFixedSize(_MOVE_BUTTON_SIDE, _MOVE_BUTTON_SIDE)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        return button

    # -------------------------------------------------------------------------
    # Cargar y guardar
    # -------------------------------------------------------------------------

    def load(self) -> None:
        """Copia la colocación del modelo y muestra el módulo activo."""
        self._layout = self._model.working_copy()
        index = self.combo_mode.findData(self.context.get("active_mode"))
        if index >= 0 and index != self.combo_mode.currentIndex():
            self.combo_mode.setCurrentIndex(index)  # -> '_fill_lists'
        else:
            self._fill_lists()

    def save(self) -> set[str]:
        """Pasa la copia al modelo (que guarda y avisa a las barras) si ha cambiado."""
        return {SETTING_SECTION_LAYOUT} if self._model.apply(self._layout) else set()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def current_mode(self) -> str:
        """Clave del módulo elegido en el desplegable ("" si no hay ninguno)."""
        return self.combo_mode.currentData() or ""

    def _fill_lists(self) -> None:
        """Pone en las dos listas las secciones del módulo elegido, como están en la copia."""
        mode = self.current_mode()
        self._filling = True
        try:
            for sidebar, section_list in self.lists.items():
                section_list.clear()
                for entry in self._layout.entries(mode, sidebar):
                    item = QListWidgetItem(self._model.title(mode, entry.id))
                    item.setData(_ROLE_SECTION_ID, entry.id)
                    # Con casilla y arrastrable, pero no se suelta nada ENCIMA de una fila
                    # (solo entre filas)
                    item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsDragEnabled
                    )
                    item.setCheckState(
                        Qt.CheckState.Checked if entry.visible else Qt.CheckState.Unchecked
                    )
                    section_list.addItem(item)
                # Un módulo sin secciones en esa barra (p. ej. uno provisional): lista apagada
                section_list.setEnabled(section_list.count() > 0)
        finally:
            self._filling = False
        self._update_buttons()

    def _on_lists_edited(self) -> None:
        """El usuario ha marcado una casilla o ha movido una fila: las listas, a la copia."""
        if self._filling:
            return
        mode = self.current_mode()
        for section_list in self.lists.values():
            for row in range(section_list.count()):
                item = section_list.item(row)
                section_id = item.data(_ROLE_SECTION_ID)
                # Colocar cada una en su fila, de arriba abajo, deja la lista en ese orden
                self._layout.move(mode, section_id, row)
                self._layout.set_visible(
                    mode, section_id, item.checkState() == Qt.CheckState.Checked
                )
        self._update_buttons()

    def _move_current(self, sidebar: Sidebar, step: int) -> None:
        """«Subir» (-1) o «Bajar» (+1) la fila elegida de una lista."""
        section_list = self.lists[sidebar]
        row = section_list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < section_list.count():
            return
        # Quitarla y ponerla en su fila nueva (conserva su casilla); al insertarla avisa
        # la lista y se apunta en la copia ('_on_lists_edited')
        item = section_list.takeItem(row)
        section_list.insertItem(target, item)
        section_list.setCurrentRow(target)

    def _reset(self, mode: str | None) -> None:
        """Devuelve a la copia la colocación de partida de un módulo (None = de todos)."""
        self._layout.reset(mode)
        self._fill_lists()

    def _update_buttons(self) -> None:
        """Activa «Subir», «Bajar» y los de restaurar según lo que se pueda hacer."""
        for sidebar, (button_up, button_down) in self._move_buttons.items():
            section_list = self.lists[sidebar]
            row = section_list.currentRow()
            button_up.setEnabled(row > 0)
            button_down.setEnabled(0 <= row < section_list.count() - 1)
        mode = self.current_mode()
        self.button_reset_mode.setEnabled(not self._is_default(mode))
        self.button_reset_all.setEnabled(
            not all(self._is_default(spec.key) for spec in self._model.modes())
        )

    def _is_default(self, mode: str) -> bool:
        """True si las dos barras de ese módulo están, en la copia, como de partida."""
        return all(self._layout.is_default(mode, sidebar) for sidebar in Sidebar)


if __name__ == "__main__":
    # Autoprueba SIN ventana (la página no se muestra: se manejan sus controles).
    # Desde la raíz del proyecto:  python -m ui_helpers.dialogs.section_layout_page
    import copy
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qtpy.QtCore import QModelIndex
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    class _FakeConfig:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}
            self.writes = 0

        def get(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self.writes += 1
            self.data[key] = copy.deepcopy(value)

    def _rows(page: SectionLayoutPage, sidebar: Sidebar) -> list[tuple[str, bool]]:
        section_list = page.lists[sidebar]
        return [
            (
                section_list.item(row).data(_ROLE_SECTION_ID),
                section_list.item(row).checkState() == Qt.CheckState.Checked,
            )
            for row in range(section_list.count())
        ]

    def _model_ids(sidebar: Sidebar, mode: str = "image") -> list[str]:
        return [entry.id for entry in model.entries(mode, sidebar)]

    config = _FakeConfig()
    model = SectionLayoutModel(SECTION_REGISTRY, config)
    model.set_visible("image", "dates", False)       # lo que ya tenía el usuario
    model.set_expanded("image", "metadata", False)
    seen: list[tuple[str, str]] = []
    model.layout_changed.connect(lambda mode, sidebar: seen.append((mode, sidebar)))
    config.writes = 0

    def _page() -> SectionLayoutPage:
        new_page = SectionLayoutPage(config, {"section_layout": model, "active_mode": "image"})
        new_page.load()
        return new_page

    # --- Al abrir: el módulo activo, con sus secciones como están en el modelo
    page = _page()
    assert page.title == "Paneles" and page.current_mode() == "image"
    assert [page.combo_mode.itemText(i) for i in range(page.combo_mode.count())] == [
        "Catálogo", "Imagen", "Vídeo", "Audio", "Tracks"]  # fmt: skip
    assert _rows(page, Sidebar.LEFT) == [
        ("library", True), ("folders", True), ("dates", False), ("keywords", True)]  # fmt: skip
    assert [row[0] for row in _rows(page, Sidebar.RIGHT)] == _model_ids(Sidebar.RIGHT)
    assert page.lists[Sidebar.LEFT].item(0).text() == "Biblioteca - Imagen"
    assert page.button_reset_mode.isEnabled() and page.button_reset_all.isEnabled()
    up, down = page._move_buttons[Sidebar.LEFT]
    assert not up.isEnabled() and not down.isEnabled()  # sin fila elegida

    assert up.text() == "" and up.toolTip() == "Subir" and down.toolTip() == "Bajar"
    assert not up.icon().isNull() and not down.icon().isNull()

    # --- Casillas, «Subir» / «Bajar» y arrastrar: cambian la copia, no el modelo
    left = page.lists[Sidebar.LEFT]
    left.item(2).setCheckState(Qt.CheckState.Checked)      # mostrar «Fechas»
    left.item(1).setCheckState(Qt.CheckState.Unchecked)    # ocultar «Carpetas»
    left.setCurrentRow(3)
    assert up.isEnabled() and not down.isEnabled()
    up.click()                                             # «keywords», una fila arriba
    assert left.currentRow() == 2 and up.isEnabled() and down.isEnabled()
    # Arrastrar una fila (lo que hace la lista al soltar): la primera, al final
    left.model().moveRow(QModelIndex(), 0, QModelIndex(), left.count())
    expected = [("folders", False), ("keywords", True), ("dates", True), ("library", True)]
    assert _rows(page, Sidebar.LEFT) == expected, _rows(page, Sidebar.LEFT)
    right = page.lists[Sidebar.RIGHT]
    right.setCurrentRow(0)
    page._move_buttons[Sidebar.RIGHT][1].click()           # «selection», una fila abajo
    assert _model_ids(Sidebar.LEFT) == ["library", "folders", "dates", "keywords"]
    assert not seen and config.writes == 0

    # --- Cambiar de módulo y volver: la copia recuerda lo hecho en cada uno
    page.combo_mode.setCurrentIndex(page.combo_mode.findData("catalog"))
    assert _rows(page, Sidebar.LEFT) == [("catalog", True), ("folders", True), ("collections", True)]
    assert not page.button_reset_mode.isEnabled() and page.button_reset_all.isEnabled()
    page.lists[Sidebar.LEFT].item(0).setCheckState(Qt.CheckState.Unchecked)
    page.combo_mode.setCurrentIndex(page.combo_mode.findData("video"))
    assert not page.lists[Sidebar.LEFT].isEnabled() and page.lists[Sidebar.RIGHT].isEnabled()
    page.combo_mode.setCurrentIndex(page.combo_mode.findData("image"))
    assert _rows(page, Sidebar.LEFT) == expected

    # --- «Aceptar»: al modelo, que guarda una vez y avisa de cada barra que cambia
    assert page.save() == {SETTING_SECTION_LAYOUT}
    assert _model_ids(Sidebar.LEFT) == ["folders", "keywords", "dates", "library"]
    assert _model_ids(Sidebar.RIGHT)[:2] == ["keyword_editor", "selection"]
    assert model.entry("image", "folders").visible is False and model.entry("image", "dates").visible
    assert model.entry("catalog", "catalog").visible is False
    assert model.entry("image", "metadata").expanded is False  # lo plegado se conserva
    assert sorted(seen) == [("catalog", "left"), ("image", "left"), ("image", "right")], seen
    assert config.writes == 1
    assert page.save() == set() and config.writes == 1  # sin más cambios, nada

    # --- «Cancelar» (no llamar a 'save'): nada cambia
    seen.clear()
    other = _page()
    other.lists[Sidebar.LEFT].item(0).setCheckState(Qt.CheckState.Checked)
    other.button_reset_all.click()
    assert not seen and config.writes == 1 and model.entry("image", "folders").visible is False

    # --- Restaurar este módulo: solo él (en la copia); los demás, como estaban
    page = _page()
    page.button_reset_mode.click()
    assert _rows(page, Sidebar.LEFT) == [
        ("library", True), ("folders", True), ("dates", True), ("keywords", True)]  # fmt: skip
    assert not page.button_reset_mode.isEnabled() and page.button_reset_all.isEnabled()
    assert page.save() == {SETTING_SECTION_LAYOUT}
    assert model.is_default("image", Sidebar.LEFT) and model.is_default("image", Sidebar.RIGHT)
    assert model.entry("catalog", "catalog").visible is False
    # --- Restaurar todos
    page = _page()
    page.button_reset_all.click()
    assert not page.button_reset_all.isEnabled()
    assert page.save() == {SETTING_SECTION_LAYOUT} and model.entry("catalog", "catalog").visible
    assert _page().save() == set()

    # --- Sin modelo en el contexto (la prueba suelta de la ventana): uno propio
    alone = SectionLayoutPage(_FakeConfig(), {})
    alone.load()
    assert alone.current_mode() == "catalog" and len(_rows(alone, Sidebar.LEFT)) == 3

    print("Autoprueba finalizada correctamente.")
