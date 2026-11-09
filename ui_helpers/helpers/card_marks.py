"""Dibujo de las marcas del usuario: estrellas, marca (recuadro / X) y selección rápida.

Las usan la TARJETA de la cuadrícula ('ui_helpers/delegates/thumbnails_delegate.py') y la
BARRA INFERIOR ('ui_helpers/widgets/organize_bar.py'): al dibujarse con las mismas
funciones, se ven exactamente igual en los dos sitios. Para cambiar un color o un grosor,
se cambia aquí y cambia en toda la interfaz.

Se dibujan con 'QPainter' (sin iconos del .qrc): se ven nítidas a cualquier tamaño y
escala de pantalla. Cada función recibe el rectángulo donde dibujar, así que la barra
puede usarlas algo más grandes que la tarjeta; al tamaño de la tarjeta dan el mismo
resultado que antes de sacarlas a este módulo.

    draw_stars(painter, rect, rating, ...)        ★★★☆☆ (las vacías, solo si se piden)
    draw_flag(painter, rect, flag, hovered=...)   marcada = recuadro blanco; rechazada = X
                                                  gris; sin marca = contorno con el ratón
    draw_reject_cross(painter, rect)              la X de "rechazada"
    draw_quick_selection(painter, circle, ...)    círculo blanco (dentro) o gris
                                                  translúcido (fuera, con el ratón)

Las funciones guardan y restauran el estado del 'painter' cuando cambian el pincel o la
pluma (salvo 'draw_stars', que respeta la fuente que haya puesto quien llama).

Los colores salen del tema ('MARK_COLORS' y, los del círculo, que va sobre la imagen,
'CARD_COLORS'; ver 'theme_colors.py'). Las constantes '*_COLOR' de aquí son sus nombres de
siempre, para quien ya las usa.

1.1.0 Colores del tema, no sueltos (los mismos valores).
1.0.0 Sacado de 'ThumbnailsDelegate' para compartirlo con la barra inferior.
"""

__version__ = "1.1.0"
__all__ = [
    "FLAG_NONE",
    "FLAG_OUTLINE_COLOR",
    "FLAG_PICKED",
    "FLAG_PICKED_COLOR",
    "FLAG_REJECTED",
    "QUICK_BORDER_COLOR",
    "QUICK_HOVER_COLOR",
    "QUICK_ON_COLOR",
    "REJECT_COLOR",
    "STAR_COLOR",
    "STAR_EMPTY_COLOR",
    "STAR_REJECTED_COLOR",
    "draw_flag",
    "draw_quick_selection",
    "draw_reject_cross",
    "draw_stars",
]

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint, QRect, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPen

# Módulos del proyecto
from ui_helpers.helpers.ui_theme import CARD_COLORS, MARK_COLORS

# Valores de la marca (los mismos que 'core.catalog.media_queries.FLAG_*'; aquí no se
# importa 'core' para que el dibujo no dependa de la base de datos)
FLAG_REJECTED, FLAG_NONE, FLAG_PICKED = -1, 0, 1

# --- Estrellas ---
STAR_COLOR = MARK_COLORS.star  # rellenas
STAR_REJECTED_COLOR = MARK_COLORS.star_rejected  # rellenas de una rechazada (apagadas)
STAR_EMPTY_COLOR = MARK_COLORS.star_empty  # vacías (visibles sobre la banda gris)
_STAR_FULL, _STAR_EMPTY = "★", "☆"

# --- Marca ---
FLAG_PICKED_COLOR = MARK_COLORS.flag_picked  # recuadro de "marcada"
FLAG_OUTLINE_COLOR = MARK_COLORS.flag_outline  # contorno de "sin marca" (con el ratón encima)
REJECT_COLOR = MARK_COLORS.reject  # X de "rechazada"
# Grosor de la X para una X de 8 px (la de la tarjeta); a otros tamaños, proporcional
_REJECT_PEN_WIDTH = 1.6
_REJECT_REFERENCE_SIZE = 8

# --- Selección rápida ---
QUICK_ON_COLOR = CARD_COLORS.quick_on  # dentro: blanco, como la marca
QUICK_HOVER_COLOR = QColor(CARD_COLORS.quick_hover)  # fuera, con el ratón: gris claro translúcido
QUICK_BORDER_COLOR = QColor(CARD_COLORS.overlay_border)  # borde fino: se ve sobre imágenes claras


