"""Vista individual: el archivo ACTUAL de la cuadrícula, a todo el espacio del centro.

Usa el MISMO modelo y el MISMO 'selectionModel' que la cuadrícula ('attach'): muestra la
fila actual ('currentIndex') y, como la selección es la misma, el inspector, la barra
inferior y los atajos de clasificación siguen funcionando sin cambios.

Qué dibuja (todo sobre el fondo de la cuadrícula, 'CARD_COLORS.grid_bg'):
    - La imagen centrada y sin deformar. Sale de la caché: la de 2560 px o la mayor que
      haya, leída en segundo plano ('FullImageLoader'). Si cabe en el espacio, a SU
      tamaño: un píxel de la imagen en un píxel físico de la pantalla, sin reescalar
      (ampliarla la emborronaría, p. ej. la vista previa de 1024 px de un DNG). Si no cabe, reducida para que quepa: para que se vea nítida
      en pantallas escaladas, se reescala en alta calidad a los píxeles FÍSICOS (mientras
      se redimensiona, un escalado rápido; el bueno, al pararse: '_HQ_DELAY_MS'). Se
      decide en cada dibujo, así que al maximizar o estrechar la ventana pasa de un caso
      al otro. Mientras llega, la miniatura que ya tiene la cuadrícula, ajustada al
      espacio (aún no se sabe el tamaño de la grande).
    - Sin miniatura: el marcador de su tipo ('card_glyphs') con el nombre debajo.
    - Archivo no disponible: la imagen oscurecida, como en la tarjeta, y el indicador con
      su explicación: «Ausente (archivo no encontrado)» o «Sin conexión (disco
      desconectado)».
    - Sin archivos en lo que se está viendo: «No hay archivos».

Zoom 1:1 ('single_view_zoom.py', que se ocupa de todo): con la lupa, un clic (o Z) amplía
la foto a 1:1 con el ORIGINAL; a 1:1 se arrastra con la mano y otro clic vuelve. Esta
vista solo le dice qué archivo muestra ('track') y dónde ha quedado la foto ajustada
('set_shown'), y le deja dibujar cuando está ampliada.

Rueda del ratón (decidido por el autor el 12/11/2026): en la vista ajustada, hacia delante
la foto anterior y hacia atrás la siguiente, una por clic de la rueda ('step_requested';
las mueve el 'CenterViewController', como las flechas). Ctrl + rueda y la rueda a 1:1 los
atiende antes el zoom.

Precarga el archivo anterior y el siguiente, para que pasar de uno a otro sea inmediato.
Solo carga imágenes cuando se dibuja: oculta (en la cuadrícula) no lee nada.

Uso (en el .ui es un widget promocionado, 'widget_single_view', dentro de 'page_single'):
    self.widget_single_view.attach(self.list_view_grid, self.mosaico_model)

1.3.0 Rueda: foto anterior o siguiente en la vista ajustada ('step_requested').
1.2.1 Al zoom, también el tamaño de la imagen de la caché que se ve (sin lupa si no hay
      nada mayor que leer).
1.2.0 Zoom 1:1 con el original ('SingleViewZoom'; vista individual a 1:1, paso 3).
1.1.0 La imagen que cabe se muestra a su tamaño (un píxel de la imagen, uno de la
      pantalla) en vez de ampliarla hasta llenar el espacio, que la emborronaba; la que no
      cabe se reduce como antes (pedido por el autor).
1.0.1 El velo y el fondo del aviso, con los colores del tema ('CARD_COLORS'; los mismos
      valores que antes).
1.0.0 Primera versión (paso A.1, subpaso 4). Entrar, salir y navegar con el teclado
      llegan en el subpaso 5.

Prueba rápida (desde la raíz del proyecto; dibuja en una imagen, no abre ventanas):
    python -m ui_helpers.widgets.single_media_view
"""

__version__ = "1.3.0"
__all__ = ["SingleMediaView"]

# Librerías estándar
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from qtpy.QtWidgets import QListView, QWidget

