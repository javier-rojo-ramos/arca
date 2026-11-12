"""Barra lateral del modo Catálogo (columna izquierda, como el panel de Lightroom Classic).

Secciones plegables, una debajo de otra, dentro de un área con desplazamiento:

    ▼ Catálogo      "Todos los archivos" y "Selección rápida" con sus contadores
    ▼ Carpetas  +   árbol de las ubicaciones del catálogo con contadores  (paso 1b)
    ▼ Colecciones + Clasificación, Etiqueta, Marcadas, Rechazadas (paso 1c) y
                    los conjuntos y colecciones del usuario               (paso 1d),
                    también las inteligentes, con su propio icono         (paso 1e)

Cómo se comunica con el resto (no sabe nada de SQL ni de la cuadrícula):
    - Cada fila lleva un 'GridSource' (qué mostrar). Al seleccionarla, la barra emite
      'source_selected(GridSource)' y el controlador se lo pasa al modelo de la cuadrícula.
    - Contadores de las secciones Catálogo y Colecciones: 'sources()' dice qué
      orígenes hay que contar; el controlador los cuenta en segundo plano
      ('media_queries.count_grid_items') y los devuelve con 'set_counts'.
    - Carpetas: el controlador lee el árbol en segundo plano ('folder_tree.fetch_folder_tree',
      que ya trae los contadores) y lo pasa con 'set_folder_tree'. Si no ha cambiado, no se
      reconstruye nada (así no se pierde la posición ni lo desplegado).
    - El botón "+" de la cabecera de Carpetas emite 'add_folder_requested' (el controlador
      abre el mismo diálogo que "Añadir carpeta al catálogo" del menú).
    - Menú contextual de las carpetas (clic derecho): "Sincronizar carpeta" emite
      'sync_folder_requested(ruta)', "Mostrar en el Explorador" emite
      'reveal_folder_requested(ruta)' y "Quitar archivos ausentes del catálogo" emite
      'remove_missing_requested(ubicación, carpeta)' y "Quitar del catálogo" emite
      'remove_folder_requested(ubicación, carpeta, nombre)'. Los atiende el controlador.
    - 'set_include_subfolders' decide si al elegir una carpeta se ven también los
      elementos de sus subcarpetas (opción de settings.json; ver el controlador). Cambia
      también los contadores: con subcarpetas o solo los de la propia carpeta.
    - Colecciones del usuario: el controlador lee el árbol ('user_collections.
      fetch_collection_tree') y lo pasa con 'set_collection_tree'. El botón "+" de la
      cabecera y el menú contextual piden crear, renombrar o eliminar (señales
      'create_collection_requested', 'rename_collection_requested',
      'delete_collection_requested'); al soltar tarjetas de la cuadrícula sobre una
      colección se emite 'media_dropped(id de la colección, MediaDrag)'. "Editar colección
      inteligente" (menú o doble clic) emite 'edit_smart_collection_requested'. La barra
      no toca la base de datos: todo lo atiende 'controllers/collection_actions.py'.
    - Iconos: los SVG de 'AppIcons' (carpeta, carpeta abierta, disco, conjunto, colección
      y colección inteligente), teñidos con 'SIDEBAR_ICON_COLOR' de ui_theme.py (None =
      el color del texto). Si un SVG aún no está en los recursos, se usa el icono estándar.
    - Menú contextual de «Selección rápida»: "Vaciar selección rápida" emite
      'clear_quick_selection_requested' (desactivado si está vacía).
    - Solo hay UNA fila seleccionada en toda la barra, aunque esté en otra sección.
    - Lo desplegado (secciones, carpetas, conjuntos, grupos del sistema) y la fila
      ELEGIDA se pueden guardar y recuperar con 'save_state' / 'restore_state' (el
      controlador lo guarda por catálogo en settings.json al cerrarlo y lo recupera al
      abrirlo: la cuadrícula vuelve a mostrar la carpeta o colección que se estaba viendo).

Se coloca en la ventana desde Qt Designer como widget PROMOCIONADO: por eso el
constructor solo recibe el widget padre.

El aspecto se define en la hoja de estilos global (ui_helpers/helpers/ui_theme.py) con los
nombres de objeto 'scroll_catalog_sidebar' y 'widget_catalog_sidebar_content'.

1.12.2 El área con desplazamiento no coge el teclado: un clic en la barra no se lo
       quita a las fotos (decidido por el autor el 12/11/2026, como Lightroom).
1.12.1 Iconos de los menús de colecciones con su variante ':menu' (en la opción
       resaltada, oscuros sobre el acento, como el texto).
1.12.0 'show_source': un origen pedido desde el inspector; si no tiene fila (una palabra
       clave), se muestra sin fila marcada (paso A.2).
1.11.0 Menú de las carpetas: "Quitar del catálogo..." (también con el disco desconectado).
       Si la carpeta elegida desaparece del árbol, se elige su carpeta padre (antes,
       "Todos los archivos").
1.10.1 Los iconos de las filas, en 'ui_helpers/helpers/sidebar_icons.py' (los usa también la
       barra del módulo Imagen).
1.10.0 Fila «Sin clasificar» en la sección Catálogo (elementos sin biblioteca); solo se
       ve si hay alguno (o si es la fila elegida).
1.9.0 'save_state' / 'restore_state' guardan también la fila elegida (carpeta, colección,
      selección rápida...): al reabrir el catálogo se vuelve a mostrar.
1.8.1 Menú contextual de «Selección rápida»: "Vaciar selección rápida".
1.8.0 Sección Catálogo: "Selección rápida" (los archivos marcados con el círculo de su
      tarjeta). Sus filas llevan icono y el mismo sangrado que las de Carpetas, para que
      todo quede alineado en vertical.
1.7.2 Las filas DESPLEGADAS (ubicaciones, carpetas, conjuntos y grupos del sistema)
      llevan su icono en el color de acento; las plegadas y las que no tienen hijos, no.
1.7.1 Iconos con color fijo (las carpetas sin subcarpetas salían en el color de acento:
      Qt las dibujaba como "desplegadas"); la carpeta abierta, en su propio color. El "+"
      de las cabeceras es un icono SVG ('AppIcons.ADD'), algo mayor y alineado a la derecha.
1.7.0 Colecciones inteligentes del usuario (icono propio, tooltip con sus reglas, crear,
      editar con doble clic o desde el menú). Iconos SVG de 'AppIcons' teñidos.
1.6.0 'save_state' / 'restore_state': lo desplegado se conserva entre sesiones. Corregido:
      al releer las colecciones, Qt seleccionaba "Rechazadas" por su cuenta.
1.5.0 Colecciones del usuario: conjuntos y colecciones estáticas, crear, renombrar,
      eliminar y soltar tarjetas de la cuadrícula sobre una colección.
1.4.0 Sección Colecciones: colecciones del sistema (core/catalog/system_collections.py).
1.3.0 Menú contextual: "Quitar archivos ausentes del catálogo...".
1.2.0 Menú contextual de las carpetas (sincronizar, mostrar en el explorador) y opción
      de incluir o no las subcarpetas.
1.1.0 Sección Carpetas: árbol de ubicaciones y carpetas con contadores, y botón "+".
"""

