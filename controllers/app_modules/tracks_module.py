"""Módulo Tracks: los recorridos GPS (archivos GPX; biblioteca Tracks).

Es el quinto módulo (botón 'btn_tracks'). Tiene su barra lateral izquierda
('LibrarySidebar': «Biblioteca - Tracks», «Carpetas» y «Fechas») y usa el inspector, la
cuadrícula y el mapa comunes. Empieza en el MAPA: es donde un track se ve como lo que es
(los del origen elegido, con su contorno; el detalle del elegido llega con el paso 4.3 de
docs/MAPA.md).

Qué hace este módulo (la barra no sabe nada de la base de datos), como 'ImageModule':
    - Pasa al 'ModuleHost' lo que se elige en la barra ('source_selected').
    - 'refresh' lee en segundo plano los contadores de la biblioteca, el árbol de carpetas
      con tracks y los años, meses y días ('timeline.fetch_timeline': por la hora LOCAL
      de salida, que el extractor guarda en 'content_created_at').
    - Lo desplegado y la fila elegida, guardados por catálogo ('save_state' /
      'restore_state'; el 'ModuleHost' los escribe en settings.json).

Lo propio de los tracks:
    - Vistas: cuadrícula y mapa (sin vista individual: un track no tiene una imagen que
      ampliar). Su mapa solo mira, como el del Catálogo (no se ubican fotos en él).
    - Orden: por fecha, distancia, desnivel y duración, además de los del archivo
      ('grid_orders.TRACK_SORT_FIELDS'); de partida, los más recientes primero.
    - Filtros: el tipo «track» en «Atributos»; en «Metadatos», fecha, actividad y programa
      con el que se creó.

Los textos de la barra están aquí ('_TEXTS').

1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.2): sustituye al módulo provisional.
"""

__version__ = "1.0.0"
__all__ = ["TracksModule"]

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
from controllers.app_modules.center_views import CenterView
from core.catalog.folder_tree import fetch_folder_tree
from core.catalog.grid_orders import TRACK_SORT_FIELDS, GridOrder
from core.catalog.grid_source import GridSource, library_source, quick_source
from core.catalog.libraries import Library
from core.catalog.media_queries import count_grid_items
from core.catalog.media_types import MediaType
from core.catalog.timeline import fetch_timeline
from ui_helpers.helpers.mode_toolbar import MODE_TRACKS
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME, reveal_in_file_manager
from ui_helpers.sidebars.library_sidebar import LibrarySidebar, LibraryTexts

# Biblioteca del módulo y sus dos orígenes fijos (los mismos que crea la barra)
LIBRARY = Library.TRACKS.value
ALL_TRACKS = library_source(LIBRARY)
TRACKS_QUICK = quick_source(LIBRARY)

# Textos de la barra
_TEXTS = LibraryTexts(
    library_title="Biblioteca - Tracks",
    all_title="Todos los tracks",
    all_tooltip="Todos los recorridos GPS (archivos GPX) del catálogo",
    quick_tooltip=(
        "Selección rápida\n\nLos tracks marcados con el círculo de su tarjeta (esquina\n"
        "superior derecha). Es la misma del Catálogo: aquí solo se ven los tracks."
    ),
)


def _fetch_sidebar_data(conn: Any) -> tuple[int, int, tuple, tuple]:
    """Lo que necesita la barra: el número de tracks y el de su selección rápida, el árbol
    de carpetas (solo con tracks) y los años con sus meses y días.

    Una sola función (una sola visita al hilo de la base de datos) para que todo llegue a
    la vez (así se sabe si la carpeta o la fecha elegida sigue existiendo).
    """
    counts = count_grid_items(conn, [ALL_TRACKS, TRACKS_QUICK])
    return (
        counts.get(ALL_TRACKS, 0),
        counts.get(TRACKS_QUICK, 0),
        fetch_folder_tree(conn, LIBRARY),
        fetch_timeline(conn, LIBRARY).values,
    )


