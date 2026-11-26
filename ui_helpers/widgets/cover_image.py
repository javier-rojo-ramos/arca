"""Recuadro cuadrado con una imagen ajustada dentro: la carátula del inspector.

Lo usa la sección «Carátula» ('ui_helpers/inspector/cover_section.py'), a todo el ancho
del inspector; más adelante (MUS 9) recibirá también las imágenes que se suelten encima.

    cover = CoverImage(parent, media_type="audio")
    cover.set_image(image)      # una QImage; None o una nula: el marcador de su tipo
    cover.has_image()
    cover.image_rect()          # dónde se dibuja la imagen (o el marcador)

Cómo se ve (acordado con el autor el 26/11/2026):
    - CUADRADO: su alto es su ancho (lo fija él mismo al cambiar de ancho: 'resizeEvent').
      Así la sección no cambia de alto al pasar de una canción a otra, aunque una carátula
      no sea cuadrada. No sirve 'heightForWidth' de Qt: la pila de secciones del inspector
      ('SectionStack', con su alto como máximo) no lo tiene en cuenta.
    - La imagen, ajustada al cuadrado sin deformarla y centrada. Las pequeñas se AMPLÍAN
      hasta llenarlo, como en Mp3tag ('ENLARGE_SMALL'; el autor lo quiere probar así: con
      False, van a su tamaño, centradas). La fila «Imagen» dice siempre su tamaño real.
    - Sin imagen, el marcador de las tarjetas ('card_glyphs.draw_placeholder'), en todo el
      cuadrado.
    - Una raya fina alrededor de la imagen (o del marcador), del color de los separadores
      del inspector ('COLORS.line'): sin ella, una portada oscura se pierde en el fondo del
      panel ('BORDER'; el autor elige con las capturas).

La imagen reducida se guarda (un QPixmap a los píxeles físicos de la pantalla): solo se
vuelve a reducir al cambiar la imagen o el tamaño del recuadro.

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 9.1).

Prueba rápida (desde la raíz del proyecto; no abre ventanas):
    python -m ui_helpers.widgets.cover_image
"""

