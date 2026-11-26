"""Módulo Audio: la música (biblioteca Música).

Es el cuarto módulo (botón 'btn_audio'). Su barra es la común de los módulos de una
biblioteca ('LibraryModule': «Biblioteca - Música» y «Carpetas»), sin «Fechas» y con dos
secciones propias (MUS 4.1; docs/MOD_MUSICA.md §7.2): «Artistas» (artista del álbum ▸
álbumes, por año) y «Años» (año ▸ álbumes), con los árboles de
'core/catalog/music_browse.py'. «Géneros» (MUS 4.2) y la vista de lista estilo Mp3tag
(GEN 18, MUS 5) llegarán después.

Decidido por el autor el 15/11/2026:
    - Vistas: la cuadrícula y, desde el 19/11/2026, la vista individual, para entrar y
      salir como en los demás módulos (doble clic o «adelante»; G, Esc o «atrás»). Hoy
      enseña el icono de música y el nombre; la carátula, cuando se lea (docs/MOD_MUSICA.md).
      La de lista, más adelante.
    - Orden: los campos de siempre más «Duración»; de partida, por nombre.
    - Filtros: el tipo «audio» en «Atributos»; en «Metadatos», fecha y palabras clave.
    - Textos de la barra, provisionales hasta que se decidan los nombres ('_TEXTS').

1.2.0 «Artistas» y «Años» en la barra, en lugar de «Fechas» (MUS 4.1; acordado con el
      autor el 26/11/2026: con las canciones, que casi siempre tienen solo el año, el
      año ▸ mes ▸ día no sirve).
1.1.0 También la vista individual: se entra y se sale como en los demás módulos (lo pidió
      el autor; antes, solo la cuadrícula).
1.0.1 Su clave, título, icono y biblioteca, de 'config/app_modules.py' (docs/PENDIENTE.md,
      GEN 12).
1.0.0 Primera versión (15/11/2026): sustituye al módulo provisional.
"""

__version__ = "1.2.0"
__all__ = ["AudioModule"]

# Módulos del proyecto
from config.app_modules import module_spec
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.library_module import LibraryModule
from core.catalog.grid_orders import NAME_ORDER, VIDEO_AUDIO_SORT_FIELDS, GridOrder
from core.catalog.media_types import MediaType
from core.catalog.music_browse import fetch_artist_tree, fetch_year_tree
from ui_helpers.helpers.mode_toolbar import MODE_AUDIO
from ui_helpers.sidebars.library_sidebar import ExtraSection, LibraryTexts
from ui_helpers.sidebars.sections.music_sections import ArtistSection, YearSection

# Su ficha: clave, título, icono, biblioteca y título de su sección
_SPEC = module_spec(MODE_AUDIO)

# Textos de la barra (provisionales)
_TEXTS = LibraryTexts(
    library_title=_SPEC.library_title,
    all_title="Toda la música",
    all_tooltip="Toda la música del catálogo (biblioteca Música)",
    quick_tooltip=(
        "Selección rápida\n\nLas canciones marcadas con el círculo de su tarjeta (esquina\n"
        "superior derecha). Es la misma del Catálogo: aquí solo se ven las de esta biblioteca."
    ),
)


# Las secciones propias de su barra (su sitio y si empiezan plegadas, en el registro de
# secciones: «Artistas» debajo de «Biblioteca» y «Años», plegada, al final)
_ARTISTS = ExtraSection(
    key="artists",
    title="Artistas",
    create=lambda library, parent: ArtistSection(library, parent),
    fetch=fetch_artist_tree,
)
_YEARS = ExtraSection(
    key="years",
    title="Años",
    create=lambda library, parent: YearSection(library, parent),
    fetch=fetch_year_tree,
)


class AudioModule(LibraryModule):
    """Módulo Audio (ver el docstring del archivo)."""

    key, title, icon, library = _SPEC.key, _SPEC.title, _SPEC.icon, _SPEC.library
    texts = _TEXTS
    extra_sections = (_ARTISTS, _YEARS)
    with_dates = False  # en su lugar, «Artistas» y «Años»

    def views(self) -> tuple[CenterView, ...]:
        """Cuadrícula y vista individual, como los demás módulos (el autor, 19/11/2026)."""
        return (CenterView.GRID, CenterView.SINGLE)

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
