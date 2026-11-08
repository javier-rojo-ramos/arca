"""Dibujos de una tarjeta que se comparten con otras vistas: marcador de tipo y aviso.

Los usan la tarjeta de la cuadrícula ('ThumbnailsDelegate') y la vista individual, para
que se vean idénticos en los dos sitios. Se dibujan con QPainter: no necesitan iconos del
.qrc y se ven nítidos a cualquier tamaño (como 'card_marks.py').

    draw_placeholder(painter, rect, media_type)
        Marcador de un archivo sin miniatura: fondo gris y un dibujo según su tipo:
            vídeo -> círculo con «reproducir»     audio -> corchea (♪)
            libro -> libro                        track -> recorrido
            foto (o tipo desconocido) -> paisaje
    draw_type_glyph(painter, box, media_type, color)
        Solo el dibujo del tipo, sin el fondo (la fila «Atributos» de la barra de filtros).
    draw_availability_badge(painter, badge, availability)
        Indicador de archivo no disponible, dentro del rectángulo 'badge':
            ausente       (MISSING) -> círculo naranja con «!»
            sin conexión  (OFFLINE) -> círculo gris con un disco tachado

Quien llama decide el tamaño y la posición (la tarjeta, 16 px en la esquina; la vista
individual, más grande).

1.1.0 'draw_type_glyph': el dibujo del tipo sin el fondo del marcador (paso A.3,
      «Atributos»). El marcador de las tarjetas no cambia.
1.0.0 Sacado de 'thumbnails_delegate.py' (2.12.0) sin cambios en el dibujo, para la vista
      individual (paso A.1).

Prueba rápida (dibuja en una imagen; no abre ninguna ventana):
    python -m ui_helpers.helpers.card_glyphs
"""

__version__ = "1.1.0"
__all__ = [
    "AVAILABLE",
    "MISSING",
    "MISSING_COLOR",
    "OFFLINE",
    "OFFLINE_COLOR",
    "draw_availability_badge",
    "draw_placeholder",
    "draw_type_glyph",
]

# Librerías estándar
from collections.abc import Callable

# Librerías de terceros (Qt)
from qtpy.QtCore import QPointF, QRect, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

# Módulos del proyecto
from ui_helpers.helpers.ui_theme import CARD_COLORS

# Disponibilidad del archivo (los mismos valores que AVAILABLE, MISSING y OFFLINE de
# 'core.catalog.media_queries'; no se importa 'core' para no depender de la base de datos)
AVAILABLE, MISSING, OFFLINE = 0, 1, 2

# Colores del indicador de no disponible (los mismos que el inspector, 'selection_section')
MISSING_COLOR = "#e8833a"  # ausente: naranja (hay que hacer algo)
OFFLINE_COLOR = "#7d7d7d"  # sin conexión: gris (volverá al conectar el disco)

# Tamaño del dibujo del marcador respecto al lado corto del marcador
DEFAULT_GLYPH_SCALE = 0.36

# Tipos de medio (los valores de 'core.catalog.media_types.MediaType')
_VIDEO, _AUDIO, _EBOOK, _TRACK = "video", "audio", "ebook", "track"


# -----------------------------------------------------------------------------
# Indicador de archivo no disponible
# -----------------------------------------------------------------------------


def draw_availability_badge(painter: QPainter, badge: QRectF, availability: int) -> None:
    """Dibuja el indicador de archivo no disponible dentro de 'badge' (un cuadrado).

    No hace nada si el archivo está disponible.
    """
    if availability not in (MISSING, OFFLINE):
        return
    size = badge.width()
    color = MISSING_COLOR if availability == MISSING else OFFLINE_COLOR

    painter.save()
    # Círculo con un borde oscuro fino: se distingue sobre cualquier miniatura
    painter.setPen(QPen(QColor(0, 0, 0, 140), 1.0))
    painter.setBrush(QColor(color))
    painter.drawEllipse(badge)

    center = badge.center()
    white = QPen(QColor("#ffffff"), size * 0.13, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(white)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if availability == MISSING:
        # «!»: un trazo vertical y un punto
        painter.drawLine(
            QPointF(center.x(), badge.top() + size * 0.24),
            QPointF(center.x(), badge.top() + size * 0.58),
        )
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center.x(), badge.top() + size * 0.76), size * 0.07, size * 0.07)
    else:
        # Disco (rectángulo redondeado) tachado por una diagonal
        disk = QRectF(0, 0, size * 0.52, size * 0.32)
        disk.moveCenter(center)
        thin = QPen(white)
        thin.setWidthF(size * 0.09)
        painter.setPen(thin)
        painter.drawRoundedRect(disk, size * 0.06, size * 0.06)
        painter.setPen(white)
        painter.drawLine(
            QPointF(badge.left() + size * 0.25, badge.bottom() - size * 0.25),
            QPointF(badge.right() - size * 0.25, badge.top() + size * 0.25),
        )
    painter.restore()


