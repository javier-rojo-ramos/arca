"""Dibujo del perfil de elevación con QPainter (lo usa 'ElevationProfile').

El widget ('ui_helpers/widgets/elevation_profile.py') guarda el estado (el perfil, el
cursor, el tramo elegido, el estilo) y atiende al ratón; aquí está CÓMO se dibuja, en
tres piezas:

    layout = build_layout(rect, metrics, style, data)
        Dónde va cada cosa: la línea de arriba, la gráfica, las marcas de los ejes y la
        escala (distancia -> x, altitud -> y). None si no hay curva que dibujar.

    pixmap = render_static(size, dpr, font, style, data, layout, runs, bands)
        Lo que NO cambia al mover el ratón: el fondo, la rejilla, los ejes con sus números,
        el área, la línea y las rayas de los saltos de segmento. El widget lo guarda y solo
        lo rehace al cambiar el tamaño, el perfil o el estilo. Los colores de la pendiente
        salen de la franja de cada punto ('bands'), ya calculada con histéresis.

    paint_overlay(painter, ...)
        Lo que cambia con el ratón: la línea de arriba (totales o tramo), la banda del
        tramo elegido y el cursor (línea vertical, círculo sobre la curva y su etiqueta).
        Se pinta encima en cada movimiento: es poco.

    ┌──────────────────────────────────────────────────────────────┐
    │   Distancia 18,4 km  ·  ↑ 556 m  ·  ↓ 566 m  ·  Mín. ...     │  <- línea de arriba
    │ 1.800 m ┤· · · · · · · · · · · · ·│· · · · · · · · · · · ·   │
    │ 1.600 m ┤· · · · · · ▁▂▃▅▆▇▇▇▆▅▃●│1.639 m · · · · · · · ·   │  <- cursor y etiqueta
    │ 1.400 m ┤· ·▁▂▃▅▆▇██████████████████▇▆▅▃▂▁ · · · · · · · ·   │
    │         └──────────────────────────────────────────────      │
    │         0 km    2 km    4 km    6 km    8 km   10 km ...     │
    └──────────────────────────────────────────────────────────────┘

La curva es la altitud SUAVIZADA del perfil; los números (cabecera, etiqueta), los de la
altitud sin suavizar ('core/tracks/profile.py'). Todos los colores y grosores salen del
estilo ('profile_style.py').

1.0.0 Primera versión (15/11/2026; docs/MOD_TRACKS.md, paso 5.2).
"""

__version__ = "1.0.0"
__all__ = ["ProfileLayout", "build_layout", "paint_overlay", "render_static"]

# Librerías estándar
import math
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtCore import QPointF, QRectF, QSize, Qt
from qtpy.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPixmap, QPolygonF

# Módulos del proyecto
from core.tracks.profile import ElevationProfileData
from ui_helpers.helpers.profile_format import (
    altitude_tick_label,
    cursor_lines,
    distance_tick_label,
    nice_range,
    nice_step,
    ticks,
)
from ui_helpers.helpers.profile_style import ProfileStyle, SlopeMode

# Medidas (px lógicos)
_PAD = 8  # margen exterior
_LABEL_GAP = 6  # entre los números de un eje y la gráfica
_HEADER_GAP = 4  # aire bajo la línea de arriba
_Y_TICK_SPACING = 26  # alto mínimo entre dos marcas de altitud
_X_LABEL_GAP = 28  # aire mínimo entre dos números del eje de distancias
_CURSOR_LABEL_GAP = 8  # de la línea del cursor a su etiqueta
_CURSOR_LABEL_PAD = (6, 3)  # relleno de la etiqueta (horizontal, vertical)

_GRID_PEN_STYLES = {
    "solid": Qt.PenStyle.SolidLine,
    "dash": Qt.PenStyle.DashLine,
    "dot": Qt.PenStyle.DotLine,
    "none": Qt.PenStyle.NoPen,
}


