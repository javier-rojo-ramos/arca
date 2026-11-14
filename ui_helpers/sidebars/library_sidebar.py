"""Barra lateral de un módulo de biblioteca (columna izquierda): biblioteca, carpetas y fechas.

Es la barra del módulo Tracks, y está hecha para servir a los demás módulos de una sola
biblioteca que lleguen (Vídeo, Audio...): se le dice la BIBLIOTECA y sus TEXTOS y monta
las secciones comunes, una debajo de otra, dentro de un área con desplazamiento:

    ▼ BIBLIOTECA - TRACKS   «Todos los tracks» y «Selección rápida», con sus contadores
    ▼ CARPETAS              ubicaciones y carpetas con archivos de la biblioteca
                            ('sections/folder_section.py')
    ▼ FECHAS                años ▸ meses ▸ días, y «Sin fecha» ('sections/date_section.py')

Es el mismo esquema que 'ImageSidebar' (de la que sale; aquella tiene además la «Lista de
palabras clave» y sigue en su archivo: unirlas es un paso aparte, anotado en
docs/PENDIENTE.md). Como ella, esta barra es el CONTENEDOR y solo NAVEGA:
    - «Biblioteca» son dos filas fijas: todo lo de la biblioteca y su «Selección rápida»
      (la misma de todo el catálogo, pero solo con lo de esta biblioteca).
    - Las secciones se dan de alta en una 'SectionStack' con su 'id' del registro
      ('ui_helpers/layout/section_registry.py': 'library', 'folders', 'dates'): el orden,
      si se ven y si están plegadas lo lleva el modelo de colocación ('bind_layout').
    - Una sola fila elegida en toda la barra; al elegirla, emite 'source_selected'.
    - El estado por catálogo ('save_state' / 'restore_state'): lo desplegado de cada
      sección y la fila elegida.

Cómo se comunica con el resto (no sabe nada de SQL ni de la cuadrícula; lo une su módulo,
p. ej. 'controllers/app_modules/tracks_module.py'):
    - Cada fila lleva un 'GridSource' (ROLE_SOURCE). Al elegirla, emite 'source_selected'.
    - 'set_library_count', 'set_folder_tree' y 'set_date_tree' reciben lo que el módulo lee
      en segundo plano. Si un árbol no ha cambiado, no se reconstruye.

Uso:
    sidebar = LibrarySidebar("tracks", LibraryTexts("Biblioteca - Tracks", "Todos los tracks", ...))
    sidebar.bind_layout(model, "tracks")
    sidebar.source_selected.connect(...)
    sidebar.all_source, sidebar.quick_source      # los orígenes de sus dos filas fijas

El aspecto se define en la hoja de estilos global (ui_theme.py) con los nombres de objeto
'scroll_library_sidebar' y 'widget_library_sidebar_content' (y los de cada sección).

1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.2): para el módulo Tracks.
"""

__version__ = "1.0.0"
__all__ = ["LibrarySidebar", "LibraryTexts"]

# Librerías estándar
from collections.abc import Iterable
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QStandardItem, QStandardItemModel
from qtpy.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.folder_tree import LocationNode
from core.catalog.grid_source import (
    GridSource,
    SourceKind,
    library_source,
    quick_source,
    source_from_dict,
    source_to_dict,
)
from core.catalog.metadata_values import MetadataValue
from ui_helpers.helpers.sidebar_icons import load_sidebar_icons
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.layout.section_layout_model import SectionLayoutModel
from ui_helpers.layout.section_registry import Sidebar
from ui_helpers.sidebars.sections.date_section import DateSection
from ui_helpers.sidebars.sections.folder_section import FolderSection
from ui_helpers.sidebars.sections.tree_section import TreeSection, make_item
from ui_helpers.widgets.collapsible_section import CollapsibleSection
from ui_helpers.widgets.section_stack import SectionStack
from ui_helpers.widgets.sidebar_tree_view import ROLE_COUNT, ROLE_SOURCE, SidebarTreeView


@dataclass(frozen=True, slots=True)
class LibraryTexts:
    """Los textos de la barra de una biblioteca.

    Attributes:
        library_title: Título de la sección de la biblioteca («Biblioteca - Tracks»).
        all_title: Fila de todo lo de la biblioteca («Todos los tracks»).
        all_tooltip: Su texto de ayuda.
        quick_tooltip: Texto de ayuda de la fila «Selección rápida».
        folders_title: Título de la sección de carpetas.
        dates_title: Título de la sección de fechas.
    """

    library_title: str
    all_title: str
    all_tooltip: str
    quick_tooltip: str
    folders_title: str = "Carpetas"
    dates_title: str = "Fechas"