# -----------------------------------------------------------------------------
# Marcador de un archivo sin miniatura
# -----------------------------------------------------------------------------


def draw_placeholder(
    painter: QPainter,
    rect: QRect | QRectF,
    media_type: str | None,
    glyph_scale: float = DEFAULT_GLYPH_SCALE,
) -> None:
    """Marcador de un archivo sin miniatura: fondo y un dibujo sencillo según el tipo.

    Args:
        painter: Pintor ya preparado.
        rect: Zona del marcador (se rellena entera).
        media_type: Tipo de medio ('photo', 'video'...); uno desconocido, como una foto.
        glyph_scale: Tamaño del dibujo respecto al lado corto de 'rect'.
    """
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(CARD_COLORS.placeholder_bg))
    painter.drawRect(rect)

    # El dibujo, centrado y proporcional al lado corto del marcador
    side = min(rect.width(), rect.height()) * glyph_scale
    if side < 8:
        painter.restore()
        return  # demasiado pequeño para que se entienda
    # El centro del propio rectángulo (en un QRect, entero: igual que antes en la tarjeta)
    center = rect.center()
    box = QRectF(center.x() - side / 2, center.y() - side / 2, side, side)
    _draw_glyph(painter, box, media_type, QColor(CARD_COLORS.placeholder_glyph))
    painter.restore()


def draw_type_glyph(
    painter: QPainter, box: QRectF, media_type: str | None, color: QColor | str
) -> None:
    """Solo el dibujo del tipo (el del marcador, sin su fondo), en el cuadrado 'box'.

    Args:
        painter: Pintor ya preparado.
        box: Zona del dibujo (cuadrada).
        media_type: Tipo de medio ('photo', 'video'...); uno desconocido, como una foto.
        color: Color del dibujo.
    """
    painter.save()
    _draw_glyph(painter, box, media_type, QColor(color))
    painter.restore()


def _draw_glyph(painter: QPainter, box: QRectF, media_type: str | None, color: QColor) -> None:
    """El dibujo de un tipo en 'box', con su grosor de línea proporcional."""
    side = min(box.width(), box.height())
    line = QPen(color, max(1.5, side / 14), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin)  # fmt: skip
    draw: Callable[[QPainter, QRectF, QColor, QPen], None] = {
        _VIDEO: _glyph_video,
        _AUDIO: _glyph_audio,
        _EBOOK: _glyph_ebook,
        _TRACK: _glyph_track,
    }.get(media_type or "", _glyph_photo)
    draw(painter, box, color, line)


def _glyph_video(painter: QPainter, box: QRectF, color: QColor, line: QPen) -> None:
    """Círculo con el triángulo de «reproducir»."""
    painter.setPen(line)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(box)
    w, h, x, y = box.width(), box.height(), box.left(), box.top()
    triangle = QPolygonF(
        [QPointF(x + w * 0.40, y + h * 0.30), QPointF(x + w * 0.40, y + h * 0.70),
         QPointF(x + w * 0.72, y + h * 0.50)]
    )  # fmt: skip
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(triangle)


def _glyph_audio(painter: QPainter, box: QRectF, color: QColor, line: QPen) -> None:
    """Corchea (♪): cabeza ovalada inclinada, plica recta y banderita curva.

    Todo son figuras RELLENAS (sin trazos): los extremos quedan limpios, sin los remates
    redondeados que dejaba una línea gruesa.
    """
    w, h, x, y = box.width(), box.height(), box.left(), box.top()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    # Cabeza: óvalo inclinado unos 20 grados, abajo a la izquierda
    head_x, head_y = x + w * 0.34, y + h * 0.80
    head_rx, head_ry = w * 0.17, h * 0.12
    painter.save()
    painter.translate(head_x, head_y)
    painter.rotate(-20)
    painter.drawEllipse(QPointF(0, 0), head_rx, head_ry)
    painter.restore()

    # Plica: rectángulo fino cuyo borde derecho toca el lado derecho de la cabeza
    stem_w = line.widthF()
    stem_right = head_x + head_rx * 0.94
    top = y + h * 0.04
    painter.drawRect(QRectF(stem_right - stem_w, top, stem_w, head_y - top))

    # Banderita: curva exterior hasta la punta y curva interior de vuelta a la plica
    flag = QPainterPath(QPointF(stem_right, top))
    flag.cubicTo(
        QPointF(stem_right + w * 0.04, top + h * 0.16),
        QPointF(stem_right + w * 0.36, top + h * 0.22),
        QPointF(stem_right + w * 0.26, top + h * 0.56),
    )
    flag.cubicTo(
        QPointF(stem_right + w * 0.26, top + h * 0.36),
        QPointF(stem_right + w * 0.10, top + h * 0.30),
        QPointF(stem_right, top + h * 0.28),
    )
    flag.closeSubpath()
    painter.drawPath(flag)


