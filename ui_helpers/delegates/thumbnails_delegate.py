"""Delegado que dibuja cada tarjeta de la cuadrícula de miniaturas (ThumbnailsDelegate).

Contenido de una tarjeta, de arriba abajo:
    - La miniatura, con su proporción, centrada en un hueco cuyo borde izquierdo coincide
      con el del nombre. Si tiene etiqueta de color, el fondo de la tarjeta (el marco que
      rodea la imagen) se tiñe con él. Las rechazadas también se tiñen.
    - Una BANDA INFERIOR gris neutra, siempre igual sea cual sea la etiqueta, con el
      nombre, las estrellas y la marca: así el texto se lee sobre cualquier color.
    - El nombre del archivo SIN extensión (elidido por el centro) y, en la misma línea y
      alineada a la derecha (encima del recuadro de la marca), su extensión.
    - Las estrellas (solo si hay 1 o más; al pasar el ratón se ven las vacías) y, a la
      derecha, el recuadro de la marca (como en Lightroom):
          marcada    -> recuadro blanco
          rechazada  -> X gris, miniatura "lavada" (blanquecina) y nombre atenuado; el
                        color de la etiqueta se sigue mostrando (como en Lightroom Classic)
          sin marca  -> nada (solo el contorno al pasar el ratón)
    - Si el archivo no está disponible en disco, la miniatura se OSCURECE (lo contrario
      que una rechazada, que se aclara), el nombre se apaga y un indicador en la esquina
      superior IZQUIERDA de la imagen dice por qué:
          ausente        -> círculo naranja con "!" (la unidad está, el archivo no:
                            se borró, movió o renombró fuera de la aplicación)
          sin conexión   -> círculo gris con un disco tachado (toda la ubicación está
                            desconectada: disco externo, unidad de red)
      Los datos (estrellas, marca, color) se siguen viendo y se pueden cambiar.
    - En la esquina superior DERECHA de la imagen, el círculo de la SELECCIÓN RÁPIDA
      (como el de la "Colección rápida" de Lightroom):
          en la selección rápida  -> círculo blanco (siempre visible, como la marca)
          fuera de ella           -> nada; con el ratón encima, un círculo gris claro
    - Si NO tiene miniatura (vídeo, audio, libro y track, que aún no generan miniaturas,
      o una foto cuya miniatura falló), un MARCADOR dibujado aquí mismo, con la proporción
      típica de su tipo y un dibujo sencillo (sin archivos ni iconos del .qrc):
          vídeo        -> 16:9 con un triángulo de "reproducir" (2:3 de póster si es de
                          la biblioteca de películas y series)
          audio        -> cuadrado con una corchea (♪)
          libro        -> 2:3 con un libro
          track GPS    -> cuadrado con un recorrido
          foto (error) -> 3:2 con un paisaje
      Una foto cuya miniatura aún se está leyendo NO lleva marcador (solo el hueco gris).
    - En los vídeos y el audio, la DURACIÓN ("0:42", "1:32:05") en la esquina inferior
      derecha de la imagen o del marcador.

El delegado solo lee del modelo los roles de 'ui_helpers/models/media_roles.py' y solo le
escribe con 'model.setData(...)': no sabe de bases de datos ni de la caché.

Interacción con el ratón:
    clic en una estrella     -> pone esa valoración (si ya era esa, la quita)
    clic en el recuadro      -> marcada <-> sin marca (una rechazada pasa a marcada)
    Mayús + clic en recuadro -> rechazada <-> sin marca
    clic en el círculo       -> entra o sale de la selección rápida
Si la tarjeta pulsada forma parte de una selección de VARIAS, el cambio se aplica a todas
las seleccionadas (el valor nuevo se decide con la tarjeta pulsada). Si no está
seleccionada, solo cambia ella.

2.14.0 Lo que va encima de la imagen (insignia de la duración, velos de rechazada y de no
       disponible) toma sus colores de 'CARD_COLORS', no sueltos (los mismos valores).
2.13.0 El marcador de tipo y el indicador de no disponible se dibujan con
       'ui_helpers/helpers/card_glyphs.py' (compartido con la vista individual). Sin cambio
       visible.
2.12.0 Colores del tema oscuro (paso T3): todos salen de 'CARD_COLORS' (theme_colors.py);
       el borde de la tarjeta bajo el ratón pasa de amarillo a gris claro.
2.11.0 Estrellas, marca y círculo de la selección rápida se dibujan con
       'ui_helpers/helpers/card_marks.py' (compartido con la barra inferior). Sin cambio
       visible.
2.10.1 Marcador de audio: una corchea rellena (sin trazos), más neutra que las dos notas unidas.
2.10.0 Marcador para las tarjetas sin miniatura (según su tipo) e insignia de duración en
       vídeos y audio (paso 4a).
2.9.0 Los clics en estrellas, marca y círculo los envía 'MediaGridView' ('handle_click')
      antes de que Qt cambie la selección: aplicar un valor a varias tarjetas ya no deja
      seleccionada solo la pulsada. Estrellas 2 px más abajo; marca a 6 px de los bordes.
2.8.0 Clic en estrellas, marca o círculo de una tarjeta seleccionada: se aplica a TODA la
      selección. La línea de estrellas y marca sube 1 px y la marca mide 1 px menos de alto.
2.7.1 El círculo de la selección rápida mide y se separa de la esquina lo mismo que el
      indicador de no disponible (16 px a 4 px de la esquina).
2.7.0 Selección rápida (círculo arriba a la derecha) y el indicador de archivo no
      disponible pasa a la esquina superior izquierda.
"""

