"""Módulo Imagen: las fotos y los vídeos del móvil (biblioteca Imagen).

Es el segundo módulo (botón 'btn_image'). Es un módulo de biblioteca más ('LibraryModule'):
su barra es la común ('LibrarySidebar': «Biblioteca - Imagen», «Carpetas» y «Fechas») con
una sección de más, la «Lista de palabras clave» ('extra_sections'), y usa el inspector y
la cuadrícula comunes.

Lo común (pasar al 'ModuleHost' lo elegido en la barra, leer en segundo plano lo que
muestra, volver a «Todas las imágenes» si lo elegido desaparece, lo guardado por catálogo y
el menú de las carpetas) está en 'LibraryModule'. Aquí queda lo de Imagen:
    - Sus textos y su sección de palabras clave (árbol con recuentos:
      'keywords.fetch_keyword_tree').
    - Sus vistas (con el mapa, donde se ubican fotos), su orden y sus filtros.
    - 'show_source': una palabra clave pedida sin biblioteca se limita a Imagen.

1.17.1 Su clave, título, icono y biblioteca, de 'config/app_modules.py' (docs/PENDIENTE.md,
       GEN 12).
1.17.0 Hereda de 'LibraryModule' y usa la barra común, con la «Lista de palabras clave»
       como sección de más (docs/PENDIENTE.md, GEN 13; antes, 'ImageSidebar'). Nada cambia
       a la vista ni en lo guardado por catálogo.
1.16.1 Ordena por los campos comunes ('COMMON_SORT_FIELDS': los mismos seis de antes; los
       de los tracks son de su módulo).
1.16.0 Une su barra al modelo de colocación de las secciones ('context.section_layout').
1.15.0 'map_options': en su mapa se ubican fotos soltándolas y se mueven las ubicadas
       (docs/MOD_TRACKS.md, paso 3.2).
1.14.0 'views': también el mapa, con la tira de fotos (docs/MOD_TRACKS.md, paso 3.1; ubicar
       fotos soltándolas en él, en el paso 3.2).
1.13.0 «Fechas» en la barra: '_fetch_sidebar_data' lee también la línea de tiempo
       ('fetch_timeline') y '_on_sidebar_data' se la pasa (paso A.4).
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

__version__ = "1.17.1"
__all__ = ["ImageModule"]

# Módulos del proyecto
from config.app_modules import module_spec
from controllers.app_modules.center_views import CenterView, MapOptions
from controllers.app_modules.library_module import LibraryModule
from core.catalog.grid_orders import CAPTURE_TIME_ORDER, COMMON_SORT_FIELDS, GridOrder
from core.catalog.grid_source import GridSource, SourceKind, keyword_source
from core.catalog.keywords import fetch_keyword_tree
from core.catalog.media_types import MediaType
from ui_helpers.helpers.mode_toolbar import MODE_IMAGE
from ui_helpers.sidebars.library_sidebar import ExtraSection, LibraryTexts
from ui_helpers.sidebars.sections.keyword_section import KeywordSection

# Su ficha: clave, título, icono, biblioteca y título de su sección
_SPEC = module_spec(MODE_IMAGE)

# Textos de la barra
_TEXTS = LibraryTexts(
    library_title=_SPEC.library_title,
    all_title="Todas las imágenes",
    all_tooltip="Todas las fotos y los vídeos de la biblioteca Imagen",
    # Sin menú: «Vaciar selección rápida» vaciaría también lo que no se ve; está en el Catálogo
    quick_tooltip=(
        "Selección rápida\n\nLas imágenes marcadas con el círculo de su tarjeta (esquina\n"
        "superior derecha). Es la misma del Catálogo: aquí solo se ven las de Imagen."
    ),
)

# La sección de más de su barra: filtro y árbol de palabras clave, solo para navegar (las
# palabras se editan en el inspector). Lo desplegado, el estado 'SIDEBAR' de 'KeywordSection'
_KEYWORDS = ExtraSection(
    key="keywords",
    title="Lista de palabras clave",
    create=lambda library, parent: KeywordSection(library, None, parent),
    fetch=fetch_keyword_tree,
)


class ImageModule(LibraryModule):
    """Módulo Imagen (ver el docstring del archivo)."""

    key, title, icon, library = _SPEC.key, _SPEC.title, _SPEC.icon, _SPEC.library
    texts = _TEXTS
    extra_sections = (_KEYWORDS,)

    def views(self) -> tuple[CenterView, ...]:
        """Cuadrícula, vista individual y mapa (empieza en la cuadrícula)."""
        return (CenterView.GRID, CenterView.SINGLE, CenterView.MAP)

    def map_options(self) -> MapOptions:
        """En el mapa de Imagen se ubican fotos (soltándolas) y se mueven las ubicadas."""
        return MapOptions(allow_geotag=True)

    def filter_media_types(self) -> tuple[str, ...]:
        """Fotos y vídeos (los del móvil entran en Imagen)."""
        return (MediaType.PHOTO, MediaType.VIDEO)

    def filter_metadata_fields(self) -> tuple[str, ...]:
        """Columnas de partida de «Metadatos», como en Lightroom."""
        return ("captured_at", "camera_model", "lens_model")

    def sort_fields(self) -> tuple[str, ...]:
        """Todos los campos de orden (de momento; llegarán los propios de las fotos)."""
        return COMMON_SORT_FIELDS

    def default_order(self) -> GridOrder:
        """Por hora de captura, ascendente (como Lightroom)."""
        return CAPTURE_TIME_ORDER

    def show_source(self, source: GridSource) -> None:
        """Lo pide el inspector (flecha «ver sus fotos»): se elige en la barra, que lo
        muestra en la cuadrícula ('source_selected') y lo deja marcado. Una palabra pedida
        sin biblioteca se limita a Imagen (así es la fila de la barra)."""
        if (
            source.kind == SourceKind.KEYWORD
            and source.keyword_id is not None
            and source.library is None
        ):
            source = keyword_source(source.keyword_id, self.library)
        super().show_source(source)
