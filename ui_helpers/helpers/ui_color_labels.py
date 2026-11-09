"""Colores y textos con los que la interfaz muestra las etiquetas de color.

Los nombres canónicos ('red', 'blue'...) y su equivalencia con Lightroom están en
'core/catalog/color_labels.py' (sin Qt). Aquí solo está el aspecto: los colores son
parecidos a los de Lightroom Classic, ajustados para que se distingan sobre el fondo
oscuro de la cuadrícula. Los valores están en el tema ('MARK_COLORS', theme_colors.py).

1.1.0 Los colores de las etiquetas salen del tema (los mismos valores).
"""

__version__ = "1.1.0"
# ruff: noqa: RUF022
__all__ = ["LABEL_TEXTS", "blend", "label_color", "label_icon"]

# Librerías de terceros (Qt)
from qtpy.QtGui import QColor, QIcon, QPixmap

from core.catalog.color_labels import COLOR_LABELS
from ui_helpers.helpers.ui_theme import COLORS, MARK_COLORS

# Color (vivo) de cada etiqueta, del tema ('label_red'...): tiñe el fondo de la tarjeta y
# rellena los cuadraditos de la barra inferior, la fila «Atributos» y los menús
_LABEL_COLORS: dict[str, str] = {name: getattr(MARK_COLORS, f"label_{name}") for name in COLOR_LABELS}

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
    pixmap.fill(label_color(name) or QColor(COLORS.text_dim))
    return QIcon(pixmap)