def draw_stars(
    painter: QPainter,
    rect: QRect,
    rating: int,
    *,
    star_width: int,
    show_empty: bool = False,
    rejected: bool = False,
) -> None:
    """Dibuja cinco estrellas en fila, de izquierda a derecha, desde 'rect.left()'.

    Usa la fuente que tenga puesta el 'painter' (el tamaño de la estrella lo decide ella).

    Args:
        painter: Donde dibujar.
        rect: Zona de las estrellas (se usa su borde izquierdo, su alto y 'star_width').
        rating: Estrellas rellenas (0 a 5).
        star_width: Ancho de cada estrella (px).
        show_empty: Dibujar también las vacías (☆): en la tarjeta, con el ratón encima.
        rejected: Rellenas en un tono apagado (archivo rechazado).
    """
    full_color = QColor(STAR_REJECTED_COLOR if rejected else STAR_COLOR)
    for star_idx in range(5):
        star_rect = QRect(rect.left() + star_idx * star_width, rect.top(), star_width, rect.height())
        if star_idx < rating:
            painter.setPen(full_color)
            painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, _STAR_FULL)
        elif show_empty:
            painter.setPen(QColor(STAR_EMPTY_COLOR))
            painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, _STAR_EMPTY)


def draw_flag(painter: QPainter, rect: QRect, flag: int, *, hovered: bool = False) -> None:
    """Dibuja la marca en 'rect' (en la tarjeta, 8 × 11 px).

        marcada    -> recuadro blanco
        rechazada  -> X gris ('draw_reject_cross')
        sin marca  -> contorno gris, solo con el ratón encima ('hovered'); si no, nada
    """
    if flag == FLAG_PICKED:
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(FLAG_PICKED_COLOR))
        painter.drawRect(rect)
        painter.restore()
    elif flag == FLAG_REJECTED:
        draw_reject_cross(painter, rect)
    elif hovered:
        painter.save()
        painter.setPen(QPen(QColor(FLAG_OUTLINE_COLOR), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        painter.restore()


def draw_reject_cross(painter: QPainter, rect: QRect, color: str = REJECT_COLOR) -> None:
    """Dibuja la X de "rechazada": cuadrada, del ancho de 'rect' y centrada en vertical.

    Args:
        painter: Donde dibujar.
        rect: Recuadro de la marca (la X usa su ancho).
        color: Color de la X (por defecto, el gris de la tarjeta).
    """
    size = rect.width()
    left = rect.left()
    top = rect.top() + (rect.height() - size) // 2
    width = _REJECT_PEN_WIDTH * size / _REJECT_REFERENCE_SIZE
    painter.save()
    painter.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPoint(left, top), QPoint(left + size, top + size))
    painter.drawLine(QPoint(left + size, top), QPoint(left, top + size))
    painter.restore()


def draw_quick_selection(
    painter: QPainter, circle: QRectF, selected: bool, *, hovered: bool = False
) -> None:
    """Dibuja el círculo de la selección rápida en 'circle' (en la tarjeta, 16 px).

        dentro de la selección rápida  -> círculo blanco (siempre)
        fuera, con el ratón encima     -> círculo gris claro translúcido
        fuera, sin ratón               -> nada
    Lleva un borde oscuro fino para que se vea también sobre una imagen clara.
    """
    if not selected and not hovered:
        return
    painter.save()
    painter.setPen(QPen(QUICK_BORDER_COLOR, 1.0))
    painter.setBrush(QColor(QUICK_ON_COLOR) if selected else QUICK_HOVER_COLOR)
    painter.drawEllipse(circle)
    painter.restore()


if __name__ == "__main__":
    # Autoprueba: dibuja todas las marcas en una imagen y comprueba algunos píxeles.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.helpers.card_marks
    import sys

    from qtpy.QtGui import QGuiApplication, QImage

    app = QGuiApplication(sys.argv)
    image = QImage(120, 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("#333333"))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_flag(p, QRect(10, 10, 8, 11), FLAG_PICKED)
    draw_flag(p, QRect(30, 10, 8, 11), FLAG_REJECTED)
    draw_flag(p, QRect(50, 10, 8, 11), FLAG_NONE)  # sin ratón: nada
    draw_quick_selection(p, QRectF(70, 10, 16, 16), True)
    draw_quick_selection(p, QRectF(95, 10, 16, 16), False)  # fuera y sin ratón: nada
    p.end()
    assert QColor(image.pixel(13, 15)) == QColor(FLAG_PICKED_COLOR)  # recuadro blanco
    assert QColor(image.pixel(54, 15)) == QColor("#333333")  # sin marca: nada
    assert QColor(image.pixel(78, 18)) == QColor(QUICK_ON_COLOR)  # círculo blanco
    assert QColor(image.pixel(103, 18)) == QColor("#333333")  # fuera: nada
    print("Autoprueba finalizada correctamente.")