class TracksModule(AppModule):
    """Módulo Tracks (ver el docstring del archivo)."""

    key = MODE_TRACKS
    title = "Tracks"
    icon = AppIcons.LIB_TRACKS

    def __init__(
        self, context: ModuleContext, *, button: QToolButton, parent: QObject | None = None
    ) -> None:
        """Crea su barra lateral (todavía sin catálogo: ver 'attach')."""
        super().__init__(context, button=button, parent=parent)
        self.sidebar = LibrarySidebar(LIBRARY, _TEXTS)
        # El orden de sus secciones, si se ven y si están plegadas: como las tenga el
        # usuario en este modo
        if context.section_layout is not None:
            self.sidebar.bind_layout(context.section_layout, self.key)
        self.sidebar.source_selected.connect(self.source_selected)
        self.sidebar.reveal_folder_requested.connect(self._on_reveal_folder)
        # Carpetas con o sin sus subcarpetas: la misma opción que el Catálogo
        self.sidebar.set_include_subfolders(self._show_subfolder_items())
        # Gestor de la base de datos (None sin catálogo) y generación (descarta
        # respuestas de un catálogo ya cerrado), como en los demás módulos
        self._db: Any = None
        self._generation = 0

    # -------------------------------------------------------------------------
    # Interfaz
    # -------------------------------------------------------------------------

    def sidebar_page(self) -> QWidget:
        """Su barra lateral."""
        return self.sidebar

    def current_source(self) -> GridSource | None:
        """Lo elegido en la barra («Todos los tracks», una carpeta, una fecha...)."""
        return self.sidebar.current_source()

    def views(self) -> tuple[CenterView, ...]:
        """Cuadrícula y mapa (en ese orden en la barra inferior, como en los demás)."""
        return (CenterView.GRID, CenterView.MAP)

    def default_view(self) -> CenterView:
        """Empieza en el mapa."""
        return CenterView.MAP

    def filter_media_types(self) -> tuple[str, ...]:
        """Solo hay tracks."""
        return (MediaType.TRACK,)

    def filter_metadata_fields(self) -> tuple[str, ...]:
        """Columnas de partida de «Metadatos»: la fecha, la actividad y el programa."""
        return ("captured_at", "track_activity", "track_creator_app")

    def sort_fields(self) -> tuple[str, ...]:
        """Los campos de orden de los tracks."""
        return TRACK_SORT_FIELDS

    def default_order(self) -> GridOrder:
        """Por fecha, los más recientes primero."""
        return GridOrder("captured_at", descending=True)

    def show_source(self, source: GridSource) -> None:
        """Lo pide otro (p. ej. el inspector): se elige en la barra, si tiene fila."""
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
        """Relee en segundo plano los contadores, las carpetas y las fechas."""
        if self._db is None:
            return
        self._db.execute_async(
            _fetch_sidebar_data,
            on_result=partial(self._on_sidebar_data, self._generation),
            on_error=lambda error: logger.warning(
                f"No se pudo leer la barra del módulo Tracks: {error}"
            ),
        )

    def save_state(self) -> dict:
        """Lo desplegado y la fila elegida de la barra (ver 'LibrarySidebar.save_state')."""
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
        """Pone los contadores y los árboles (si siguen siendo del catálogo abierto).

        Si la carpeta o la fecha elegida ya no existe (se borró, o ya no tiene tracks), se
        vuelve a «Todos los tracks».
        """
        if generation != self._generation or self._db is None:
            return
        count, quick_count, folders, dates = data
        self.sidebar.set_library_count(count, quick_count)
        self.sidebar.set_folder_tree(folders)
        self.sidebar.set_date_tree(dates)
        current = self.sidebar.current_source()
        if current != ALL_TRACKS and not self.sidebar.has_source(current):
            self.sidebar.select_source(ALL_TRACKS)
