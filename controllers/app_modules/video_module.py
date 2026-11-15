"""Módulo Vídeo: las películas y series (biblioteca Vídeos).

Es el tercer módulo (botón 'btn_video'). Por ahora, con la barra común de los módulos de
una biblioteca ('LibraryModule': «Biblioteca - Vídeos», «Carpetas» y «Fechas»); su
navegación propia (películas con cartel, directores y actores) llegará con el paso A.6 de
docs/PENDIENTE.md. Los vídeos del móvil no están aquí: son de la biblioteca Imágenes y se
ven en el módulo Imagen.

Decidido por el autor el 15/11/2026:
    - Vistas: cuadrícula y vista individual (sin mapa: las películas no tienen ubicación).
    - Orden: los campos de siempre más «Duración»; de partida, por nombre.
    - Filtros: el tipo «vídeo» en «Atributos»; en «Metadatos», fecha y palabras clave.
    - Textos de la barra, provisionales hasta que se decidan los nombres ('_TEXTS').

1.0.0 Primera versión (15/11/2026): sustituye al módulo provisional.
"""

__version__ = "1.0.0"
__all__ = ["VideoModule"]

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.library_module import LibraryModule
from core.catalog.grid_orders import NAME_ORDER, VIDEO_AUDIO_SORT_FIELDS, GridOrder
from core.catalog.libraries import Library
from core.catalog.media_types import MediaType
from ui_helpers.helpers.mode_toolbar import MODE_VIDEO
from ui_helpers.sidebars.library_sidebar import LibraryTexts

# Textos de la barra (provisionales)
_TEXTS = LibraryTexts(
    library_title="Biblioteca - Vídeos",
    all_title="Todos los vídeos",
    all_tooltip="Todas las películas y series del catálogo (biblioteca Vídeos)",
    quick_tooltip=(
        "Selección rápida\n\nLos vídeos marcados con el círculo de su tarjeta (esquina\n"
        "superior derecha). Es la misma del Catálogo: aquí solo se ven los de esta biblioteca."
    ),
)


class VideoModule(LibraryModule):
    """Módulo Vídeo (ver el docstring del archivo)."""

    key = MODE_VIDEO
    title = "Vídeo"
    icon = AppIcons.LIB_VIDEO
    library = Library.VIDEO.value
    texts = _TEXTS

    def views(self) -> tuple[CenterView, ...]:
        """Cuadrícula y vista individual."""
        return (CenterView.GRID, CenterView.SINGLE)

    def filter_media_types(self) -> tuple[str, ...]:
        """Solo hay vídeos."""
        return (MediaType.VIDEO,)

    def filter_metadata_fields(self) -> tuple[str, ...]:
        """Columnas de partida de «Metadatos»: la fecha y las palabras clave."""
        return ("captured_at", "keyword")

    def sort_fields(self) -> tuple[str, ...]:
        """Los de siempre más «Duración»."""
        return VIDEO_AUDIO_SORT_FIELDS

    def default_order(self) -> GridOrder:
        """Por nombre."""
        return NAME_ORDER
