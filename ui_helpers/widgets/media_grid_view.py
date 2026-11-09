"""Cuadrícula de tarjetas con una imagen de arrastre pequeña y semitransparente.

'QListView', en modo iconos, arrastra una imagen con TODAS las tarjetas seleccionadas a
tamaño real y con el cursor donde se pulsó: al llevarlas a la barra lateral tapan la
colección de destino y cuesta acertar. Esta vista solo cambia esa imagen (como Lightroom):

    ┌──┐
    │  │┐   <- miniatura de la tarjeta pulsada (~72 px), algo transparente, con borde
    └──┘┘   <- si hay varias, "pila" de tarjetas detrás y un contador en color de acento
       (12)

La imagen va ABAJO A LA DERECHA del cursor, separada unos píxeles, para que la punta del
cursor (lo que decide dónde se suelta) quede siempre a la vista.

Además, los clics en las zonas activas de una tarjeta (estrellas, marca, círculo de la
selección rápida) se atienden AQUÍ, antes de que Qt toque la selección, y se envían al
delegado ('ThumbnailsDelegate.handle_click'). Sin esto, al pulsar una estrella de una
tarjeta que forma parte de una selección múltiple, Qt dejaba seleccionada solo esa al
soltar el botón (así funciona la selección extendida de 'QListView' para poder arrastrar
varias). Ahora la selección se conserva y el valor se aplica a todas.

Lo que se arrastra (los 'id' de las tarjetas) no cambia: lo sigue preparando el modelo
('MediaGridModel.mimeData'). Se promociona en el .ui: 'list_view_grid' es un
'MediaGridView' (cabecera 'ui_helpers/widgets/media_grid_view.h').

1.2.0 Colores del tema: el borde de la imagen arrastrada ('CARD_COLORS.drag_border') y el
      número de la insignia, oscuro sobre el acento ('text_on_accent'; antes blanco, que
      sobre el ámbar no se leía).
"""