# Módulos del proyecto
from ui_helpers.delegates.thumbnails_delegate import ThumbnailsDelegate
from ui_helpers.helpers import card_glyphs
from ui_helpers.helpers.ui_theme import CARD_COLORS, COLORS
from ui_helpers.helpers.zoom_geometry import wheel_steps
from ui_helpers.models.full_image_loader import FullImageLoader
from ui_helpers.models.media_roles import (
    ROLE_AVAILABILITY,
    ROLE_MEDIA_ID,
    ROLE_MEDIA_TYPE,
)
from ui_helpers.widgets.single_view_zoom import SingleViewZoom

# Textos de la interfaz (decididos por el autor el 08/11/2026)
EMPTY_TEXT = "No hay archivos"
UNAVAILABLE_TEXTS = {
    card_glyphs.MISSING: "Ausente (archivo no encontrado)",
    card_glyphs.OFFLINE: "Sin conexión (disco desconectado)",
}

# Medidas (px lógicos)
_MARGIN = 16  # aire alrededor de la imagen
_BADGE_SIZE = 28  # indicador de no disponible (en la tarjeta, 16)
_BADGE_MARGIN = 12  # distancia del indicador a la esquina de la imagen
_LABEL_PAD_X, _LABEL_PAD_Y = 8, 4  # margen del texto del aviso dentro de su fondo
_PLACEHOLDER_SCALE = 0.5  # tamaño del marcador respecto al espacio
_NAME_GAP = 10  # entre el marcador y el nombre

# Cuánto se oscurece la imagen de un archivo no disponible (el mismo que la tarjeta)
_UNAVAILABLE_DIM = ThumbnailsDelegate.UNAVAILABLE_DIM
# Fondo del texto del aviso: negro translúcido, se lee sobre cualquier imagen (como la
# insignia de duración de la tarjeta)
_LABEL_BG = QColor(CARD_COLORS.overlay_bg)
# Espera (ms) desde el último cambio de tamaño hasta reescalar en alta calidad
_HQ_DELAY_MS = 120