__version__ = "2.14.0"
__all__ = ["ThumbnailsDelegate"]

# Librerías estándar
import os
from typing import ClassVar

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt
from qtpy.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from qtpy.QtWidgets import QStyle, QStyledItemDelegate

# Módulos del proyecto
from ui_helpers.helpers import card_glyphs, card_marks
from ui_helpers.helpers.ui_color_labels import blend, label_color
from ui_helpers.helpers.ui_theme import CARD_COLORS
from ui_helpers.models.media_roles import (
    ROLE_AVAILABILITY,
    ROLE_COLOR_LABEL,
    ROLE_DURATION,
    ROLE_FLAG,
    ROLE_FLAGGED,
    ROLE_LIBRARY,
    ROLE_MEDIA_TYPE,
    ROLE_QUICK_SELECTION,
    ROLE_RATING,
    ROLE_THUMBNAIL_STATUS,
)

# Valores de la marca (los mismos que 'core.catalog.media_queries.FLAG_*')
_REJECTED, _NONE, _PICKED = -1, 0, 1

# Disponibilidad del archivo (los mismos que AVAILABLE, MISSING y OFFLINE de
# 'core.catalog.media_queries')
_AVAILABLE, _MISSING, _OFFLINE = 0, 1, 2

# Estado de la miniatura con error (el mismo que en 'media_items.thumbnail_status')
_THUMBNAIL_ERROR = 2

# Tipos de medio (los valores de 'core.catalog.media_types.MediaType') y la biblioteca de
# películas y series ('core.catalog.libraries.Library.VIDEO'): el delegado no importa
# 'core' para seguir sin saber nada de la base de datos
_PHOTO, _VIDEO, _AUDIO, _EBOOK, _TRACK = "photo", "video", "audio", "ebook", "track"
_MOVIES_LIBRARY = "video"


