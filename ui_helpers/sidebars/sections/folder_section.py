"""Sección «Carpetas» de la barra de un módulo: ubicaciones y carpetas con sus recuentos.

Como el árbol de carpetas del Catálogo, pero solo con las carpetas que tienen algo de la
biblioteca del módulo (por su CONTENIDO, no por el tipo declarado al añadirlas; decidido
por el autor el 04/11/2026) y contando solo eso. Al elegir una, la cuadrícula muestra solo
lo de esa biblioteca ('folder_source(..., library=...)'), con o sin subcarpetas según la
opción del Catálogo «Mostrar los elementos de las subcarpetas».

    - Ubicación: icono de disco; si está desconectada, en gris y con «(desconectada)» en su
      texto emergente. Una ubicación que aparece por primera vez se muestra desplegada.
    - Carpeta desplegada: icono de la carpeta abierta, en el color de acento.
    - Menú: solo «Mostrar en el Explorador» ('reveal_folder_requested'): sincronizar y
      quitar ausentes están en el Catálogo (la barra de un módulo es para navegar).

Uso (lo hace la barra, p. ej. 'ImageSidebar'; ver 'tree_section.py'):
    folders = FolderSection("image", load_sidebar_icons(parent), parent)
    folders.set_tree(locations)            # 'fetch_folder_tree(conn, "image")', del módulo
    folders.set_include_subfolders(False)  # la opción del Catálogo

Estado por catálogo ('save_state'): 'expanded_folders' (lo desplegado, [ubicación, ruta]) y
'known_locations' (las ubicaciones ya vistas).

1.0.0 Primera versión: sale de 'image_sidebar.py' (1.7.3) al dividirla en un archivo por
      sección (12/11/2026); hace lo mismo que antes.
"""

__version__ = "1.0.0"
__all__ = ["FolderSection"]

# Librerías estándar
from collections.abc import Iterable
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, QPoint, Qt, Signal
from qtpy.QtGui import QBrush, QIcon, QPalette, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import QMenu, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.folder_tree import FolderNode, LocationNode
from core.catalog.grid_source import GridSource, SourceKind, folder_source
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME
from ui_helpers.sidebars.sections.tree_section import TreeSection, make_item
from ui_helpers.widgets.sidebar_tree_view import SidebarTreeView

# Roles propios: (ubicación, ruta relativa) para recordar lo desplegado, ruta absoluta (para
# «Mostrar en el Explorador»), si está conectada y clave del icono
_ROLE_FOLDER_KEY = Qt.ItemDataRole.UserRole + 41
_ROLE_PATH = Qt.ItemDataRole.UserRole + 42
_ROLE_ONLINE = Qt.ItemDataRole.UserRole + 43
_ROLE_ICON_KEY = Qt.ItemDataRole.UserRole + 44