class SingleMediaView(QWidget):
    """Muestra el archivo actual de la cuadrícula (ver el docstring del archivo).

    Signals:
        step_requested(int): la rueda pide otra foto: -1 la anterior, +1 la siguiente
            (o más, si se gira deprisa).
    """

    step_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid: QListView | None = None
        self._model: Any = None  # MediaGridModel (o uno compatible, en la autoprueba)
        self._loader: FullImageLoader | None = None
        # Imagen ya preparada para dibujar (reescalada en alta calidad o a su tamaño):
        # ((id, ancho y alto físicos, clave de la imagen, escala de la pantalla), pixmap)
        self._scaled: tuple[tuple[int, int, int, int, float], QPixmap] | None = None
        self._hq_timer = QTimer(self)
        self._hq_timer.setSingleShot(True)
        self._hq_timer.setInterval(_HQ_DELAY_MS)
        self._hq_timer.timeout.connect(self.update)
        # Recibirá el teclado (flechas, Esc...: subpaso 5); los atajos de clasificación los
        # atiende 'GridActions' con el mismo modelo y selección
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # Zoom 1:1 (lupa, clic, arrastre, Z, Ctrl + rueda y el original): en 'SingleViewZoom'
        self._zoom = SingleViewZoom(self)
        self._wheel = 0  # giro de la rueda que aún no llega a un clic (panel táctil)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def attach(self, grid: QListView, model: Any) -> None:
        """Se conecta a la cuadrícula: su modelo y su selección son los de esta vista."""
        self._grid = grid
        self._model = model
        self._loader = FullImageLoader(lambda: (model.catalog_key(), model.thumbnail_cache), self)
        self._loader.loaded.connect(self._on_loaded)
        self._zoom.attach(model)
        model.modelReset.connect(self._on_rows_changed)
        model.rowsInserted.connect(self._on_rows_changed)
        model.rowsRemoved.connect(self._on_rows_changed)
        model.dataChanged.connect(self._on_data_changed)
        model.thumbnails_refreshed.connect(self._on_thumbnails_refreshed)
        model.missing_retried.connect(self._on_missing_retried)
        grid.selectionModel().currentChanged.connect(self._on_rows_changed)

    def current_row(self) -> int:
        """Fila que se muestra: la actual de la cuadrícula; si no hay, la primera
        seleccionada o la primera de todas. -1 si no hay filas."""
        if self._model is None or self._grid is None or self._model.rowCount() == 0:
            return -1
        current = self._grid.currentIndex()
        if current.isValid():
            return current.row()
        selected = self._grid.selectionModel().selectedIndexes()
        return min(index.row() for index in selected) if selected else 0

    def shutdown(self) -> None:
        """Para las lecturas en curso (al cerrar la aplicación)."""
        if self._loader is not None:
            self._loader.shutdown()
        self._zoom.shutdown()

    # -------------------------------------------------------------------------
    # Avisos del modelo y del cargador
    # -------------------------------------------------------------------------

    def _current_id(self) -> int | None:
        row = self.current_row()
        return None if row < 0 else self._model.index(row, 0).data(ROLE_MEDIA_ID)

    def _on_rows_changed(self, *_args: object) -> None:
        self.update()

    def _on_loaded(self, media_id: int, _image: QImage) -> None:
        if media_id == self._current_id():
            self.update()

    def _on_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex, _roles: Any = None) -> None:
        row = self.current_row()
        if top_left.row() <= row <= bottom_right.row():
            self.update()  # disponibilidad, nombre, miniatura de la cuadrícula...

    def _on_thumbnails_refreshed(self, media_ids: list[int]) -> None:
        if self._loader is not None:
            self._loader.forget(media_ids)
        if self._current_id() in media_ids:
            self.update()

    def _on_missing_retried(self) -> None:
        if self._loader is not None:
            self._loader.forget_missing()
        self.update()

    # -------------------------------------------------------------------------
    # Dibujo
    # -------------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # nombre de Qt
        """Vista ajustada: hacia delante, la foto anterior; hacia atrás, la siguiente (una por
        clic). Ctrl + rueda y la rueda a 1:1 no llegan aquí: los atiende el zoom."""
        steps, self._wheel = wheel_steps(self._wheel, event.angleDelta().y())
        if steps:
            self.step_requested.emit(-steps)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._hq_timer.start()  # el escalado bueno, cuando deje de cambiar de tamaño

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(CARD_COLORS.grid_bg))
        row = self.current_row()
        if row < 0 or self._loader is None:
            self._zoom.track(None, None, card_glyphs.AVAILABLE)  # nada que ampliar
            if self._model is not None:
                self._draw_centered_text(painter, self.rect(), EMPTY_TEXT, COLORS.text_dim)
            painter.end()
            return

        index = self._model.index(row, 0)
        media_id = index.data(ROLE_MEDIA_ID)
        media_type = index.data(ROLE_MEDIA_TYPE) or ""
        availability = index.data(ROLE_AVAILABILITY) or card_glyphs.AVAILABLE
        # El zoom sabe qué se ve (si cambia de archivo o deja de estar disponible, vuelve a
        # la vista ajustada)
        self._zoom.track(media_id, media_type, availability)
        area = self.rect().adjusted(_MARGIN, _MARGIN, -_MARGIN, -_MARGIN)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        image = self._loader.image(media_type, media_id)
        interim = index.data(Qt.ItemDataRole.DecorationRole)
        if self._zoom.active:
            # A 1:1 dibuja el zoom: el original o, mientras llega, la imagen de la caché
            if image is not None and not image.isNull():
                self._zoom.paint(painter, image)
            else:
                self._zoom.paint(painter, interim if isinstance(interim, QPixmap) else None)
        else:
            target = QRectF()  # dónde ha quedado lo dibujado (vacío: solo el fondo)
            photo = QRectF()  # dónde ha quedado la FOTO (el marcador no se amplía)
            source = None  # y, si es la imagen grande de la caché, su tamaño
            if image is not None and not image.isNull():
                target = photo = self._draw_image(painter, area, media_id, image)
                source = image.size()
            elif image is None and isinstance(interim, QPixmap) and not interim.isNull():
                # Mientras llega la grande: la de la cuadrícula, ajustada al espacio
                fitted = self._fit(area, interim.size())
                painter.drawPixmap(fitted, interim)
                target = photo = QRectF(fitted)
            elif image is not None:
                # Sin miniatura: el marcador de su tipo y el nombre
                target = QRectF(
                    self._draw_placeholder(painter, area, media_type, str(index.data() or ""))
                )
            if availability != card_glyphs.AVAILABLE and target.isValid():
                self._draw_unavailable(painter, target, availability)
            self._zoom.set_shown(photo, source)
        painter.end()

        # Las vecinas, para que las flechas vayan al momento
        neighbours = []
        for other in (row - 1, row + 1):
            if 0 <= other < self._model.rowCount():
                other_index = self._model.index(other, 0)
                neighbours.append((other_index.data(ROLE_MEDIA_TYPE) or "", other_index.data(ROLE_MEDIA_ID)))
        self._loader.prefetch(neighbours)

    def _draw_image(self, painter: QPainter, area: QRect, media_id: int, image: QImage) -> QRectF:
        """Dibuja la imagen grande en 'area' y devuelve dónde ha quedado (px lógicos).

        Si cabe, a su tamaño: un píxel de la imagen en un píxel físico, sin reescalar, y
        con la esquina en un píxel físico entero (entre dos, Qt la suavizaría). Si no
        cabe, reducida para que quepa ('_fit' y '_scaled_pixmap').
        """
        ratio = self.devicePixelRatioF()
        natural = QSizeF(image.width() / ratio, image.height() / ratio)
        if natural.width() <= area.width() and natural.height() <= area.height():
            left = round((area.x() + (area.width() - natural.width()) / 2) * ratio) / ratio
            top = round((area.y() + (area.height() - natural.height()) / 2) * ratio) / ratio
            corner = QPointF(left, top)
            painter.drawPixmap(corner, self._native_pixmap(media_id, image))
            return QRectF(corner, natural)
        fitted = self._fit(area, image.size())
        painter.drawPixmap(fitted, self._scaled_pixmap(media_id, image, fitted))
        return QRectF(fitted)

    @staticmethod
    def _fit(area: QRect, size: QSize) -> QRect:
        """El mayor rectángulo con la proporción de 'size', centrado en 'area'."""
        if size.width() <= 0 or size.height() <= 0 or area.width() <= 0 or area.height() <= 0:
            return QRect()
        scaled = size.scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect(0, 0, scaled.width(), scaled.height())
        target.moveCenter(area.center())
        return target

    def _scaled_pixmap(self, media_id: int, image: QImage, target: QRect) -> QPixmap:
        """La imagen reescalada en alta calidad a los píxeles físicos de 'target'.

        Si todavía no está hecha a este tamaño y la ventana se está redimensionando, se
        devuelve la imagen tal cual (QPainter la escala deprisa) y se rehace al pararse.
        """
        ratio = self.devicePixelRatioF()
        width, height = round(target.width() * ratio), round(target.height() * ratio)
        key = (media_id, width, height, image.cacheKey(), ratio)
        if self._scaled is not None and self._scaled[0] == key:
            return self._scaled[1]
        if self._hq_timer.isActive():
            return QPixmap.fromImage(image)  # escalado rápido mientras cambia de tamaño
        pixmap = QPixmap.fromImage(
            image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        )  # fmt: skip
        pixmap.setDevicePixelRatio(ratio)
        self._scaled = (key, pixmap)
        return pixmap

    def _native_pixmap(self, media_id: int, image: QImage) -> QPixmap:
        """La imagen tal cual, para dibujarla a su tamaño: cada píxel, en uno físico.

        Lleva la escala de la pantalla ('devicePixelRatio'): así Qt la pinta con su ancho
        en píxeles físicos y no la amplía. Se guarda como la reescalada (una conversión
        por imagen, no una por dibujo).
        """
        ratio = self.devicePixelRatioF()
        key = (media_id, image.width(), image.height(), image.cacheKey(), ratio)
        if self._scaled is not None and self._scaled[0] == key:
            return self._scaled[1]
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(ratio)
        self._scaled = (key, pixmap)
        return pixmap

    def _draw_placeholder(self, painter: QPainter, area: QRect, media_type: str, name: str) -> QRect:
        """Marcador del tipo, centrado, con el nombre debajo. Devuelve su rectángulo."""
        aspect = ThumbnailsDelegate.PLACEHOLDER_ASPECT.get(media_type, 3 / 2)
        name_height = painter.fontMetrics().height() + _NAME_GAP
        room = area.adjusted(0, 0, 0, -name_height)
        box = QSize(round(1000 * aspect), 1000).scaled(
            round(room.width() * _PLACEHOLDER_SCALE), round(room.height() * _PLACEHOLDER_SCALE),
            Qt.AspectRatioMode.KeepAspectRatio,
        )  # fmt: skip
        target = QRect(0, 0, box.width(), box.height())
        target.moveCenter(room.center())
        card_glyphs.draw_placeholder(painter, target, media_type)
        name_rect = QRect(area.left(), target.bottom() + _NAME_GAP, area.width(), name_height)
        painter.setPen(QColor(CARD_COLORS.text))
        elided = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, area.width())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided)
        return target

    def _draw_unavailable(self, painter: QPainter, target: QRectF, availability: int) -> None:
        """Velo oscuro (como la tarjeta), indicador y su explicación en la esquina."""
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(card_glyphs.veil(CARD_COLORS.unavailable_dim, _UNAVAILABLE_DIM))
        painter.drawRect(target)
        badge = QRectF(target.left() + _BADGE_MARGIN, target.top() + _BADGE_MARGIN, _BADGE_SIZE, _BADGE_SIZE)
        card_glyphs.draw_availability_badge(painter, badge, availability)

        text = UNAVAILABLE_TEXTS.get(availability, "")
        font = QFont(painter.font())
        font.setPointSizeF(font.pointSizeF() + 1)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        label = QRectF(
            badge.right() + 8, badge.center().y() - metrics.height() / 2 - _LABEL_PAD_Y,
            metrics.horizontalAdvance(text) + 2 * _LABEL_PAD_X, metrics.height() + 2 * _LABEL_PAD_Y,
        )  # fmt: skip
        painter.setBrush(_LABEL_BG)
        painter.drawRoundedRect(label, 4, 4)
        painter.setPen(QColor(CARD_COLORS.text_highlighted))
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    @staticmethod
    def _draw_centered_text(painter: QPainter, rect: QRect, text: str, color: str) -> None:
        painter.setPen(QColor(color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


if __name__ == "__main__":
    # Autoprueba SIN ventana: un modelo de mentira y 'grab()' (dibuja en una imagen).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.single_media_view
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import QPoint
    from qtpy.QtGui import QStandardItem, QStandardItemModel
    from qtpy.QtWidgets import QApplication

    app = QApplication([])

    class _Model(QStandardItemModel):
        """Lo que la vista usa del 'MediaGridModel' (sin catálogo: nunca hay imagen grande)."""

        thumbnails_refreshed = Signal(list)
        missing_retried = Signal()
        thumbnail_cache = None

        def catalog_key(self) -> str:
            return ""

    def add(model: _Model, media_id: int, media_type: str, availability: int, color: str | None) -> None:
        item = QStandardItem(f"archivo_{media_id}.jpg")
        item.setData(media_id, ROLE_MEDIA_ID)
        item.setData(media_type, ROLE_MEDIA_TYPE)
        item.setData(availability, ROLE_AVAILABILITY)
        if color:
            pixmap = QPixmap(300, 200)
            pixmap.fill(QColor(color))
            item.setData(pixmap, Qt.ItemDataRole.DecorationRole)
        model.appendRow(item)

    holder = QWidget()  # nunca se muestra
    model = _Model(holder)
    grid = QListView(holder)
    grid.setModel(model)
    view = SingleMediaView(holder)
    view.resize(600, 400)
    view.attach(grid, model)
    bg = QColor(CARD_COLORS.grid_bg).name()

    def shot() -> QImage:
        return view.grab().toImage()

    # Sin archivos: el fondo y el texto «No hay archivos» (hay píxeles que no son fondo)
    image = shot()
    assert image.pixelColor(5, 5).name() == bg and view.current_row() == -1
    assert any(image.pixelColor(x, 200).name() != bg for x in range(200, 400))

    # Un archivo con la miniatura de la cuadrícula (roja): se ve en el centro mientras tanto
    add(model, 1, "photo", card_glyphs.AVAILABLE, "#ff0000")
    add(model, 2, "video", card_glyphs.MISSING, "#00ff00")
    add(model, 3, "audio", card_glyphs.OFFLINE, None)
    assert view.current_row() == 0  # sin fila actual: la primera
    assert shot().pixelColor(300, 200).name() == "#ff0000"

    # La fila actual de la cuadrícula manda; ausente: imagen oscurecida y el indicador
    grid.setCurrentIndex(model.index(1, 0))
    image = shot()
    assert view.current_row() == 1
    center = image.pixelColor(300, 200)
    assert center.green() < 200 and center.red() == 0, center.name()  # verde, oscurecido
    assert any(image.pixelColor(x, y).name() == card_glyphs.MISSING_COLOR
               for x in range(20, 120) for y in range(40, 140))  # fmt: skip

    # Sin miniatura y sabido que no la tiene: el marcador de su tipo
    view._loader._missing.add(3)
    grid.setCurrentIndex(model.index(2, 0))
    image = shot()
    assert QColor(CARD_COLORS.placeholder_bg).name() in {
        image.pixelColor(x, y).name() for x in range(150, 450, 10) for y in range(100, 300, 10)
    }

    # Imagen grande ya leída y MÁS PEQUEÑA que el espacio (600 x 400 menos 16 de margen):
    # a su tamaño, centrada y píxel a píxel (rayas de 1 px: si se reescalara, se mezclarían)
    small = QImage(200, 100, QImage.Format.Format_RGB32)
    for x in range(200):
        for y in range(100):
            small.setPixelColor(x, y, QColor("#ffffff" if x % 2 else "#0000ff"))
    add(model, 4, "photo", card_glyphs.AVAILABLE, "#ff0000")
    view._loader._images[4] = small
    grid.setCurrentIndex(model.index(3, 0))
    image = shot()
    left, top = 16 + (568 - 200) // 2, 16 + (368 - 100) // 2  # 200, 150
    assert image.pixelColor(left - 1, top + 50).name() == bg
    assert image.pixelColor(left + 200, top + 50).name() == bg
    assert image.pixelColor(left + 50, top - 1).name() == bg
    assert all(
        image.pixelColor(left + x, top + y) == small.pixelColor(x, y)
        for x in range(200) for y in (0, 37, 99)
    ), "la imagen pequeña no se ha dibujado píxel a píxel"  # fmt: skip

    # MÁS GRANDE que el espacio (1200 x 800): reducida para que quepa (552 x 368), centrada
    big = QImage(1200, 800, QImage.Format.Format_RGB32)
    big.fill(QColor("#ffff00"))
    add(model, 5, "photo", card_glyphs.AVAILABLE, "#ff0000")
    view._loader._images[5] = big
    grid.setCurrentIndex(model.index(4, 0))
    image = shot()
    assert image.pixelColor(24, 16).name() == "#ffff00"  # esquina: 16 + (568 - 552) / 2
    assert image.pixelColor(575, 383).name() == "#ffff00"
    assert image.pixelColor(22, 200).name() == bg and image.pixelColor(578, 200).name() == bg

    # La ventana se maximiza: ahora cabe y se ve a su tamaño, sin ampliarla
    view.resize(1600, 1000)
    image = shot()
    left, top = 16 + (1568 - 1200) // 2, 16 + (968 - 800) // 2  # 200, 100
    assert image.pixelColor(left, top).name() == "#ffff00"
    assert image.pixelColor(left - 1, top).name() == bg
    assert image.pixelColor(left + 1199, top + 799).name() == "#ffff00"
    assert image.pixelColor(left + 1200, top + 799).name() == bg
    assert image.pixelColor(left, top - 1).name() == bg
    view.resize(600, 400)

    # Se vacía lo que se ve: otra vez «No hay archivos»
    model.clear()
    assert view.current_row() == -1 and shot().pixelColor(5, 5).name() == bg

    view.shutdown()
    holder.deleteLater()
    # La rueda: hacia atrás, la siguiente; hacia delante, la anterior; giros pequeños, sumados
    steps: list[int] = []
    view.step_requested.connect(steps.append)

    def roll(dy: int) -> None:
        point = QPointF(50, 50)
        QApplication.sendEvent(view, QWheelEvent(
            point, point, QPoint(0, 0), QPoint(0, dy), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))  # fmt: skip

    roll(-120)
    roll(120)
    roll(60)
    roll(60)
    assert steps == [1, -1, -1], steps
    print("Autoprueba finalizada correctamente.")