__version__ = "1.0.0"
__all__ = ["BORDER", "ENLARGE_SMALL", "CoverImage"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint, QRect, QRectF, QSize, Qt
from qtpy.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from qtpy.QtWidgets import QSizePolicy, QWidget

# Módulos del proyecto
from ui_helpers.helpers import card_glyphs
from ui_helpers.helpers.ui_theme import COLORS

# Las imágenes más pequeñas que el recuadro se amplían hasta llenarlo (False: a su tamaño)
ENLARGE_SMALL = True
# Raya fina alrededor de la imagen o del marcador
BORDER = True
# Lado que pide el recuadro si nadie le da otro (px lógicos); el de verdad, el del panel
_DEFAULT_SIDE = 240
_MINIMUM_SIDE = 48


class CoverImage(QWidget):
    """Recuadro cuadrado con una imagen o el marcador (ver el docstring del archivo)."""

    def __init__(self, parent: QWidget | None = None, *, media_type: str = "audio") -> None:
        super().__init__(parent)
        self._media_type = media_type
        self._image: QImage | None = None
        self.border = BORDER
        # La imagen reducida para el tamaño de ahora: ((ancho, alto, escala), pixmap)
        self._scaled: tuple[tuple[int, int, float], QPixmap] | None = None
        # A lo ancho, el que le dé el layout; a lo alto, fijo: el ancho (ver 'resizeEvent')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(_DEFAULT_SIDE)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def set_image(self, image: QImage | None) -> None:
        """Pone la imagen (None o una nula: el marcador). La misma de antes, nada."""
        new = image if image is not None and not image.isNull() else None
        old = self._image
        if new is None and old is None:
            return
        if new is not None and old is not None and new.cacheKey() == old.cacheKey():
            return
        self._image = new
        self._scaled = None
        self.update()

    def has_image(self) -> bool:
        """True si enseña una imagen (no el marcador)."""
        return self._image is not None

    def image_rect(self) -> QRect:
        """Dónde se dibuja la imagen: ajustada al cuadrado y centrada. Sin imagen, el
        cuadrado entero (el marcador)."""
        square = self._square()
        if self._image is None or square.isEmpty():
            return square
        width, height = self._image.width(), self._image.height()
        side = square.width()
        # A su tamaño (sin ampliar), un píxel de la imagen es uno de la pantalla
        natural = max(width, height) / self.devicePixelRatioF()
        scale = side / max(width, height)
        if not ENLARGE_SMALL and natural < side:
            scale = 1 / self.devicePixelRatioF()
        size = QSize(max(1, round(width * scale)), max(1, round(height * scale)))
        corner = QPoint(
            square.x() + (side - size.width()) // 2, square.y() + (side - size.height()) // 2
        )
        return QRect(corner, size)

    # -------------------------------------------------------------------------
    # QWidget
    # -------------------------------------------------------------------------

    def sizeHint(self) -> QSize:  # nombre de Qt
        return QSize(_DEFAULT_SIDE, self.minimumHeight())

    def minimumSizeHint(self) -> QSize:  # nombre de Qt
        return QSize(_MINIMUM_SIDE, self.minimumHeight())

    def resizeEvent(self, event) -> None:  # nombre de Qt
        """Al cambiar de ancho, el alto pasa a ser el mismo (el layout lo coloca después)."""
        super().resizeEvent(event)
        side = max(_MINIMUM_SIDE, event.size().width())
        if side != self.minimumHeight():
            self.setFixedHeight(side)

    def paintEvent(self, event) -> None:  # nombre de Qt
        painter = QPainter(self)
        frame = self.image_rect()
        if frame.isEmpty():
            return
        if self._image is None:
            card_glyphs.draw_placeholder(painter, frame, self._media_type)
        else:
            painter.drawPixmap(frame.topLeft(), self._scaled_pixmap(frame.size()))
        if self.border:
            painter.setPen(QPen(QColor(COLORS.line), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Por dentro del borde: tapa el píxel de fuera de la imagen, no la agranda
            painter.drawRect(QRectF(frame).adjusted(0.5, 0.5, -0.5, -0.5))

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _square(self) -> QRect:
        """El cuadrado: el lado menor del widget, centrado a lo ancho (arriba del todo)."""
        side = min(self.width(), self.height())
        return QRect((self.width() - side) // 2, 0, side, side)

    def _scaled_pixmap(self, size: QSize) -> QPixmap:
        """La imagen reducida a ese tamaño (en px lógicos), a los píxeles físicos de la
        pantalla. Se guarda hasta que cambie la imagen o el tamaño."""
        ratio = self.devicePixelRatioF()
        key = (size.width(), size.height(), ratio)
        if self._scaled is not None and self._scaled[0] == key:
            return self._scaled[1]
        assert self._image is not None
        physical = QSize(round(size.width() * ratio), round(size.height() * ratio))
        scaled = self._image.scaled(
            physical,
            Qt.AspectRatioMode.IgnoreAspectRatio,  # 'image_rect' ya conserva la proporción
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap = QPixmap.fromImage(scaled)
        pixmap.setDevicePixelRatio(ratio)
        self._scaled = (key, pixmap)
        return pixmap


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen': nada se ve en pantalla).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.cover_image
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication, QVBoxLayout

    from ui_helpers.helpers.ui_theme import CARD_COLORS

    app = QApplication([])

    def solid(width: int, height: int, color: str) -> QImage:
        """Una imagen de prueba de un solo color."""
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        return image

    def pixel(widget: QWidget, x: int, y: int) -> str:
        """El color de un punto del widget dibujado (a escala 1)."""
        return widget.grab().toImage().pixelColor(x, y).name()

    # Dentro de un layout, como en el inspector (mostrado sin pantalla: 'offscreen')
    holder = QWidget()
    holder.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    holder_layout = QVBoxLayout(holder)
    holder_layout.setContentsMargins(0, 0, 0, 0)
    cover = CoverImage(holder)
    holder_layout.addWidget(cover)
    holder_layout.addStretch(1)
    holder.resize(300, 600)
    holder.show()
    app.processEvents()
    assert (cover.width(), cover.height()) == (300, 300), cover.size()  # el alto, el ancho
    holder.resize(220, 600)  # más estrecho: más bajo
    app.processEvents()
    assert (cover.width(), cover.height()) == (220, 220), cover.size()
    holder.resize(300, 600)
    app.processEvents()

    # 1. Sin imagen: el marcador en todo el cuadrado, con la raya
    assert not cover.has_image() and cover.image_rect() == QRect(0, 0, 300, 300)
    assert pixel(cover, 0, 0) == QColor(COLORS.line).name()
    assert pixel(cover, 5, 5) == QColor(CARD_COLORS.placeholder_bg).name()

    # 2. Una cuadrada grande: reducida a todo el cuadrado
    cover.set_image(solid(1200, 1200, "#204080"))
    assert cover.has_image() and cover.image_rect() == QRect(0, 0, 300, 300)
    assert pixel(cover, 150, 150) == "#204080" and pixel(cover, 0, 150) == QColor(COLORS.line).name()

    # 3. Apaisada: a todo el ancho, centrada en alto (el recuadro sigue cuadrado)
    cover.set_image(solid(1200, 800, "#802040"))
    assert cover.image_rect() == QRect(0, 50, 300, 200), cover.image_rect()

    # 4. Pequeña: ampliada hasta llenarlo ('ENLARGE_SMALL')
    cover.set_image(solid(100, 100, "#408020"))
    assert cover.image_rect() == QRect(0, 0, 300, 300)

    # 5. La misma imagen otra vez: no se vuelve a reducir; una nula: el marcador
    small = solid(100, 100, "#408020")
    cover.set_image(small)
    cover.grab()
    kept = cover._scaled
    cover.set_image(small)
    assert cover._scaled is kept
    cover.set_image(QImage())
    assert not cover.has_image()

    # 6. Sin raya: el borde es de la imagen
    cover.border = False
    cover.set_image(solid(1200, 1200, "#204080"))
    assert pixel(cover, 0, 0) == "#204080"

    # 7. Más ancho que alto (oculto, aún sin su alto): el cuadrado, centrado a lo ancho
    lone = CoverImage()
    lone.resize(400, 240)
    assert lone.height() == 240 and lone.image_rect() == QRect(80, 0, 240, 240)
    lone.deleteLater()
    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
