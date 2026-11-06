"""Colores y textos con los que la interfaz muestra las etiquetas de color.

Los nombres canónicos ('red', 'blue'...) y su equivalencia con Lightroom están en
'core/catalog/color_labels.py' (sin Qt). Aquí solo está el aspecto: los colores son
parecidos a los de Lightroom Classic, ajustados para que se distingan sobre el fondo
oscuro de la cuadrícula.
"""

__version__ = "1.0.0"
# ruff: noqa: RUF022
__all__ = ["LABEL_TEXTS", "blend", "label_color", "label_icon"]

# Librerías de terceros (Qt)
from qtpy.QtGui import QColor, QIcon, QPixmap

from core.catalog.color_labels import COLOR_LABELS

# Color (vivo) de cada etiqueta: se usa para el marco alrededor de la miniatura
_LABEL_COLORS: dict[str, str] = {
    "red": "#e0453f",
    "yellow": "#e8c53a",
    "green": "#4cae4f",
    "blue": "#3d8fe0",
    "purple": "#9a5fc4",
}

# Texto de cada etiqueta en los menús
LABEL_TEXTS: dict[str, str] = {
    "red": "Roja",
    "yellow": "Amarilla",
    "green": "Verde",
    "blue": "Azul",
    "purple": "Púrpura",
}

assert set(_LABEL_COLORS) == set(LABEL_TEXTS) == set(COLOR_LABELS)  # no puede desincronizarse


def label_color(name: str | None) -> QColor | None:
    """Devuelve el color de una etiqueta, o None si 'name' es None o no se conoce."""
    hex_color = _LABEL_COLORS.get(name) if name else None
    return QColor(hex_color) if hex_color else None


def blend(base: QColor, tint: QColor, amount: float) -> QColor:
    """Mezcla 'tint' sobre 'base': amount=0 da 'base' y amount=1 da 'tint'."""
    inverse = 1.0 - amount
    return QColor(
        round(base.red() * inverse + tint.red() * amount),
        round(base.green() * inverse + tint.green() * amount),
        round(base.blue() * inverse + tint.blue() * amount),
    )


def label_icon(name: str, size: int = 12) -> QIcon:
    """Cuadradito del color de la etiqueta, para los menús."""
    pixmap = QPixmap(size, size)
    pixmap.fill(label_color(name) or QColor("#888888"))
    return QIcon(pixmap)
