"""Iconos de las filas de las barras laterales (unidades, carpetas, colecciones).

Los usan la barra del Catálogo ('catalog_sidebar.py') y la de los módulos de una
biblioteca ('library_sidebar.py', sección «Carpetas»), para que se vean igual.

Son los SVG de 'AppIcons', teñidos con 'SIDEBAR_ICON_COLOR'. El color se fija AQUÍ (no se
deja a la paleta): el árbol pide el icono en estado "On" para las filas que considera
desplegadas (también las que no tienen hijos, p. ej. una ubicación sin subcarpetas) y, con
el color de la paleta, ese estado se pinta con el color de acento.

Cada icono tiene además una variante "<clave>:open", en 'SIDEBAR_ICON_OPEN_COLOR', para
cuando su fila está DESPLEGADA (la de la carpeta es la carpeta abierta): la barra la pone y
la quita al desplegar y plegar.

Y otra, "<clave>:menu", para las opciones de los menús (p. ej. «Editar colección
inteligente…»): en la opción resaltada toma el color del texto sobre el acento
('ui_icons.menu_icon').

Si un SVG todavía no está en los recursos (.qrc), se usa el icono estándar del sistema,
para que la barra nunca se quede sin iconos.

Una carpeta que ya no está en el disco ('folder_missing') y una ubicación desconectada
('drive_offline') llevan, en lugar de su icono, el aviso de las tarjetas (círculo naranja
con «!» y gris con un disco tachado; 'card_glyphs.availability_icon'); desplegadas, igual.
Los textos de la carpeta que falta, que también comparten las dos barras, están aquí:
'MISSING_FOLDER_TOOLTIP' (segunda línea de su texto emergente) y 'MISSING_FOLDER_NOTE' (la
nota de su menú).

1.2.0 'folder_missing' y 'drive_offline', con el aviso de las tarjetas, y los textos de la
      carpeta que falta (CAT 6.2).
1.1.0 Variante "<clave>:menu" para los menús (con 'menu_icon').
"""

__version__ = "1.2.0"
__all__ = ["MISSING_FOLDER_NOTE", "MISSING_FOLDER_TOOLTIP", "load_sidebar_icons"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile
from qtpy.QtGui import QColor, QIcon, QPalette
from qtpy.QtWidgets import QStyle, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from ui_helpers.helpers.card_glyphs import MISSING, OFFLINE, availability_icon
from ui_helpers.helpers.ui_icons import menu_icon, tinted_icon
from ui_helpers.helpers.ui_theme import SIDEBAR_ICON_COLOR, SIDEBAR_ICON_OPEN_COLOR

# Textos de una carpeta que ya no está en el disco (los de una ubicación desconectada,
# «(desconectada)» y «(ubicación desconectada)», los pone cada barra)
MISSING_FOLDER_TOOLTIP = (
    "No se encuentra en el disco (se ha movido, renombrado o borrado fuera de la aplicación)"
)
MISSING_FOLDER_NOTE = "(no se encuentra en el disco)"


def load_sidebar_icons(widget: QWidget) -> dict[str, QIcon]:
    """Iconos por clave ('drive', 'folder', 'set', 'collection', 'smart', y
    'folder_missing' y 'drive_offline') y sus variantes ':open' (fila desplegada) y ':menu'
    (opción de un menú). 'widget' da el estilo (iconos de reserva) y la paleta."""
    style = widget.style()
    palette = widget.palette()
    normal = QColor(SIDEBAR_ICON_COLOR) if SIDEBAR_ICON_COLOR else palette.color(QPalette.ColorRole.ButtonText)
    opened = (
        QColor(SIDEBAR_ICON_OPEN_COLOR)
        if SIDEBAR_ICON_OPEN_COLOR
        else palette.color(QPalette.ColorRole.Highlight)
    )
    wanted = {
        "drive": (getattr(AppIcons, "DRIVE", ""), QStyle.StandardPixmap.SP_DriveHDIcon),
        "folder": (getattr(AppIcons, "FOLDER", ""), QStyle.StandardPixmap.SP_DirIcon),
        "folder_open": (getattr(AppIcons, "FOLDER_OPEN", ""), QStyle.StandardPixmap.SP_DirOpenIcon),
        "set": (getattr(AppIcons, "COLLECTION_SET", ""), QStyle.StandardPixmap.SP_DirClosedIcon),
        "collection": (getattr(AppIcons, "COLLECTION", ""), QStyle.StandardPixmap.SP_FileDialogListView),
        "smart": (getattr(AppIcons, "COLLECTION_SMART", ""), QStyle.StandardPixmap.SP_FileDialogDetailedView),
    }
    # La carpeta desplegada se dibuja con el SVG de la carpeta abierta
    open_paths = {"folder": wanted["folder_open"][0]}
    icons: dict[str, QIcon] = {}
    for key, (path, fallback) in wanted.items():
        open_path = open_paths.get(key, path)
        if path and QFile.exists(path):
            icons[key] = tinted_icon(path, normal)
            icons[f"{key}:open"] = tinted_icon(
                open_path if open_path and QFile.exists(open_path) else path, opened
            )
            icons[f"{key}:menu"] = menu_icon(path, normal)
        else:
            icons[key] = icons[f"{key}:open"] = icons[f"{key}:menu"] = style.standardIcon(fallback)
    # Carpeta que falta y ubicación desconectada: el aviso de las tarjetas en lugar del
    # icono, igual desplegadas (CAT 6.2)
    for key, availability in (("folder_missing", MISSING), ("drive_offline", OFFLINE)):
        icons[key] = icons[f"{key}:open"] = icons[f"{key}:menu"] = availability_icon(availability)
    return icons
