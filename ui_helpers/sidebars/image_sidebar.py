"""Barra lateral del módulo Imagen (columna izquierda): biblioteca y palabras clave.

Secciones plegables, una debajo de otra, dentro de un área con desplazamiento (como la
barra del Catálogo):

    ▼ BIBLIOTECA - IMAGEN  «Todas las imágenes» y «Selección rápida», con sus contadores
    ▼ CARPETAS          ubicaciones y carpetas con imágenes, con sus contadores
    ▼ LISTA DE PALABRAS CLAVE   [ Filtrar palabras clave       ]
                        ▸ Coche                    12
                            Opel Astra               10
                            Toyota Corolla            2
                        ▸ Familia                  ...

Árbol de palabras clave (paso K3, como la «Lista de palabras clave» de Lightroom):
    - Los recuentos INCLUYEN las hijas: «Coche» cuenta las fotos de todos los modelos,
      aunque no lleven «Coche» asignada (cada foto una vez). Lightroom cuenta solo las
      asignadas directamente; aquí se prefirió así (decidido el 03/11/2026, a revisar por
      el autor al verlo). Las palabras sin fotos de la biblioteca no muestran número.
    - Al elegir una palabra, la cuadrícula muestra sus fotos Y las de sus hijas
      ('grid_source.keyword_source').
    - La caja de arriba filtra el árbol mientras se escribe, sin distinguir mayúsculas ni
      acentos: quedan las palabras que coinciden y sus padres (desplegados). Al vaciarla,
      el árbol vuelve a como estaba.

Cómo se comunica con el resto (no sabe nada de SQL ni de la cuadrícula; lo une
'controllers/app_modules/image_module.py'):
    - Cada fila lleva un 'GridSource' (ROLE_SOURCE). Al elegirla, emite 'source_selected'.
    - 'set_library_count' y 'set_keyword_tree' reciben lo que el módulo lee en segundo
      plano. Si el árbol no ha cambiado, no se reconstruye (no se pierde lo desplegado).
    - 'save_state' / 'restore_state': secciones plegadas, palabras desplegadas y la fila
      elegida (el módulo lo guarda por catálogo).
    - «Selección rápida» (04/11/2026): la misma del Catálogo (una sola para todo el
      catálogo), pero solo se ven sus imágenes y vídeos del móvil ('quick_source("image")').
      Sin menú: «Vaciar selección rápida» vaciaría también lo que no se ve; está en el
      Catálogo.
    - «Carpetas» (04/11/2026): el árbol de ubicaciones y carpetas, como en el Catálogo,
      pero solo con las que tienen algo de la biblioteca Imagen (por su CONTENIDO, no por
      el tipo declarado al añadirlas; decidido por el autor) y contando solo eso. Al
      elegir una, la cuadrícula muestra solo sus imágenes ('folder_source(...,
      library="image")'), con o sin subcarpetas según la opción del Catálogo. Menú: solo
      «Mostrar en el Explorador» ('reveal_folder_requested').
    - Esta barra es para NAVEGAR (decidido por el autor el 04/11/2026): editar las
      palabras (asignar, soltar tarjetas, crear, renombrar, mover, borrar) se hace en el
      inspector, en su «Lista de palabras clave».

El aspecto se define en la hoja de estilos global (ui_theme.py) con los nombres de objeto
'scroll_image_sidebar', 'widget_image_sidebar_content' y 'edit_keyword_filter'.

1.7.1 La fila elegida por código (p. ej. con la flecha del inspector) se repinta al
      momento: antes no se veía marcada hasta pasar el ratón por encima.
1.7.0 'show_source': elegir desde fuera (la flecha «ver sus fotos» del inspector); si
      la palabra está oculta por el filtro, se vacía; se despliegan sus padres.
1.6.1 Icono delante de «Todas las imágenes» y «Selección rápida», como en el Catálogo.
1.6.0 «Selección rápida» (solo lo de Imagen) bajo «Todas las imágenes».
1.5.0 Sección «Carpetas» (solo con contenido de Imagen), entre la biblioteca y las palabras.
1.4.0 Solo para navegar: se quitan el menú contextual del árbol y soltar tarjetas (pasan al
      inspector); la sección de arriba se llama «Biblioteca - Imagen».
1.3.0 Soltar tarjetas de la cuadrícula sobre una palabra para asignarla ('media_dropped').
1.2.0 Menú contextual del árbol para gestionarlo ('keyword_menu.py', señal
      'operation_requested'; paso K4c-2).
1.1.0 La sección se llama «Lista de palabras clave» (como en Lightroom y en el inspector).
      Lo desplegado se lleva en 'ui_helpers/helpers/keyword_expansion.py' (estado
      'SIDEBAR'), independiente del árbol del inspector; se sigue guardando por catálogo
      en 'expanded_keywords'.
1.0.1 'filter_keyword_tree' pasa a 'core/catalog/keywords.py' (se sigue exportando desde
      aquí) y el bloqueo de señales, a 'ui_helpers/helpers/signal_blocker.py': los usa
      también el árbol con casillas del inspector (paso K4b).
"""

