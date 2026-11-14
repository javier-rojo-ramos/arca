"""Lista de módulos de la aplicación, en el orden de la toolbar.

Es el ÚNICO sitio que hay que tocar para dar de alta un módulo (o para sustituir uno
provisional por el de verdad):

    1. Escribir su clase, heredando de 'AppModule' (ver 'base.py'; ejemplo completo en
       'catalog_module.py').
    2. Añadir (o sustituir) su línea en 'create_modules'.
    3. Si es un botón nuevo, añadirlo en el .ui dentro de 'frame_toolbar' (y ejecutar
       'build_ui.py').

Los botones de la toolbar están en el .ui (se diseñan con Qt Designer); aquí solo se dice
qué módulo activa cada uno.

1.3.0 Tracks, con su módulo de verdad ('TracksModule'; docs/MAPA.md, paso 4.2).
1.2.0 Módulo provisional Tracks (botón 'btn_tracks'); Vídeo y Audio, con su icono.
"""

__version__ = "1.3.0"
__all__ = ["create_modules"]

# Librerías estándar
from typing import Any

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.base import AppModule, ModuleContext
from controllers.app_modules.catalog_module import CatalogModule
from controllers.app_modules.image_module import ImageModule
from controllers.app_modules.placeholder_module import PlaceholderModule
from controllers.app_modules.tracks_module import TracksModule
from ui_helpers.helpers.mode_toolbar import MODE_AUDIO, MODE_VIDEO


def create_modules(ui: Any, context: ModuleContext) -> list[AppModule]:
    """Crea los módulos de la aplicación, en el orden de la toolbar (el primero, el inicial).

    Args:
        ui: Ventana principal (de ella se toman los botones y widgets del .ui).
        context: Lo que comparte la ventana principal con los módulos.

    Returns:
        Los módulos, listos para pasarlos a 'ModuleHost'.
    """
    return [
        # Catálogo: todos los archivos (barra lateral 'CatalogSidebar' del .ui)
        CatalogModule(
            context,
            button=ui.btn_catalog,
            sidebar=ui.widget_catalog_sidebar,
            page=ui.page_catalog_default,
        ),
        # Imagen: fotos y vídeos del móvil, con el árbol de palabras clave (barra propia)
        ImageModule(context, button=ui.btn_image),
        # Provisionales hasta que tengan su clase (ya con su botón y su icono)
        PlaceholderModule(
            context,
            key=MODE_VIDEO,
            title="Vídeo",
            icon=AppIcons.LIB_VIDEO,
            button=ui.btn_video,
        ),
        PlaceholderModule(
            context,
            key=MODE_AUDIO,
            title="Audio",
            icon=AppIcons.LIB_AUDIO,
            button=ui.btn_audio,
        ),
        # Tracks: los recorridos GPS (barra propia; empieza en el mapa)
        TracksModule(context, button=ui.btn_tracks),
    ]
