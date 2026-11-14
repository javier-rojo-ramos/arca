"""El recorrido de un track como dibujo pequeño: la «miniatura» de su tarjeta.

Un track no tiene imagen. Su tarjeta enseñaba el mismo símbolo para todos; ahora dibuja la
FORMA de su recorrido, con el contorno que ya guarda el catálogo
('track_details.overview': unos cien puntos, ver 'core/tracks/simplify.py'). Se dibuja al
vuelo cada vez que se pinta la tarjeta (decidido por el autor el 14/11/2026: en una carpeta
no hay más de cien o doscientos tracks): sin caché de imágenes ni versiones que subir, y
con los colores del tema.

Dos pasos, separados para no repetir cuentas al pintar:

    outline = outline_from_overview(texto)       # una vez por track (lo guarda el modelo)
    draw_track_outline(painter, rect, outline)   # cada vez que se pinta la tarjeta

'TrackOutline' son los segmentos del recorrido ya ENCAJADOS en un cuadrado de lado 1
(x hacia el este, y hacia abajo), conservando la proporción real: un recorrido alargado de
norte a sur queda alto y estrecho, centrado. La longitud se encoge con el coseno de la
latitud media (a 42° N, un grado de longitud mide tres cuartos de uno de latitud): sin
eso, las rutas saldrían estiradas a lo ancho.

'outline_from_overview' no depende de Qt (se puede probar sola); el dibujo, sí.

1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.5).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.helpers.track_outline
"""

__version__ = "1.0.0"
__all__ = ["TrackOutline", "draw_track_outline", "normalize_outline", "outline_from_overview"]

# Librerías estándar
import math
from collections.abc import Iterable, Sequence

# Librerías de terceros (Qt)
from qtpy.QtCore import QPointF, QRect, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPainterPath, QPen

# Módulos del proyecto
from core.tracks.simplify import decode_overview
from ui_helpers.helpers.ui_theme import CARD_COLORS

# Los segmentos de un recorrido encajados en el cuadrado unidad: cada punto, (x, y) en 0..1
TrackOutline = tuple[tuple[tuple[float, float], ...], ...]

# Hueco que se deja alrededor del dibujo, como parte del lado corto de la tarjeta
_MARGIN = 0.14
# Grosor de la línea y radio de los puntos de salida y de llegada, como parte del lado
# corto; y sus mínimos en px (para las tarjetas pequeñas de la tira del mapa)
_LINE_WIDTH = 1 / 55
_MIN_LINE_WIDTH = 1.4
_DOT_RADIUS = 1 / 32
_MIN_DOT_RADIUS = 2.2
# Por debajo de este lado (px) no se dibuja nada: no se entendería
_MIN_SIDE = 16


def normalize_outline(segments: Iterable[Sequence[tuple[float, float]]]) -> TrackOutline | None:
    """Encaja un recorrido (segmentos de (latitud, longitud)) en el cuadrado unidad,
    conservando su proporción y centrado (ver el docstring del archivo).

    Returns:
        Los segmentos encajados, o None si no hay al menos dos puntos distintos (no hay
        forma que dibujar).
    """
    kept = [tuple(segment) for segment in segments if len(segment) > 0]
    points = [point for segment in kept for point in segment]
    if len(points) < 2:
        return None
    latitudes = [latitude for latitude, _longitude in points]
    # Un grado de longitud mide menos cuanto más lejos del ecuador
    shrink = max(0.01, math.cos(math.radians((min(latitudes) + max(latitudes)) / 2)))
    xs = [longitude * shrink for _latitude, longitude in points]
    west, east = min(xs), max(xs)
    south, north = min(latitudes), max(latitudes)
    width, height = east - west, north - south
    span = max(width, height)
    if span <= 0:
        return None  # todos los puntos en el mismo sitio
    # Centrado: lo que le falta al lado corto se reparte a los dos lados
    offset_x = (span - width) / 2
    offset_y = (span - height) / 2
    return tuple(
        tuple(
            (
                (longitude * shrink - west + offset_x) / span,
                (north - latitude + offset_y) / span,  # el norte, arriba
            )
            for latitude, longitude in segment
        )
        for segment in kept
    )


