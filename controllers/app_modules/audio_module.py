"""Módulo Audio: la música (biblioteca Música).

Es el cuarto módulo (botón 'btn_audio'). Por ahora, con la barra común de los módulos de
una biblioteca ('LibraryModule': «Biblioteca - Música», «Carpetas» y «Fechas»); su
navegación propia (artistas, álbumes y géneros) y la vista de lista estilo Mp3tag llegarán
con los pasos A.6 y A.5 de docs/PENDIENTE.md.

Decidido por el autor el 15/11/2026:
    - Vistas: solo la cuadrícula (la vista individual de una canción no tendría qué
      enseñar; la de lista, más adelante).
    - Orden: los campos de siempre más «Duración»; de partida, por nombre.
    - Filtros: el tipo «audio» en «Atributos»; en «Metadatos», fecha y palabras clave.
    - Textos de la barra, provisionales hasta que se decidan los nombres ('_TEXTS').

1.0.0 Primera versión (15/11/2026): sustituye al módulo provisional.
"""

__version__ = "1.0.0"
__all__ = ["AudioModule"]

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.library_module import LibraryModule
from core.catalog.grid_orders import NAME_ORDER, VIDEO_AUDIO_SORT_FIELDS, GridOrder
from core.catalog.libraries import Library
from core.catalog.media_types import MediaType
from ui_helpers.helpers.mode_toolbar import MODE_AUDIO
from ui_helpers.sidebars.library_sidebar import LibraryTexts

# Textos de la barra (provisionales)
_TEXTS = LibraryTexts(
    library_title="Biblioteca - Música",
    all_title="Toda la música",
    all_tooltip="Toda la música del catálogo (biblioteca Música)",
    quick_tooltip=(
        "Selección rápida\n\nLas canciones marcadas con el círculo de su tarjeta (esquina\n"
        "superior derecha). Es la misma del Catálogo: aquí solo se ven las de esta biblioteca."
    ),
)


class AudioModule(LibraryModule):
    """Módulo Audio (ver el docstring del archivo)."""

    key = MODE_AUDIO
    title = "Audio"
    icon = AppIcons.LIB_AUDIO
    library = Library.AUDIO.value
    texts = _TEXTS

    def views(self) -> tuple[CenterView, ...]:
        """Solo la cuadrícula."""
        return (CenterView.GRID,)

    def filter_media_types(self) -> tuple[str, ...]:
        """Solo hay audio."""
        return (MediaType.AUDIO,)

    def filter_metadata_fields(self) -> tuple[str, ...]:
        """Columnas de partida de «Metadatos»: la fecha y las palabras clave."""
        return ("captured_at", "keyword")

    def sort_fields(self) -> tuple[str, ...]:
        """Los de siempre más «Duración»."""
        return VIDEO_AUDIO_SORT_FIELDS

    def default_order(self) -> GridOrder:
        """Por nombre."""
        return NAME_ORDER