@dataclass(frozen=True, slots=True)
class ProfileLayout:
    """Dónde va cada cosa del perfil y su escala (ver el docstring del archivo).

    Attributes:
        header: La franja de la línea de arriba (None si el estilo no la muestra).
        plot: El rectángulo de la gráfica (los ejes son su borde izquierdo e inferior).
        distance_max: Distancia del final del recorrido (la gráfica va de 0 a ella).
        altitude_low: Altitud del borde inferior de la gráfica.
        altitude_high: Altitud del borde superior.
        x_ticks: Distancias de las marcas del eje horizontal.
        x_step: Paso entre esas marcas (decide si se escriben en km o en m).
        y_ticks: Altitudes de las marcas del eje vertical.
    """

    header: QRectF | None
    plot: QRectF
    distance_max: float
    altitude_low: float
    altitude_high: float
    x_ticks: tuple[float, ...]
    x_step: float
    y_ticks: tuple[float, ...]

    def x(self, distance_m: float) -> float:
        """Posición horizontal de una distancia."""
        span = self.distance_max if self.distance_max > 0 else 1.0
        return self.plot.left() + distance_m / span * self.plot.width()

    def y(self, altitude_m: float) -> float:
        """Posición vertical de una altitud."""
        span = self.altitude_high - self.altitude_low
        return self.plot.bottom() - (altitude_m - self.altitude_low) / span * self.plot.height()

    def distance_at(self, x: float) -> float:
        """La distancia bajo una posición horizontal (fuera de la gráfica, la del borde)."""
        if self.plot.width() <= 0:
            return 0.0
        fraction = min(1.0, max(0.0, (x - self.plot.left()) / self.plot.width()))
        return fraction * self.distance_max