def outline_from_overview(overview: str | None) -> TrackOutline | None:
    """El dibujo de un track a partir de su contorno del catálogo
    ('track_details.overview'). None si no tiene contorno o no da para una forma."""
    if not overview:
        return None
    try:
        return normalize_outline(decode_overview(overview))
    except (ValueError, IndexError):
        return None  # un contorno dañado: la tarjeta se queda con su símbolo


def draw_track_outline(
    painter: QPainter,
    rect: QRect | QRectF,
    outline: TrackOutline,
    *,
    color: QColor | str | None = None,
    background: QColor | str | None = None,
) -> None:
    """Dibuja el recorrido en 'rect': fondo, línea y los puntos de salida y de llegada.

    Args:
        painter: Pintor ya preparado.
        rect: Zona de la tarjeta (se rellena entera con el fondo).
        outline: El recorrido encajado ('outline_from_overview').
        color: Color de la línea (por defecto, el de los símbolos de las tarjetas).
        background: Color del fondo (por defecto, el de las tarjetas sin miniatura).
    """
    area = QRectF(rect)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(background or CARD_COLORS.placeholder_bg))
    painter.drawRect(rect)

    side = min(area.width(), area.height())
    if side < _MIN_SIDE or not outline:
        painter.restore()
        return
    # Un cuadrado centrado en la tarjeta, con su margen
    inner = side * (1 - 2 * _MARGIN)
    left = area.center().x() - inner / 2
    top = area.center().y() - inner / 2

    path = QPainterPath()
    for segment in outline:
        first = True
        for x, y in segment:
            point = QPointF(left + x * inner, top + y * inner)
            if first:
                path.moveTo(point)
                first = False
            else:
                path.lineTo(point)

    line_color = QColor(color or CARD_COLORS.placeholder_glyph)
    pen = QPen(
        line_color,
        max(_MIN_LINE_WIDTH, side * _LINE_WIDTH),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    # La salida, un punto relleno; la llegada, un anillo (así se sabe el sentido)
    radius = max(_MIN_DOT_RADIUS, side * _DOT_RADIUS)
    start_x, start_y = outline[0][0]
    end_x, end_y = outline[-1][-1]
    start = QPointF(left + start_x * inner, top + start_y * inner)
    end = QPointF(left + end_x * inner, top + end_y * inner)
    painter.setBrush(QColor(background or CARD_COLORS.placeholder_bg))
    painter.drawEllipse(end, radius, radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(line_color)
    painter.drawEllipse(start, radius, radius)
    painter.restore()


if __name__ == "__main__":
    # Autoprueba sin ventana: las cuentas, y el dibujo sobre una imagen en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.helpers.track_outline
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qtpy.QtGui import QImage
    from qtpy.QtWidgets import QApplication

    from core.tracks.simplify import encode_overview

    app = QApplication.instance() or QApplication([])

    def _box(outline: TrackOutline) -> tuple[float, float, float, float]:
        xs = [x for segment in outline for x, _y in segment]
        ys = [y for segment in outline for _x, y in segment]
        return round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)

    def _at(point: tuple[float, float]) -> tuple[float, float]:
        return round(point[0], 3), round(point[1], 3)

    # --- Cerca del ecuador, un recorrido de norte a sur: alto, estrecho y centrado
    # (se compara con tres decimales: la longitud ya encoge un poco a medio grado)
    tall = normalize_outline([[(0.0, 0.0), (1.0, 0.0), (1.0, 0.2)]])
    assert tall is not None and _box(tall) == (0.4, 0.0, 0.6, 1.0), _box(tall)
    # El norte, arriba: el primer punto (el más al sur) queda abajo
    assert _at(tall[0][0]) == (0.4, 1.0) and _at(tall[0][1]) == (0.4, 0.0)
    # De oeste a este: ancho y bajo
    wide = normalize_outline([[(0.0, 0.0), (0.0, 2.0), (0.5, 2.0)]])
    assert wide is not None and _box(wide) == (0.0, 0.375, 1.0, 0.625), _box(wide)

    # --- La longitud encoge con la latitud: a 60° N, un grado de longitud es medio de latitud
    north = normalize_outline([[(59.5, 10.0), (60.5, 10.0), (60.5, 11.0)]])
    assert north is not None
    left_x, _top, right_x, _bottom = _box(north)
    assert abs((right_x - left_x) - 0.5) < 0.01, _box(north)  # 1° de ancho, la mitad que 1° de alto

    # --- Varios segmentos: se encajan juntos y siguen separados; los vacíos, fuera
    two = normalize_outline([[(0.0, 0.0), (0.0, 1.0)], [], [(1.0, 0.0), (1.0, 1.0)]])
    assert two is not None and len(two) == 2 and _box(two) == (0.0, 0.0, 1.0, 1.0)

    # --- Sin forma que dibujar
    for nothing in ([], [[]], [[(1.0, 1.0)]], [[(1.0, 1.0), (1.0, 1.0)]]):
        assert normalize_outline(nothing) is None, nothing

    # --- Desde el contorno del catálogo
    flat = [42.0, 0.0, 42.01, 0.0, 42.01, 0.02, 42.02, 0.02]
    overview = encode_overview([flat])
    outline = outline_from_overview(overview)
    assert outline is not None and len(outline) == 1 and len(outline[0]) == 4
    assert outline_from_overview(None) is None and outline_from_overview("") is None

    # --- El dibujo: llena el fondo y pinta la línea dentro de su margen
    def _render(size: int, shape: TrackOutline) -> QImage:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(QColor(255, 0, 255))  # un color que no es del tema: debe taparse entero
        painter = QPainter(image)
        draw_track_outline(painter, QRect(0, 0, size, size), shape,
                           color=QColor(250, 250, 250), background=QColor(10, 10, 10))  # fmt: skip
        painter.end()
        return image

    def _drawn(image: QImage) -> list[tuple[int, int]]:
        """Los píxeles claros (los de la línea)."""
        return [
            (x, y)
            for x in range(image.width())
            for y in range(image.height())
            if QColor(image.pixel(x, y)).lightness() > 128
        ]

    image = _render(120, outline)
    assert all(
        QColor(image.pixel(x, y)) != QColor(255, 0, 255) for x in range(120) for y in range(120)
    ), "el fondo no se ha rellenado entero"
    pixels = _drawn(image)
    assert len(pixels) > 150, len(pixels)
    xs, ys = [x for x, _y in pixels], [y for _x, y in pixels]
    margin = 120 * _MARGIN
    assert min(xs) >= margin - 6 and max(xs) <= 120 - margin + 6, (min(xs), max(xs))
    assert min(ys) >= margin - 6 and max(ys) <= 120 - margin + 6, (min(ys), max(ys))
    # El recorrido de prueba va de sur a norte: ocupa todo el alto útil
    assert max(ys) - min(ys) > 120 * (1 - 2 * _MARGIN) - 4
    # En una tarjeta pequeña (la tira del mapa) sigue viéndose; en una diminuta, solo el fondo
    assert len(_drawn(_render(48, outline))) > 30
    assert _drawn(_render(12, outline)) == []
    # Con los colores del tema (los de por defecto) no falla
    themed = QImage(64, 64, QImage.Format.Format_ARGB32)
    themed.fill(QColor(0, 0, 0))
    themed_painter = QPainter(themed)
    draw_track_outline(themed_painter, QRect(0, 0, 64, 64), outline)
    themed_painter.end()

    print("Autoprueba finalizada correctamente.")
