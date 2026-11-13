"""Módulo de constantes globales de la aplicación.

Este módulo centraliza todas las configuraciones estáticas, valores por defecto,
y constantes de negocio utilizadas a lo largo de la aplicación. Su propósito es
evitar "números mágicos" o cadenas de texto hardcodeadas en la lógica principal.

Incluye:
    - Rutas de iconos de la interfaz (vinculados a recursos.qrc).
    - Constantes de negocio (IVA, tarifas por defecto de módulos).
    - Listas de referencia estáticas (tipos de vía, tipologías, meses).
    - Parámetros de comportamiento y métricas de la interfaz de usuario (UI).
"""

# ruff: noqa: RUF022
__all__ = [
    "AppIcons",
    "SETTING_CONFIRM_MULTI_EDIT",
    "SETTING_INSPECTOR_METADATA_PRESET",
    "SETTING_INSPECTOR_SECTIONS",
    "SETTING_FILTER_METADATA_HEIGHT",
    "SETTING_FILTER_PRESETS",
    "SETTING_GPU_RENDERING",
    "SETTING_ACTIVE_MODULE",
    "SETTING_LAST_ADD_FOLDER_PARENT",
    "SETTING_MAP_CACHE_MB",
    "SETTING_MAP_FILMSTRIP",
    "SETTING_MAP_LAYER",
    "SETTING_MAP_USER_LAYERS",
    "SETTING_MAIN_SPLITTER_STATE",
    "SETTING_SHOW_SUBFOLDER_ITEMS",
    "SETTING_SIDEBAR_STATE",
    "SETTING_WRITE_USER_DATA_TO_FILES",
    "SIDEBAR_CATALOG_DEFAULT_WIDTH",
    "SIDEBAR_METADATA_DEFAULT_WIDTH",
    "SNAP_GAP",
    "SNAP_THRESHOLD",
    "STATUSBAR_DURATION",
    "THUMBNAIL_SIZE_DEFAULT",
    "THUMBNAIL_SIZE_MAX",
    "THUMBNAIL_SIZE_MIN",
]


# Esta clase se debe actualizar con el contenido del archivo 'recursos.qrc'
class AppIcons:
    MAIN_ICON = ":/img/main_icon.ico"
    LOGO = ":/img/logo.png"
    CHECK_CIRCLE = ":/img/check_circle.svg"
    CHECK_CIRCLE__GREEN = ":/img/check_circle__green.svg"
    CLOSE = ":/img/close.svg"
    ERROR = ":/img/error.svg"
    ERROR__RED = ":/img/error__red.svg"
    FOLDER = ":/img/folder.svg"
    FOLDER_OPEN = ":/img/folder_open.svg"
    # Barra lateral del catálogo (Material Symbols; si falta alguno en el .qrc, la barra
    # usa el icono estándar del sistema)
    ADD = ":/img/add.svg"  # botón "+" de las cabeceras (Carpetas, Colecciones)
    DRIVE = ":/img/storage.svg"  # ubicación (disco o carpeta raíz)
    COLLECTION_SET = ":/img/folder.svg"  # conjunto de colecciones
    COLLECTION = ":/img/folder_special.svg"  # colección
    COLLECTION_SMART = ":/img/folder_managed.svg"  # colección inteligente
    INFO = ":/img/info.svg"
    WARNING = ":/img/warning.svg"
    NEW = ":/img/note_add.svg"
    OPEN = ":/img/file_open.svg"
    TASK_NEW = ":/img/create_new_folder.svg"
    TASK_EDIT = ":/img/bookmark_manager.svg"
    TASK_DELETE = ":/img/folder_delete.svg"
    SELECT_ALL = ":/img/check_box_all.svg"
    SELECT_NONE = ":/img/check_box_none.svg"
    UP = ":/img/arrow_circle_up.svg"
    DOWN = ":/img/arrow_circle_down.svg"
    EQUAL = ":/img/equal.svg"
    SETTINGS = ":/img/settings.svg"
    SETTINGS_APP = ":/img/settings_applications.svg"
    BACK = ":/img/arrow_back_ios.svg"
    FORWARD = ":/img/arrow_forward_ios.svg"
    LIB_IMAGE = ":/img/library_image.svg"
    LIB_ALL = ":/img/library_all.svg"
    VIEW_GRID = ":/img/view_grid.svg"
    VIEW_FULL = ":/img/view_full.svg"
    VIEW_MAP = ":/img/view_map.svg"
    FILMSTRIP_SHOW = ":/img/filmstrip_show.svg"
    FILMSTRIP_HIDE = ":/img/filmstrip_hide.svg"
    LOCK_CLOSED = ":/img/lock_closed.svg"
    LOCK_OPEN = ":/img/lock_open.svg"


# Constantes de UI
SNAP_THRESHOLD = 15
SNAP_GAP = 8
STATUSBAR_DURATION = 5000

