"""Módulo Catálogo: todos los archivos del catálogo, sean del tipo que sean.

Es el primer módulo (botón 'btn_catalog'). Su barra lateral es 'CatalogSidebar' (secciones
CATÁLOGO, CARPETAS y COLECCIONES), que ya existe en el .ui ('widget_catalog_sidebar',
dentro de 'page_catalog_default'), y la cuadrícula muestra lo que se elige en ella.

Qué hace este módulo (antes estaba repartido por 'main_window_controller.py'):
    - Pasa al 'ModuleHost' lo que se elige en la barra ('source_selected').
    - Rellena la barra: contadores de las filas, árbol de carpetas y árbol de colecciones
      (todo en segundo plano, en 'refresh').
    - Colecciones del usuario: crea y conecta 'CollectionActions' (barra + menú de la
      cuadrícula + base de datos).
    - Opción "Mostrar los elementos de las subcarpetas" (Opciones > Catálogo).
    - Lo desplegado y la fila elegida, guardados por catálogo ('save_state' /
      'restore_state'; el 'ModuleHost' los escribe en settings.json).

Qué NO hace: las operaciones con el catálogo entero que se piden desde su barra (añadir,
sincronizar o mostrar una carpeta, quitar ausentes, vaciar la selección rápida) siguen en
el controlador principal, que conecta esas señales de 'CatalogSidebar' directamente.

Orden de la cuadrícula: todos los campos de 'grid_orders.py'; parte de «Nombre» (con tipos
mezclados, la hora de captura dejaría al final todo lo que no la tiene).

1.1.0 'sort_fields' y 'default_order' (orden de partida: «Nombre»).
"""

__version__ = "1.1.0"
__all__ = ["CatalogModule"]

# Librerías estándar
from functools import partial
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QToolButton, QWidget

# Módulos del proyecto
from config.app_constants import SETTING_SHOW_SUBFOLDER_ITEMS, AppIcons
from controllers.app_modules.base import AppModule, ModuleContext
from controllers.collection_actions import CollectionActions
from core.catalog.folder_tree import LocationNode, fetch_folder_tree
from core.catalog.grid_orders import NAME_ORDER, SORT_FIELDS, GridOrder
from core.catalog.grid_source import GridSource, SourceKind
from core.catalog.media_queries import count_grid_items
from ui_helpers.helpers.mode_toolbar import MODE_CATALOG
from ui_helpers.sidebars.catalog_sidebar import CatalogSidebar