__version__ = "1.7.1"
__all__ = ["ImageSidebar", "filter_keyword_tree"]

# Librerías estándar
from collections.abc import Iterable
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, QPoint, Qt, Signal
from qtpy.QtGui import QBrush, QPalette, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import QFrame, QLineEdit, QMenu, QScrollArea, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.folder_tree import FolderNode, LocationNode
from core.catalog.grid_source import (
    GridSource,
    SourceKind,
    folder_source,
    keyword_source,
    library_source,
    quick_source,
    source_from_dict,
    source_to_dict,
)
from core.catalog.keywords import KeywordTreeNode, filter_keyword_tree
from core.catalog.libraries import Library
from ui_helpers.helpers.keyword_expansion import SIDEBAR, KeywordExpansion, keyword_expansion
from ui_helpers.helpers.sidebar_icons import load_sidebar_icons
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME
from ui_helpers.widgets.collapsible_section import CollapsibleSection
from ui_helpers.widgets.sidebar_tree_view import ROLE_COUNT, ROLE_SOURCE, SidebarTreeView

# Biblioteca del módulo y su origen «todas las imágenes»
LIBRARY = Library.IMAGE.value
ALL_IMAGES = library_source(LIBRARY)
# La selección rápida, solo con lo de la biblioteca Imagen
IMAGE_QUICK = quick_source(LIBRARY)

# Rol propio: id de la palabra de la fila (para recordar lo desplegado)
_ROLE_KEYWORD_ID = Qt.ItemDataRole.UserRole + 40
# Roles propios de las carpetas: (ubicación, ruta relativa) para recordar lo desplegado,
# ruta absoluta (para «Mostrar en el Explorador»), si está conectada y clave del icono
_ROLE_FOLDER_KEY = Qt.ItemDataRole.UserRole + 41
_ROLE_PATH = Qt.ItemDataRole.UserRole + 42
_ROLE_ONLINE = Qt.ItemDataRole.UserRole + 43
_ROLE_ICON_KEY = Qt.ItemDataRole.UserRole + 44


# 'filter_keyword_tree' está en 'core/catalog/keywords.py' (la usa también el inspector)


