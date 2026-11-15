"""Módulo Tracks: los recorridos GPS (archivos GPX; biblioteca Tracks).

Es el quinto módulo (botón 'btn_tracks'). Tiene su barra lateral izquierda
('LibrarySidebar': «Biblioteca - Tracks», «Carpetas» y «Fechas») y usa el inspector, la
cuadrícula y el mapa comunes. Empieza en el MAPA: es donde un track se ve como lo que es
(los del origen elegido, con su contorno; el detalle del elegido llega con el paso 4.3 de
docs/MAPA.md).

Lo común con los demás módulos de una biblioteca (la barra, lo que se lee para ella, lo
guardado y el menú de las carpetas) está en 'LibraryModule' ('library_module.py'). Las
fechas de los tracks son las de la hora LOCAL de salida, que el extractor guarda en
'content_created_at'.

Lo propio de los tracks:
    - Vistas: cuadrícula y mapa (sin vista individual: un track no tiene una imagen que
      ampliar). Su mapa solo mira, como el del Catálogo (no se ubican fotos en él); debajo,
      la banda del perfil de elevación del track activo, y la tira de fotos empieza oculta
      ('map_options').
    - Orden: por fecha, distancia, desnivel y duración, además de los del archivo
      ('grid_orders.TRACK_SORT_FIELDS'); de partida, los más recientes primero.
    - Filtros: el tipo «track» en «Atributos»; en «Metadatos», fecha, actividad y programa
      con el que se creó.

Los textos de la barra están aquí ('_TEXTS').

1.2.0 Lo común con los demás módulos de una biblioteca pasa a 'LibraryModule' (sin
      cambiar lo que hace), para Vídeo y Audio.
1.1.0 'map_options': el perfil de elevación bajo el mapa y la tira de fotos oculta al
      principio (docs/MAPA.md, paso 5.3a).
1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.2): sustituye al módulo provisional.
"""

__version__ = "1.2.0"
__all__ = ["TracksModule"]

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.center_views import CenterView, MapOptions
from controllers.app_modules.library_module import LibraryModule
from core.catalog.grid_orders import TRACK_SORT_FIELDS, GridOrder
from core.catalog.libraries import Library
from core.catalog.media_types import MediaType
from ui_helpers.helpers.mode_toolbar import MODE_TRACKS
from ui_helpers.sidebars.library_sidebar import LibraryTexts

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


class TracksModule(LibraryModule):
    """Módulo Tracks (ver el docstring del archivo)."""

    key = MODE_TRACKS
    title = "Tracks"
    icon = AppIcons.LIB_TRACKS
    library = Library.TRACKS.value
    texts = _TEXTS

    def views(self) -> tuple[CenterView, ...]:
        """Cuadrícula y mapa (en ese orden en la barra inferior, como en los demás)."""
        return (CenterView.GRID, CenterView.MAP)

    def default_view(self) -> CenterView:
        """Empieza en el mapa."""
        return CenterView.MAP

    def map_options(self) -> MapOptions:
        """Su mapa solo mira; debajo, el perfil del track activo; la tira de fotos empieza
        oculta (docs/MAPA.md, paso 5.3a; D11)."""
        return MapOptions(show_profile=True, filmstrip_starts_visible=False)

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