class ThumbnailsDelegate(QStyledItemDelegate):
    """Delegado para dibujar celdas personalizadas en QListView."""

    STAR_W = 12  # Ancho individual de cada estrella
    ROW_H = 14  # Alto del área de estrellas
    MARGIN = 6  # Margen izquierdo de las estrellas

    FLAG_W, FLAG_H = 8, 11  # Dimensiones del recuadro de la marca
    FLAG_INSET = 6  # Distancia al borde inferior de la tarjeta
    FLAG_RIGHT_INSET = 6  # Distancia al borde derecho (= margen del nombre; alinea la extensión)
    FLAG_HIT_PAD = 4  # Margen extra para clics en el recuadro

    PAD = 6  # Margen entre el borde de la tarjeta y el hueco de la miniatura (izquierda,
    #          derecha y por encima de la banda; = margen del nombre)
    TOP_PAD = 8  # Margen superior: 2 px más, para que se vea igual de holgado que los demás lados
    EXT_GAP = 6  # Separación mínima entre el nombre y la extensión

    # Banda inferior (nombre, estrellas y marca): gris neutro para que el texto se lea
    # sobre cualquier etiqueta de color; un poco más clara con el ratón encima o seleccionada
    BAND_TOP_PAD = 4  # Espacio de la banda por encima del nombre
    # (Los colores de la banda, del fondo y del borde están en 'CARD_COLORS': theme_colors.py)

    REJECTED_WASH = 0.55  # Cuánto se "lava" de blanco la miniatura de una rechazada (0 = nada, 1 = blanco)
    LABEL_TINT = 0.5  # Cuánto se tiñe el fondo con el color de la etiqueta (0 a 1)
    UNAVAILABLE_DIM = 0.55  # Cuánto se oscurece la miniatura de un archivo no disponible (0 a 1)
    BADGE_SIZE = 16  # Diámetro (px lógicos) del indicador de archivo no disponible
    BADGE_MARGIN = 4  # Distancia del indicador a la esquina de la imagen
    # (Los colores del indicador están en 'card_glyphs': compartidos con la vista individual)

    # Círculo de la selección rápida (esquina superior derecha de la imagen)
    QUICK_SIZE = BADGE_SIZE  # Diámetro (px lógicos): igual que el indicador de no disponible
    QUICK_MARGIN = BADGE_MARGIN  # Distancia a la esquina: también igual, para que queden simétricos
    QUICK_HIT_PAD = 4  # Margen extra para acertar con el clic
    # (Sus colores, y los de las estrellas y la marca, están en 'card_marks': compartidos
    # con la barra inferior)

    # --- Marcador de las tarjetas sin miniatura (paso 4a) ---
    # (Sus colores están en 'CARD_COLORS'; el dibujo de cada tipo, en 'card_glyphs')
    PLACEHOLDER_GLYPH_SCALE = 0.36  # tamaño del dibujo respecto al lado corto del marcador
    # Proporción (ancho / alto) del marcador de cada tipo de medio
    PLACEHOLDER_ASPECT: ClassVar[dict[str, float]] = {_VIDEO: 16 / 9, _AUDIO: 1.0, _EBOOK: 2 / 3, _TRACK: 1.0, _PHOTO: 3 / 2}
    POSTER_ASPECT = 2 / 3  # vídeo de la biblioteca de películas y series: póster de cine

    # --- Insignia de duración (vídeo y audio) ---
    DURATION_HEIGHT = 15  # alto de la insignia (px lógicos)
    DURATION_PAD_X = 4  # margen horizontal del texto dentro de la insignia
    DURATION_MARGIN = 4  # distancia a la esquina inferior derecha de la imagen
    DURATION_BG = QColor(CARD_COLORS.overlay_bg)  # negro translúcido: se lee sobre cualquier imagen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_size = QSize(176, 208)
        self._name_font = QFont("Arial", 8)
        self._star_font = QFont("Arial", 9)
        self._duration_font = QFont("Arial", 7)
        self._duration_font.setBold(True)

    def sizeHint(self, option, index) -> QSize:
        return self.item_size

    def helpEvent(self, event, view, option, index) -> bool:
        """Bloquea la aparición de tooltips emergentes al pasar el ratón."""
        return False

    # -------------------------------------------------------------------------
    # Geometría
    # -------------------------------------------------------------------------

    def _get_interactive_rects(self, cell_rect: QRect) -> tuple[QRect, QRect]:
        """Calcula las zonas interactivas del recuadro de la marca y las estrellas."""
        y = cell_rect.bottom() - 19  # línea de las estrellas

        stars_rect = QRect(cell_rect.left() + self.MARGIN, y, self.STAR_W * 5, self.ROW_H)

        right_edge = cell_rect.left() + cell_rect.width()
        bottom_edge = cell_rect.top() + cell_rect.height()
        # La marca queda a 6 px de los bordes derecho e inferior de la tarjeta (el mismo
        # margen que el nombre a la izquierda); la extensión del nombre se alinea con ella
        flag_rect = QRect(
            right_edge - self.FLAG_RIGHT_INSET - self.FLAG_W,
            bottom_edge - self.FLAG_INSET - self.FLAG_H,
            self.FLAG_W,
            self.FLAG_H,
        )
        return flag_rect, stars_rect

    @staticmethod
    def _name_rect(cell_rect: QRect) -> QRect:
        return QRect(cell_rect.left() + 6, cell_rect.bottom() - 38, cell_rect.width() - 12, 15)

    def _band_rect(self, cell_rect: QRect) -> QRect:
        """Banda inferior gris: desde un poco por encima del nombre hasta abajo.

        Ocupa el ancho de la tarjeta menos el margen de 1 px que la separa de las vecinas
        (el borde se dibuja encima).
        """
        top = self._name_rect(cell_rect).top() - self.BAND_TOP_PAD
        return QRect(cell_rect.left() + 1, top, cell_rect.width() - 2, cell_rect.bottom() - top)

    def _image_slot(self, cell_rect: QRect) -> QRect:
        """Hueco en el que se encaja la miniatura (su borde izquierdo coincide con el del nombre).

        Termina a 'PAD' píxeles de la banda: el color de la etiqueta rodea la imagen por
        igual arriba, a los lados y abajo.
        """
        band_top = self._band_rect(cell_rect).top()
        top = cell_rect.top() + self.TOP_PAD
        return QRect(
            cell_rect.left() + self.PAD,
            top,
            cell_rect.width() - 2 * self.PAD,
            band_top - self.PAD - top,
        )

    @staticmethod
    def _image_rect(slot: QRect, pixmap: object) -> QRect:
        """Rectángulo que ocupa la miniatura dentro de su hueco (proporción conservada).

        Sin miniatura (aún no generada), el hueco entero. Lo usan el pintado y el ratón,
        así que el círculo de la selección rápida se pulsa justo donde se dibuja.
        """
        if not isinstance(pixmap, QPixmap) or pixmap.isNull():
            return QRect(slot)
        dpr = pixmap.devicePixelRatio()
        size = QSize(round(pixmap.width() / dpr), round(pixmap.height() / dpr)).scaled(
            slot.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        return QRect(
            slot.left() + (slot.width() - size.width()) // 2,
            slot.top() + (slot.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )

    def _needs_placeholder(self, index, pixmap: object) -> bool:
        """True si la tarjeta lleva marcador en lugar de miniatura.

        Sin miniatura y: de un tipo que todavía no genera miniaturas (todo menos las
        fotos), o una foto cuya miniatura falló. Una foto cuya miniatura aún se está
        leyendo NO lleva marcador (aparecerá enseguida).
        """
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            return False
        media_type = index.data(ROLE_MEDIA_TYPE)
        if media_type is None:
            return False  # modelo sin tipo (p. ej. el prototipo antiguo)
        return media_type != _PHOTO or index.data(ROLE_THUMBNAIL_STATUS) == _THUMBNAIL_ERROR

    def _placeholder_aspect(self, index) -> float:
        """Proporción del marcador según el tipo (y, en el vídeo, la biblioteca)."""
        media_type = index.data(ROLE_MEDIA_TYPE)
        if media_type == _VIDEO and index.data(ROLE_LIBRARY) == _MOVIES_LIBRARY:
            return self.POSTER_ASPECT
        return self.PLACEHOLDER_ASPECT.get(media_type, 1.0)

    @staticmethod
    def _fit_aspect(slot: QRect, aspect: float) -> QRect:
        """El mayor rectángulo de proporción 'aspect' (ancho / alto) centrado en 'slot'."""
        width, height = slot.width(), slot.height()
        if width <= 0 or height <= 0:
            return QRect(slot)
        if width / height > aspect:
            width = max(1, round(height * aspect))
        else:
            height = max(1, round(width / aspect))
        return QRect(
            slot.left() + (slot.width() - width) // 2,
            slot.top() + (slot.height() - height) // 2,
            width,
            height,
        )

    def _content_rect(self, slot: QRect, index, pixmap: object) -> QRect:
        """Rectángulo de lo que se dibuja en el hueco: la miniatura o el marcador.

        Lo usan el pintado y el ratón, así que el círculo de la selección rápida se pulsa
        justo donde se dibuja, también sobre un marcador.
        """
        if self._needs_placeholder(index, pixmap):
            return self._fit_aspect(slot, self._placeholder_aspect(index))
        return self._image_rect(slot, pixmap)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """'0:42', '12:05' o '1:32:05' (como los reproductores)."""
        total = max(0, round(seconds))
        hours, rest = divmod(total, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"

    def _quick_rect(self, image_rect: QRect) -> QRectF:
        """Círculo de la selección rápida: esquina superior derecha de la imagen."""
        size = float(self.QUICK_SIZE)
        return QRectF(
            image_rect.right() + 1 - self.QUICK_MARGIN - size,
            image_rect.top() + self.QUICK_MARGIN,
            size,
            size,
        )

    @staticmethod
    def _split_name(file_name: str) -> tuple[str, str]:
        """Separa 'IMG_1.HEIC' en ('IMG_1', 'HEIC'): la extensión sin punto y siempre en mayúsculas.

        Un nombre sin extensión, o que solo empieza por punto ('.gitignore'), no se parte.
        """
        base, extension = os.path.splitext(file_name)
        return (base, extension[1:].upper()) if extension else (file_name, "")

    @staticmethod
    def _flag_of(index) -> int:
        """Marca del elemento: -1 rechazada, 0 sin marca, 1 marcada."""
        flag = index.data(ROLE_FLAG)
        if flag is None:  # modelo sin ROLE_FLAG (el prototipo antiguo): solo había bool
            return _PICKED if index.data(ROLE_FLAGGED) else _NONE
        return int(flag)

    # -------------------------------------------------------------------------
    # Pintado
    # -------------------------------------------------------------------------

    def paint(self, painter: QPainter, option, index) -> None:
        """Renderiza cada tarjeta gráfica."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = option.rect
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)

        rating = index.data(ROLE_RATING) or 0
        flag = self._flag_of(index)
        label = label_color(index.data(ROLE_COLOR_LABEL))
        is_rejected = flag == _REJECTED
        availability = index.data(ROLE_AVAILABILITY) or _AVAILABLE
        is_unavailable = availability != _AVAILABLE

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # --- Fondo, banda inferior y borde de la tarjeta ---
        cards = CARD_COLORS
        if is_selected:
            bg_color, border_color, border_width = QColor(cards.bg_selected), QColor(cards.line_selected), 2
            band_color = QColor(cards.band_selected)
        elif is_hovered:
            bg_color, border_color, border_width = QColor(cards.bg_hover), QColor(cards.line_hover), 2
            band_color = QColor(cards.band_hover)
        else:
            # En reposo: un escalón por encima de la cuadrícula y línea oscura como límite
            bg_color, border_color, border_width = QColor(cards.bg), QColor(cards.line), 1
            band_color = QColor(cards.band)

        # La etiqueta tiñe el fondo (el marco de la imagen) también en las rechazadas,
        # como Lightroom Classic. La banda inferior no se tiñe: así el texto siempre se lee
        if label is not None:
            bg_color = blend(bg_color, label, self.LABEL_TINT)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRect(rect.adjusted(1, 1, -1, -1))
        painter.setBrush(band_color)
        painter.drawRect(self._band_rect(rect))
        # El borde se dibuja el último, encima del fondo y de la banda
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border_color, border_width))
        painter.drawRect(rect.adjusted(1, 1, -1, -1))

        # --- Miniatura (y marco de color) ---
        slot = self._image_slot(rect)
        fit_area = slot  # la imagen se encaja en todo el hueco (ya no hay marco de color)

        target = self._content_rect(fit_area, index, pixmap)
        has_pixmap = isinstance(pixmap, QPixmap) and not pixmap.isNull()
        if has_pixmap or self._needs_placeholder(index, pixmap):
            if has_pixmap:
                painter.drawPixmap(target, pixmap)
            else:
                self._draw_placeholder(painter, target, index.data(ROLE_MEDIA_TYPE))
            if is_rejected:
                # Velo blanco translúcido solo sobre la imagen: la miniatura queda blanquecina
                # y destaca sobre el fondo oscuro, sin tocar el color de fondo de la tarjeta
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(card_glyphs.veil(cards.rejected_wash, self.REJECTED_WASH))
                painter.drawRect(target)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(cards.placeholder_bg))  # hueco sin miniatura: más claro que la tarjeta
            painter.drawRect(fit_area)

        if is_unavailable:
            # Archivo no disponible: velo negro translúcido sobre la imagen (va encima del
            # blanco de la rechazada: este estado manda) y su indicador en la esquina
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(card_glyphs.veil(cards.unavailable_dim, self.UNAVAILABLE_DIM))
            painter.drawRect(target)
            self._draw_availability_badge(painter, target, availability)

        # Duración de vídeos y audio (encima de los velos, abajo a la derecha)
        duration = index.data(ROLE_DURATION)
        if duration and index.data(ROLE_MEDIA_TYPE) in (_VIDEO, _AUDIO):
            self._draw_duration(painter, target, duration)

        # Círculo de la selección rápida (encima de los velos: se ve igual en todas)
        card_marks.draw_quick_selection(
            painter, self._quick_rect(target), bool(index.data(ROLE_QUICK_SELECTION)),
            hovered=is_hovered,
        )

        # --- Nombre del archivo (sobre la banda gris: siempre el mismo fondo) ---
        highlighted = is_selected or is_hovered
        if is_unavailable:
            # Apagado: el archivo no está (más que en una rechazada), pero legible
            text_color = QColor(cards.text_unavailable_highlighted if highlighted else cards.text_unavailable)
        elif is_rejected:
            text_color = QColor(cards.text_rejected_highlighted if highlighted else cards.text_rejected)
        else:
            # Blanco en selección o hover; gris muy claro en reposo
            text_color = QColor(cards.text_highlighted if highlighted else cards.text)
        painter.setPen(text_color)
        painter.setFont(self._name_font)
        flag_rect, stars_rect = self._get_interactive_rects(rect)
        text_rect = self._name_rect(rect)

        # La extensión va aparte, a la derecha de la misma línea y alineada con el borde
        # derecho del recuadro de la marca; el nombre ocupa el resto (sin extensión)
        base_name, extension = self._split_name(text)
        metrics = painter.fontMetrics()
        ext_width = metrics.horizontalAdvance(extension) if extension else 0
        ext_right = flag_rect.left() + flag_rect.width()  # borde derecho (exclusivo) del recuadro
        name_width = text_rect.width()
        if extension:
            name_width = max(0, ext_right - ext_width - self.EXT_GAP - text_rect.left())

        elided = metrics.elidedText(base_name, Qt.TextElideMode.ElideMiddle, name_width)
        painter.drawText(
            QRect(text_rect.left(), text_rect.top(), name_width, text_rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )
        if extension:
            painter.drawText(
                QRect(ext_right - ext_width, text_rect.top(), ext_width, text_rect.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                extension,
            )

        # --- Estrellas (las rellenas siempre; las vacías, al pasar el ratón) ---
        painter.setFont(self._star_font)
        card_marks.draw_stars(
            painter, stars_rect, rating, star_width=self.STAR_W,
            show_empty=is_hovered, rejected=is_rejected,
        )  # fmt: skip

        # --- Recuadro de la marca ---
        card_marks.draw_flag(painter, flag_rect, flag, hovered=is_hovered)

        painter.restore()

    def _draw_availability_badge(
        self, painter: QPainter, image_rect: QRect, availability: int
    ) -> None:
        """Dibuja el indicador de archivo no disponible en la esquina superior izquierda
        (el dibujo, compartido con la vista individual, está en 'card_glyphs')."""
        badge = QRectF(
            image_rect.left() + self.BADGE_MARGIN,
            image_rect.top() + self.BADGE_MARGIN,
            float(self.BADGE_SIZE),
            float(self.BADGE_SIZE),
        )
        card_glyphs.draw_availability_badge(painter, badge, availability)

    def _draw_duration(self, painter: QPainter, image_rect: QRect, seconds: float) -> None:
        """Insignia con la duración en la esquina inferior derecha de la imagen."""
        text = self._format_duration(seconds)
        painter.save()
        painter.setFont(self._duration_font)
        width = painter.fontMetrics().horizontalAdvance(text) + 2 * self.DURATION_PAD_X
        badge = QRectF(
            image_rect.right() + 1 - self.DURATION_MARGIN - width,
            image_rect.bottom() + 1 - self.DURATION_MARGIN - self.DURATION_HEIGHT,
            width,
            self.DURATION_HEIGHT,
        )
        # Si la imagen es tan pequeña que no cabe, no se dibuja (no se tapa la miniatura)
        if badge.width() + 2 * self.DURATION_MARGIN <= image_rect.width():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.DURATION_BG)
            painter.drawRoundedRect(badge, 3, 3)
            painter.setPen(QColor(CARD_COLORS.overlay_text))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _draw_placeholder(self, painter: QPainter, rect: QRect, media_type: str | None) -> None:
        """Marcador de una tarjeta sin miniatura (compartido con la vista individual)."""
        card_glyphs.draw_placeholder(painter, rect, media_type, self.PLACEHOLDER_GLYPH_SCALE)

    # -------------------------------------------------------------------------
    # Ratón
    # -------------------------------------------------------------------------
    # Los clics en las zonas activas (estrellas, marca, círculo) los envía la propia vista
    # ('MediaGridView.mousePressEvent' -> 'handle_click') ANTES de que Qt toque la
    # selección: si llegaran por 'editorEvent', Qt ya habría decidido seleccionar solo la
    # tarjeta pulsada al soltar el botón, y una selección múltiple se perdería.
    # 'editorEvent' se mantiene por si el delegado se usa en una vista normal.

    def is_active_zone(self, cell_rect: QRect, index, pos: QPoint) -> bool:
        """True si 'pos' cae en una zona que se pulsa (estrella, marca o círculo)."""
        return self._zone_at(cell_rect, index, pos) is not None

    def _zone_at(self, cell_rect: QRect, index, pos: QPoint) -> str | None:
        """Zona activa bajo 'pos': "quick", "flag", "stars" o None."""
        flag_rect, stars_rect = self._get_interactive_rects(cell_rect)
        # Círculo de la selección rápida (se calcula igual que al pintarlo)
        image_rect = self._content_rect(
            self._image_slot(cell_rect), index, index.data(Qt.ItemDataRole.DecorationRole)
        )
        pad = self.QUICK_HIT_PAD
        if self._quick_rect(image_rect).adjusted(-pad, -pad, pad, pad).contains(QPointF(pos)):
            return "quick"
        pad = self.FLAG_HIT_PAD
        if flag_rect.adjusted(-pad, -pad, pad, pad).contains(pos):
            return "flag"
        if stars_rect.contains(pos):
            return "stars"
        return None

    def handle_click(
        self, pos: QPoint, modifiers, model, cell_rect: QRect, index, view=None
    ) -> bool:
        """Atiende un clic en la tarjeta 'index' (en coordenadas de la vista).

        Args:
            pos: Punto pulsado.
            modifiers: Teclas modificadoras (Mayús + marca = rechazar).
            model: Modelo de la cuadrícula.
            cell_rect: Rectángulo de la tarjeta.
            index: Tarjeta pulsada.
            view: Vista (para saber qué hay seleccionado). Sin ella, solo cambia la pulsada.

        Returns:
            True si el clic cayó en una zona activa (y se ha aplicado).
        """
        zone = self._zone_at(cell_rect, index, pos)
        if zone == "quick":
            selected = bool(index.data(ROLE_QUICK_SELECTION))
            self._apply(model, view, index, not selected, ROLE_QUICK_SELECTION)
        elif zone == "flag":
            current = self._flag_of(index)
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                new_flag = _NONE if current == _REJECTED else _REJECTED
            else:
                new_flag = _NONE if current == _PICKED else _PICKED
            self._apply(model, view, index, new_flag, ROLE_FLAG)
        elif zone == "stars":
            _flag_rect, stars_rect = self._get_interactive_rects(cell_rect)
            clicked_star = (pos.x() - stars_rect.left()) // self.STAR_W + 1
            clicked_star = max(1, min(5, clicked_star))
            current_rating = index.data(ROLE_RATING) or 0
            new_rating = 0 if current_rating == clicked_star else clicked_star
            self._apply(model, view, index, new_rating, ROLE_RATING)
        else:
            return False
        return True

    @staticmethod
    def _target_rows(view, index) -> list[int]:
        """Filas a las que se aplica un clic en la tarjeta 'index'.

        Si está seleccionada y hay más seleccionadas, todas ellas (como el teclado y el
        menú contextual); si no, solo ella.
        """
        selection = view.selectionModel() if hasattr(view, "selectionModel") else None
        if selection is not None and selection.isSelected(index):
            rows = sorted({i.row() for i in selection.selectedIndexes()})
            if len(rows) > 1:
                return rows
        return [index.row()]

    @classmethod
    def _apply(cls, model, view, index, value, role) -> None:
        """Escribe 'value' (por rol) en la tarjeta pulsada o en toda la selección."""
        rows = cls._target_rows(view, index)
        if len(rows) > 1 and hasattr(model, "set_data_rows"):
            model.set_data_rows(rows, value, role)
        else:
            model.setData(index, value, role)

    def editorEvent(self, event, model, option, index) -> bool:
        """Clics que llegan por la vía normal de Qt (vista que no es 'MediaGridView')."""
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if self.handle_click(
                pos, event.modifiers(), model, option.rect, index, option.widget
            ):
                return True
        return super().editorEvent(event, model, option, index)
