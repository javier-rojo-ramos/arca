"""Barra lateral del módulo Imagen (columna izquierda): biblioteca, carpetas, fechas y
palabras clave.

Secciones plegables, una debajo de otra, dentro de un área con desplazamiento (como la
barra del Catálogo):

    ▼ BIBLIOTECA - IMAGEN       «Todas las imágenes» y «Selección rápida», con sus contadores
    ▼ CARPETAS                  ubicaciones y carpetas con imágenes ('sections/folder_section.py')
    ▼ FECHAS                    años ▸ meses ▸ días, y «Sin fecha» ('sections/date_section.py')
    ▼ LISTA DE PALABRAS CLAVE   filtro y árbol de palabras ('sections/keyword_section.py')

Esta barra es el CONTENEDOR: cada sección con árbol está en su archivo de 'sections/' (ver
'tree_section.py') y aquí solo queda lo común:
    - «Biblioteca - Imagen» (dos filas fijas: no merece un archivo propio). «Selección
      rápida» (04/11/2026) es la misma del Catálogo (una sola para todo el catálogo), pero
      solo se ven sus imágenes y vídeos del móvil ('quick_source("image")'). Sin menú:
      «Vaciar selección rápida» vaciaría también lo que no se ve; está en el Catálogo.
    - Las secciones, en el orden de '_build_ui' (una lista: cambiarlo es cambiar la lista).
    - Una sola fila elegida en toda la barra; al elegirla, emite 'source_selected'.
    - La fila elegida, otra vez marcada cuando una sección rehace su árbol ('rebuilt').
    - El estado por catálogo: secciones plegadas, lo de cada sección y la fila elegida.

Esta barra es para NAVEGAR (decidido por el autor el 04/11/2026): editar las palabras clave
se hace en el inspector, en su «Lista de palabras clave».

Cómo se comunica con el resto (no sabe nada de SQL ni de la cuadrícula; lo une
'controllers/app_modules/image_module.py'):
    - Cada fila lleva un 'GridSource' (ROLE_SOURCE). Al elegirla, emite 'source_selected'.
    - 'set_library_count', 'set_folder_tree', 'set_date_tree' y 'set_keyword_tree' reciben
      lo que el módulo lee en segundo plano. Si un árbol no ha cambiado, no se reconstruye (no se pierde lo
      desplegado).
    - 'save_state' / 'restore_state': secciones plegadas, lo desplegado y la fila elegida
      (el módulo lo guarda por catálogo).

El aspecto se define en la hoja de estilos global (ui_theme.py) con los nombres de objeto
'scroll_image_sidebar' y 'widget_image_sidebar_content' (y los de cada sección).

2.1.1 El área con desplazamiento no coge el teclado: un clic en la barra no se lo quita
      a las fotos (decidido por el autor el 12/11/2026, como Lightroom).
2.1.0 Sección «Fechas» debajo de «Carpetas» ('sections/date_section.py', 'set_date_tree';
      paso A.4).
2.0.0 Dividida en un archivo por sección (pedido por el autor el 12/11/2026): las
      «Carpetas» pasan a 'sections/folder_section.py' y la «Lista de palabras clave», a
      'sections/keyword_section.py'; aquí queda el contenedor. Nada cambia a la vista y lo
      guardado por catálogo tiene las mismas claves. 'filter_keyword_tree' ya no se exporta
      desde aquí (nadie la importaba: está en 'core/catalog/keywords.py').
1.7.3 El filtro de palabras clave, a 8 px de los lados (antes, 6) en su propia fila; el
      árbol, a todo el ancho como el de carpetas (sus números, alineados con los de las
      carpetas) y con los nombres en la columna de las flechas de las subcarpetas
      ('_KEYWORD_NAME_INDENT'). Pedido por el autor.
1.7.2 El filtro de palabras clave, a 8 px de la cabecera de la sección (antes, 4).
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

__version__ = "2.1.1"
__all__ = ["ALL_IMAGES", "IMAGE_QUICK", "LIBRARY", "ImageSidebar"]

# Librerías estándar
from collections.abc import Iterable

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
from core.catalog.keywords import KeywordTreeNode
from core.catalog.libraries import Library
from core.catalog.metadata_values import MetadataValue
from ui_helpers.helpers.keyword_expansion import KeywordExpansion
from ui_helpers.helpers.sidebar_icons import load_sidebar_icons
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.sidebars.sections.date_section import DateSection
from ui_helpers.sidebars.sections.folder_section import FolderSection
from ui_helpers.sidebars.sections.keyword_section import KeywordSection
from ui_helpers.sidebars.sections.tree_section import TreeSection, make_item
from ui_helpers.widgets.collapsible_section import CollapsibleSection
from ui_helpers.widgets.sidebar_tree_view import ROLE_COUNT, ROLE_SOURCE, SidebarTreeView

# Biblioteca del módulo y su origen «todas las imágenes»
LIBRARY = Library.IMAGE.value
ALL_IMAGES = library_source(LIBRARY)
# La selección rápida, solo con lo de la biblioteca Imagen
IMAGE_QUICK = quick_source(LIBRARY)


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
        self._icons = load_sidebar_icons(self)
        self._build_ui(expansion)
        self.select_source(ALL_IMAGES, emit=False)

    # -------------------------------------------------------------------------
    # Construcción
    # -------------------------------------------------------------------------

    def _build_ui(self, expansion: KeywordExpansion | None) -> None:
        """Área con desplazamiento y las secciones, en su orden."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setObjectName("scroll_image_sidebar")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Sin teclado: un clic en la barra (fuera de una caja de texto) no se lo quita a las
        # fotos; si no, Qt se lo daría a esta área (la primera de más arriba que lo acepta)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget(scroll)
        content.setObjectName("widget_image_sidebar_content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        scroll.setWidget(content)

        self._folders = FolderSection(LIBRARY, self._icons, content)
        self._folders.reveal_folder_requested.connect(self.reveal_folder_requested)
        self._dates = DateSection(LIBRARY, content)
        self._keywords = KeywordSection(LIBRARY, expansion, content)
        # Las secciones con árbol (en 'sections/'): la fila elegida se busca en ellas
        self._sections: tuple[TreeSection, ...] = (self._folders, self._dates, self._keywords)

        # Las secciones plegables, de arriba abajo: (clave en el estado guardado, título,
        # contenido). Para cambiar el orden basta con cambiar esta lista
        self._collapsibles: dict[str, CollapsibleSection] = {}
        for key, title, widget in (
            ("library", "Biblioteca - Imagen", self._build_library(content)),
            ("folders", "Carpetas", self._folders),
            ("dates", "Fechas", self._dates),
            ("keywords", "Lista de palabras clave", self._keywords),
        ):
            section = CollapsibleSection(title, content)
            section.set_content(widget)
            layout.addWidget(section)
            self._collapsibles[key] = section
        layout.addStretch(1)

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
        """«Todas las imágenes» y «Selección rápida»."""
        self._library_model = QStandardItemModel(self)
        self._library_view = SidebarTreeView(parent)
        self._library_view.setModel(self._library_model)
        self._all_item = make_item("Todas las imágenes", ALL_IMAGES)
        self._all_item.setToolTip("Todas las fotos y los vídeos de la biblioteca Imagen")
        self._quick_item = make_item("Selección rápida", IMAGE_QUICK)
        self._quick_item.setToolTip(
            "Selección rápida\n\nLas imágenes marcadas con el círculo de su tarjeta (esquina\n"
            "superior derecha). Es la misma del Catálogo: aquí solo se ven las de Imagen."
        )
        # El mismo icono que «Todos los archivos» y «Selección rápida» en el Catálogo (así
        # los nombres quedan alineados con los de las carpetas)
        for item in (self._all_item, self._quick_item):
            item.setIcon(self._icons["smart"])
            self._library_model.appendRow(item)
        return self._library_view

    # -------------------------------------------------------------------------
    # Datos (los pone el módulo)
    # -------------------------------------------------------------------------

    def set_library_count(self, count: int | None, quick_count: int | None = None) -> None:
        """Contadores de «Todas las imágenes» y de «Selección rápida»."""
        self._all_item.setData(count, ROLE_COUNT)
        self._quick_item.setData(quick_count, ROLE_COUNT)

    def set_keyword_tree(self, tree: tuple[KeywordTreeNode, ...]) -> None:
        """Pone el árbol de palabras clave (no hace nada si no ha cambiado)."""
        self._keywords.set_tree(tree)

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
        """Sin catálogo: árboles vacíos, sin contadores, «Todas las imágenes» elegida."""
        for tree_section in self._sections:
            tree_section.reset()
        self.set_library_count(None)
        self.select_source(ALL_IMAGES, emit=False)

    def current_source(self) -> GridSource:
        """Lo elegido en la barra."""
        return self._current

    def has_source(self, source: GridSource) -> bool:
        """True si hay una fila para ese origen (una palabra filtrada no la tiene)."""
        return self._find_item(source) is not None

    def is_filtering(self) -> bool:
        """True si hay texto en «Filtrar palabras clave»."""
        return self._keywords.is_filtering()

    def select_source(self, source: GridSource, *, emit: bool = True) -> None:
        """Elige una fila por su origen (si no existe, «Todas las imágenes»)."""
        item = self._find_item(source)
        if item is None:
            source, item = ALL_IMAGES, self._all_item
        self._clear_other_selections(self._view_of(item))
        self._mark(item)
        changed = source != self._current
        self._current = source
        if emit and changed:
            self.source_selected.emit(source)

    def show_source(self, source: GridSource) -> None:
        """Elige un origen pedido desde fuera (p. ej. una palabra desde el inspector) y lo
        muestra en la cuadrícula. Antes, su sección prepara el árbol para que se vea (una
        palabra: vacía el filtro si la oculta y despliega sus padres)."""
        for tree_section in self._sections:
            tree_section.reveal(source)
        item = self._find_item(source)
        if item is None:
            return  # p. ej. una palabra que ya no existe
        self.select_source(source, emit=True)
        self._view_of(item).scrollTo(item.index())

    # -------------------------------------------------------------------------
    # Estado (por catálogo)
    # -------------------------------------------------------------------------

    def save_state(self) -> dict:
        """Secciones plegadas, lo de cada sección (lo desplegado) y la fila elegida (para
        JSON). Claves: 'sections', 'expanded_folders', 'known_locations', 'expanded_dates'
        (desde la 2.1.0), 'expanded_keywords' y 'selected'."""
        state: dict = {
            "sections": {key: section.is_expanded() for key, section in self._collapsibles.items()}
        }
        for tree_section in self._sections:
            state.update(tree_section.save_state())
        state["selected"] = source_to_dict(self._current)
        return state

    def restore_state(self, state: object) -> None:
        """Recupera lo guardado con 'save_state' (lo que no se entienda se ignora)."""
        if not isinstance(state, dict):
            return
        sections = state.get("sections")
        if isinstance(sections, dict):
            for key, section in self._collapsibles.items():
                if isinstance(sections.get(key), bool):
                    section.set_expanded(sections[key])
        for tree_section in self._sections:
            tree_section.restore_state(state)
        selected = source_from_dict(
            state.get("selected"), include_subfolders=self._folders.include_subfolders
        )
        if selected in (ALL_IMAGES, IMAGE_QUICK):
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
        """La fila de un origen, o None si no está (p. ej. una palabra filtrada)."""
        if source == ALL_IMAGES:
            return self._all_item
        if source == IMAGE_QUICK:
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