def build_layout(
    rect: QRectF, metrics: QFontMetricsF, style: ProfileStyle, data: ElevationProfileData | None
) -> ProfileLayout | None:
    """Coloca la línea de arriba, la gráfica y las marcas de los ejes en 'rect'.

    Returns:
        La colocación, o None si no hay curva que dibujar (sin perfil o sin altitud).
    """
    totals = data.totals if data is not None else None
    if totals is None or totals.elevation_min_m is None or totals.elevation_max_m is None:
        return None
    line_height = metrics.height()
    header = None
    top = rect.top() + _PAD / 2
    if style.show_header:
        header = QRectF(rect.left(), top, rect.width(), line_height)
        top = header.bottom() + _HEADER_GAP
    top += line_height / 2  # para que quepa entero el número de la marca más alta
    bottom = rect.bottom() - _PAD / 2 - line_height - _LABEL_GAP / 2
    height = max(10.0, bottom - top)

    # Eje vertical: sus marcas deciden el ancho de los números y, con él, dónde empieza
    low, high, step = nice_range(
        totals.elevation_min_m, totals.elevation_max_m, max(2, int(height // _Y_TICK_SPACING))
    )
    y_ticks = tuple(ticks(low, high, step))
    label_width = max(metrics.horizontalAdvance(altitude_tick_label(v)) for v in y_ticks)
    left = rect.left() + _PAD + label_width + _LABEL_GAP
    right = rect.right() - _PAD * 2
    width = max(10.0, right - left)

    # Eje horizontal: tantas marcas como quepan con sus números separados
    distance_max = totals.distance_m
    widest = metrics.horizontalAdvance(distance_tick_label(distance_max, 1000.0))
    x_step = nice_step(distance_max, max(2, int(width // (widest + _X_LABEL_GAP))))
    x_ticks = tuple(ticks(0.0, distance_max, x_step))
    plot = QRectF(left, top, width, height)
    return ProfileLayout(header, plot, distance_max, low, high, x_ticks, x_step, y_ticks)


# -----------------------------------------------------------------------------
# Lo fijo: rejilla, ejes, área y línea
# -----------------------------------------------------------------------------


def render_static(
    size: QSize,
    device_pixel_ratio: float,
    font: QFont,
    style: ProfileStyle,
    data: ElevationProfileData | None,
    layout: ProfileLayout | None,
    runs: list[list[int]],
    bands: list[int],
) -> QPixmap:
    """Dibuja lo que no cambia con el ratón (ver el docstring del archivo).

    Args:
        runs: Los trozos de puntos que se dibujan ('core.tracks.profile.drawing_runs').
        bands: La franja de pendiente de cada punto del perfil ('profile_style.slope_bands').
    """
    pixmap = QPixmap(
        max(1, math.ceil(size.width() * device_pixel_ratio)),
        max(1, math.ceil(size.height() * device_pixel_ratio)),
    )
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(QColor(style.colors.background))
    if data is None or layout is None:
        return pixmap
    painter = QPainter(pixmap)
    painter.setFont(font)
    _draw_grid_and_axes(painter, QFontMetricsF(font), style, layout, size)
    _draw_curve(painter, style, data, layout, runs, bands)
    if style.show_segment_breaks:
        _draw_segment_breaks(painter, style, data, layout)
    painter.end()
    return pixmap


def _crisp(value: float) -> float:
    """Coordenada en el centro de un píxel: una raya de 1 px sale nítida, no en dos grises."""
    return math.floor(value) + 0.5


def _draw_grid_and_axes(
    painter: QPainter,
    metrics: QFontMetricsF,
    style: ProfileStyle,
    layout: ProfileLayout,
    size: QSize,
) -> None:
    colors, plot = style.colors, layout.plot
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    # Rejilla: una raya por marca (las del borde son los ejes)
    pen = QPen(QColor(colors.grid), style.grid_width, _GRID_PEN_STYLES[style.grid_pattern])
    pen.setCosmetic(True)
    painter.setPen(pen)
    for altitude in layout.y_ticks:
        y = layout.y(altitude)
        if y < plot.bottom() - 1:
            painter.drawLine(QPointF(plot.left(), _crisp(y)), QPointF(plot.right(), _crisp(y)))
    for distance in layout.x_ticks:
        x = layout.x(distance)
        if x > plot.left() + 1:
            painter.drawLine(QPointF(_crisp(x), plot.top()), QPointF(_crisp(x), plot.bottom()))

    # Ejes: abajo y a la izquierda
    painter.setPen(QPen(QColor(colors.axis), 1))
    bottom, left = _crisp(plot.bottom()), _crisp(plot.left())
    painter.drawLine(QPointF(left, plot.top()), QPointF(left, bottom))
    painter.drawLine(QPointF(left, bottom), QPointF(plot.right(), bottom))

    # Números: los de altitud a la izquierda, centrados en su raya; los de distancia
    # debajo, centrados en la suya pero sin salirse del widget
    painter.setPen(QColor(colors.axis_text))
    line_height = metrics.height()
    labels_width = plot.left() - _LABEL_GAP - _PAD / 2
    right_middle = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    for altitude in layout.y_ticks:
        box = QRectF(_PAD / 2, layout.y(altitude) - line_height / 2, labels_width, line_height)
        painter.drawText(box, right_middle, altitude_tick_label(altitude))
    top = plot.bottom() + _LABEL_GAP / 2
    for distance in layout.x_ticks:
        text = distance_tick_label(distance, layout.x_step)
        width = metrics.horizontalAdvance(text)
        left_edge = min(max(0.0, layout.x(distance) - width / 2), size.width() - width)
        box = QRectF(left_edge, top, width + 1, line_height)
        painter.drawText(box, Qt.AlignmentFlag.AlignLeft, text)


def _band_color(style: ProfileStyle, band: int, fallback: str, opacity: float = 1.0) -> QColor:
    """Color de una franja de pendiente (-1, la desconocida: 'fallback')."""
    color = QColor(style.colors.slope[band] if band >= 0 else fallback)
    color.setAlphaF(opacity if band >= 0 else 1.0)
    return color


def _draw_curve(
    painter: QPainter,
    style: ProfileStyle,
    data: ElevationProfileData,
    layout: ProfileLayout,
    runs: list[list[int]],
    point_bands: list[int],
) -> None:
    """El área bajo la curva y la línea, según cómo se muestre la pendiente."""
    colors = style.colors
    distances, smoothed = data.distances, data.smoothed
    floor = layout.plot.bottom()
    painter.setPen(Qt.PenStyle.NoPen)

    for run in runs:
        points = [QPointF(layout.x(distances[i]), layout.y(smoothed[i])) for i in run]
        if len(points) < 2:
            continue
        # Franja de cada tramo entre dos puntos dibujados: la de su final
        bands = [point_bands[i] for i in run[1:]]

        if style.slope_mode is SlopeMode.AREA:
            # Una figura por grupo de tramos seguidos de la misma franja. Sin suavizado de
            # bordes: con él, entre dos figuras vecinas se vería una raya del fondo (la
            # línea, encima y con suavizado, tapa el borde de arriba)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for start, end, band in _groups(bands):
                top_edge = points[start : end + 2]
                polygon = QPolygonF([*top_edge, QPointF(top_edge[-1].x(), floor),
                                     QPointF(top_edge[0].x(), floor)])  # fmt: skip
                painter.setBrush(_band_color(style, band, colors.area, style.slope_area_opacity))
                painter.drawPolygon(polygon)
        else:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QColor(colors.area))
            painter.drawPolygon(QPolygonF([*points, QPointF(points[-1].x(), floor),
                                           QPointF(points[0].x(), floor)]))  # fmt: skip

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if style.slope_mode is SlopeMode.LINE:
            # Una línea por grupo de la misma franja; con extremos redondos, las uniones
            # entre colores no dejan huecos
            for start, end, band in _groups(bands):
                pen = QPen(_band_color(style, band, colors.line), style.slope_line_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawPolyline(QPolygonF(points[start : end + 2]))
        else:
            pen = QPen(QColor(colors.line), style.line_width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF(points))
        painter.setPen(Qt.PenStyle.NoPen)


def _groups(bands: list[int]) -> list[tuple[int, int, int]]:
    """Agrupa los tramos seguidos de la misma franja: (primer tramo, último, franja). El
    tramo k va del punto k al k + 1."""
    groups: list[tuple[int, int, int]] = []
    start = 0
    for k in range(1, len(bands) + 1):
        if k == len(bands) or bands[k] != bands[start]:
            groups.append((start, k - 1, bands[start]))
            start = k
    return groups


def _draw_segment_breaks(
    painter: QPainter, style: ProfileStyle, data: ElevationProfileData, layout: ProfileLayout
) -> None:
    """Una raya discontinua donde empieza cada segmento (salvo el primero)."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    pen = QPen(QColor(style.colors.segment_break), 1, Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    painter.setPen(pen)
    plot = layout.plot
    for start in data.segment_starts[1:]:
        x = _crisp(layout.x(data.distances[start]))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))


# -----------------------------------------------------------------------------
# Lo que cambia con el ratón: línea de arriba, tramo y cursor
# -----------------------------------------------------------------------------


def paint_overlay(
    painter: QPainter,
    rect: QRectF,
    font: QFont,
    style: ProfileStyle,
    data: ElevationProfileData | None,
    layout: ProfileLayout | None,
    *,
    header: str,
    message: str,
    cursor: int | None,
    selection: tuple[int, int] | None,
) -> None:
    """Pinta encima de lo fijo (ver el docstring del archivo).

    Args:
        header: Texto de la línea de arriba (vacío, nada).
        message: Aviso en el centro (vacío, nada): sin perfil, o sin altitud.
        cursor: Punto del cursor (None, sin cursor).
        selection: Tramo elegido (primero, último), o None.
    """
    colors = style.colors
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    if header and style.show_header:
        line = layout.header if layout is not None and layout.header is not None else QRectF(
            rect.left(), rect.top() + _PAD / 2, rect.width(), metrics.height()
        )
        painter.setPen(QColor(colors.header_text))
        text = metrics.elidedText(header, Qt.TextElideMode.ElideRight, line.width() - 2 * _PAD)
        painter.drawText(line, Qt.AlignmentFlag.AlignCenter, text)
    if message:
        painter.setPen(QColor(colors.message_text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, message)
    if data is None or layout is None:
        return
    plot = layout.plot

    if selection is not None:
        first, last = selection
        left, right = layout.x(data.distances[first]), layout.x(data.distances[last])
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(QRectF(left, plot.top(), max(1.0, right - left), plot.height()),
                         QColor(colors.selection))  # fmt: skip
        painter.setPen(QPen(QColor(colors.selection_edge), 1))
        for x in (left, right):
            painter.drawLine(QPointF(_crisp(x), plot.top()), QPointF(_crisp(x), plot.bottom()))

    if cursor is not None:
        _draw_cursor(painter, metrics, style, data, layout, cursor)


def _draw_cursor(
    painter: QPainter,
    metrics: QFontMetricsF,
    style: ProfileStyle,
    data: ElevationProfileData,
    layout: ProfileLayout,
    index: int,
) -> None:
    """Línea vertical, círculo sobre la curva (si el punto tiene altitud) y etiqueta."""
    colors, plot = style.colors, layout.plot
    x = layout.x(data.distances[index])

    # La línea, con un borde oscuro a cada lado: se lee sobre cualquier color de la pendiente
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    strokes = ((colors.cursor_outline, style.cursor_width + 2), (colors.cursor, style.cursor_width))
    for color, width in strokes:
        pen = QPen(QColor(color), width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(_crisp(x), plot.top()), QPointF(_crisp(x), plot.bottom()))

    # El círculo, como el punto ámbar del mapa
    value = data.smoothed[index]
    curve_y: float | None = None
    if not math.isnan(value):
        curve_y = layout.y(value)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(colors.cursor_outline), 1.5))
        painter.setBrush(QColor(colors.cursor))
        painter.drawEllipse(QPointF(_crisp(x), curve_y), style.cursor_radius, style.cursor_radius)

    # La etiqueta: a la derecha de la línea (a la izquierda si no cabe), arriba (abajo si
    # el círculo está en la mitad de arriba, para no taparlo)
    lines = cursor_lines(data, index)
    pad_x, pad_y = _CURSOR_LABEL_PAD
    width = max(metrics.horizontalAdvance(line) for line in lines) + 2 * pad_x
    height = len(lines) * metrics.height() + 2 * pad_y
    left = x + _CURSOR_LABEL_GAP
    if left + width > plot.right():
        left = x - _CURSOR_LABEL_GAP - width
    top = plot.top() + 2
    if curve_y is not None and curve_y < plot.top() + plot.height() / 2:
        top = plot.bottom() - height - 2
    box = QRectF(left, top, width, height)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colors.label_background))
    painter.drawRoundedRect(box, 3, 3)
    painter.setPen(QColor(colors.label_text))
    for number, line in enumerate(lines):
        row = QRectF(left + pad_x, top + pad_y + number * metrics.height(), width - 2 * pad_x,
                     metrics.height())  # fmt: skip
        painter.drawText(row, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
