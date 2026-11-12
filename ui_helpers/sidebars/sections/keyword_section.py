"""Sección «Lista de palabras clave» de la barra de un módulo: filtro y árbol de palabras.

Como la «Lista de palabras clave» de Lightroom (paso K3):

    [ Filtrar palabras clave       ]
    ▸ Coche                    12
        Opel Astra               10
        Toyota Corolla            2
    ▸ Familia                  ...

    - Los recuentos INCLUYEN las hijas: «Coche» cuenta las fotos de todos los modelos,
      aunque no lleven «Coche» asignada (cada foto una vez). Lightroom cuenta solo las
      asignadas directamente; aquí se prefirió así (decidido el 03/11/2026, a revisar por
      el autor al verlo). Las palabras sin nada de la biblioteca (ni ellas ni sus hijas)
      no muestran número y salen en gris, como una carpeta de un disco desconectado
      (decidido por el autor el 12/11/2026); se pueden elegir igual.
    - Al elegir una palabra, la cuadrícula muestra lo suyo Y lo de sus hijas, solo de la
      biblioteca del módulo ('grid_source.keyword_source').
    - La caja de arriba filtra el árbol mientras se escribe, sin distinguir mayúsculas ni
      acentos ('keywords.filter_keyword_tree'): quedan las palabras que coinciden y sus
      padres (desplegados). Al vaciarla, el árbol vuelve a como estaba.
    - Solo para NAVEGAR (decidido por el autor el 04/11/2026): editar las palabras
      (asignar, soltar tarjetas, crear, renombrar, mover, borrar) se hace en el inspector.

Lo desplegado se lleva en un 'KeywordExpansion' (estado 'SIDEBAR'), independiente del
árbol con casillas del inspector; se guarda por catálogo en 'expanded_keywords'.

El aspecto del filtro se define en la hoja de estilos global (ui_theme.py) con el nombre de
objeto 'edit_keyword_filter'.

Uso (lo hace la barra, p. ej. 'ImageSidebar'; ver 'tree_section.py'):
    keywords = KeywordSection("image", parent=parent)
    keywords.set_tree(tree)   # 'fetch_keyword_tree(conn, "image")', del módulo

1.1.0 Las palabras sin nada de la biblioteca, en gris (el «desactivado» de la paleta).
1.0.1 La sangría de los nombres, 'TEXT_NAME_INDENT' de 'tree_section.py' (la comparte con
      las fechas); antes, '_KEYWORD_NAME_INDENT' aquí. El mismo valor.
1.0.0 Primera versión: sale de 'image_sidebar.py' (1.7.3) al dividirla en un archivo por
      sección (12/11/2026); hace lo mismo que antes.
"""

__version__ = "1.1.0"
__all__ = ["KeywordSection"]

# Librerías estándar
from collections.abc import Iterable

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, Qt
from qtpy.QtGui import QBrush, QPalette, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.grid_source import GridSource, SourceKind, keyword_source
from core.catalog.keywords import KeywordTreeNode, filter_keyword_tree
from ui_helpers.helpers.keyword_expansion import SIDEBAR, KeywordExpansion, keyword_expansion
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.sidebars.sections.tree_section import TEXT_NAME_INDENT, TreeSection, make_item
from ui_helpers.widgets.sidebar_tree_view import SidebarTreeView

# Rol propio: id de la palabra de la fila (para recordar lo desplegado)
_ROLE_KEYWORD_ID = Qt.ItemDataRole.UserRole + 40

# Distancia del filtro a los lados de la barra (px lógicos): la misma que a la cabecera de
# su sección y que la del contenido del inspector
_FILTER_SIDE_MARGIN = 8