class ImageSidebar(QWidget):
    """Barra lateral del módulo Imagen (ver el docstring del módulo).

    Signals:
        source_selected(object): el usuario ha elegido una fila (su 'GridSource').
        reveal_folder_requested(str): «Mostrar en el Explorador» en el menú de una carpeta
            (ruta absoluta).
    """

    source_selected = Signal(object)
    reveal_folder_requested = Signal(str)

    def __init__(
        self, parent: QWidget | None = None, expansion: KeywordExpansion | None = None
    ) -> None:
        super().__init__(parent)
        self._current: GridSource = ALL_IMAGES
        self._tree: tuple[KeywordTreeNode, ...] = ()
        # Palabras desplegadas (sin filtro); el árbol del inspector tiene las suyas
        self._expansion = expansion if expansion is not None else keyword_expansion(SIDEBAR)
        self._expansion.changed.connect(self._apply_expansion)
        self._views: list[SidebarTreeView] = []
        # Carpetas: el árbol mostrado, si se ven también las subcarpetas (opción del
        # Catálogo), lo desplegado ((ubicación, ruta)) y las ubicaciones ya vistas (una
        # nueva aparece desplegada)
        self._folder_tree: tuple[LocationNode, ...] = ()
        self._include_subfolders = True
        self._expanded_folders: set[tuple[int, str]] = set()
        self._known_locations: set[int] = set()
        self._icons = load_sidebar_icons(self)
        self._build_ui()
        self.set_keyword_tree(())
        self.select_source(ALL_IMAGES, emit=False)

    # -------------------------------------------------------------------------
    # Construcción
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Área con desplazamiento y las dos secciones."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setObjectName("scroll_image_sidebar")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget(scroll)
        content.setObjectName("widget_image_sidebar_content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        scroll.setWidget(content)

        # --- Biblioteca: «Todas las imágenes» ---
        self.section_library = CollapsibleSection("Biblioteca - Imagen", content)
        self._library_view, self._library_model = self._new_tree()
        self._all_item = self._make_item("Todas las imágenes", ALL_IMAGES)
        self._all_item.setToolTip("Todas las fotos y los vídeos de la biblioteca Imagen")
        self._library_model.appendRow(self._all_item)
        self._quick_item = self._make_item("Selección rápida", IMAGE_QUICK)
        self._quick_item.setToolTip(
            "Selección rápida\n\nLas imágenes marcadas con el círculo de su tarjeta (esquina\n"
            "superior derecha). Es la misma del Catálogo: aquí solo se ven las de Imagen."
        )
        self._library_model.appendRow(self._quick_item)
        # El mismo icono que «Todos los archivos» y «Selección rápida» en el Catálogo (así
        # los nombres quedan alineados con los de las carpetas)
        self._set_icon(self._all_item, "smart")
        self._set_icon(self._quick_item, "smart")
        self.section_library.set_content(self._library_view)
        layout.addWidget(self.section_library)

        # --- Carpetas: las que tienen imágenes ---
        self.section_folders = CollapsibleSection("Carpetas", content)
        self._folder_view, self._folder_model = self._new_tree()
        self._folder_view.expanded.connect(lambda index: self._on_folder_expanded(index, True))
        self._folder_view.collapsed.connect(lambda index: self._on_folder_expanded(index, False))
        self._folder_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._folder_view.customContextMenuRequested.connect(self._show_folder_menu)
        self.section_folders.set_content(self._folder_view)
        layout.addWidget(self.section_folders)

        # --- Palabras clave: filtro + árbol ---
        self.section_keywords = CollapsibleSection("Lista de palabras clave", content)
        box = QWidget(content)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(6, 2, 6, 4)
        box_layout.setSpacing(4)
        self._filter = QLineEdit(box)
        self._filter.setObjectName("edit_keyword_filter")
        self._filter.setPlaceholderText("Filtrar palabras clave")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._rebuild_keywords)
        box_layout.addWidget(self._filter)
        self._keyword_view, self._keyword_model = self._new_tree()
        self._keyword_view.expanded.connect(lambda index: self._on_expanded(index, True))
        self._keyword_view.collapsed.connect(lambda index: self._on_expanded(index, False))
        box_layout.addWidget(self._keyword_view)
        self.section_keywords.set_content(box)
        layout.addWidget(self.section_keywords)

        layout.addStretch(1)

    def _new_tree(self) -> tuple[SidebarTreeView, QStandardItemModel]:
        """Un árbol con su modelo, conectado a la selección común de la barra."""
        model = QStandardItemModel(self)
        view = SidebarTreeView()
        view.setModel(model)
        view.selectionModel().selectionChanged.connect(
            lambda selected, _deselected, v=view: self._on_selection_changed(v, selected)
        )
        self._views.append(view)
        return view, model

    @staticmethod
    def _make_item(text: str, source: GridSource | None, count: int | None = None) -> QStandardItem:
        """Una fila (sin añadirla a ningún sitio)."""
        item = QStandardItem(text)
        item.setEditable(False)
        item.setData(source, ROLE_SOURCE)
        item.setData(count, ROLE_COUNT)
        return item

    # -------------------------------------------------------------------------
    # Datos (los pone el módulo)
    # -------------------------------------------------------------------------

    def set_library_count(self, count: int | None, quick_count: int | None = None) -> None:
        """Contadores de «Todas las imágenes» y de «Selección rápida»."""
        self._all_item.setData(count, ROLE_COUNT)
        self._quick_item.setData(quick_count, ROLE_COUNT)

    def set_keyword_tree(self, tree: tuple[KeywordTreeNode, ...]) -> None:
        """Pone el árbol de palabras clave (no hace nada si no ha cambiado)."""
        if tree == self._tree and self._keyword_model.rowCount() > 0:
            return
        self._tree = tree
        self._rebuild_keywords()

    def set_folder_tree(self, locations: Iterable[LocationNode]) -> None:
        """Pone el árbol de carpetas (no hace nada si no ha cambiado)."""
        locations = tuple(locations)
        if locations == self._folder_tree and self._folder_model.rowCount() > 0:
            return
        self._folder_tree = locations
        self._rebuild_folders()

    def set_include_subfolders(self, include: bool) -> None:
        """Opción del Catálogo «Mostrar los elementos de las subcarpetas»: cambia los
        contadores y lo que muestra cada carpeta. Si hay una elegida, se emite su origen
        nuevo (la cuadrícula se recarga)."""
        if include == self._include_subfolders:
            return
        self._include_subfolders = include
        self._rebuild_folders()
        if self._current.kind == SourceKind.FOLDER:
            self._current = self._folder_source(self._current.location_id, self._current.folder)
            self.source_selected.emit(self._current)

    def reset(self) -> None:
        """Sin catálogo: árbol vacío, sin contadores, «Todas las imágenes» elegida."""
        self._tree = ()
        self._expansion.replace(())
        self._folder_tree = ()
        self._expanded_folders.clear()
        self._known_locations.clear()
        self._rebuild_folders()
        self.set_library_count(None)
        with _blocked(self._filter):
            self._filter.clear()
        self._rebuild_keywords()
        self.select_source(ALL_IMAGES, emit=False)

    def current_source(self) -> GridSource:
        """Lo elegido en la barra."""
        return self._current

    def has_source(self, source: GridSource) -> bool:
        """True si hay una fila para ese origen (una palabra filtrada no la tiene)."""
        return self._find_item(source) is not None

    def is_filtering(self) -> bool:
        """True si hay texto en «Filtrar palabras clave»."""
        return bool(self._filter.text().strip())

    def select_source(self, source: GridSource, *, emit: bool = True) -> None:
        """Elige una fila por su origen (si no existe, «Todas las imágenes»)."""
        item = self._find_item(source)
        if item is None:
            source, item = ALL_IMAGES, self._all_item
        view = self._view_of(item)
        self._clear_other_selections(view)
        with _blocked(view.selectionModel()):
            view.setCurrentIndex(item.index())
        # Con las señales de la selección bloqueadas la vista no se entera: se repinta
        view.viewport().update()
        changed = source != self._current
        self._current = source
        if emit and changed:
            self.source_selected.emit(source)

    def show_source(self, source: GridSource) -> None:
        """Elige un origen pedido desde fuera (p. ej. una palabra desde el inspector) y lo
        muestra en la cuadrícula. Una palabra: si el filtro la oculta, se vacía el filtro;
        se despliegan sus padres para que se vea marcada."""
        if source.kind == SourceKind.KEYWORD and source.keyword_id is not None:
            if self._find_item(source) is None and self.is_filtering():
                self._filter.clear()  # rehace el árbol entero
            for ancestor in self._keyword_ancestors(source.keyword_id):
                self._expansion.set_expanded(ancestor, True)  # el árbol se despliega solo
        if self._find_item(source) is None:
            return  # p. ej. una palabra que ya no existe
        self.select_source(source, emit=True)
        item = self._find_item(source)
        if item is not None:
            self._view_of(item).scrollTo(item.index())

    def _keyword_ancestors(self, keyword_id: int) -> list[int]:
        """Ids de los padres (y abuelos...) de una palabra en el árbol de la barra."""

        def visit(nodes: Iterable[KeywordTreeNode], parents: list[int]) -> list[int] | None:
            for node in nodes:
                if node.id == keyword_id:
                    return parents
                found = visit(node.children, [*parents, node.id])
                if found is not None:
                    return found
            return None

        return visit(self._tree, []) or []

    # -------------------------------------------------------------------------
    # Estado (por catálogo)
    # -------------------------------------------------------------------------

    def save_state(self) -> dict:
        """Secciones plegadas, palabras desplegadas y fila elegida (para JSON)."""
        return {
            "sections": {
                "library": self.section_library.is_expanded(),
                "folders": self.section_folders.is_expanded(),
                "keywords": self.section_keywords.is_expanded(),
            },
            "expanded_keywords": sorted(self._expansion.ids()),
            "expanded_folders": sorted([location, folder] for location, folder in self._expanded_folders),
            "known_locations": sorted(self._known_locations),
            "selected": source_to_dict(self._current),
        }

    def restore_state(self, state: object) -> None:
        """Recupera lo guardado con 'save_state' (lo que no se entienda se ignora)."""
        if not isinstance(state, dict):
            return
        sections = state.get("sections")
        if isinstance(sections, dict):
            pairs = (
                ("library", self.section_library),
                ("folders", self.section_folders),
                ("keywords", self.section_keywords),
            )
            for key, section in pairs:
                if isinstance(sections.get(key), bool):
                    section.set_expanded(sections[key])
        expanded = state.get("expanded_keywords")
        if isinstance(expanded, list):
            self._expansion.replace(expanded)
        folders = state.get("expanded_folders")
        if isinstance(folders, list):
            self._expanded_folders = {
                (entry[0], entry[1])
                for entry in folders
                if isinstance(entry, list) and len(entry) == 2
                and isinstance(entry[0], int) and isinstance(entry[1], str)
            }
        known = state.get("known_locations")
        if isinstance(known, list):
            self._known_locations = {value for value in known if isinstance(value, int)}
        selected = source_from_dict(state.get("selected"), include_subfolders=self._include_subfolders)
        if selected in (ALL_IMAGES, IMAGE_QUICK):
            self.select_source(selected, emit=False)
        elif selected is not None and selected.kind == SourceKind.FOLDER and selected.library == LIBRARY:
            # La carpeta llega después (con el árbol): se recuerda y se marca al llegar
            self._clear_other_selections(None)
            self._current = selected
        elif selected is not None and selected.kind == SourceKind.KEYWORD:
            # La palabra puede no estar aún en el árbol (llega después): se recuerda y se
            # marca al llegar ('_rebuild_keywords')
            self._clear_other_selections(None)
            self._current = selected

    # -------------------------------------------------------------------------
    # Árbol de carpetas (como el del Catálogo, solo con lo de Imagen)
    # -------------------------------------------------------------------------

    def _folder_source(self, location_id: int, relative_path: str) -> GridSource:
        """Origen de una carpeta: solo sus imágenes, con o sin subcarpetas (la opción)."""
        return folder_source(
            location_id, relative_path, include_subfolders=self._include_subfolders, library=LIBRARY
        )

    def _folder_count(self, node: FolderNode) -> int | None:
        """Contador: con sus subcarpetas o solo lo suyo, según la opción (0 = sin número)."""
        count = node.count if self._include_subfolders else node.direct_count
        return count or None

    def _rebuild_folders(self) -> None:
        """Rehace el árbol de carpetas conservando lo desplegado y la carpeta elegida.

        No se bloquean las señales del MODELO (ver TRAMPAS.md): solo las de la vista (lo
        desplegado por código no se anota) y las de su selección.
        """
        view, model = self._folder_view, self._folder_model
        offline = QBrush(view.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
        with _blocked(view.selectionModel(), view):
            model.clear()
            root = model.invisibleRootItem()
            for location in self._folder_tree:
                item = self._make_item(
                    location.name, self._folder_source(location.location_id, ""),
                    self._folder_count(location.root),
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
                self._append_folders(item, location, location.root.children, None if location.is_online else offline)
                # Una ubicación que aparece por primera vez se muestra desplegada
                if location.location_id not in self._known_locations:
                    self._known_locations.add(location.location_id)
                    self._expanded_folders.add((location.location_id, ""))
            self._expand_folders(root)
        view.updateGeometry()
        # La carpeta elegida, otra vez marcada (si sigue en el árbol)
        if self._current.kind == SourceKind.FOLDER:
            item = self._find_item(self._current)
            if item is not None:
                with _blocked(view.selectionModel()):
                    view.setCurrentIndex(item.index())
                # Con las señales de la selección bloqueadas la vista no se entera: se repinta
                view.viewport().update()

    def _append_folders(
        self,
        parent: QStandardItem,
        location: LocationNode,
        children: tuple[FolderNode, ...],
        foreground: QBrush | None,
    ) -> None:
        """Añade (recursivamente) las subcarpetas de una carpeta."""
        for node in children:
            item = self._make_item(
                node.name, self._folder_source(location.location_id, node.relative_path),
                self._folder_count(node),
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
            self._append_folders(item, location, node.children, foreground)

    def _expand_folders(self, parent: QStandardItem) -> None:
        """Despliega las carpetas que lo estaban (solo las que tienen subcarpetas: Qt da
        por desplegada también una fila sin hijos si se le pide)."""
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if child.hasChildren() and tuple(child.data(_ROLE_FOLDER_KEY) or ()) in self._expanded_folders:
                self._folder_view.setExpanded(child.index(), True)
                self._update_open_icon(child, True)
            self._expand_folders(child)

    def _set_icon(self, item: QStandardItem, key: str) -> None:
        """Pone a una fila el icono 'key' (y lo anota para desplegar y plegar)."""
        item.setIcon(self._icons[key])
        item.setData(key, _ROLE_ICON_KEY)

    def _update_open_icon(self, item: QStandardItem | None, is_open: bool) -> None:
        """Desplegada = icono de la carpeta abierta, en el color de acento."""
        key = item.data(_ROLE_ICON_KEY) if item is not None else None
        if key:
            item.setIcon(self._icons[f"{key}:open" if is_open else key])

    def _on_folder_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo que despliega o pliega el usuario."""
        key = index.data(_ROLE_FOLDER_KEY)
        if key is not None:
            key = tuple(key)
            (self._expanded_folders.add if expanded else self._expanded_folders.discard)(key)
        self._update_open_icon(self._folder_model.itemFromIndex(index), expanded)

    def _show_folder_menu(self, position: QPoint) -> None:
        """Menú de una carpeta: solo «Mostrar en el Explorador» (sincronizar y quitar
        ausentes están en el Catálogo: esta barra es para navegar)."""
        index = self._folder_view.indexAt(position)
        path = index.data(_ROLE_PATH) if index.isValid() else None
        if not path:
            return
        menu = QMenu(self._folder_view)
        reveal = menu.addAction(f"Mostrar en {FILE_MANAGER_NAME}")
        if not index.data(_ROLE_ONLINE):
            reveal.setEnabled(False)
            menu.addSeparator()
            menu.addAction("(ubicación desconectada)").setEnabled(False)
        if menu.exec(self._folder_view.viewport().mapToGlobal(position)) is reveal:
            self.reveal_folder_requested.emit(path)

    # -------------------------------------------------------------------------
    # Árbol de palabras clave
    # -------------------------------------------------------------------------

    def _rebuild_keywords(self) -> None:
        """Rehace el árbol con el filtro actual, conservando lo desplegado y lo elegido."""
        filtering = bool(self._filter.text().strip())
        shown = filter_keyword_tree(self._tree, self._filter.text())
        view, model = self._keyword_view, self._keyword_model
        with _blocked(view.selectionModel(), view):
            model.clear()
            self._append_nodes(model.invisibleRootItem(), shown)
            # Con filtro, todo desplegado (se ve dónde está cada coincidencia); sin filtro,
            # lo que el usuario tenía desplegado
            if filtering:
                view.expandAll()
            else:
                self._expand_saved(model.invisibleRootItem())
        view.updateGeometry()
        # La fila elegida, otra vez marcada (si sigue en el árbol)
        if self._current.kind == SourceKind.KEYWORD:
            item = self._find_item(self._current)
            if item is not None:
                with _blocked(view.selectionModel()):
                    view.setCurrentIndex(item.index())
                # Con las señales de la selección bloqueadas la vista no se entera: se repinta
                view.viewport().update()

    def _append_nodes(self, parent: QStandardItem, nodes: Iterable[KeywordTreeNode]) -> None:
        """Añade las palabras (y sus hijas) bajo 'parent'."""
        for node in nodes:
            # Sin fotos en la biblioteca: sin número (como una carpeta vacía)
            item = self._make_item(node.name, keyword_source(node.id, LIBRARY), node.count or None)
            item.setData(node.id, _ROLE_KEYWORD_ID)
            tooltip = f"{node.name}\n{node.count} con esta palabra o sus hijas"
            if node.direct_count != node.count:
                tooltip += f" ({node.direct_count} la tienen asignada directamente)"
            if node.needs_review:
                tooltip += "\nPalabra suelta con el nombre de otras del árbol: revisar dónde va."
            item.setToolTip(tooltip)
            parent.appendRow(item)
            self._append_nodes(item, node.children)

    def _expand_saved(self, parent: QStandardItem) -> None:
        """Despliega las filas que el usuario tenía desplegadas."""
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if self._expansion.is_expanded(child.data(_ROLE_KEYWORD_ID)):
                self._keyword_view.expand(child.index())
            self._expand_saved(child)

    def _apply_expansion(self) -> None:
        """Lo desplegado ha cambiado (p. ej. al recuperarlo): el árbol se pone igual.

        Con texto en el filtro no se toca (está todo desplegado); al vaciarlo, se rehace
        con lo desplegado de ese momento.
        """
        if self._filter.text().strip():
            return

        def visit(parent: QStandardItem) -> None:
            for row in range(parent.rowCount()):
                child = parent.child(row)
                if child.hasChildren():
                    expanded = self._expansion.is_expanded(child.data(_ROLE_KEYWORD_ID))
                    self._keyword_view.setExpanded(child.index(), expanded)
                    visit(child)

        visit(self._keyword_model.invisibleRootItem())

    def _on_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo desplegado por el usuario (no lo que despliega el filtro)."""
        if self._filter.text().strip():
            return
        keyword_id = index.data(_ROLE_KEYWORD_ID)
        if isinstance(keyword_id, int):
            self._expansion.set_expanded(keyword_id, expanded)

    def _view_of(self, item: QStandardItem) -> SidebarTreeView:
        """El árbol en el que está una fila."""
        if item is self._all_item or item is self._quick_item:
            return self._library_view
        return self._folder_view if item.model() is self._folder_model else self._keyword_view

    def _find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de un origen, o None si no está (p. ej. una palabra filtrada)."""
        if source == ALL_IMAGES:
            return self._all_item
        if source == IMAGE_QUICK:
            return self._quick_item
        if source.kind == SourceKind.FOLDER:
            return self._find_folder(self._folder_model.invisibleRootItem(), source)
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

        return search(self._keyword_model.invisibleRootItem())

    def _find_folder(self, parent: QStandardItem, source: GridSource) -> QStandardItem | None:
        """La fila de una carpeta (por su ubicación y su ruta)."""
        wanted = (source.location_id, source.folder)
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if tuple(child.data(_ROLE_FOLDER_KEY) or ()) == wanted:
                return child
            found = self._find_folder(child, source)
            if found is not None:
                return found
        return None

    # -------------------------------------------------------------------------
    # Selección
    # -------------------------------------------------------------------------

    def _on_selection_changed(self, view: SidebarTreeView, selected) -> None:
        """El usuario ha elegido una fila en uno de los dos árboles."""
        indexes = selected.indexes()
        if not indexes:
            return
        source = indexes[0].data(ROLE_SOURCE)
        if source is None:
            return
        self._clear_other_selections(view)
        if source != self._current:
            self._current = source
            self.source_selected.emit(source)

    def _clear_other_selections(self, keep: SidebarTreeView | None) -> None:
        """Una sola fila elegida en toda la barra."""
        for other in self._views:
            if other is not keep:
                with _blocked(other.selectionModel()):
                    other.selectionModel().clearSelection()
                other.viewport().update()