def _glyph_ebook(painter: QPainter, box: QRectF, color: QColor, line: QPen) -> None:
    """Libro: tapa con el lomo y unas líneas de texto."""
    w, h, x, y = box.width(), box.height(), box.left(), box.top()
    painter.setPen(line)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    cover = QRectF(x + w * 0.18, y, w * 0.64, h)
    painter.drawRoundedRect(cover, w * 0.05, w * 0.05)
    spine = cover.left() + w * 0.12
    painter.drawLine(QPointF(spine, cover.top()), QPointF(spine, cover.bottom()))
    for fraction in (0.30, 0.45):
        line_y = y + h * fraction
        painter.drawLine(QPointF(spine + w * 0.10, line_y), QPointF(cover.right() - w * 0.10, line_y))


def _glyph_track(painter: QPainter, box: QRectF, color: QColor, line: QPen) -> None:
    """Recorrido: una línea quebrada con la salida y la llegada marcadas."""
    w, h, x, y = box.width(), box.height(), box.left(), box.top()
    points = [QPointF(x + w * fx, y + h * fy) for fx, fy in
              ((0.05, 0.85), (0.30, 0.55), (0.50, 0.70), (0.72, 0.30), (0.95, 0.15))]  # fmt: skip
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    painter.setPen(line)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    radius = w * 0.08
    for point in (points[0], points[-1]):
        painter.drawEllipse(point, radius, radius)


def _glyph_photo(painter: QPainter, box: QRectF, color: QColor, line: QPen) -> None:
    """Paisaje (marco, montaña y sol): una foto sin miniatura, o un tipo desconocido."""
    w, h, x, y = box.width(), box.height(), box.left(), box.top()
    frame = QRectF(x, y + h * 0.12, w, h * 0.76)
    painter.setPen(line)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(frame, w * 0.05, w * 0.05)
    mountain = QPolygonF(
        [QPointF(frame.left() + w * 0.08, frame.bottom() - h * 0.06),
         QPointF(frame.left() + w * 0.40, frame.top() + h * 0.30),
         QPointF(frame.left() + w * 0.62, frame.bottom() - h * 0.20),
         QPointF(frame.left() + w * 0.75, frame.top() + h * 0.45),
         QPointF(frame.right() - w * 0.08, frame.bottom() - h * 0.06)]
    )  # fmt: skip
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(mountain)
    sun = w * 0.08
    painter.drawEllipse(QPointF(frame.right() - w * 0.22, frame.top() + h * 0.20), sun, sun)


if __name__ == "__main__":
    # Autoprueba SIN ventana: dibuja en imágenes y mira los colores de algunos píxeles.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.helpers.card_glyphs
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtGui import QGuiApplication, QImage

    app = QGuiApplication([])

    def render(draw: Callable[[QPainter], None], size: int = 120) -> QImage:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw(painter)
        painter.end()
        return image

    def colors_in(image: QImage) -> set[str]:
        return {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}

    bg = QColor(CARD_COLORS.placeholder_bg).name()
    glyph = QColor(CARD_COLORS.placeholder_glyph).name()
    for media_type in ("photo", "video", "audio", "ebook", "track", None, "otro"):
        image = render(lambda p, t=media_type: draw_placeholder(p, QRect(0, 0, 120, 120), t))
        assert image.pixelColor(2, 2).name() == bg, media_type  # el fondo, en la esquina
        assert glyph in colors_in(image), media_type  # y el dibujo, dentro
    # Demasiado pequeño: solo el fondo
    tiny = render(lambda p: draw_placeholder(p, QRect(0, 0, 12, 12), "video"), size=12)
    assert colors_in(tiny) == {bg}
    # Solo el dibujo, sin fondo, en el color pedido
    for media_type in ("photo", "video", "audio", "ebook", "track"):
        image = render(lambda p, t=media_type: draw_type_glyph(p, QRectF(2, 2, 16, 16), t, "#ff0000"), size=20)
        assert image.pixelColor(0, 0).alpha() == 0, media_type  # sin fondo
        assert any(image.pixelColor(x, y).red() > 200 for x in range(20) for y in range(20)), media_type

    # Indicador: naranja si falta, gris sin conexión, nada si está disponible
    missing = render(lambda p: draw_availability_badge(p, QRectF(10, 10, 100, 100), MISSING))
    offline = render(lambda p: draw_availability_badge(p, QRectF(10, 10, 100, 100), OFFLINE))
    nothing = render(lambda p: draw_availability_badge(p, QRectF(10, 10, 100, 100), AVAILABLE))
    assert missing.pixelColor(20, 60).name() == MISSING_COLOR
    assert offline.pixelColor(20, 60).name() == OFFLINE_COLOR
    assert nothing.pixelColor(60, 60).alpha() == 0
    assert "#ffffff" in colors_in(missing) and "#ffffff" in colors_in(offline)
    print("Autoprueba finalizada correctamente.")
