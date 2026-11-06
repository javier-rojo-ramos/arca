"""Iconos de las filas de las barras laterales (unidades, carpetas, colecciones).

Los usan la barra del Catálogo ('catalog_sidebar.py') y la del módulo Imagen
('image_sidebar.py', sección «Carpetas»), para que las dos se vean igual.

Son los SVG de 'AppIcons', teñidos con 'SIDEBAR_ICON_COLOR'. El color se fija AQUÍ (no se
deja a la paleta): el árbol pide el icono en estado "On" para las filas que considera
desplegadas (también las que no tienen hijos, p. ej. una ubicación sin subcarpetas) y, con
el color de la paleta, ese estado se pinta con el color de acento.

Cada icono tiene además una variante "<clave>:open", en 'SIDEBAR_ICON_OPEN_COLOR', para
cuando su fila está DESPLEGADA (la de la carpeta es la carpeta abierta): la barra la pone y
la quita al desplegar y plegar.

Si un SVG todavía no está en los recursos (.qrc), se usa el icono estándar del sistema,
para que la barra nunca se quede sin iconos.
"""

__version__ = "1.0.0"
__all__ = ["load_sidebar_icons"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile
from qtpy.QtGui import QColor, QIcon, QPalette
from qtpy.QtWidgets import QStyle, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_theme import SIDEBAR_ICON_COLOR, SIDEBAR_ICON_OPEN_COLOR


def load_sidebar_icons(widget: QWidget) -> dict[str, QIcon]:
    """Iconos por clave ('drive', 'folder', 'set', 'collection', 'smart') y su variante
    ':open'. 'widget' da el estilo (iconos de reserva) y la paleta."""
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
        else:
            icons[key] = icons[f"{key}:open"] = style.standardIcon(fallback)
    return icons
