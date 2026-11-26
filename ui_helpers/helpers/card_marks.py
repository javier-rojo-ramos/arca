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
    star_path(box, device_pixel_ratio)            la forma de una estrella, ajustada al píxel
    draw_flag(painter, rect, flag, hovered=...)   marcada = recuadro blanco; rechazada = X
                                                  gris; sin marca = contorno con el ratón
    draw_reject_cross(painter, rect)              la X de "rechazada"
    draw_quick_selection(painter, circle, ...)    círculo blanco (dentro) o gris
                                                  translúcido (fuera, con el ratón)

Las funciones guardan y restauran el estado del 'painter' cuando cambian el pincel o la
pluma.

Las estrellas se dibujan (no son el carácter ★ de una fuente): así son iguales en Windows,
macOS y Linux (docs/DECISIONES.md, 24/11/2026). Cada una ocupa el cuadrado que ocupaba el
carácter (el ancho de su hueco menos 1 px, pegado a la izquierda y centrado en vertical) y
se ajusta a los píxeles de la pantalla ('star_path') para que salga nítida.

Los colores salen del tema ('MARK_COLORS' y, los del círculo, que va sobre la imagen,
'CARD_COLORS'; ver 'theme_colors.py'). Las constantes '*_COLOR' de aquí son sus nombres de
siempre, para quien ya las usa.

1.3.0 'draw_stars(..., gap=)': separación entre las estrellas (las barras, con el recuadro
      del ratón; las tarjetas, sin ella, como antes). El autor, 26/11/2026.
1.2.0 Estrellas dibujadas (GEN 21.3; antes, el carácter ★ con la fuente de quien llamaba,
      Arial, que no lo tiene: salía de «Segoe UI Symbol» en Windows y de otra fuente en los
      demás sistemas): de punta fina, en el mismo cuadrado que el carácter, con la caja y
      los hombros en el borde de un píxel ('star_path'). Ya no usan la fuente del 'painter'.