__version__ = "1.12.2"
__all__ = ["CatalogSidebar"]

# Librerías estándar
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtCore import (
    QEvent,
    QFile,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QSize,
    Qt,
    Signal,
)
from qtpy.QtGui import QBrush, QColor, QIcon, QPalette, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import (
    QFrame,
    QLabel,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.folder_tree import FolderNode, LocationNode
from core.catalog.grid_source import (
    ALL_ITEMS,
    QUICK_SELECTION,
    UNCLASSIFIED,
    GridSource,
    SourceKind,
    collection_source,
    folder_source,
    smart_collection_source,
    source_from_dict,
    source_to_dict,
)
from core.catalog.smart_rules import describe_rules
from core.catalog.system_collections import SYSTEM_COLLECTIONS, SystemCollection
from core.catalog.user_collections import KIND_SET, KIND_SMART, KIND_STATIC, CollectionNode
from ui_helpers.helpers.sidebar_icons import load_sidebar_icons
from ui_helpers.helpers.ui_color_labels import label_icon
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_theme import ACCENT_COLOR
from ui_helpers.models.media_mime import MEDIA_IDS_MIME, decode_media_ids
from ui_helpers.widgets.collapsible_section import CollapsibleSection
from ui_helpers.widgets.sidebar_tree_view import ROLE_COUNT, ROLE_SOURCE, SidebarTreeView

# Roles propios de las filas del árbol de carpetas (además de ROLE_SOURCE y ROLE_COUNT)
_ROLE_PATH = Qt.ItemDataRole.UserRole + 10  # str: ruta absoluta de la carpeta
_ROLE_ONLINE = Qt.ItemDataRole.UserRole + 11  # bool: si su ubicación está conectada
# Roles propios de las filas de las colecciones del usuario
_ROLE_COLLECTION_ID = Qt.ItemDataRole.UserRole + 20  # int: 'collections.id'
_ROLE_COLLECTION_KIND = Qt.ItemDataRole.UserRole + 21  # str: KIND_SET, KIND_STATIC o KIND_SMART
# Clave del icono de la fila en '_icons' ("folder", "set"...): al desplegarla se cambia por
# su variante "<clave>:open" (en el color de acento) y al plegarla se vuelve a la normal
_ROLE_ICON_KEY = Qt.ItemDataRole.UserRole + 30

# Texto de los menús para crear cada tipo (en el orden en que aparecen)
_CREATE_ACTIONS: tuple[tuple[str, str], ...] = (
    (KIND_SET, "Crear conjunto de colecciones..."),
    (KIND_STATIC, "Crear colección..."),
    (KIND_SMART, "Crear colección inteligente..."),
)
_CREATE_HERE_ACTIONS: tuple[tuple[str, str], ...] = (
    (KIND_SET, "Crear conjunto aquí..."),
    (KIND_STATIC, "Crear colección aquí..."),
    (KIND_SMART, "Crear colección inteligente aquí..."),
)
# Qué es cada tipo (primera línea del tooltip)
_KIND_NAMES = {
    KIND_SET: "Conjunto de colecciones",
    KIND_STATIC: "Colección",
    KIND_SMART: "Colección inteligente",
}


@contextmanager
def _signals_blocked(selection_model: QItemSelectionModel) -> Iterator[None]:
    """Bloquea las señales de un modelo de selección mientras dura el bloque 'with'.

    Así un cambio de selección hecho por código no se confunde con un clic del usuario.
    """
    previous = selection_model.blockSignals(True)
    try:
        yield
    finally:
        selection_model.blockSignals(previous)


class CatalogSidebar(QWidget):
    """Barra lateral del catálogo: secciones Catálogo, Carpetas y Colecciones.

    Signals:
        source_selected(object): el usuario eligió una fila; lleva su 'GridSource'.
        add_folder_requested(): el usuario pulsó "+" en la cabecera de Carpetas.
        sync_folder_requested(str): "Sincronizar carpeta" en el menú de una carpeta.
        reveal_folder_requested(str): "Mostrar en el Explorador" en el menú de una carpeta.
        remove_missing_requested(int, str): "Quitar archivos ausentes del catálogo" en el
            menú de una carpeta (id de la ubicación y carpeta relativa; '' = toda).
        remove_folder_requested(int, str, str): "Quitar del catálogo" en el menú de una
            carpeta o ubicación (id de la ubicación, carpeta relativa, '' = la ubicación, y
            el nombre que se ve en el árbol).
        create_collection_requested(str, object): crear una colección, una colección
            inteligente o un conjunto (KIND_STATIC, KIND_SMART o KIND_SET, y el id del
            conjunto donde crearla o None).
        edit_smart_collection_requested(int): editar las reglas de una colección
            inteligente del usuario (su id).
        rename_collection_requested(int, str): renombrar (id y nombre actual).
        delete_collection_requested(int, str, str): eliminar (id, nombre y tipo).
        media_dropped(int, object): se han soltado tarjetas sobre una colección (id de la
            colección y un 'MediaDrag' con los 'id' de las tarjetas).
        clear_quick_selection_requested(): "Vaciar selección rápida" en el menú de su fila.
    """

    source_selected = Signal(object)
    add_folder_requested = Signal()
    sync_folder_requested = Signal(str)  # ruta absoluta de la carpeta
    reveal_folder_requested = Signal(str)  # ruta absoluta de la carpeta
    remove_missing_requested = Signal(int, str)  # ubicación y carpeta relativa
    remove_folder_requested = Signal(int, str, str)  # ubicación, carpeta relativa y nombre
    create_collection_requested = Signal(str, object)  # tipo y conjunto (o None)
    rename_collection_requested = Signal(int, str)  # id y nombre actual
    delete_collection_requested = Signal(int, str, str)  # id, nombre y tipo
    media_dropped = Signal(int, object)  # id de la colección y MediaDrag
    edit_smart_collection_requested = Signal(int)  # id de la colección inteligente
    clear_quick_selection_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Filas de las secciones fijas (Catálogo y, más adelante, colecciones): se cuentan
        # con 'count_grid_items' (ver 'sources' y 'set_counts')
        self._items: dict[GridSource, QStandardItem] = {}
        # Filas del árbol de carpetas: se reconstruyen con cada árbol nuevo y sus
        # contadores vienen con el propio árbol
        self._folder_items: dict[GridSource, QStandardItem] = {}
        # Último árbol mostrado (para no reconstruir si no ha cambiado)
        self._folder_tree: tuple[LocationNode, ...] | None = None
        # Carpetas desplegadas (se conservan al reconstruir el árbol)
        self._expanded: set[GridSource] = set()
        # Ubicaciones ya vistas: una ubicación NUEVA aparece desplegada la primera vez
        self._known_locations: set[int] = set()
        # Árboles de todas las secciones (para que solo haya una selección en total)
        self._views: list[SidebarTreeView] = []
        # Origen mostrado ahora en la cuadrícula
        self._current: GridSource = ALL_ITEMS
        # Si al elegir una carpeta se ven también sus subcarpetas (ver 'set_include_subfolders')
        self._include_subfolders = True
        # Colecciones del usuario: filas (por origen), último árbol y conjuntos desplegados
        self._collection_items: dict[GridSource, QStandardItem] = {}
        self._collection_tree: tuple[CollectionNode, ...] | None = None
        self._expanded_sets: set[int] = set()
        # Grupos del sistema desplegados ("Clasificación", "Etiqueta"), por nombre
        self._expanded_system: set[str] = set()
        # Fila resaltada mientras se arrastran tarjetas por encima (destino de la soltada)
        self._drop_target: QStandardItem | None = None
        # Orígenes de las colecciones del usuario por su id (para seguir a una colección
        # inteligente aunque cambien sus reglas: su origen cambia, su id no)
        self._collection_sources: dict[int, GridSource] = {}
        # Iconos de las filas (SVG de 'AppIcons' teñidos; ver '_load_icons')
        self._icons = self._load_icons()

        self._build_ui()
        self.set_folder_tree(())
        self.select_source(ALL_ITEMS, emit=False)

    # -------------------------------------------------------------------------
    # Construcción
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Crea el área con desplazamiento y las tres secciones."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toda la barra se desplaza a la vez (las secciones no tienen barra propia)
        scroll = QScrollArea(self)
        scroll.setObjectName("scroll_catalog_sidebar")
        scroll.setWidgetResizable(True)  # el contenido toma el ancho de la barra
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Sin teclado: un clic en la barra (fuera de una caja de texto) no se lo quita a las
        # fotos; si no, Qt se lo daría a esta área (la primera de más arriba que lo acepta)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget(scroll)
        content.setObjectName("widget_catalog_sidebar_content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        scroll.setWidget(content)

        # --- Catálogo ---
        # Árbol "con ramas" (flat=False) aunque sus filas no tengan hijos: así reserva el
        # hueco de la flecha y las filas quedan alineadas con las de Carpetas y Colecciones
        self.section_catalog = CollapsibleSection("Catálogo", content)
        view, model = self._new_tree(flat=False)
        root = model.invisibleRootItem()
        catalog_rows = (
            ("Todos los archivos", ALL_ITEMS, "Todos los archivos del catálogo"),
            (
                "Selección rápida",
                QUICK_SELECTION,
                "Selección rápida\n\nLos archivos marcados con el círculo de su tarjeta\n"
                "(esquina superior derecha de la miniatura).",
            ),
            (
                "Sin clasificar",
                UNCLASSIFIED,
                (
                    "Sin clasificar\n\nVídeos de carpetas «Detectar automáticamente» cuyo nombre\n"
                    "no dice si son clips personales o películas.\n\n"
                    "Clic derecho en la cuadrícula > Biblioteca para clasificarlos."
                ),
            ),
        )
        for text, source, tooltip in catalog_rows:
            item = self._add_source_item(root, text, source)
            self._set_icon(item, "smart")
            item.setToolTip(tooltip)
        # Clic derecho: menú de la fila (de momento, solo la de la selección rápida)
        self._catalog_view = view
        # «Sin clasificar» solo se ve cuando hay algo (ver '_update_unclassified_row')
        self._unclassified_item = self._items[UNCLASSIFIED]
        self._update_unclassified_row()
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._show_catalog_menu)
        self.section_catalog.set_content(view)
        layout.addWidget(self.section_catalog)

        # --- Carpetas ---
        self.section_folders = CollapsibleSection("Carpetas", content)
        self._folders_view, self._folders_model = self._new_tree(flat=False)
        # Lo desplegado se recuerda para mantenerlo al reconstruir el árbol
        self._folders_view.expanded.connect(self._on_folder_expanded)
        self._folders_view.collapsed.connect(self._on_folder_collapsed)
        # Clic derecho: menú de la carpeta
        self._folders_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._folders_view.customContextMenuRequested.connect(self._show_folder_menu)
        self.section_folders.set_content(self._folders_view)
        self.section_folders.add_header_widget(self._make_add_folder_button())
        layout.addWidget(self.section_folders)

        # --- Colecciones: primero las del sistema, después las del usuario ---
        self.section_collections = CollapsibleSection("Colecciones", content)
        self._collections_view, self._collections_model = self._new_tree(flat=False)
        self._add_system_collections(
            self._collections_model.invisibleRootItem(), SYSTEM_COLLECTIONS
        )
        # Las filas de primer nivel del sistema: lo que hay detrás es del usuario
        self._system_row_count = self._collections_model.rowCount()
        view = self._collections_view
        view.expanded.connect(self._on_collection_expanded)
        view.collapsed.connect(self._on_collection_collapsed)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._show_collection_menu)
        # Doble clic sobre una colección inteligente: editar sus reglas (como Lightroom)
        view.doubleClicked.connect(self._on_collection_double_clicked)
        # Soltar tarjetas de la cuadrícula sobre una colección (ver 'eventFilter')
        view.setAcceptDrops(True)
        view.viewport().setAcceptDrops(True)
        view.viewport().installEventFilter(self)
        self.section_collections.set_content(view)
        self.section_collections.add_header_widget(self._make_add_collection_button())
        layout.addWidget(self.section_collections)

        # Lo que sobre queda abajo, vacío: las secciones se apilan arriba
        layout.addStretch(1)

    def _load_icons(self) -> dict[str, QIcon]:
        """Iconos de las filas (ver 'ui_helpers/helpers/sidebar_icons.py', compartidos con
        la barra del módulo Imagen)."""
        return load_sidebar_icons(self)

    def _set_icon(self, item: QStandardItem, key: str) -> None:
        """Pone a una fila el icono 'key' de '_icons' (y lo anota para desplegar/plegar)."""
        item.setIcon(self._icons[key])
        item.setData(key, _ROLE_ICON_KEY)

    def _update_open_icon(self, model: QStandardItemModel, index: QModelIndex, is_open: bool) -> None:
        """Desplegada = icono en el color de acento (variante ':open'); plegada = normal."""
        key = index.data(_ROLE_ICON_KEY) if index.isValid() else None
        item = model.itemFromIndex(index) if key else None
        if item is not None:
            item.setIcon(self._icons[f"{key}:open" if is_open else key])

    @staticmethod
    def _style_add_button(button: QToolButton) -> None:
        """Aspecto del "+" de una cabecera: icono SVG (acento al pasar el ratón) o el signo."""
        path = getattr(AppIcons, "ADD", "")
        if path and QFile.exists(path):
            button.setIcon(tinted_icon(path, hover_color=ACCENT_COLOR))
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        else:
            button.setText("+")  # sin el SVG: el signo, en grande (ver ui_theme.py)
        button.setAutoRaise(True)

    def _add_system_collections(
        self, parent: QStandardItem, collections: tuple[SystemCollection, ...]
    ) -> None:
        """Añade (recursivamente) las colecciones del sistema.

        Los grupos ("Clasificación", "Etiqueta") empiezan plegados, como en Lightroom; al
        pulsarlos muestran todo lo de su grupo (con alguna estrella, con algún color).
        Son colecciones inteligentes: llevan su icono (las de color, su muestra de color)
        y sus reglas en el tooltip.
        """
        for collection in collections:
            item = self._add_source_item(parent, collection.name, collection.source)
            if collection.color_label is not None:
                item.setIcon(label_icon(collection.color_label))
            else:
                self._set_icon(item, "smart")
            if collection.source.rules is not None:
                item.setToolTip(
                    "Colección inteligente del sistema\n\n" + describe_rules(collection.source.rules)
                )
            self._add_system_collections(item, collection.children)

    def _show_catalog_menu(self, position: QPoint) -> None:
        """Menú contextual de la sección Catálogo (solo la fila «Selección rápida» tiene)."""
        index = self._catalog_view.indexAt(position)
        if not index.isValid() or index.data(ROLE_SOURCE) != QUICK_SELECTION:
            return
        menu = QMenu(self)
        action = menu.addAction("Vaciar selección rápida")
        action.triggered.connect(self.clear_quick_selection_requested.emit)
        # Vacía (contador 0) no hay nada que vaciar; sin contador todavía, se deja activa
        action.setEnabled(index.data(ROLE_COUNT) != 0)
        menu.exec(self._catalog_view.viewport().mapToGlobal(position))

    def _make_add_folder_button(self) -> QToolButton:
        """Botón "+" de la cabecera de Carpetas (como el de Lightroom)."""
        button = QToolButton()
        button.setObjectName("btn_sidebar_add_folder")
        self._style_add_button(button)
        button.setToolTip("Añadir carpeta al catálogo...")
        button.clicked.connect(self.add_folder_requested.emit)
        return button

    def _make_add_collection_button(self) -> QToolButton:
        """Botón "+" de la cabecera de Colecciones: crear una colección o un conjunto."""
        button = QToolButton()
        button.setObjectName("btn_sidebar_add_collection")  # aspecto: ver ui_theme.py
        self._style_add_button(button)
        button.setToolTip("Crear conjunto, colección o colección inteligente...")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        self._add_create_actions(menu, None)
        button.setMenu(menu)
        return button

    def _add_create_actions(self, menu: QMenu, parent_id: int | None) -> None:
        """Añade a un menú "Crear conjunto / colección / colección inteligente".

        Args:
            menu: Menú donde se añaden.
            parent_id: Conjunto donde se crearía (None = primer nivel; con un conjunto,
                los textos dicen "aquí").
        """
        icons = {KIND_SET: "set", KIND_STATIC: "collection", KIND_SMART: "smart"}
        actions = _CREATE_ACTIONS if parent_id is None else _CREATE_HERE_ACTIONS
        for kind, text in actions:
            action = menu.addAction(self._icons[f"{icons[kind]}:menu"], text)
            action.triggered.connect(
                lambda _checked=False, k=kind: self.create_collection_requested.emit(k, parent_id)
            )

    def _new_tree(self, *, flat: bool) -> tuple[SidebarTreeView, QStandardItemModel]:
        """Crea un árbol con su modelo y lo conecta a la selección común.

        Args:
            flat: True para una lista sin ramas (sin la flecha de desplegar).
        """
        model = QStandardItemModel(self)
        view = SidebarTreeView()
        view.setModel(model)
        view.setRootIsDecorated(not flat)
        # 'selectionModel()' existe ya: se crea al asignar el modelo
        view.selectionModel().selectionChanged.connect(
            lambda selected, _deselected, v=view: self._on_selection_changed(v, selected)
        )
        self._views.append(view)
        return view, model

    def _add_source_item(
        self, parent: QStandardItem, text: str, source: GridSource | None
    ) -> QStandardItem:
        """Añade una fila de una sección fija que, al pulsarla, muestra 'source'.

        Args:
            parent: Fila padre (o 'invisibleRootItem()' para el primer nivel).
            text: Texto de la fila.
            source: Origen asociado (None = la fila no filtra, solo agrupa).
        """
        item = self._make_item(text, source)
        if source is not None:
            self._items[source] = item
        parent.appendRow(item)
        return item

    @staticmethod
    def _make_item(
        text: str, source: GridSource | None, count: int | None = None, icon: QIcon | None = None
    ) -> QStandardItem:
        """Crea una fila (sin añadirla a ningún sitio)."""
        item = QStandardItem(text)
        item.setEditable(False)
        item.setData(source, ROLE_SOURCE)
        item.setData(count, ROLE_COUNT)
        if icon is not None:
            item.setIcon(icon)
        if source is None:
            # Una fila que solo agrupa no se puede seleccionar (no cambia la cuadrícula)
            item.setSelectable(False)
        return item

    @staticmethod
    def _placeholder(text: str) -> QLabel:
        """Texto gris para las secciones aún sin contenido."""
        label = QLabel(text)
        label.setEnabled(False)  # se pinta con el color atenuado de la paleta
        label.setContentsMargins(12, 2, 0, 2)
        return label

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def sources(self) -> list[GridSource]:
        """Orígenes de las secciones fijas: los que hay que contar con 'count_grid_items'.

        Las carpetas no están aquí: sus contadores llegan con el árbol ('set_folder_tree').
        """
        return list(self._items)

    def set_counts(self, counts: dict[GridSource, int]) -> None:
        """Pone el contador de cada fila fija. Las que no vengan en 'counts' quedan en blanco."""
        for source, item in self._items.items():
            item.setData(counts.get(source), ROLE_COUNT)
        self._update_unclassified_row()

    def _update_unclassified_row(self) -> None:
        """Muestra la fila «Sin clasificar» solo si hay algo sin clasificar o si está elegida.

        Así no ocupa sitio cuando no hace falta (lo normal), pero no desaparece mientras
        se está viendo (p. ej. al clasificar el último vídeo).
        """
        item = getattr(self, "_unclassified_item", None)
        if item is None:
            return  # todavía construyendo la barra
        hidden = not item.data(ROLE_COUNT) and self._current != UNCLASSIFIED
        view = self._catalog_view
        if view.isRowHidden(item.row(), QModelIndex()) != hidden:
            view.setRowHidden(item.row(), QModelIndex(), hidden)
            view.updateGeometry()  # el árbol ajusta su alto a las filas visibles

    def set_folder_tree(self, locations: Iterable[LocationNode]) -> None:
        """Muestra el árbol de carpetas (ubicaciones, carpetas y sus contadores).

        Si es igual que el que ya se muestra, no hace nada. Al reconstruirlo se conservan
        las carpetas desplegadas y la selección. Si la carpeta seleccionada ya no existe
        (p. ej. se quitó del catálogo), se vuelve a "Todos los archivos".
        """
        locations = tuple(locations)
        if locations == self._folder_tree:
            return
        self._folder_tree = locations

        view, model = self._folders_view, self._folders_model
        # Color atenuado para las ubicaciones desconectadas (se siguen pudiendo ver)
        offline_brush = QBrush(view.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))

        with _signals_blocked(view.selectionModel()):
            model.clear()
            self._folder_items.clear()
            root = model.invisibleRootItem()

            if not locations:
                empty = self._make_item("Ninguna carpeta: añádela con +", None)
                empty.setEnabled(False)
                root.appendRow(empty)

            for location in locations:
                source = self._source_for(location.location_id, "")
                item = self._make_item(
                    location.name, source, self._count_of(location.root)
                )
                self._set_icon(item, "drive")
                item.setData(location.absolute_path, _ROLE_PATH)
                item.setData(location.is_online, _ROLE_ONLINE)
                tooltip = location.absolute_path
                if not location.is_online:
                    tooltip += "\n(desconectada)"
                    item.setForeground(offline_brush)
                item.setToolTip(tooltip)
                self._folder_items[source] = item
                root.appendRow(item)
                self._add_folder_children(
                    item, location, location.root.children,
                    None if location.is_online else offline_brush,
                )  # fmt: skip

                # Una ubicación que aparece por primera vez se muestra desplegada
                if location.location_id not in self._known_locations:
                    self._known_locations.add(location.location_id)
                    self._expanded.add(source)

            # Se vuelven a desplegar las carpetas que lo estaban (con su carpeta abierta).
            # Solo las que tienen subcarpetas: Qt da por "desplegada" también una fila sin
            # hijos si se le pide, y la dibuja como tal
            for source in list(self._expanded):
                item = self._folder_items.get(source)
                if item is not None and item.hasChildren():
                    view.setExpanded(item.index(), True)
                    self._update_open_icon(model, item.index(), True)

        # La selección: se mantiene la carpeta elegida; si ya no existe (p. ej. se ha quitado
        # del catálogo), la carpeta más cercana que la contenga y, si no queda ninguna (se
        # ha quitado la ubicación entera), "Todos los archivos"
        current = self._current
        if current.kind == SourceKind.FOLDER:
            if current in self._folder_items:
                self.select_source(current, emit=False)
            else:
                self.select_source(self._closest_folder(current), emit=True)

    def _closest_folder(self, source: GridSource) -> GridSource:
        """La carpeta del árbol más cercana que contiene a 'source', o 'ALL_ITEMS' si no hay.

        Se sube de nivel en nivel ('2024/Viaje/Día 1' -> '2024/Viaje' -> '2024' -> la
        ubicación): una carpeta padre sin archivos propios ni otras subcarpetas también
        desaparece del árbol al quitar su única subcarpeta.
        """
        if source.location_id is None:
            return ALL_ITEMS
        parts = source.folder.split("/") if source.folder else []
        while parts:
            parts.pop()
            parent = self._source_for(source.location_id, "/".join(parts))
            if parent in self._folder_items:
                return parent
        return ALL_ITEMS

    def set_collection_tree(self, nodes: Iterable[CollectionNode]) -> None:
        """Muestra las colecciones y conjuntos del usuario (debajo de los del sistema).

        Si el árbol es igual que el que ya se muestra, no hace nada. Al reconstruirlo se
        conservan los conjuntos desplegados y la selección; si la colección seleccionada
        ya no existe (p. ej. se acaba de eliminar), se vuelve a "Todos los archivos".
        """
        nodes = tuple(nodes)
        if nodes == self._collection_tree:
            return
        self._collection_tree = nodes
        self._clear_drop_target()

        view, model = self._collections_view, self._collections_model

        with _signals_blocked(view.selectionModel()):
            # Se quita la fila "actual" ANTES de quitar filas: con selección única, si Qt
            # quita la fila actual elige él otra (la anterior: "Rechazadas") y la SELECCIONA.
            # La selección correcta se vuelve a poner al final
            view.selectionModel().clear()
            # Se quitan las filas del usuario (las del sistema se quedan)
            extra = model.rowCount() - self._system_row_count
            if extra > 0:
                model.removeRows(self._system_row_count, extra)
            self._collection_items.clear()
            self._collection_sources.clear()
            self._add_user_collections(model.invisibleRootItem(), nodes)
            # Se vuelven a desplegar los conjuntos que lo estaban
            for row in range(self._system_row_count, model.rowCount()):
                self._restore_expanded_sets(model.index(row, 0))
        view.viewport().update()

        # La selección: si lo elegido está en este árbol (una colección del sistema o del
        # usuario), se vuelve a marcar; si era una colección que ya no existe, "Todos".
        # Una colección del usuario se sigue por su id: si se han editado sus reglas, su
        # origen es otro y se emite para que la cuadrícula se recargue con las nuevas
        current = self._current
        system_item = self._items.get(current)
        if system_item is not None and system_item.model() is model:
            self.select_source(current, emit=False)
        elif current.collection_id is not None and current.kind in (
            SourceKind.COLLECTION,
            SourceKind.SMART,
        ):
            new_source = self._collection_sources.get(current.collection_id)
            if new_source is None:
                self.select_source(ALL_ITEMS, emit=True)  # ya no existe (o sus reglas no se leen)
            else:
                self.select_source(new_source, emit=new_source != current)

    # -------------------------------------------------------------------------
    # Estado visual entre sesiones (lo desplegado)
    # -------------------------------------------------------------------------

    def save_state(self) -> dict:
        """Lo desplegado de la barra lateral, en un diccionario que se puede guardar en JSON.

        Las carpetas se guardan como (ubicación, carpeta) y los conjuntos por su 'id': solo
        tienen sentido en ESTE catálogo (el controlador lo guarda por catálogo).
        """
        return {
            "sections": {
                "catalog": self.section_catalog.is_expanded(),
                "folders": self.section_folders.is_expanded(),
                "collections": self.section_collections.is_expanded(),
            },
            "expanded_folders": sorted(
                [source.location_id, source.folder]
                for source in self._expanded
                if source.location_id is not None
            ),
            "known_locations": sorted(self._known_locations),
            "expanded_sets": sorted(self._expanded_sets),
            "expanded_system": sorted(self._expanded_system),
            # Lo que muestra la cuadrícula (ver 'source_to_dict')
            "selected": source_to_dict(self._current),
        }

    def restore_state(self, state: object) -> None:
        """Recupera lo guardado con 'save_state' (llamar al abrir el catálogo, antes de que
        lleguen los árboles: se aplica al construirlos).

        Tolera datos incompletos o de otra versión (lo que no se entiende se ignora).
        """
        if not isinstance(state, dict):
            return

        sections = state.get("sections")
        if isinstance(sections, dict):
            for key, section in (
                ("catalog", self.section_catalog),
                ("folders", self.section_folders),
                ("collections", self.section_collections),
            ):
                if isinstance(sections.get(key), bool):
                    section.set_expanded(sections[key])

        folders = state.get("expanded_folders")
        if isinstance(folders, list):
            self._expanded = {
                self._source_for(entry[0], entry[1])
                for entry in folders
                if isinstance(entry, list) and len(entry) == 2
                and isinstance(entry[0], int) and isinstance(entry[1], str)
            }  # fmt: skip
        known = state.get("known_locations")
        if isinstance(known, list):
            self._known_locations = {value for value in known if isinstance(value, int)}
        sets = state.get("expanded_sets")
        if isinstance(sets, list):
            self._expanded_sets = {value for value in sets if isinstance(value, int)}
        system = state.get("expanded_system")
        if isinstance(system, list):
            self._expanded_system = {value for value in system if isinstance(value, str)}
            self._apply_system_expansion()

        selected = source_from_dict(
            state.get("selected"), include_subfolders=self._include_subfolders
        )
        if selected is not None and selected != ALL_ITEMS:
            self._restore_selection(selected)

    def _restore_selection(self, source: GridSource) -> None:
        """Vuelve a elegir lo que se estaba viendo al cerrar el catálogo.

        Se llama al abrirlo, ANTES de que lleguen los árboles de carpetas y colecciones:
            - Filas fijas (Todos, Selección rápida, colecciones del sistema): ya existen,
              se seleccionan y se emite su origen.
            - Carpeta o colección estática: su origen está completo, así que se emite ya
              (la cuadrícula no pasa antes por "Todos los archivos"). La fila se marca al
              llegar su árbol; si ya no existe, el árbol vuelve a "Todos los archivos".
            - Colección inteligente del usuario: sus reglas están en la base de datos, así
              que se anota y se emite al llegar el árbol de colecciones (que la sigue por
              su id, como al editarla).
        """
        if source in self._items:
            self.select_source(source, emit=True)
            return
        # Se olvidan los árboles mostrados: el próximo que llegue (aunque sea vacío) se
        # procesa siempre, y así se comprueba si lo guardado sigue existiendo
        self._folder_tree = None
        self._collection_tree = None
        self._clear_other_selections(None)
        self._current = source
        if source.kind != SourceKind.SMART:  # inteligente del usuario: aún sin reglas
            self.source_selected.emit(source)

    def _apply_system_expansion(self) -> None:
        """Despliega o pliega los grupos del sistema según '_expanded_system'."""
        view, model = self._collections_view, self._collections_model
        for row in range(self._system_row_count):
            index = model.index(row, 0)
            if model.hasChildren(index):
                view.setExpanded(index, index.data(Qt.ItemDataRole.DisplayRole) in self._expanded_system)

    def set_include_subfolders(self, include: bool) -> None:
        """Decide si al elegir una carpeta se ven también los elementos de sus subcarpetas.

        Reconstruye el árbol (cambian los orígenes y los contadores) conservando lo
        desplegado. Si hay una carpeta seleccionada, se emite 'source_selected' con su
        origen nuevo para que la cuadrícula se recargue.
        """
        if include == self._include_subfolders:
            return
        self._include_subfolders = include

        # Lo desplegado y la selección actual pasan a los orígenes con la opción nueva
        self._expanded = {
            replace(source, include_subfolders=include) for source in self._expanded
        }
        folder_selected = self._current.kind == SourceKind.FOLDER
        if folder_selected:
            self._current = replace(self._current, include_subfolders=include)

        # Se fuerza la reconstrucción con el mismo árbol
        tree = self._folder_tree or ()
        self._folder_tree = None
        self.set_folder_tree(tree)

        # (si la carpeta ya no existía, 'set_folder_tree' ya volvió a "Todos los archivos")
        if folder_selected and self._current.kind == SourceKind.FOLDER:
            self.source_selected.emit(self._current)

    def current_source(self) -> GridSource:
        """Origen seleccionado ahora."""
        return self._current

    def select_collection(self, collection_id: int, *, emit: bool = True) -> None:
        """Selecciona una colección del usuario por su id (p. ej. la recién creada)."""
        source = self._collection_sources.get(collection_id)
        if source is not None:
            self.select_source(source, emit=emit)

    def show_source(self, source: GridSource) -> None:
        """Muestra un origen pedido desde fuera de la barra (la flecha «ver sus fotos» del
        inspector). Si tiene fila, se elige; si no (una palabra clave), la cuadrícula lo
        muestra y la barra se queda SIN fila marcada: pulsar cualquier fila, también la que
        estaba elegida, vuelve a ella. Se recuerda al cerrar el catálogo, como una fila."""
        if source in self._items or source in self._folder_items or source in self._collection_items:
            self.select_source(source, emit=True)
            return
        self._clear_other_selections(None)
        self._current = source
        self._update_unclassified_row()  # «Sin clasificar» deja de estar elegida
        self.source_selected.emit(source)

    def select_source(self, source: GridSource, *, emit: bool = True) -> None:
        """Selecciona la fila de un origen (p. ej. al abrir un catálogo).

        Si la fila está dentro de una carpeta plegada, se despliegan sus carpetas padre.

        Args:
            source: Origen a seleccionar. Si no hay ninguna fila con él, no hace nada.
            emit: Si es False, no se emite 'source_selected' (el que llama ya sabe qué
                mostrar).
        """
        item = (
            self._items.get(source)
            or self._folder_items.get(source)
            or self._collection_items.get(source)
        )
        if item is None:
            return
        index = item.index()
        target = next((v for v in self._views if v.model() is index.model()), None)
        if target is None:
            return
        # Que se vea: se despliegan sus carpetas padre
        parent = index.parent()
        while parent.isValid():
            target.setExpanded(parent, True)
            parent = parent.parent()
        # Antes de marcarla: si es «Sin clasificar» (oculta sin elementos), que se vea
        self._current = source
        self._update_unclassified_row()
        # Se quitan las demás selecciones y se marca esta, sin avisar a nadie todavía
        self._clear_other_selections(target)
        with _signals_blocked(target.selectionModel()):
            target.setCurrentIndex(index)
        target.viewport().update()  # el bloqueo de señales impide el repintado automático
        if emit:
            self.source_selected.emit(source)

    def reset(self) -> None:
        """Vuelve al estado inicial (catálogo cerrado): sin contadores ni carpetas.

        Lo desplegado se olvida: es de otro catálogo.
        """
        self._current = ALL_ITEMS  # así 'set_folder_tree' no intenta volver a una carpeta
        self.set_counts({})
        self._expanded.clear()
        self._known_locations.clear()
        self.set_folder_tree(())
        self._expanded_sets.clear()
        self.set_collection_tree(())
        self.select_source(ALL_ITEMS, emit=False)

    # -------------------------------------------------------------------------
    # Árbol de carpetas
    # -------------------------------------------------------------------------

    def _add_folder_children(
        self,
        parent_item: QStandardItem,
        location: LocationNode,
        children: tuple[FolderNode, ...],
        foreground: QBrush | None,
    ) -> None:
        """Añade (recursivamente) las subcarpetas de una carpeta."""
        for node in children:
            source = self._source_for(location.location_id, node.relative_path)
            item = self._make_item(node.name, source, self._count_of(node))
            self._set_icon(item, "folder")
            # Ruta completa con el separador del sistema (barra invertida en Windows)
            full_path = str(Path(location.absolute_path) / node.relative_path)
            item.setToolTip(full_path)
            item.setData(full_path, _ROLE_PATH)
            item.setData(location.is_online, _ROLE_ONLINE)
            if foreground is not None:
                item.setForeground(foreground)
            self._folder_items[source] = item
            parent_item.appendRow(item)
            self._add_folder_children(item, location, node.children, foreground)

    def _source_for(self, location_id: int, relative_path: str) -> GridSource:
        """Origen de una carpeta, con la opción actual de incluir o no las subcarpetas."""
        return folder_source(
            location_id, relative_path, include_subfolders=self._include_subfolders
        )

    def _count_of(self, node: FolderNode) -> int:
        """Contador de una carpeta: con sus subcarpetas o solo lo suyo, según la opción."""
        return node.count if self._include_subfolders else node.direct_count

    def _show_folder_menu(self, position: QPoint) -> None:
        """Menú contextual de una carpeta (o de una ubicación) del árbol."""
        view = self._folders_view
        index = view.indexAt(position)
        if not index.isValid() or index.data(ROLE_SOURCE) is None:
            return  # p. ej. el texto "Ninguna carpeta"
        source: GridSource = index.data(ROLE_SOURCE)
        path = index.data(_ROLE_PATH)
        online = bool(index.data(_ROLE_ONLINE))

        menu = QMenu(view)
        sync_action = menu.addAction("Sincronizar carpeta")
        reveal_action = menu.addAction(f"Mostrar en {FILE_MANAGER_NAME}")
        menu.addSeparator()
        remove_action = menu.addAction("Quitar archivos ausentes del catálogo...")
        # Siempre activa, también con el disco desconectado: no toca el disco (sirve, p. ej.,
        # para quitar un disco que ya no existe)
        remove_folder_action = menu.addAction("Quitar del catálogo...")
        if not online:
            # Con el disco desconectado no hay nada que leer ni que mostrar, y no se sabe
            # si los archivos siguen ahí (no se pueden quitar los ausentes)
            for action in (sync_action, reveal_action, remove_action):
                action.setEnabled(False)
            menu.addSeparator()
            note = menu.addAction("(ubicación desconectada)")
            note.setEnabled(False)

        chosen = menu.exec(view.viewport().mapToGlobal(position))
        if chosen is sync_action:
            self.sync_folder_requested.emit(path)
        elif chosen is reveal_action:
            self.reveal_folder_requested.emit(path)
        elif chosen is remove_action and source.location_id is not None:
            self.remove_missing_requested.emit(source.location_id, source.folder)
        elif chosen is remove_folder_action and source.location_id is not None:
            name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            self.remove_folder_requested.emit(source.location_id, source.folder, name)

    def _on_folder_expanded(self, index: QModelIndex) -> None:
        source = index.data(ROLE_SOURCE)
        if source is not None:
            self._expanded.add(source)
        self._update_open_icon(self._folders_model, index, True)

    def _on_folder_collapsed(self, index: QModelIndex) -> None:
        self._expanded.discard(index.data(ROLE_SOURCE))
        self._update_open_icon(self._folders_model, index, False)

    # -------------------------------------------------------------------------
    # Colecciones del usuario
    # -------------------------------------------------------------------------

    def _add_user_collections(self, parent: QStandardItem, nodes: tuple[CollectionNode, ...]) -> None:
        """Añade (recursivamente) los conjuntos y colecciones del usuario.

        Los conjuntos no se pueden seleccionar (solo agrupan, como en Lightroom); las
        colecciones (estáticas e inteligentes) muestran sus archivos al pulsarlas. Cada
        tipo lleva su icono, y el tooltip dice qué es (y, en las inteligentes, sus reglas).
        Una inteligente cuyas reglas no se pueden leer se muestra, sin poder pulsarse, para
        poder editarla o eliminarla desde su menú.
        """
        for node in nodes:
            tooltip = f"{_KIND_NAMES.get(node.kind, 'Colección')}\n{node.path_name}"
            if node.kind == KIND_SET:
                item = self._make_item(node.name, None, None)
                self._set_icon(item, "set")
                item.setEnabled(True)  # no seleccionable, pero no gris: tiene su menú
            elif node.kind == KIND_SMART and node.rules is None:
                item = self._make_item(node.name, None, None)
                self._set_icon(item, "smart")
                item.setEnabled(True)
                item.setForeground(
                    QBrush(self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
                )
                tooltip += f"\n\nNo se pueden leer sus reglas: {node.rules_error}\nEdítala para corregirlas."
            else:
                if node.kind == KIND_SMART:
                    source = smart_collection_source(node.id, node.rules)
                    icon_key = "smart"
                    tooltip += "\n\n" + describe_rules(node.rules)
                else:
                    source = collection_source(node.id)
                    icon_key = "collection"
                item = self._make_item(node.name, source, node.count)
                self._set_icon(item, icon_key)
                self._collection_items[source] = item
                self._collection_sources[node.id] = source
            item.setData(node.id, _ROLE_COLLECTION_ID)
            item.setData(node.kind, _ROLE_COLLECTION_KIND)
            item.setToolTip(tooltip)
            parent.appendRow(item)
            self._add_user_collections(item, node.children)

    def _on_collection_double_clicked(self, index: QModelIndex) -> None:
        if index.data(_ROLE_COLLECTION_KIND) == KIND_SMART:
            self.edit_smart_collection_requested.emit(index.data(_ROLE_COLLECTION_ID))

    def _restore_expanded_sets(self, index: QModelIndex) -> None:
        """Vuelve a desplegar (recursivamente) los conjuntos que estaban desplegados."""
        if index.data(_ROLE_COLLECTION_ID) in self._expanded_sets:
            self._collections_view.setExpanded(index, True)
        model = self._collections_model
        for row in range(model.rowCount(index)):
            self._restore_expanded_sets(model.index(row, 0, index))

    def _on_collection_expanded(self, index: QModelIndex) -> None:
        self._update_open_icon(self._collections_model, index, True)
        collection_id = index.data(_ROLE_COLLECTION_ID)
        if collection_id is not None:
            self._expanded_sets.add(collection_id)
        elif not index.parent().isValid():
            # Grupo del sistema de primer nivel ("Clasificación", "Etiqueta")
            self._expanded_system.add(index.data(Qt.ItemDataRole.DisplayRole))

    def _on_collection_collapsed(self, index: QModelIndex) -> None:
        self._update_open_icon(self._collections_model, index, False)
        collection_id = index.data(_ROLE_COLLECTION_ID)
        if collection_id is not None:
            self._expanded_sets.discard(collection_id)
        else:
            self._expanded_system.discard(index.data(Qt.ItemDataRole.DisplayRole))

    def _show_collection_menu(self, position: QPoint) -> None:
        """Menú contextual de la sección Colecciones.

        - Sobre una colección del usuario: renombrar y eliminar.
        - Sobre una colección inteligente: además, editar sus reglas.
        - Sobre un conjunto: además, crear dentro de él un conjunto, una colección o una
          colección inteligente.
        - En un hueco vacío: crear en el primer nivel.
        - Sobre una colección del sistema: nada (no se pueden cambiar).
        """
        view = self._collections_view
        index = view.indexAt(position)
        collection_id = index.data(_ROLE_COLLECTION_ID) if index.isValid() else None
        if index.isValid() and collection_id is None:
            return  # colección del sistema

        menu = QMenu(view)
        if collection_id is None:
            self._add_create_actions(menu, None)
        else:
            name = index.data(Qt.ItemDataRole.DisplayRole)
            kind = index.data(_ROLE_COLLECTION_KIND)
            if kind == KIND_SET:
                self._add_create_actions(menu, collection_id)
                menu.addSeparator()
            elif kind == KIND_SMART:
                edit_action = menu.addAction(self._icons["smart:menu"], "Editar colección inteligente...")
                edit_action.triggered.connect(
                    lambda _checked=False: self.edit_smart_collection_requested.emit(collection_id)
                )
                menu.addSeparator()
            menu.addAction(
                "Renombrar...",
                lambda: self.rename_collection_requested.emit(collection_id, name),
            )
            menu.addAction(
                "Eliminar...",
                lambda: self.delete_collection_requested.emit(collection_id, name, kind),
            )
        menu.exec(view.viewport().mapToGlobal(position))

    # -------------------------------------------------------------------------
    # Soltar tarjetas de la cuadrícula sobre una colección
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Arrastrar y soltar sobre el árbol de colecciones (su 'viewport').

        Solo se aceptan tarjetas de la cuadrícula (formato MEDIA_IDS_MIME) y solo sobre una
        colección ESTÁTICA del usuario. Mientras se arrastra, la colección de debajo se
        resalta.
        """
        if watched is not self._collections_view.viewport():
            return super().eventFilter(watched, event)

        event_type = event.type()
        if event_type == QEvent.Type.DragEnter:
            if event.mimeData().hasFormat(MEDIA_IDS_MIME):
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            else:
                event.ignore()
            return True

        if event_type == QEvent.Type.DragMove:
            item = self._drop_item_at(event.position().toPoint())
            self._set_drop_target(item)
            if item is not None:
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            else:
                event.ignore()
            return True

        if event_type == QEvent.Type.DragLeave:
            self._clear_drop_target()
            return True

        if event_type == QEvent.Type.Drop:
            item = self._drop_item_at(event.position().toPoint())
            self._clear_drop_target()
            drag = decode_media_ids(event.mimeData())
            if item is None or drag is None:
                event.ignore()
                return True
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.media_dropped.emit(item.data(_ROLE_COLLECTION_ID), drag)
            return True

        return super().eventFilter(watched, event)

    def _drop_item_at(self, position: QPoint) -> QStandardItem | None:
        """Colección estática del usuario bajo el ratón, o None si no hay ninguna."""
        index = self._collections_view.indexAt(position)
        if not index.isValid() or index.data(_ROLE_COLLECTION_KIND) != KIND_STATIC:
            return None
        return self._collections_model.itemFromIndex(index)

    def _set_drop_target(self, item: QStandardItem | None) -> None:
        """Resalta la colección sobre la que se soltarían las tarjetas."""
        if item is self._drop_target:
            return
        self._clear_drop_target()
        if item is not None:
            highlight = QColor(self.palette().color(QPalette.ColorRole.Highlight))
            highlight.setAlpha(110)
            item.setData(QBrush(highlight), Qt.ItemDataRole.BackgroundRole)
            self._drop_target = item

    def _clear_drop_target(self) -> None:
        """Quita el resaltado de la colección destino (si lo había)."""
        if self._drop_target is not None:
            try:
                self._drop_target.setData(None, Qt.ItemDataRole.BackgroundRole)
            except RuntimeError:
                pass  # la fila ya no existe (se reconstruyó el árbol)
            self._drop_target = None

    # -------------------------------------------------------------------------
    # Selección (una sola en toda la barra)
    # -------------------------------------------------------------------------

    def _on_selection_changed(self, view: SidebarTreeView, selected: QItemSelection) -> None:
        """El usuario (ratón o teclado) ha seleccionado una fila en uno de los árboles."""
        indexes = selected.indexes()
        if not indexes:
            return  # solo se ha quitado una selección (p. ej. al limpiar otro árbol)
        source = indexes[0].data(ROLE_SOURCE)
        if source is None:
            return
        self._clear_other_selections(view)
        if source != self._current:
            self._current = source
            self._update_unclassified_row()  # deja de estar elegida: quizá se oculta
            self.source_selected.emit(source)

    def _clear_other_selections(self, keep: SidebarTreeView | None) -> None:
        """Quita la selección de todos los árboles menos 'keep' (None = de todos)."""
        for other in self._views:
            if other is keep:
                continue
            with _signals_blocked(other.selectionModel()):
                other.selectionModel().clearSelection()
            other.viewport().update()
