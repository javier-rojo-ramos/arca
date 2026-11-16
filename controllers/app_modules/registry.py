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

1.4.0 Vídeo y Audio, con su módulo ('VideoModule' y 'AudioModule', con la barra de Tracks;
      ya no queda ningún provisional).
1.3.0 Tracks, con su módulo de verdad ('TracksModule'; docs/MOD_TRACKS.md, paso 4.2).
1.2.0 Módulo provisional Tracks (botón 'btn_tracks'); Vídeo y Audio, con su icono.
"""

__version__ = "1.4.0"
__all__ = ["create_modules"]

# Librerías estándar
from typing import Any

# Módulos del proyecto
from controllers.app_modules.audio_module import AudioModule
from controllers.app_modules.base import AppModule, ModuleContext
from controllers.app_modules.catalog_module import CatalogModule
from controllers.app_modules.image_module import ImageModule
from controllers.app_modules.tracks_module import TracksModule
from controllers.app_modules.video_module import VideoModule


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
        # Vídeo: películas y series; Audio: la música (por ahora, con la barra de Tracks)
        VideoModule(context, button=ui.btn_video),
        AudioModule(context, button=ui.btn_audio),
        # Tracks: los recorridos GPS (barra propia; empieza en el mapa)
        TracksModule(context, button=ui.btn_tracks),
    ]