class LibrarySidebar(QWidget):
    """Barra lateral de un módulo de biblioteca (ver el docstring del módulo).

    Signals:
        source_selected(object): el usuario ha elegido una fila (su 'GridSource').
        reveal_folder_requested(str): «Mostrar en el Explorador» en el menú de una carpeta
            (ruta absoluta).
    """

    source_selected = Signal(object)
    reveal_folder_requested = Signal(str)

    def __init__(self, library: str, texts: LibraryTexts, parent: QWidget | None = None) -> None:
        """Crea la barra vacía (sin contadores ni árboles).

        Args:
            library: Biblioteca del módulo ('tracks'...).
            texts: Sus textos.
            parent: Widget padre.
        """
        super().__init__(parent)
        self._library = library
        self._texts = texts
        # Los orígenes de las dos filas fijas
        self.all_source: GridSource = library_source(library)
        self.quick_source: GridSource = quick_source(library)
        self._current: GridSource = self.all_source
        self._icons = load_sidebar_icons(self)
        self._build_ui()
        self.select_source(self.all_source, emit=False)

    # -------------------------------------------------------------------------
    # Construcción
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Área con desplazamiento y las secciones, en su orden de partida."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setObjectName("scroll_library_sidebar")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Sin teclado: un clic en la barra (fuera de una caja de texto) no se lo quita a
        # los archivos; si no, Qt se lo daría a esta área
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget(scroll)
        content.setObjectName("widget_library_sidebar_content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        scroll.setWidget(content)

        self._folders = FolderSection(self._library, self._icons, content)
        self._folders.reveal_folder_requested.connect(self.reveal_folder_requested)
        self._dates = DateSection(self._library, content)
        # Las secciones con árbol (en 'sections/'): la fila elegida se busca en ellas
        self._sections: tuple[TreeSection, ...] = (self._folders, self._dates)

        # Las secciones plegables, en su orden de partida: ('id' en el registro de
        # secciones, título, contenido). Van en una pila que las coloca como diga el modelo
        # de colocación ('bind_layout')
        self._stack = SectionStack(content)
        for key, title, widget in (
            ("library", self._texts.library_title, self._build_library(content)),
            ("folders", self._texts.folders_title, self._folders),
            ("dates", self._texts.dates_title, self._dates),
        ):
            section = CollapsibleSection(title, content)
            section.set_content(widget)
            self._stack.add_section(key, section)
        layout.addWidget(self._stack)
        layout.addStretch(1)
        # El menú de las secciones (mostrar, ocultar, restaurar), también en el hueco vacío
        self._stack.watch_empty_area(content)

        # Una sola fila elegida en toda la barra; al rehacer un árbol, la elegida se marca
        self._views: list[SidebarTreeView] = [self._library_view]
        for tree_section in self._sections:
            self._views.extend(tree_section.views())
            tree_section.rebuilt.connect(self._remark_current)
        for view in self._views:
            view.selectionModel().selectionChanged.connect(
                lambda selected, _deselected, v=view: self._on_selection_changed(v, selected)
            )

    def _build_library(self, parent: QWidget) -> SidebarTreeView:
        """Las dos filas fijas: todo lo de la biblioteca y su «Selección rápida»."""
        self._library_model = QStandardItemModel(self)
        self._library_view = SidebarTreeView(parent)
        self._library_view.setModel(self._library_model)
        self._all_item = make_item(self._texts.all_title, self.all_source)
        self._all_item.setToolTip(self._texts.all_tooltip)
        self._quick_item = make_item("Selección rápida", self.quick_source)
        self._quick_item.setToolTip(self._texts.quick_tooltip)
        # El mismo icono que en el Catálogo y en Imagen (así los nombres quedan alineados
        # con los de las carpetas)
        for item in (self._all_item, self._quick_item):
            item.setIcon(self._icons["smart"])
            self._library_model.appendRow(item)
        return self._library_view

    def bind_layout(self, model: SectionLayoutModel, mode: str) -> None:
        """Une las secciones al modelo de colocación (orden, visibles y plegadas), para el
        modo de esta barra. Sin llamarlo, quedan en su orden de partida, todas a la vista."""
        self._stack.bind(model, mode, Sidebar.LEFT)

    # -------------------------------------------------------------------------
    # Datos (los pone el módulo)
    # -------------------------------------------------------------------------

    def set_library_count(self, count: int | None, quick_count: int | None = None) -> None:
        """Contadores de la fila de todo lo de la biblioteca y de «Selección rápida»."""
        self._all_item.setData(count, ROLE_COUNT)
        self._quick_item.setData(quick_count, ROLE_COUNT)

    def set_folder_tree(self, locations: Iterable[LocationNode]) -> None:
        """Pone el árbol de carpetas (no hace nada si no ha cambiado)."""
        self._folders.set_tree(locations)

    def set_date_tree(self, values: Iterable[MetadataValue]) -> None:
        """Pone los años, meses y días ('fetch_timeline(...).values'; no hace nada si no
        han cambiado)."""
        self._dates.set_tree(tuple(values))

    def set_include_subfolders(self, include: bool) -> None:
        """Opción del Catálogo «Mostrar los elementos de las subcarpetas»: cambia los
        contadores y lo que muestra cada carpeta. Si hay una elegida, se emite su origen
        nuevo (la cuadrícula se recarga)."""
        if not self._folders.set_include_subfolders(include):
            return
        if self._current.kind == SourceKind.FOLDER:
            self._current = self._folders.folder_source(self._current.location_id, self._current.folder)
            self.source_selected.emit(self._current)

    def reset(self) -> None:
        """Sin catálogo: árboles vacíos, sin contadores, la primera fila elegida."""
        for tree_section in self._sections:
            tree_section.reset()
        self.set_library_count(None)
        self.select_source(self.all_source, emit=False)

    def current_source(self) -> GridSource:
        """Lo elegido en la barra."""
        return self._current

    def has_source(self, source: GridSource) -> bool:
        """True si hay una fila para ese origen."""
        return self._find_item(source) is not None

    def select_source(self, source: GridSource, *, emit: bool = True) -> None:
        """Elige una fila por su origen (si no existe, la de todo lo de la biblioteca)."""
        item = self._find_item(source)
        if item is None:
            source, item = self.all_source, self._all_item
        self._clear_other_selections(self._view_of(item))
        self._mark(item)
        changed = source != self._current
        self._current = source
        if emit and changed:
            self.source_selected.emit(source)

    def show_source(self, source: GridSource) -> None:
        """Elige un origen pedido desde fuera (p. ej. desde el inspector) y lo muestra en la
        cuadrícula; si no tiene fila en esta barra, no hace nada."""
        for tree_section in self._sections:
            tree_section.reveal(source)
        item = self._find_item(source)
        if item is None:
            return
        self.select_source(source, emit=True)
        self._view_of(item).scrollTo(item.index())

    # -------------------------------------------------------------------------
    # Estado (por catálogo)
    # -------------------------------------------------------------------------

    def save_state(self) -> dict:
        """Lo de cada sección (lo desplegado) y la fila elegida (para JSON). Claves:
        'expanded_folders', 'known_locations', 'expanded_dates' y 'selected'. Lo plegado de
        las secciones lo lleva el modelo de colocación."""
        state: dict = {}
        for tree_section in self._sections:
            state.update(tree_section.save_state())
        state["selected"] = source_to_dict(self._current)
        return state

    def restore_state(self, state: object) -> None:
        """Recupera lo guardado con 'save_state' (lo que no se entienda se ignora)."""
        if not isinstance(state, dict):
            return
        for tree_section in self._sections:
            tree_section.restore_state(state)
        selected = source_from_dict(
            state.get("selected"), include_subfolders=self._folders.include_subfolders
        )
        if selected in (self.all_source, self.quick_source):
            self.select_source(selected, emit=False)
        elif selected is not None and any(s.owns(selected) for s in self._sections):
            # Su fila puede no estar aún (el árbol llega después): se recuerda y se marca
            # al llegar ('_remark_current')
            self._clear_other_selections(None)
            self._current = selected

    # -------------------------------------------------------------------------
    # Filas y selección
    # -------------------------------------------------------------------------

    def _find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de un origen, o None si no está."""
        if source == self.all_source:
            return self._all_item
        if source == self.quick_source:
            return self._quick_item
        for tree_section in self._sections:
            item = tree_section.find_item(source)
            if item is not None:
                return item
        return None

    def _view_of(self, item: QStandardItem) -> SidebarTreeView:
        """El árbol en el que está una fila."""
        model = item.model()
        return next((view for view in self._views if view.model() is model), self._library_view)

    def _mark(self, item: QStandardItem) -> None:
        """Marca una fila sin avisar (no es el usuario quien la elige)."""
        view = self._view_of(item)
        with _blocked(view.selectionModel()):
            view.setCurrentIndex(item.index())
        # Con las señales de la selección bloqueadas la vista no se entera: se repinta
        view.viewport().update()

    def _remark_current(self) -> None:
        """Una sección ha rehecho su árbol: la fila elegida, otra vez marcada (si está)."""
        item = self._find_item(self._current)
        if item is not None:
            self._mark(item)

    def _on_selection_changed(self, view: SidebarTreeView, selected) -> None:
        """El usuario ha elegido una fila en uno de los árboles."""
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
