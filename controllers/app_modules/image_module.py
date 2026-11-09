"""Módulo Imagen: las fotos y los vídeos del móvil (biblioteca Imagen).

Es el segundo módulo (botón 'btn_image'). De momento tiene su barra lateral izquierda
('ImageSidebar': «Todas las imágenes» y el árbol de PALABRAS CLAVE, paso K3) y usa el
inspector y la cuadrícula comunes. Llegarán: línea de tiempo (año → mes → día), vista
individual, y la edición de palabras clave y ubicación en su panel derecho (K4).

Qué hace este módulo (la barra no sabe nada de la base de datos):
    - Pasa al 'ModuleHost' lo que se elige en la barra ('source_selected').
    - 'refresh' lee en segundo plano el contador de «Todas las imágenes» y el árbol de
      palabras clave con sus recuentos ('keywords.fetch_keyword_tree').
    - Lo desplegado y la fila elegida, guardados por catálogo ('save_state' /
      'restore_state'; el 'ModuleHost' los escribe en settings.json). Lo desplegado del
      árbol con casillas del inspector ya no es de este módulo: lo guarda el inspector.

1.12.0 'filter_metadata_fields': Fecha de captura, Modelo de la cámara y Objetivo, como
       Lightroom (decidido por el autor el 09/11/2026). Paso A.3.
1.11.0 'filter_media_types': foto y vídeo (lo que entra en Imagen). Paso A.3.
1.10.0 'show_source': una palabra clave pedida sin biblioteca se limita a Imagen (la
       flecha del inspector la pide sin biblioteca; paso A.2).
1.9.0 Lo desplegado del árbol del inspector lo guarda 'InspectorController' (el inspector
      es común a todos los módulos).
1.8.0 'sort_fields' y 'default_order' (orden de partida: «Hora de captura»).
1.7.0 'show_source': la flecha «ver sus fotos» del inspector elige la palabra en la barra.
1.6.0 «Selección rápida» de Imagen: su contador se lee con los demás.
1.5.0 Sección «Carpetas» de la barra: árbol con lo de Imagen ('fetch_folder_tree(conn,
      "image")'), opción de subcarpetas del Catálogo y «Mostrar en el Explorador».
1.4.0 La barra es solo para navegar: el menú del árbol y soltar tarjetas pasan al inspector.
1.3.0 Soltar tarjetas sobre una palabra del árbol se la asigna ('_on_media_dropped'; K4c-3).
1.2.0 El menú contextual del árbol pide los cambios con 'catalog_edit_requested' (K4c-2).
1.1.0 Guarda y recupera lo desplegado del árbol del inspector (clave
      'inspector_expanded_keywords'), para que se abra como se dejó.
"""

__version__ = "1.12.0"
__all__ = ["ImageModule"]

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
from core.catalog.folder_tree import fetch_folder_tree
from core.catalog.grid_orders import CAPTURE_TIME_ORDER, SORT_FIELDS, GridOrder
from core.catalog.grid_source import GridSource, SourceKind, keyword_source
from core.catalog.keywords import fetch_keyword_tree
from core.catalog.libraries import Library
from core.catalog.media_queries import count_grid_items
from core.catalog.media_types import MediaType
from ui_helpers.helpers.mode_toolbar import MODE_IMAGE
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME, reveal_in_file_manager
from ui_helpers.sidebars.image_sidebar import ALL_IMAGES, IMAGE_QUICK, LIBRARY, ImageSidebar


def _fetch_sidebar_data(conn: Any) -> tuple[int, int, tuple, tuple]:
    """Lo que necesita la barra: el número de imágenes y el de su selección rápida, el
    árbol de carpetas (solo con lo de Imagen) y el de palabras clave.

    Una sola función (una sola visita al hilo de la base de datos) para que todo llegue a
    la vez (así se sabe si la carpeta o la palabra elegida sigue existiendo).
    """
    counts = count_grid_items(conn, [ALL_IMAGES, IMAGE_QUICK])
    return (
        counts.get(ALL_IMAGES, 0),
        counts.get(IMAGE_QUICK, 0),
        fetch_folder_tree(conn, LIBRARY),
        fetch_keyword_tree(conn, LIBRARY),
    )