class KeywordSection(TreeSection):
    """Filtro y árbol de palabras clave de una biblioteca (ver el docstring del módulo)."""

    def __init__(
        self,
        library: str,
        expansion: KeywordExpansion | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Crea la sección vacía.

        Args:
            library: Biblioteca del módulo ('image'...).
            expansion: Lo desplegado (por defecto, el estado 'SIDEBAR').
            parent: Widget padre.
        """
        super().__init__(parent)
        self._library = library
        self._tree: tuple[KeywordTreeNode, ...] = ()
        # Palabras desplegadas (sin filtro); el árbol del inspector tiene las suyas
        self._expansion = expansion if expansion is not None else keyword_expansion(SIDEBAR)
        self._expansion.changed.connect(self._apply_expansion)

        layout = QVBoxLayout(self)
        # Sin márgenes a los lados: el árbol ocupa todo el ancho, como el de carpetas, y sus
        # flechas y números quedan alineados con los de las carpetas. Arriba, 6: con los 2
        # del cuerpo de la sección, el filtro queda a 8 px de la cabecera (pedido por el
        # autor el 11/11/2026 para toda caja bajo un título)
        layout.setContentsMargins(0, 6, 0, 4)
        layout.setSpacing(4)
        # El filtro, en su fila: a 8 px de los lados, como de la cabecera
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(_FILTER_SIDE_MARGIN, 0, _FILTER_SIDE_MARGIN, 0)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("edit_keyword_filter")
        self._filter.setPlaceholderText("Filtrar palabras clave")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._rebuild)
        filter_row.addWidget(self._filter)
        layout.addLayout(filter_row)
        self._model = QStandardItemModel(self)
        # Los nombres, en la columna de las flechas de las subcarpetas ('TEXT_NAME_INDENT')
        self._view = SidebarTreeView(self, name_indent=TEXT_NAME_INDENT)
        self._view.setModel(self._model)
        self._view.expanded.connect(lambda index: self._on_expanded(index, True))
        self._view.collapsed.connect(lambda index: self._on_expanded(index, False))
        layout.addWidget(self._view)

    # -------------------------------------------------------------------------
    # Datos (los pone la barra)
    # -------------------------------------------------------------------------

    def set_tree(self, tree: tuple[KeywordTreeNode, ...]) -> None:
        """Pone el árbol de palabras clave (no hace nada si no ha cambiado)."""
        if tree == self._tree and self._model.rowCount() > 0:
            return
        self._tree = tree
        self._rebuild()

    def is_filtering(self) -> bool:
        """True si hay texto en «Filtrar palabras clave»."""
        return bool(self._filter.text().strip())

    # -------------------------------------------------------------------------
    # 'TreeSection'
    # -------------------------------------------------------------------------

    def views(self) -> tuple[SidebarTreeView, ...]:
        return (self._view,)

    def find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de una palabra, o None si no está (p. ej. oculta por el filtro)."""
        if source.kind != SourceKind.KEYWORD:
            return None

        def search(parent: QStandardItem) -> QStandardItem | None:
            for row in range(parent.rowCount()):
                child = parent.child(row)
                if child.data(_ROLE_KEYWORD_ID) == source.keyword_id:
                    return child
                found = search(child)
                if found is not None:
                    return found
            return None

        return search(self._model.invisibleRootItem())

    def owns(self, source: GridSource) -> bool:
        return source.kind == SourceKind.KEYWORD

    def reveal(self, source: GridSource) -> None:
        """Una palabra pedida desde fuera (p. ej. desde el inspector): si el filtro la
        oculta, se vacía; se despliegan sus padres para que se vea marcada."""
        if source.kind != SourceKind.KEYWORD or source.keyword_id is None:
            return
        if self.find_item(source) is None and self.is_filtering():
            self._filter.clear()  # rehace el árbol entero
        for ancestor in self._ancestors(source.keyword_id):
            self._expansion.set_expanded(ancestor, True)  # el árbol se despliega solo

    def save_state(self) -> dict:
        return {"expanded_keywords": sorted(self._expansion.ids())}

    def restore_state(self, state: dict) -> None:
        expanded = state.get("expanded_keywords")
        if isinstance(expanded, list):
            self._expansion.replace(expanded)

    def reset(self) -> None:
        self._tree = ()
        self._expansion.replace(())
        with _blocked(self._filter):
            self._filter.clear()
        self._rebuild()

    # -------------------------------------------------------------------------
    # Árbol
    # -------------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Rehace el árbol con el filtro actual, conservando lo desplegado; después,
        'rebuilt' (la barra vuelve a marcar la fila elegida)."""
        filtering = self.is_filtering()
        shown = filter_keyword_tree(self._tree, self._filter.text())
        view, model = self._view, self._model
        with _blocked(view.selectionModel(), view):
            model.clear()
            # Las palabras sin nada de la biblioteca, con el gris de lo desactivado
            disabled = QPalette.ColorGroup.Disabled
            dim = QBrush(view.palette().color(disabled, QPalette.ColorRole.Text))
            self._append(model.invisibleRootItem(), shown, dim)
            # Con filtro, todo desplegado (se ve dónde está cada coincidencia); sin filtro,
            # lo que el usuario tenía desplegado
            if filtering:
                view.expandAll()
            else:
                self._expand_saved(model.invisibleRootItem())
        view.updateGeometry()
        self.rebuilt.emit()

    def _append(self, parent: QStandardItem, nodes: Iterable[KeywordTreeNode], dim: QBrush) -> None:
        """Añade las palabras (y sus hijas) bajo 'parent'; las que no tienen nada, en 'dim'."""
        for node in nodes:
            # Sin nada en la biblioteca: sin número (como una carpeta vacía) y en gris
            item = make_item(node.name, keyword_source(node.id, self._library), node.count or None)
            if not node.count:
                item.setForeground(dim)
            item.setData(node.id, _ROLE_KEYWORD_ID)
            tooltip = f"{node.name}\n{node.count} con esta palabra o sus hijas"
            if node.direct_count != node.count:
                tooltip += f" ({node.direct_count} la tienen asignada directamente)"
            if node.needs_review:
                tooltip += "\nPalabra suelta con el nombre de otras del árbol: revisar dónde va."
            item.setToolTip(tooltip)
            parent.appendRow(item)
            self._append(item, node.children, dim)

    def _expand_saved(self, parent: QStandardItem) -> None:
        """Despliega las filas que el usuario tenía desplegadas."""
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if self._expansion.is_expanded(child.data(_ROLE_KEYWORD_ID)):
                self._view.expand(child.index())
            self._expand_saved(child)

    def _apply_expansion(self) -> None:
        """Lo desplegado ha cambiado (p. ej. al recuperarlo): el árbol se pone igual.

        Con texto en el filtro no se toca (está todo desplegado); al vaciarlo, se rehace
        con lo desplegado de ese momento.
        """
        if self.is_filtering():
            return

        def visit(parent: QStandardItem) -> None:
            for row in range(parent.rowCount()):
                child = parent.child(row)
                if child.hasChildren():
                    expanded = self._expansion.is_expanded(child.data(_ROLE_KEYWORD_ID))
                    self._view.setExpanded(child.index(), expanded)
                    visit(child)

        visit(self._model.invisibleRootItem())

    def _on_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo desplegado por el usuario (no lo que despliega el filtro)."""
        if self.is_filtering():
            return
        keyword_id = index.data(_ROLE_KEYWORD_ID)
        if isinstance(keyword_id, int):
            self._expansion.set_expanded(keyword_id, expanded)

    def _ancestors(self, keyword_id: int) -> list[int]:
        """Ids de los padres (y abuelos...) de una palabra en el árbol."""

        def visit(nodes: Iterable[KeywordTreeNode], parents: list[int]) -> list[int] | None:
            for node in nodes:
                if node.id == keyword_id:
                    return parents
                found = visit(node.children, [*parents, node.id])
                if found is not None:
                    return found
            return None

        return visit(self._tree, []) or []