1.1.0 Colores del tema, no sueltos (los mismos valores).
1.0.0 Sacado de 'ThumbnailsDelegate' para compartirlo con la barra inferior.
"""

__version__ = "1.3.0"
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
    "star_path",
]

# Librerías estándar
import math

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPainterPath, QPen

# Módulos del proyecto
from ui_helpers.helpers.ui_theme import CARD_COLORS, MARK_COLORS

# Valores de la marca (los mismos que 'core.catalog.media_queries.FLAG_*'; aquí no se
# importa 'core' para que el dibujo no dependa de la base de datos)
FLAG_REJECTED, FLAG_NONE, FLAG_PICKED = -1, 0, 1

# --- Estrellas ---
STAR_COLOR = MARK_COLORS.star  # rellenas
STAR_REJECTED_COLOR = MARK_COLORS.star_rejected  # rellenas de una rechazada (apagadas)
STAR_EMPTY_COLOR = MARK_COLORS.star_empty  # vacías (visibles sobre la banda gris)
# La forma: cinco puntas, una hacia arriba, «de punta fina»: el radio de dentro, el 40 % del
# de fuera (en la regular, el 38,2 %). Elegida por el autor el 24/11/2026 (GEN 21.0)
_STAR_INNER_RATIO = 0.40
# Grosor del contorno de las vacías (px)
_EMPTY_STAR_PEN = 1.0

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


def _unit_star(inner_ratio: float) -> tuple[tuple[float, float], ...]:
    """Las 10 esquinas de la estrella (la punta, arriba), encajadas en un cuadrado de 0 a 1."""
    corners = []
    for index in range(10):
        radius = 1.0 if index % 2 == 0 else inner_ratio
        angle = math.radians(-90 + index * 36)
        corners.append((radius * math.cos(angle), radius * math.sin(angle)))
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    return tuple(
        ((x - min(xs)) / (max(xs) - min(xs)), (y - min(ys)) / (max(ys) - min(ys)))
        for x, y in corners
    )


_STAR_UNIT = _unit_star(_STAR_INNER_RATIO)
# Altura (de 0 a 1) de los «hombros»: las dos puntas laterales de arriba, donde acaba el
# borde de arriba de los brazos, casi horizontal. 'star_path' la lleva al borde de un píxel
_STAR_SHOULDER = (_STAR_UNIT[1][1] + _STAR_UNIT[9][1]) / 2


def _device_round(value: float) -> int:
    """Redondeo al píxel más cercano, siempre hacia arriba en el medio (round() de Python
    redondea .5 al par: 19,5 -> 20 pero 22,5 -> 22, y las estrellas bailarían)."""
    return math.floor(value + 0.5)


def star_path(box: QRectF, device_pixel_ratio: float = 1.0, *, inset: float = 0.0) -> QPainterPath:
    """La estrella que llena 'box' (un cuadrado), ajustada a los píxeles de la pantalla.

    La caja se lleva a píxeles físicos enteros y los hombros, al borde de un píxel (la parte
    de arriba se estira o encoge una fracción de píxel): así la punta, las de abajo y el
    borde de arriba de los brazos salen nítidos. Medido el 24/11/2026 (GEN 21.3): en la
    barra, un 28 % de píxeles a medias al 100 % y un 21 % al 150 % (sin ajustar los
    hombros, un 34 % y un 30 %; el carácter de antes, un 20 % al 150 %).

    Args:
        box: El cuadrado de la estrella, en px lógicos.
        device_pixel_ratio: Píxeles físicos por px lógico (1 al 100 %; 1,5 al 150 %).
        inset: Cuánto se mete hacia dentro (px lógicos) después de ajustarla: para un
            contorno, la mitad de su grosor, así su borde de fuera cae donde el de la llena.
    """
    dpr = device_pixel_ratio
    left, top = _device_round(box.left() * dpr), _device_round(box.top() * dpr)
    width, height = _device_round(box.width() * dpr), _device_round(box.height() * dpr)
    shoulder = _STAR_SHOULDER * height
    snapped = _device_round(shoulder)
    margin = inset * dpr

    def device_y(unit_y: float) -> float:
        y = unit_y * height
        # Por tramos: arriba (0) y abajo (alto) no se mueven; los hombros, a un píxel entero
        if y <= shoulder:
            y = y * snapped / shoulder if shoulder else y
        else:
            y = snapped + (y - shoulder) * (height - snapped) / (height - shoulder)
        return y

    inner_w, inner_h = width - 2 * margin, height - 2 * margin
    path = QPainterPath()
    for index, (unit_x, unit_y) in enumerate(_STAR_UNIT):
        y = device_y(unit_y)
        point = QPointF(
            (left + margin + unit_x * inner_w) / dpr,
            (top + margin + y * inner_h / height) / dpr if height else top / dpr,
        )
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def draw_stars(
    painter: QPainter,
    rect: QRect,
    rating: int,
    *,
    star_width: int,
    show_empty: bool = False,
    rejected: bool = False,
    gap: int = 0,
) -> None:
    """Dibuja cinco estrellas en fila, de izquierda a derecha, desde 'rect.left()'.

    Cada una, en un cuadrado del ancho de su hueco menos 1 px (en la tarjeta, 11 px; en las
    barras, 15), pegado a la izquierda del hueco y centrado en vertical en 'rect' (hacia
    arriba si sobra un píxel): el sitio que ocupaba el carácter ★ de antes. Las vacías, con
    un contorno de 1 px. No usa la fuente del 'painter'.

    Args:
        painter: Donde dibujar.
        rect: Zona de las estrellas (se usa su borde izquierdo, su alto y 'star_width').
        rating: Estrellas rellenas (0 a 5).
        star_width: Ancho de cada estrella (px).
        show_empty: Dibujar también las vacías (☆): en la tarjeta, con el ratón encima.
        rejected: Rellenas en un tono apagado (archivo rechazado).
        gap: Px de más entre dos estrellas (los huecos van de 'star_width' + 'gap' en
            'star_width' + 'gap'). En las barras, que enmarcan la estrella bajo el ratón,
            para que el recuadro no pise las de al lado; en la tarjeta, ninguno.
    """
    size = star_width - 1
    top = rect.top() + (rect.height() - size) // 2
    device = painter.device()
    dpr = device.devicePixelRatioF() if device is not None else 1.0
    full_color = QColor(STAR_REJECTED_COLOR if rejected else STAR_COLOR)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for star_idx in range(5):
        box = QRectF(rect.left() + star_idx * (star_width + gap), top, size, size)
        if star_idx < rating:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(full_color)
            painter.drawPath(star_path(box, dpr))
        elif show_empty:
            painter.setPen(QPen(QColor(STAR_EMPTY_COLOR), _EMPTY_STAR_PEN))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(star_path(box, dpr, inset=_EMPTY_STAR_PEN / 2))
    painter.restore()


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
    print("Marca, X y selección rápida: bien")

    # Estrellas: en el cuadrado que ocupaba el carácter de antes (medido el 24/11/2026):
    # tarjeta, 11 px en una franja de 14, desde y = 1; barra inferior, 15 px en una de 26,
    # desde y = 5; «Atributos», 15 px en una de 22, desde y = 3. Y al 150 %, en píxeles
    # físicos enteros
    background = QColor("#2a2a2a")

    def star_box(star_w: int, row_h: int, rating: int, dpr: float = 1.0, **kwargs: bool):
        """Dibuja las estrellas y devuelve la caja de lo dibujado (x, y, ancho, alto)."""
        img = QImage(round(star_w * 5 * dpr), round(row_h * dpr), QImage.Format.Format_ARGB32)
        img.setDevicePixelRatio(dpr)
        img.fill(background)
        painter = QPainter(img)
        draw_stars(painter, QRect(0, 0, star_w * 5, row_h), rating, star_width=star_w, **kwargs)
        painter.end()
        xs, ys = [], []
        for y in range(img.height()):
            for x in range(img.width()):
                if QColor(img.pixel(x, y)) != background:
                    xs.append(x)
                    ys.append(y)
        return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1), img

    for star_w, row_h, top in ((12, 14, 1), (16, 26, 5), (16, 22, 3)):
        size = star_w - 1
        box, img = star_box(star_w, row_h, 3)
        assert box == (0, top, 2 * star_w + size, size), (star_w, row_h, box)
        # El centro de la primera, lleno del color de la estrella
        center = QColor(img.pixel(size // 2, top + size // 2))
        assert center == QColor(STAR_COLOR), center.name()
        box, _ = star_box(star_w, row_h, 3, show_empty=True)  # con las vacías: las cinco
        assert box == (0, top, 4 * star_w + size, size), (star_w, row_h, box)
        box, img = star_box(star_w, row_h, 1, rejected=True)
        assert QColor(img.pixel(size // 2, top + size // 2)) == QColor(STAR_REJECTED_COLOR)
    # Al 150 %: la tarjeta, 17 px físicos (11 × 1,5 = 16,5 -> 17) desde y = 2 (1,5 -> 2)
    box, _ = star_box(12, 14, 1, dpr=1.5)
    assert box == (0, 2, 17, 17), box
    # Sin valoración y sin vacías: nada
    empty = QImage(60, 14, QImage.Format.Format_ARGB32)
    empty.fill(background)
    painter = QPainter(empty)
    draw_stars(painter, QRect(0, 0, 60, 14), 0, star_width=12)
    painter.end()
    assert all(QColor(empty.pixel(x, y)) == background for x in range(60) for y in range(14))
    print("Estrellas: en el cuadrado del carácter de antes (100 % y 150 %), colores bien")
    print("Autoprueba finalizada correctamente.")