class ImageModule(AppModule):
    """Módulo Imagen (ver el docstring del archivo)."""

    key = MODE_IMAGE
    title = "Imagen"
    # 'getattr': si el icono no está en 'AppIcons', el botón muestra su inicial
    icon = getattr(AppIcons, "LIB_IMAGE", None)

    def __init__(
        self, context: ModuleContext, *, button: QToolButton, parent: QObject | None = None
    ) -> None:
        """Crea su barra lateral (todavía sin catálogo: ver 'attach')."""
        super().__init__(context, button=button, parent=parent)
        self.sidebar = ImageSidebar()
        self.sidebar.source_selected.connect(self.source_selected)
        self.sidebar.reveal_folder_requested.connect(self._on_reveal_folder)
        # Carpetas con o sin sus subcarpetas: la misma opción que el Catálogo
        self.sidebar.set_include_subfolders(self._show_subfolder_items())
        # Gestor de la base de datos (None sin catálogo) y generación (descarta
        # respuestas de un catálogo ya cerrado), como en 'CatalogModule'
        self._db: Any = None
        self._generation = 0

    # -------------------------------------------------------------------------
    # Interfaz
    # -------------------------------------------------------------------------

    def sidebar_page(self) -> QWidget:
        """Su barra lateral."""
        return self.sidebar

    def current_source(self) -> GridSource | None:
        """Lo elegido en la barra («Todas las imágenes» o una palabra clave)."""
        return self.sidebar.current_source()

    def filter_media_types(self) -> tuple[str, ...]:
        """Fotos y vídeos (los del móvil entran en Imagen)."""
        return (MediaType.PHOTO, MediaType.VIDEO)

    def filter_metadata_fields(self) -> tuple[str, ...]:
        """Columnas de partida de «Metadatos», como en Lightroom."""
        return ("captured_at", "camera_model", "lens_model")

    def sort_fields(self) -> tuple[str, ...]:
        """Todos los campos de orden (de momento; llegarán los propios de las fotos)."""
        return tuple(SORT_FIELDS)

    def default_order(self) -> GridOrder:
        """Por hora de captura, ascendente (como Lightroom)."""
        return CAPTURE_TIME_ORDER

    def show_source(self, source: GridSource) -> None:
        """Lo pide el inspector (flecha «ver sus fotos»): se elige en la barra, que lo
        muestra en la cuadrícula ('source_selected') y lo deja marcado. Una palabra pedida
        sin biblioteca se limita a Imagen (así es la fila de la barra)."""
        if source.kind == SourceKind.KEYWORD and source.keyword_id is not None and source.library is None:
            source = keyword_source(source.keyword_id, Library.IMAGE.value)
        self.sidebar.show_source(source)

    # -------------------------------------------------------------------------
    # Ciclo de vida del catálogo
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Path) -> None:
        """Empieza a trabajar con un catálogo recién abierto."""
        self._db = db
        self._generation += 1

    def detach(self) -> None:
        """Olvida el catálogo y deja la barra vacía."""
        self._db = None
        self._generation += 1
        self.sidebar.reset()

    def refresh(self) -> None:
        """Relee en segundo plano el contador y el árbol de palabras clave."""
        if self._db is None:
            return
        self._db.execute_async(
            _fetch_sidebar_data,
            on_result=partial(self._on_sidebar_data, self._generation),
            on_error=lambda error: logger.warning(
                f"No se pudo leer el árbol de palabras clave: {error}"
            ),
        )

    def save_state(self) -> dict:
        """Lo desplegado y la fila elegida de la barra (ver 'ImageSidebar.save_state')."""
        return self.sidebar.save_state()

    def restore_state(self, state: object) -> None:
        """Recupera lo desplegado de la barra y la fila elegida."""
        self.sidebar.restore_state(state)

    def apply_settings(self, changed: set[str]) -> None:
        """Si ha cambiado la opción de las subcarpetas, las «Carpetas» se rehacen (y, si hay
        una elegida, la cuadrícula se recarga)."""
        if SETTING_SHOW_SUBFOLDER_ITEMS in changed:
            self.sidebar.set_include_subfolders(self._show_subfolder_items())

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _show_subfolder_items(self) -> bool:
        """Opción «Mostrar los elementos de las subcarpetas» (por defecto, activada)."""
        value = self.context.config.get(SETTING_SHOW_SUBFOLDER_ITEMS, True)
        return value if isinstance(value, bool) else True

    def _on_reveal_folder(self, folder: str) -> None:
        """Menú de una carpeta > «Mostrar en el Explorador» (el Finder en macOS)."""
        if not Path(folder).is_dir():
            self.context.message_box.warning(
                f"La carpeta no existe (¿se ha movido, renombrado o borrado?):\n{folder}"
            )
            return
        if not reveal_in_file_manager(folder):
            self.context.message_box.warning(f"No se pudo abrir {FILE_MANAGER_NAME}:\n{folder}")

    def _on_sidebar_data(self, generation: int, data: tuple[int, int, tuple, tuple]) -> None:
        """Pone el contador y los árboles (si siguen siendo del catálogo abierto).

        Si la carpeta o la palabra elegida ya no existe (se borró, o ya no tiene
        imágenes), se vuelve a «Todas las imágenes».
        """
        if generation != self._generation or self._db is None:
            return
        count, quick_count, folders, tree = data
        self.sidebar.set_library_count(count, quick_count)
        self.sidebar.set_folder_tree(folders)
        self.sidebar.set_keyword_tree(tree)
        current = self.sidebar.current_source()
        if current != ALL_IMAGES and not self.sidebar.is_filtering() and not self.sidebar.has_source(current):
            self.sidebar.select_source(ALL_IMAGES)