__version__ = "1.2.0"
__all__ = ["MediaGridView"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QPoint, QRectF, Qt
from qtpy.QtGui import QColor, QDrag, QFont, QIcon, QImage, QMouseEvent, QPainter, QPen, QPixmap
from loguru import logger
from qtpy.QtWidgets import QListView, QWidget

# Módulos del proyecto
from ui_helpers.helpers.ui_theme import ACCENT_COLOR, CARD_COLORS, COLORS, GRID_BG

# Lado máximo de la miniatura arrastrada (píxeles lógicos)
DRAG_THUMB_SIDE = 72
# Separación entre la punta del cursor y la imagen (abajo a la derecha)
DRAG_CURSOR_GAP = 14
# Opacidad de la imagen (1 = opaca): deja intuir lo que hay debajo
DRAG_OPACITY = 0.8
# Desplazamiento de cada tarjeta de la "pila" (cuando se arrastran varias)
DRAG_STACK_STEP = 4
# Tarjetas de la pila que se dibujan detrás como mucho
DRAG_STACK_MAX = 2


class MediaGridView(QListView):
    """'QListView' de la cuadrícula, con una imagen de arrastre propia."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # True desde que se pulsa en una zona activa hasta que se suelta el botón: los
        # eventos de ese clic (mover, soltar) no llegan a Qt (no seleccionan ni arrastran)
        self._swallowing_click = False

    # -------------------------------------------------------------------------
    # Clics en las zonas activas de la tarjeta (estrellas, marca, círculo)
    # -------------------------------------------------------------------------

    def _active_zone_click(self, event: QMouseEvent) -> bool:
        """Envía al delegado un clic izquierdo en una zona activa de una tarjeta.

        Con Ctrl, Alt o Meta el clic se deja a Qt (Ctrl + clic = añadir o quitar de la
        selección). Mayús sí pasa: el delegado la usa en la marca (rechazar).

        Returns:
            True si era una zona activa (el clic ya está atendido).
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(pos)
        if not index.isValid():
            return False
        delegate = self.itemDelegateForIndex(index) if hasattr(self, "itemDelegateForIndex") else self.itemDelegate()
        if not hasattr(delegate, "handle_click"):
            return False
        rect = self.visualRect(index)
        if event.type() == QEvent.Type.MouseButtonDblClick:
            # Doble clic en una zona activa: el primer clic ya la cambió; no se repite
            # (ni se abre nada)
            return delegate.is_active_zone(rect, index, pos)
        return delegate.handle_click(pos, event.modifiers(), self.model(), rect, index, self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - nombre de Qt
        if self._active_zone_click(event):
            self._swallowing_click = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - nombre de Qt
        if self._active_zone_click(event):
            self._swallowing_click = True
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - nombre de Qt
        if self._swallowing_click and event.buttons() != Qt.MouseButton.NoButton:
            event.accept()  # arrastrar desde una estrella no selecciona ni arrastra tarjetas
            return
        self._swallowing_click = False
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - nombre de Qt
        if self._swallowing_click:
            self._swallowing_click = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------------------
    # Arrastre
    # -------------------------------------------------------------------------

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # noqa: N802 - nombre de Qt
        """Empieza a arrastrar las tarjetas seleccionadas, con una imagen pequeña.

        Hace lo mismo que 'QAbstractItemView.startDrag' (datos del modelo, solo copiar),
        salvo la imagen: en lugar de todas las tarjetas a tamaño real, una miniatura.
        """
        indexes = [
            index
            for index in self.selectedIndexes()
            if index.isValid() and (self.model().flags(index) & Qt.ItemFlag.ItemIsDragEnabled)
        ]
        if not indexes:
            return
        logger.debug(f"Arrastre de {len(indexes)} tarjeta(s) con imagen reducida.")
        mime = self.model().mimeData(indexes)
        if mime is None:
            return

        # La tarjeta "principal" es la que se pulsó (la actual), si forma parte de lo arrastrado
        current = self.currentIndex()
        main = current if current in indexes else indexes[0]

        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self._drag_pixmap(main.data(Qt.ItemDataRole.DecorationRole), len(indexes))
        drag.setPixmap(pixmap)
        # Punto de agarre en la esquina superior izquierda: la imagen (que empieza tras el
        # margen transparente) queda abajo a la derecha de la punta del cursor
        drag.setHotSpot(QPoint(0, 0))
        drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)

    def _drag_pixmap(self, decoration: object, count: int) -> QPixmap:
        """Dibuja la imagen de arrastre.

        Args:
            decoration: Lo que da el modelo como imagen de la tarjeta (QPixmap, QImage,
                QIcon o None si aún no hay miniatura).
            count: Número de tarjetas arrastradas.

        Returns:
            Imagen con un margen transparente arriba a la izquierda (DRAG_CURSOR_GAP).
        """
        ratio = self.devicePixelRatioF()
        thumb = self._thumbnail_image(decoration, ratio)

        # Tamaño de la miniatura en píxeles lógicos (proporción del original, lado ≤ 72)
        if thumb is not None and not thumb.isNull():
            logical_w = thumb.width() / ratio
            logical_h = thumb.height() / ratio
            scale = min(DRAG_THUMB_SIDE / max(logical_w, 1), DRAG_THUMB_SIDE / max(logical_h, 1), 1.0)
            thumb_w, thumb_h = max(1.0, logical_w * scale), max(1.0, logical_h * scale)
        else:
            thumb_w = thumb_h = DRAG_THUMB_SIDE * 0.75  # cuadro gris si aún no hay miniatura

        stack = min(count - 1, DRAG_STACK_MAX)
        stack_offset = stack * DRAG_STACK_STEP
        badge_text = str(count) if count > 1 else ""
        badge_font = QFont(self.font())
        badge_font.setBold(True)
        badge_font.setPointSizeF(max(7.0, badge_font.pointSizeF() * 0.85))
        badge_h = 18 if badge_text else 0
        badge_w = max(badge_h, 10 + len(badge_text) * 8) if badge_text else 0

        # Lienzo: margen del cursor + miniatura + pila + mitad del contador que sobresale
        width = DRAG_CURSOR_GAP + thumb_w + stack_offset + badge_w / 2 + 2
        height = DRAG_CURSOR_GAP + thumb_h + stack_offset + badge_h / 2 + 2
        canvas = QPixmap(round(width * ratio), round(height * ratio))
        canvas.setDevicePixelRatio(ratio)  # se dibuja en píxeles lógicos, nítido en HiDPI
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(DRAG_OPACITY)
        border = QPen(QColor(CARD_COLORS.drag_border), 1)

        # Pila: tarjetas grises detrás (de la más lejana a la más cercana)
        for step in range(stack, 0, -1):
            offset = step * DRAG_STACK_STEP
            rect = QRectF(DRAG_CURSOR_GAP + offset, DRAG_CURSOR_GAP + offset, thumb_w, thumb_h)
            painter.setPen(border)
            painter.setBrush(QColor(GRID_BG).lighter(140))
            painter.drawRect(rect)

        # Miniatura principal (delante)
        main_rect = QRectF(DRAG_CURSOR_GAP, DRAG_CURSOR_GAP, thumb_w, thumb_h)
        if thumb is not None and not thumb.isNull():
            painter.drawImage(main_rect, thumb)
        else:
            painter.fillRect(main_rect, QColor(GRID_BG).lighter(170))
        painter.setPen(border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(main_rect.adjusted(0.5, 0.5, -0.5, -0.5))

        # Contador (opaco, para que se lea bien) en la esquina inferior derecha
        if badge_text:
            painter.setOpacity(1.0)
            badge = QRectF(
                main_rect.right() + stack_offset - badge_w / 2,
                main_rect.bottom() + stack_offset - badge_h / 2,
                badge_w,
                badge_h,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ACCENT_COLOR))
            painter.drawRoundedRect(badge, badge_h / 2, badge_h / 2)
            painter.setPen(QColor(COLORS.text_on_accent))  # oscuro: el blanco no se lee
            painter.setFont(badge_font)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, badge_text)

        painter.end()
        return canvas

    @staticmethod
    def _thumbnail_image(decoration: object, ratio: float) -> QImage | None:
        """Convierte la imagen de la tarjeta (QPixmap, QImage o QIcon) en un QImage."""
        if isinstance(decoration, QPixmap):
            return decoration.toImage()
        if isinstance(decoration, QImage):
            return decoration
        if isinstance(decoration, QIcon) and not decoration.isNull():
            side = round(DRAG_THUMB_SIDE * ratio)
            return decoration.pixmap(side, side).toImage()
        return None