# Tamaño (en píxeles) de las miniaturas del mosaico: rango permitido del slider
# (slider_thumbnails) y valor por defecto la primera vez que se abre el programa
THUMBNAIL_SIZE_MIN = 120
THUMBNAIL_SIZE_MAX = 300
THUMBNAIL_SIZE_DEFAULT = 160

# Ancho inicial (píxeles) de las barras laterales la primera vez que se abre el programa
# (o si el valor guardado no sirve). Después se usa el que deje el usuario al arrastrar
# los separadores, guardado en settings.json (SETTING_MAIN_SPLITTER_STATE)
SIDEBAR_CATALOG_DEFAULT_WIDTH = 250  # izquierda: Catálogo, Carpetas, Colecciones
SIDEBAR_METADATA_DEFAULT_WIDTH = 280  # derecha: metadatos

# Claves de settings.json que se usan en varios módulos (así no se escriben a mano)
# Escribir la valoración, la marca y el color en los archivos (XMP o archivo de carpeta)
SETTING_WRITE_USER_DATA_TO_FILES = "write_user_data_to_files"
# Anchos de las barras laterales y de la zona central (estado de 'splitter_main', en hexadecimal)
SETTING_MAIN_SPLITTER_STATE = "main_splitter_state"
# Al elegir una carpeta en la barra lateral, mostrar también lo de sus subcarpetas
# (Opciones > Catálogo; como "Mostrar fotos en subcarpetas" de Lightroom)
SETTING_SHOW_SUBFOLDER_ITEMS = "show_subfolder_items"
# Lo desplegado y lo elegido en las barras laterales de cada módulo, POR CATÁLOGO:
# {"<carpeta del catálogo>": {"modules": {"catalog": {...}, ...}}}
# (ver controllers/app_modules/module_host.py; el formato anterior, sin "modules", se
# sigue leyendo como el estado del módulo Catálogo)
SETTING_SIDEBAR_STATE = "sidebar_state"
# Vista elegida en la sección «Metadatos» del inspector ("default", "location", "exif"...;
# ver ui_helpers/inspector/metadata_fields.py)
SETTING_INSPECTOR_METADATA_PRESET = "inspector_metadata_preset"
# Preguntar antes de poner el mismo metadato (título, pie...) a varios archivos que tienen
# valores distintos (aviso «Edición múltiple»; False = «No volver a mostrar»). True si no consta
SETTING_CONFIRM_MULTI_EDIT = "confirm_multi_edit"

# Secciones del inspector desplegadas o plegadas: {clave de la sección: True/False}.
# Es común a todos los catálogos (la barra izquierda, en cambio, se guarda por catálogo)
SETTING_INSPECTOR_SECTIONS = "inspector_sections"

# Alto del panel «Metadatos» de la barra de filtros (px lógicos; se cambia arrastrando su
# borde inferior). Uno para todos los módulos y catálogos. None = el de partida
SETTING_FILTER_METADATA_HEIGHT = "filter_metadata_height"

# Ajustes personalizados de la barra de filtros: lista de {"name", "filter"} en el orden
# del desplegable (ver 'core/catalog/filter_presets.py'). Una para todos los módulos y
# catálogos. None = los de fábrica (aún sin cambiar)
SETTING_FILTER_PRESETS = "filter_presets"

# Dibujar la ventana con la GPU (Opciones > General: «Usar aceleración por GPU si está
# disponible»; ver 'ui_helpers/helpers/gpu_composition.py'). Se aplica al volver a abrir
# la aplicación. None = según el sistema (sí en Windows y macOS, no en Linux)
SETTING_GPU_RENDERING = "gpu_rendering"

# Módulo activo al cerrar la aplicación ('catalog', 'image', 'video', 'audio'): se
# vuelve a él al arrancar. Es común a todos los catálogos
SETTING_ACTIVE_MODULE = "active_module"

# Carpeta en la que se abre «Añadir carpeta»: la que contiene la última carpeta añadida
# (así, para añadir varias de un mismo sitio, no hay que volver a navegar hasta allí).
# Común a todos los catálogos. "" = la carpeta personal; si ya no existe, también
SETTING_LAST_ADD_FOLDER_PARENT = "last_add_folder_parent"

# Capa del mapa que se ve (su clave en 'core/maps/tile_layers.py'). Una para toda la
# aplicación (decidido por el autor el 13/11/2026). None = la de partida (el callejero)
SETTING_MAP_LAYER = "map_layer"

# Capas propias del mapa (Opciones > Mapa): lista de {key, name, url, attribution,
# max_zoom} (ver 'core/maps/tile_layers.user_layers_from_settings'). Una para toda la
# aplicación
SETTING_MAP_USER_LAYERS = "map_user_layers"

# Tamaño máximo de la caché de teselas de los mapas, en MB (Opciones > Mapa; 2 GB,
# decidido por el autor el 13/11/2026)
SETTING_MAP_CACHE_MB = "map_cache_mb"

# Tira de fotos debajo del mapa: {"visible": bool, "height": px lógicos}. Una para toda
# la aplicación (se muestra u oculta con su botón de la barra inferior o con F6)
SETTING_MAP_FILMSTRIP = "map_filmstrip"