class FolderSection(TreeSection):
    """Árbol de ubicaciones y carpetas de una biblioteca (ver el docstring del módulo).

    Signals:
        reveal_folder_requested(str): «Mostrar en el Explorador» (ruta absoluta).
    """

    reveal_folder_requested = Signal(str)

    def __init__(self, library: str, icons: dict[str, QIcon], parent: QWidget | None = None) -> None:
        """Crea la sección vacía.

        Args:
            library: Biblioteca del módulo ('image'...).
            icons: Los de 'load_sidebar_icons' (los comparte con la barra).
            parent: Widget padre.
        """
        super().__init__(parent)
        self._library = library
        self._icons = icons
        # El árbol mostrado, si se ven también las subcarpetas (opción del Catálogo), lo
        # desplegado ((ubicación, ruta)) y las ubicaciones ya vistas (una nueva aparece
        # desplegada)
        self._tree: tuple[LocationNode, ...] = ()
        self._include_subfolders = True
        self._expanded: set[tuple[int, str]] = set()
        self._known_locations: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._model = QStandardItemModel(self)
        self._view = SidebarTreeView(self)
        self._view.setModel(self._model)
        self._view.expanded.connect(lambda index: self._on_expanded(index, True))
        self._view.collapsed.connect(lambda index: self._on_expanded(index, False))
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self._view)

    # -------------------------------------------------------------------------
    # Datos y opción (los pone la barra)
    # -------------------------------------------------------------------------

    @property
    def include_subfolders(self) -> bool:
        """Si cada carpeta cuenta y muestra también lo de sus subcarpetas."""
        return self._include_subfolders

    def set_tree(self, locations: Iterable[LocationNode]) -> None:
        """Pone el árbol de carpetas (no hace nada si no ha cambiado)."""
        locations = tuple(locations)
        if locations == self._tree and self._model.rowCount() > 0:
            return
        self._tree = locations
        self._rebuild()

    def set_include_subfolders(self, include: bool) -> bool:
        """Opción del Catálogo «Mostrar los elementos de las subcarpetas»: cambia los
        contadores y lo que muestra cada carpeta.

        Returns:
            True si ha cambiado (la barra vuelve a emitir la carpeta elegida, si la hay).
        """
        if include == self._include_subfolders:
            return False
        self._include_subfolders = include
        self._rebuild()
        return True

    def folder_source(self, location_id: int, relative_path: str) -> GridSource:
        """Origen de una carpeta: solo lo de la biblioteca, con o sin subcarpetas (la opción)."""
        return folder_source(
            location_id,
            relative_path,
            include_subfolders=self._include_subfolders,
            library=self._library,
        )

    # -------------------------------------------------------------------------
    # 'TreeSection'
    # -------------------------------------------------------------------------

    def views(self) -> tuple[SidebarTreeView, ...]:
        return (self._view,)

    def find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de una carpeta (por su ubicación y su ruta)."""
        if source.kind != SourceKind.FOLDER:
            return None
        return self._find(self._model.invisibleRootItem(), (source.location_id, source.folder))

    def owns(self, source: GridSource) -> bool:
        return source.kind == SourceKind.FOLDER and source.library == self._library

    def save_state(self) -> dict:
        return {
            "expanded_folders": sorted([location, folder] for location, folder in self._expanded),
            "known_locations": sorted(self._known_locations),
        }

    def restore_state(self, state: dict) -> None:
        folders = state.get("expanded_folders")
        if isinstance(folders, list):
            self._expanded = {
                (entry[0], entry[1])
                for entry in folders
                if isinstance(entry, list) and len(entry) == 2
                and isinstance(entry[0], int) and isinstance(entry[1], str)
            }  # fmt: skip
        known = state.get("known_locations")
        if isinstance(known, list):
            self._known_locations = {value for value in known if isinstance(value, int)}

    def reset(self) -> None:
        self._tree = ()
        self._expanded.clear()
        self._known_locations.clear()
        self._rebuild()

    # -------------------------------------------------------------------------
    # Árbol
    # -------------------------------------------------------------------------

    def _count(self, node: FolderNode) -> int | None:
        """Contador: con sus subcarpetas o solo lo suyo, según la opción (0 = sin número)."""
        count = node.count if self._include_subfolders else node.direct_count
        return count or None

    def _rebuild(self) -> None:
        """Rehace el árbol conservando lo desplegado; después, 'rebuilt' (la barra vuelve a
        marcar la fila elegida).

        No se bloquean las señales del MODELO (ver TRAMPAS.md): solo las de la vista (lo
        desplegado por código no se anota) y las de su selección.
        """
        view, model = self._view, self._model
        offline = QBrush(view.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
        with _blocked(view.selectionModel(), view):
            model.clear()
            root = model.invisibleRootItem()
            for location in self._tree:
                item = make_item(
                    location.name, self.folder_source(location.location_id, ""),
                    self._count(location.root),
                )  # fmt: skip
                self._set_icon(item, "drive")
                item.setData((location.location_id, ""), _ROLE_FOLDER_KEY)
                item.setData(location.absolute_path, _ROLE_PATH)
                item.setData(location.is_online, _ROLE_ONLINE)
                tooltip = location.absolute_path
                if not location.is_online:
                    tooltip += "\n(desconectada)"
                    item.setForeground(offline)
                item.setToolTip(tooltip)
                root.appendRow(item)
                self._append(item, location, location.root.children, None if location.is_online else offline)
                # Una ubicación que aparece por primera vez se muestra desplegada
                if location.location_id not in self._known_locations:
                    self._known_locations.add(location.location_id)
                    self._expanded.add((location.location_id, ""))
            self._expand_saved(root)
        view.updateGeometry()
        self.rebuilt.emit()

    def _append(
        self,
        parent: QStandardItem,
        location: LocationNode,
        children: tuple[FolderNode, ...],
        foreground: QBrush | None,
    ) -> None:
        """Añade (recursivamente) las subcarpetas de una carpeta."""
        for node in children:
            item = make_item(
                node.name, self.folder_source(location.location_id, node.relative_path),
                self._count(node),
            )  # fmt: skip
            self._set_icon(item, "folder")
            # Ruta completa con el separador del sistema (barra invertida en Windows)
            full_path = str(Path(location.absolute_path) / node.relative_path)
            item.setToolTip(full_path)
            item.setData((location.location_id, node.relative_path), _ROLE_FOLDER_KEY)
            item.setData(full_path, _ROLE_PATH)
            item.setData(location.is_online, _ROLE_ONLINE)
            if foreground is not None:
                item.setForeground(foreground)
            parent.appendRow(item)
            self._append(item, location, node.children, foreground)

    def _expand_saved(self, parent: QStandardItem) -> None:
        """Despliega las carpetas que lo estaban (solo las que tienen subcarpetas: Qt da
        por desplegada también una fila sin hijos si se le pide)."""
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if child.hasChildren() and tuple(child.data(_ROLE_FOLDER_KEY) or ()) in self._expanded:
                self._view.setExpanded(child.index(), True)
                self._update_open_icon(child, True)
            self._expand_saved(child)

    def _find(self, parent: QStandardItem, wanted: tuple[int | None, str]) -> QStandardItem | None:
        """La fila de (ubicación, ruta) bajo 'parent', o None."""
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if tuple(child.data(_ROLE_FOLDER_KEY) or ()) == wanted:
                return child
            found = self._find(child, wanted)
            if found is not None:
                return found
        return None

    # -------------------------------------------------------------------------
    # Iconos, desplegar y menú
    # -------------------------------------------------------------------------

    def _set_icon(self, item: QStandardItem, key: str) -> None:
        """Pone a una fila el icono 'key' (y lo anota para desplegar y plegar)."""
        item.setIcon(self._icons[key])
        item.setData(key, _ROLE_ICON_KEY)

    def _update_open_icon(self, item: QStandardItem | None, is_open: bool) -> None:
        """Desplegada = icono de la carpeta abierta, en el color de acento."""
        key = item.data(_ROLE_ICON_KEY) if item is not None else None
        if key:
            item.setIcon(self._icons[f"{key}:open" if is_open else key])

    def _on_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo que despliega o pliega el usuario."""
        key = index.data(_ROLE_FOLDER_KEY)
        if key is not None:
            key = tuple(key)
            (self._expanded.add if expanded else self._expanded.discard)(key)
        self._update_open_icon(self._model.itemFromIndex(index), expanded)

    def _show_menu(self, position: QPoint) -> None:
        """Menú de una carpeta: solo «Mostrar en el Explorador» (sincronizar y quitar
        ausentes están en el Catálogo: esta barra es para navegar)."""
        index = self._view.indexAt(position)
        path = index.data(_ROLE_PATH) if index.isValid() else None
        if not path:
            return
        menu = QMenu(self._view)
        reveal = menu.addAction(f"Mostrar en {FILE_MANAGER_NAME}")
        if not index.data(_ROLE_ONLINE):
            reveal.setEnabled(False)
            menu.addSeparator()
            menu.addAction("(ubicación desconectada)").setEnabled(False)
        if menu.exec(self._view.viewport().mapToGlobal(position)) is reveal:
            self.reveal_folder_requested.emit(path)