class CatalogModule(AppModule):
    """Módulo Catálogo (ver el docstring del archivo)."""

    key = MODE_CATALOG
    title = "Catálogo"
    # 'getattr': si el icono no está en 'AppIcons', el botón muestra su inicial
    icon = getattr(AppIcons, "LIB_ALL", None)

    def __init__(
        self,
        context: ModuleContext,
        *,
        button: QToolButton,
        sidebar: CatalogSidebar,
        page: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Conecta la barra lateral del catálogo (todavía sin catálogo: ver 'attach').

        Args:
            context: Lo que comparte la ventana principal.
            button: Botón de la toolbar ('btn_catalog').
            sidebar: Barra lateral del catálogo ('widget_catalog_sidebar' del .ui).
            page: Página del 'stacked_widget_sidebar_catalog' que la contiene
                ('page_catalog_default' del .ui).
            parent: Objeto padre.
        """
        super().__init__(context, button=button, parent=parent)
        self.sidebar = sidebar
        self._page = page

        # Gestor de la base de datos (None mientras no haya catálogo abierto)
        self._db: Any = None
        # Sube con cada 'attach' y 'detach': una respuesta de la base de datos que llega
        # de un catálogo anterior (abierto y cerrado deprisa) se descarta
        self._generation = 0

        # Lo que se elige en la barra se pasa tal cual al 'ModuleHost' (señal a señal)
        sidebar.source_selected.connect(self.source_selected)

        # Colecciones del usuario: barra lateral + menú de la cuadrícula + base de datos
        self.collection_actions = CollectionActions(
            context.window,
            sidebar,
            context.grid_view,
            context.grid_model,
            context.grid_actions,
            context.message_box,
        )

        # Carpetas con o sin sus subcarpetas (Opciones > Catálogo). Aún no hay catálogo
        # abierto, así que no se recarga nada
        sidebar.set_include_subfolders(self._show_subfolder_items())

    # -------------------------------------------------------------------------
    # Interfaz
    # -------------------------------------------------------------------------

    def sidebar_page(self) -> QWidget:
        """La página del .ui que contiene 'CatalogSidebar'."""
        return self._page

    def current_source(self) -> GridSource | None:
        """Lo elegido en la barra lateral.

        Una colección inteligente del usuario recién restaurada aún no tiene sus reglas
        (llegan con el árbol de colecciones): mientras tanto, el módulo no decide (None),
        para no pedir a la cuadrícula un origen incompleto.
        """
        source = self.sidebar.current_source()
        if source.kind == SourceKind.SMART and source.rules is None:
            return None
        return source

    def sort_fields(self) -> tuple[str, ...]:
        """Todos los campos de orden (sirven para cualquier tipo de archivo)."""
        return tuple(SORT_FIELDS)

    def default_order(self) -> GridOrder:
        """Por nombre, ascendente."""
        return NAME_ORDER

    # -------------------------------------------------------------------------
    # Ciclo de vida del catálogo
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Path) -> None:
        """Empieza a trabajar con un catálogo recién abierto (pide el árbol de colecciones)."""
        self._db = db
        self._generation += 1
        self.collection_actions.attach(db, catalog_dir)

    def detach(self) -> None:
        """Olvida el catálogo y deja la barra vacía ("Todos los archivos", sin contadores)."""
        self._db = None
        self._generation += 1
        self.collection_actions.detach()
        self.sidebar.reset()

    def refresh(self) -> None:
        """Relee en segundo plano los contadores, el árbol de carpetas y el de colecciones.

        Si los árboles no han cambiado, la barra no los reconstruye.
        """
        if self._db is None:
            return
        generation = self._generation
        # 'count_grid_items(conn, sources)': la conexión la pone el gestor
        self._db.execute_async(
            count_grid_items,
            self.sidebar.sources(),
            on_result=partial(self._on_counts, generation),
            on_error=lambda error: logger.warning(
                f"No se pudieron contar los elementos de la barra lateral: {error}"
            ),
        )
        # Árbol de carpetas (ya trae los contadores de cada carpeta)
        self._db.execute_async(
            fetch_folder_tree,
            on_result=partial(self._on_folder_tree, generation),
            on_error=lambda error: logger.warning(
                f"No se pudo leer el árbol de carpetas: {error}"
            ),
        )
        # Colecciones del usuario (también con sus contadores)
        self.collection_actions.refresh()

    def save_state(self) -> dict:
        """Lo desplegado y la fila elegida en la barra (ver 'CatalogSidebar.save_state')."""
        return self.sidebar.save_state()

    def restore_state(self, state: object) -> None:
        """Recupera lo desplegado y la fila elegida (puede emitir 'source_selected')."""
        self.sidebar.restore_state(state)

    def apply_settings(self, changed: set[str]) -> None:
        """Si ha cambiado la opción de las subcarpetas, la barra rehace el árbol.

        Si hay una carpeta elegida, la barra emite su origen nuevo y la cuadrícula se
        recarga sola.
        """
        if SETTING_SHOW_SUBFOLDER_ITEMS in changed:
            self.sidebar.set_include_subfolders(self._show_subfolder_items())

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_counts(self, generation: int, counts: dict) -> None:
        """Pone los contadores en la barra (si siguen siendo del catálogo abierto)."""
        if generation == self._generation and self._db is not None:
            self.sidebar.set_counts(counts)

    def _on_folder_tree(self, generation: int, locations: tuple[LocationNode, ...]) -> None:
        """Pone el árbol de carpetas en la barra (si sigue siendo del catálogo abierto)."""
        if generation == self._generation and self._db is not None:
            self.sidebar.set_folder_tree(locations)

    def _show_subfolder_items(self) -> bool:
        """Lee la opción "Mostrar los elementos de las subcarpetas" (por defecto, activada)."""
        value = self.context.config.get(SETTING_SHOW_SUBFOLDER_ITEMS, True)
        if not isinstance(value, bool):
            logger.warning(
                f"'{SETTING_SHOW_SUBFOLDER_ITEMS}' no válido en la configuración: "
                f"{value!r}. Se usa el valor por defecto (activada)."
            )
            return True
        return value
