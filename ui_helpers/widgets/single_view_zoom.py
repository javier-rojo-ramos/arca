"""Zoom 1:1 de la vista individual: lupa, clic, arrastre, tecla Z y el original.

Lo crea 'SingleMediaView' (es suyo) y se ocupa de todo lo del zoom, para que la vista solo
tenga que decirle qué muestra y pedirle que dibuje cuando está ampliada:

    zoom = SingleViewZoom(view)
    zoom.attach(model)                                 # le pide la ruta y las dimensiones
    zoom.track(media_id, media_type, availability)     # al dibujar: qué archivo se ve
    if zoom.active:
        zoom.paint(painter, imagen_de_la_cache)        # a 1:1 dibuja él
    else:
        ...                                            # la vista dibuja la ajustada
        zoom.set_shown(rect, tamaño_de_la_imagen)      # y le dice dónde ha quedado

Cómo funciona (decidido por el autor el 12/11/2026; ver DECISIONES.md):
    - Lupa (cursor) al pasar por la foto si a 1:1 se vería más grande
      ('zoom_geometry.can_zoom'). Solo en fotos disponibles cuyas dimensiones se conocen:
      la ruta y las dimensiones se piden al modelo en segundo plano al cambiar de archivo
      ('MediaGridModel.request_media_file'; la lista de la cuadrícula no lleva rutas).
      Qué se verá a 1:1 ('_full_pixels'): lo que dice el catálogo, SALVO que la imagen
      grande de la caché mida menos de 2560 px: la escalera de miniaturas nunca amplía,
      así que no había nada mayor que leer (p. ej. un DNG con una vista previa de 1024
      px, aunque el catálogo diga 6000). Mientras se ve la miniatura de la cuadrícula
      (aún llega la de la caché), sin lupa. Si el original llega y no es mayor que lo que
      ya se veía, se vuelve a la vista ajustada y esa foto se queda sin lupa.
    - Clic (sin arrastrar): 1:1, con el punto pulsado bajo el ratón; a 1:1 la foto usa
      todo el espacio, sin el margen de la vista ajustada. Z hace lo mismo, desde el
      centro.
    - A 1:1: mano abierta; al arrastrar, cerrada, y la foto se mueve sin salirse del
      espacio. Otro clic (o Z) vuelve a la vista ajustada.
    - Mientras llega el original ('OriginalImageLoader'), la imagen de la caché ampliada,
      sin aviso. Si el original mide otra cosa que lo que dice el catálogo (la vista previa
      de un RAW), el punto del centro se queda en el centro. Si no se puede leer, sigue la
      de la caché (el motivo, en el registro).
    - Al cambiar de archivo, al ocultarse la vista (vuelta a la cuadrícula) o si el archivo
      deja de estar disponible: vista ajustada, y el original se suelta de la memoria.
    - Al cambiar el tamaño de la ventana (o de pantalla, con otra escala), el punto del
      centro sigue en el centro.
    - Rueda (decidido por el autor el 12/11/2026): Ctrl + rueda hacia delante amplía a 1:1
      en el punto del ratón (fuera de la foto, desde el centro) y hacia atrás vuelve. A
      1:1, la rueda sola mueve la foto en vertical (Mayús + rueda o la rueda horizontal,
      en horizontal): no cambia de foto, para no perder por un roce la zona que se mira.
      En la vista ajustada, la rueda sola no es suya: la vista pasa de foto con ella.

La lupa se dibuja aquí (Qt no la trae), con los colores del tema para lo que va sobre la
imagen ('overlay_text' sobre un halo 'overlay_bg'). Las manos son las de Qt.

1.1.0 Rueda: Ctrl + rueda, zoom; a 1:1, la rueda mueve la foto ('_on_wheel').
1.0.1 Sin lupa en una foto de la que no se puede leer nada mayor que la imagen de la
      caché (antes salía con un DNG de vista previa pequeña: se ampliaba un instante y
      volvía a su tamaño con la mano; lo vio el autor). Ver «Qué se verá a 1:1».
1.0.0 Primera versión (vista individual a 1:1, paso 3).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m ui_helpers.widgets.single_view_zoom
"""

__version__ = "1.1.0"
__all__ = ["SingleViewZoom", "magnifier_cursor"]

# Librerías estándar
from dataclasses import replace
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt
from qtpy.QtGui import QColor, QCursor, QImage, QPainter, QPen, QPixmap, QWheelEvent
from qtpy.QtWidgets import QApplication, QWidget

# Módulos del proyecto
from core.catalog.media_queries import AVAILABLE, MediaFile
from core.catalog.media_types import MediaType
from core.thumbnails.sizes import ThumbnailSize
from ui_helpers.helpers.ui_theme import CARD_COLORS
from ui_helpers.helpers.zoom_geometry import (
    WHEEL_STEP,
    Point,
    Rect,
    Size,
    can_zoom,
    center_of,
    clamp_offset,
    offset_keeping,
    relative_point,
    wheel_steps,
    zoomed_size,
)
from ui_helpers.models.original_image_loader import OriginalImageLoader

# Lado largo de la mayor imagen de la caché: una más pequeña es la imagen entera que se
# pudo leer del archivo (la escalera de miniaturas nunca amplía)
_CACHE_FULL_SIDE = ThumbnailSize.FULLSCREEN.max_side

# Cuánto se mueve la foto a 1:1 por cada línea de un clic de rueda (px lógicos): con las
# 3 líneas de Windows, 120 px por clic
_WHEEL_LINE_PX = 40

# Lupa (px lógicos): tamaño del dibujo, centro y radio de la lente, mango y grosores
_CURSOR_SIZE = 24
_LENS_CENTER = 9.5
_LENS_RADIUS = 6.0
_HANDLE = (14.0, 20.5)  # del borde de la lente a la punta, en diagonal
_PLUS = 3.0  # medio brazo del «+»
_HALO_WIDTH = 4.0
_LINE_WIDTH = 1.6
_HOTSPOT = 9  # el centro de la lente


def magnifier_cursor(ratio: float) -> QCursor:
    """Cursor de lupa con «+» (ampliar), nítido con la escala de pantalla 'ratio'."""
    size = round(_CURSOR_SIZE * ratio)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(ratio)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    center = QPointF(_LENS_CENTER, _LENS_CENTER)
    # Primero el halo oscuro y encima el trazo claro: se ve sobre cualquier foto
    for color, width in ((CARD_COLORS.overlay_bg, _HALO_WIDTH), (CARD_COLORS.overlay_text, _LINE_WIDTH)):
        pen = QPen(QColor(color), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(center, _LENS_RADIUS, _LENS_RADIUS)
        painter.drawLine(QPointF(_HANDLE[0], _HANDLE[0]), QPointF(_HANDLE[1], _HANDLE[1]))
        painter.drawLine(center - QPointF(_PLUS, 0), center + QPointF(_PLUS, 0))
        painter.drawLine(center - QPointF(0, _PLUS), center + QPointF(0, _PLUS))
    painter.end()
    return QCursor(pixmap, _HOTSPOT, _HOTSPOT)


def _as_rect(rect: QRectF) -> Rect:
    return rect.x(), rect.y(), rect.width(), rect.height()


class SingleViewZoom(QObject):
    """El zoom 1:1 de una vista individual (ver el docstring del archivo)."""

    def __init__(self, view: QWidget, loader: OriginalImageLoader | None = None) -> None:
        """Se engancha a la vista (ratón, teclado, tamaño) con un filtro de eventos.

        Args:
            view: La vista individual.
            loader: Quien lee los originales (en las pruebas, uno de mentira).
        """
        super().__init__(view)
        self._view = view
        self._model: Any = None
        self._loader = loader if loader is not None else OriginalImageLoader(self)
        self._loader.loaded.connect(self._on_original)
        # El archivo que se ve
        self._media_id: int | None = None
        self._media_type = ""
        self._available = False
        self._file: MediaFile | None = None  # ruta y dimensiones (llegan en segundo plano)
        self._shown = QRectF()  # dónde se ve la foto en la vista ajustada
        self._source: tuple[int, int] | None = None  # la imagen de la caché que se ve
        # A 1:1: escala de la pantalla, píxeles de lo que se muestra a 1:1, su tamaño en
        # px lógicos, su esquina y el original (None mientras llega)
        self._active = False
        self._ratio = 1.0
        self._pixels: tuple[int, int] = (0, 0)
        self._zoomed: Size = (0.0, 0.0)
        self._offset: Point = (0.0, 0.0)
        self._original: QImage | None = None
        # Ratón: dónde se pulsó (None = no pulsado), la última posición y si se arrastra
        self._press: QPointF | None = None
        self._last = QPointF()
        self._dragging = False
        self._zoom_wheel = 0  # giro de Ctrl + rueda que aún no llega a un clic
        self._magnifiers: dict[float, QCursor] = {}
        view.setMouseTracking(True)
        view.installEventFilter(self)

    # -------------------------------------------------------------------------
    # Interfaz pública (la usa la vista)
    # -------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        """True si se ve a 1:1 (la vista le deja dibujar a él)."""
        return self._active

    def attach(self, model: Any) -> None:
        """El modelo de la cuadrícula (sabe pedir la ruta y las dimensiones de un archivo)."""
        self._model = model

    def track(self, media_id: int | None, media_type: str | None, availability: int) -> None:
        """Qué archivo se ve (lo dice la vista al dibujar). Si cambia, vuelve a la vista
        ajustada y pide su ruta y sus dimensiones; si deja de estar disponible, también."""
        available = availability == AVAILABLE
        if media_id != self._media_id:
            self.reset()
            self._media_id = media_id
            self._media_type = media_type or ""
            self._available = available
            self._file = None
            self._shown = QRectF()
            self._source = None
            self._request_file()
        elif available != self._available:
            self._available = available
            if not available:
                self.reset()
            elif self._file is None:
                self._request_file()

    def set_shown(self, rect: QRectF, source: QSize | None = None) -> None:
        """Dónde ha dibujado la vista la foto ajustada (vacío: no hay foto) y, si es la
        imagen grande de la caché, su tamaño (None: la miniatura de la cuadrícula, mientras
        llega; sin ella no se sabe qué se podrá ver a 1:1)."""
        size = None
        if source is not None and not source.isEmpty():
            size = (source.width(), source.height())
        if rect != self._shown or size != self._source:
            self._shown = QRectF(rect)
            self._source = size
            self._update_cursor()

    def paint(self, painter: QPainter, placeholder: QImage | QPixmap | None) -> None:
        """Dibuja la foto a 1:1: el original o, mientras llega, 'placeholder' (la imagen de
        la caché) ampliada al mismo tamaño."""
        ratio = self._view.devicePixelRatioF()
        if ratio != self._ratio:  # la ventana ha pasado a una pantalla con otra escala
            self._ratio = ratio
            area = self._area()
            self._keep_center(zoomed_size(self._pixels, ratio), area, area)
            if self._original is not None:
                self._original.setDevicePixelRatio(ratio)
        corner = QPointF(*self._offset)
        if self._original is not None:
            # Un píxel de la imagen en uno físico: sin escalar (la esquina, en un píxel entero)
            painter.drawImage(corner, self._original)
        elif placeholder is not None and not placeholder.isNull():
            target = QRectF(corner.x(), corner.y(), *self._zoomed)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            if isinstance(placeholder, QImage):
                painter.drawImage(target, placeholder)
            else:
                painter.drawPixmap(target, placeholder, QRectF(placeholder.rect()))
            painter.restore()

    def reset(self) -> None:
        """Vuelve a la vista ajustada y suelta el original de la memoria."""
        was_zoomed = self._active
        self._active = False
        self._original = None
        self._press = None
        self._dragging = False
        self._loader.cancel()
        if was_zoomed:
            self._view.update()
        self._update_cursor()

    def shutdown(self) -> None:
        """Para la lectura del original (al cerrar la aplicación)."""
        self._loader.shutdown()

    # -------------------------------------------------------------------------
    # Ratón, teclado y tamaño (filtro de eventos de la vista)
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # nombre de Qt
        if watched is not self._view:
            return False
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == Qt.MouseButton.LeftButton:
                self._press = self._last = event.position()
                self._dragging = False
                self._update_cursor()
        elif kind == QEvent.Type.MouseMove:
            self._on_mouse_move(event.position(), bool(event.buttons() & Qt.MouseButton.LeftButton))
        elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            clicked = self._press is not None and not self._dragging
            self._press = None
            self._dragging = False
            if clicked:
                if self._active:
                    self.reset()
                elif self._shown.contains(event.position()):
                    self._zoom_in(event.position())
            self._update_cursor(event.position())
        elif kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Z and event.modifiers() in (
            Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier
        ):
            if self._active:
                self.reset()
                return True
            if self._can_zoom():
                self._zoom_in(None)
                return True
        elif kind == QEvent.Type.Resize and self._active:
            old, new = event.oldSize(), event.size()
            if old.isValid():
                self._keep_center(
                    self._zoomed, (0.0, 0.0, old.width(), old.height()),
                    (0.0, 0.0, new.width(), new.height()),
                )  # fmt: skip
        elif kind == QEvent.Type.Wheel:
            return self._on_wheel(event)
        elif kind == QEvent.Type.Hide:
            self.reset()  # vuelta a la cuadrícula: se suelta el original
        return False  # el resto (y el foco al pulsar) sigue su camino

    def _on_wheel(self, event: QWheelEvent) -> bool:
        """Ctrl + rueda: zoom (un paso por clic). A 1:1, la rueda mueve la foto. Devuelve
        False si no es suya (la rueda sola en la vista ajustada: pasar de foto)."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps, self._zoom_wheel = wheel_steps(self._zoom_wheel, event.angleDelta().y())
            if steps > 0 and not self._active and self._can_zoom():
                position = event.position()
                self._zoom_in(position if self._shown.contains(position) else None)
            elif steps < 0 and self._active:
                self.reset()
            return True  # Ctrl + rueda nunca pasa de foto
        if not self._active:
            return False
        pixels = event.pixelDelta()
        if not pixels.isNull():  # paneles táctiles que dan el desplazamiento en píxeles
            dx, dy = float(pixels.x()), float(pixels.y())
        else:
            per_step = QApplication.wheelScrollLines() * _WHEEL_LINE_PX
            angle = event.angleDelta()
            dx, dy = angle.x() / WHEEL_STEP * per_step, angle.y() / WHEEL_STEP * per_step
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and not dx:
            dx, dy = dy, 0.0  # Mayús + rueda: en horizontal
        self._offset = clamp_offset(
            (self._offset[0] + dx, self._offset[1] + dy), self._zoomed, self._area(), self._ratio
        )
        self._view.update()
        return True

    def _on_mouse_move(self, position: QPointF, pressed: bool) -> None:
        """Arrastrar (a 1:1, mueve la foto) o, sin botón, el cursor que toca."""
        if self._press is None or not pressed:
            self._update_cursor(position)
            return
        if not self._dragging:
            moved = (position - self._press).manhattanLength()
            self._dragging = moved >= QApplication.startDragDistance()
        if self._dragging and self._active:
            delta = position - self._last
            self._offset = clamp_offset(
                (self._offset[0] + delta.x(), self._offset[1] + delta.y()),
                self._zoomed, self._area(), self._ratio,
            )  # fmt: skip
            self._view.update()
        self._last = position

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _area(self) -> Rect:
        """El espacio a 1:1: toda la vista (sin el margen de la ajustada)."""
        return 0.0, 0.0, float(self._view.width()), float(self._view.height())

    def _request_file(self) -> None:
        """Pide al modelo la ruta y las dimensiones del archivo que se ve (solo fotos)."""
        request = getattr(self._model, "request_media_file", None)
        if request is None or self._media_id is None or self._media_type != MediaType.PHOTO:
            return
        media_id = self._media_id
        request(media_id, lambda file: self._on_file(media_id, file))

    def _on_file(self, media_id: int, file: MediaFile | None) -> None:
        if media_id == self._media_id:
            self._file = file
            self._update_cursor()

    def _full_pixels(self) -> tuple[int, int] | None:
        """Lo que se verá a 1:1 (ver «Qué se verá a 1:1» en el docstring del archivo), o
        None si aún no se sabe."""
        if self._source is None:
            return None  # aún se ve la miniatura de la cuadrícula
        if max(self._source) < _CACHE_FULL_SIDE:
            return self._source  # no había nada mayor que leer
        return self._file.pixels if self._file is not None else None

    def _can_zoom(self) -> bool:
        """Si ahora se puede ampliar: foto disponible, de tamaño conocido y mayor a 1:1."""
        pixels = self._full_pixels()
        if self._active or not self._available or self._file is None or pixels is None:
            return False
        if self._shown.isEmpty():
            return False
        return self._gains(pixels)

    def _gains(self, pixels: tuple[int, int]) -> bool:
        """Si una imagen de 'pixels' a 1:1 se ve más grande que la foto ajustada."""
        zoomed = zoomed_size(pixels, self._view.devicePixelRatioF())
        return can_zoom((self._shown.width(), self._shown.height()), zoomed)

    def _zoom_in(self, position: QPointF | None) -> None:
        """A 1:1: el punto pulsado bajo el ratón (sin punto: el centro, en el centro)."""
        pixels = self._full_pixels()
        if not self._can_zoom() or self._file is None or pixels is None:
            return
        self._ratio = self._view.devicePixelRatioF()
        self._pixels = pixels
        self._zoomed = zoomed_size(self._pixels, self._ratio)
        area = self._area()
        if position is None:
            relative, anchor = (0.5, 0.5), center_of(area)
        else:
            anchor = (position.x(), position.y())
            relative = relative_point(_as_rect(self._shown), anchor)
        self._offset = offset_keeping(relative, anchor, self._zoomed, area, self._ratio)
        self._active = True
        self._original = None
        self._loader.request(self._media_type, self._file.media_id, self._file.path)
        self._update_cursor()
        self._view.update()

    def _on_original(self, media_id: int, image: QImage) -> None:
        """Ha llegado el original: sustituye a la imagen de la caché ampliada."""
        if not self._active or media_id != self._media_id or image.isNull():
            return  # tarde, de otro archivo, o no se pudo leer (sigue la de la caché)
        pixels = (image.width(), image.height())
        if self._file is not None and pixels != self._file.pixels:
            # Lo que de verdad se puede ver (p. ej. la vista previa de un RAW): manda para
            # esta foto desde ahora
            self._file = replace(self._file, pixels=pixels)
        if not self._gains(pixels):
            self.reset()  # no se ve más grande que la ajustada: a ella, y sin lupa
            return
        if pixels != self._pixels:  # p. ej. la vista previa de un RAW: el centro, igual
            self._pixels = pixels
            area = self._area()
            self._keep_center(zoomed_size(pixels, self._ratio), area, area)
        image.setDevicePixelRatio(self._ratio)
        self._original = image
        self._view.update()

    def _keep_center(self, zoomed: Size, old_area: Rect, new_area: Rect) -> None:
        """Nuevo tamaño (o espacio) a 1:1, con el punto del centro de la foto en el centro."""
        relative = relative_point((*self._offset, *self._zoomed), center_of(old_area))
        self._zoomed = zoomed
        self._offset = offset_keeping(relative, center_of(new_area), zoomed, new_area, self._ratio)
        self._view.update()

    def _update_cursor(self, position: QPointF | None = None) -> None:
        """Lupa sobre una foto que se puede ampliar; manos a 1:1; si no, el normal."""
        if self._active:
            closed = self._press is not None
            self._view.setCursor(Qt.CursorShape.ClosedHandCursor if closed else Qt.CursorShape.OpenHandCursor)
            return
        if position is None:
            position = QPointF(self._view.mapFromGlobal(QCursor.pos()))
        if self._can_zoom() and self._shown.contains(position):
            ratio = self._view.devicePixelRatioF()
            if ratio not in self._magnifiers:
                self._magnifiers[ratio] = magnifier_cursor(ratio)
            self._view.setCursor(self._magnifiers[ratio])
        else:
            self._view.unsetCursor()


if __name__ == "__main__":
    # Autoprueba SIN ventana: eventos de ratón y teclado enviados a mano, un modelo y un
    # cargador de mentira. Ejecutar desde la raíz:  python -m ui_helpers.widgets.single_view_zoom
    import os
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import QPoint, QSize, Signal
    from qtpy.QtGui import QKeyEvent, QMouseEvent, QResizeEvent

    app = QApplication([])

    class _Loader(QObject):
        """Apunta lo que se le pide; el original lo «entrega» la prueba."""

        loaded = Signal(int, QImage)

        def __init__(self) -> None:
            super().__init__()
            self.requests: list[int] = []
            self.cancels = 0

        def request(self, _media_type: str, media_id: int, _path: Path) -> None:
            self.requests.append(media_id)

        def cancel(self) -> None:
            self.cancels += 1

        def shutdown(self) -> None:
            pass

    class _Model:
        """Responde en el acto con las dimensiones de cada archivo."""

        def __init__(self) -> None:
            self.files = {
                1: MediaFile(1, Path("a.jpg"), (6000, 4000), AVAILABLE),
                2: MediaFile(2, Path("b.jpg"), None, AVAILABLE),  # sin leer metadatos
            }

        def request_media_file(self, media_id: int, on_result: Any) -> bool:
            on_result(self.files.get(media_id))
            return True

    view = QWidget()
    view.resize(1000, 600)
    loader = _Loader()
    zoom = SingleViewZoom(view, loader)  # type: ignore[arg-type]
    zoom.attach(_Model())
    SHOWN = QRectF(50, 0, 900, 600)  # la vista ajustada de una foto de 3:2
    BIG = QSize(2560, 1707)  # su imagen grande de la caché (la foto pasa de 2560 px)

    def mouse(kind: QEvent.Type, x: float, y: float, button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> None:
        held = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
        if kind == QEvent.Type.MouseMove and button == Qt.MouseButton.NoButton:
            held = Qt.MouseButton.NoButton
        point = QPointF(x, y)
        event = QMouseEvent(kind, point, point, button if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
                            held, Qt.KeyboardModifier.NoModifier)  # fmt: skip
        QApplication.sendEvent(view, event)

    def click(x: float, y: float) -> None:
        mouse(QEvent.Type.MouseButtonPress, x, y)
        mouse(QEvent.Type.MouseButtonRelease, x, y)

    def key_z() -> None:
        QApplication.sendEvent(view, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier))

    def shape() -> Qt.CursorShape:
        return view.cursor().shape()

    # 1. Lupa sobre la foto; fuera de ella (el margen), el cursor normal
    zoom.track(1, "photo", AVAILABLE)
    zoom.set_shown(SHOWN, BIG)
    mouse(QEvent.Type.MouseMove, 500, 300, Qt.MouseButton.NoButton)
    assert shape() == Qt.CursorShape.BitmapCursor, shape()
    mouse(QEvent.Type.MouseMove, 10, 300, Qt.MouseButton.NoButton)
    assert shape() == Qt.CursorShape.ArrowCursor, shape()
    click(10, 300)  # clic en el margen: nada
    assert not zoom.active

    # 2. Clic en el centro: 1:1 con ese punto bajo el ratón; mano abierta; se pide el original
    click(500, 300)
    assert zoom.active and zoom._offset == (500 - 3000, 300 - 2000), zoom._offset
    assert loader.requests == [1] and shape() == Qt.CursorShape.OpenHandCursor

    # 3. Arrastrar: mano cerrada y la foto se mueve con el ratón (sin volver a la ajustada)
    mouse(QEvent.Type.MouseButtonPress, 500, 300)
    assert shape() == Qt.CursorShape.ClosedHandCursor
    mouse(QEvent.Type.MouseMove, 520, 300)  # pasa el umbral: empieza a arrastrar
    mouse(QEvent.Type.MouseMove, 600, 350)
    mouse(QEvent.Type.MouseButtonRelease, 600, 350)
    assert zoom.active and zoom._offset == (-2400, -1650), zoom._offset
    assert shape() == Qt.CursorShape.OpenHandCursor
    # Arrastrar más allá del borde: la foto no se separa de él
    mouse(QEvent.Type.MouseButtonPress, 100, 100)
    mouse(QEvent.Type.MouseMove, 120, 100)
    mouse(QEvent.Type.MouseMove, 9000, 9000)
    mouse(QEvent.Type.MouseButtonRelease, 9000, 9000)
    assert zoom._offset == (0, 0), zoom._offset

    # 4. Llega el original con otro tamaño (p. ej. la vista previa de un RAW): el punto del
    #    centro sigue en el centro; se dibuja sin escalar
    zoom._offset = (-2500.0, -1700.0)
    middle = relative_point((*zoom._offset, *zoom._zoomed), (500, 300))
    original = QImage(3000, 2000, QImage.Format.Format_RGB32)
    original.fill(QColor(0, 200, 0))
    loader.loaded.emit(1, original)
    assert zoom._zoomed == (3000, 2000)
    now = relative_point((*zoom._offset, *zoom._zoomed), (500, 300))
    assert all(abs(a - b) < 0.001 for a, b in zip(middle, now, strict=True)), (middle, now)
    canvas = QImage(1000, 600, QImage.Format.Format_RGB32)
    canvas.fill(QColor(0, 0, 0))
    painter = QPainter(canvas)
    zoom.paint(painter, None)
    painter.end()
    assert canvas.pixelColor(500, 300).green() == 200
    # Un original de otro archivo (tarde) o que no se pudo leer: no cambia nada
    loader.loaded.emit(7, QImage(10, 10, QImage.Format.Format_RGB32))
    loader.loaded.emit(1, QImage())
    # (la señal entrega una copia de la QImage: se compara su tamaño y su color)
    assert zoom._original is not None and zoom._original.size() == QSize(3000, 2000)
    assert zoom._original.pixelColor(10, 10).green() == 200

    # 5. Cambia el tamaño de la ventana: el punto del centro sigue en el centro
    middle = relative_point((*zoom._offset, *zoom._zoomed), (500, 300))
    view.resize(1200, 800)
    QApplication.sendEvent(view, QResizeEvent(QSize(1200, 800), QSize(1000, 600)))
    now = relative_point((*zoom._offset, *zoom._zoomed), (600, 400))
    assert all(abs(a - b) < 0.001 for a, b in zip(middle, now, strict=True)), (middle, now)
    view.resize(1000, 600)
    QApplication.sendEvent(view, QResizeEvent(QSize(1000, 600), QSize(1200, 800)))

    # 6. Clic sin arrastrar: vuelve a la ajustada y suelta el original
    cancels = loader.cancels
    click(500, 300)
    assert not zoom.active and zoom._original is None and loader.cancels > cancels
    assert shape() == Qt.CursorShape.BitmapCursor  # el ratón sigue sobre la foto: lupa

    # 7. Z: amplía desde el centro y vuelve (a 3000 × 2000: lo que midió su original en el
    #    paso 4, que manda desde entonces)
    key_z()
    assert zoom.active and zoom._offset == (500 - 1500, 300 - 1000), zoom._offset
    key_z()
    assert not zoom.active

    # 8. Otro archivo, la vista oculta o el archivo no disponible: vuelta a la ajustada
    click(500, 300)
    zoom.track(3, "photo", AVAILABLE)
    assert not zoom.active
    zoom.track(1, "photo", AVAILABLE)
    zoom.set_shown(SHOWN, BIG)
    click(500, 300)
    QApplication.sendEvent(view, QEvent(QEvent.Type.Hide))
    assert not zoom.active
    click(500, 300)
    zoom.track(1, "photo", 1)  # MISSING
    assert not zoom.active
    click(500, 300)  # no disponible: no amplía
    assert not zoom.active and shape() == Qt.CursorShape.ArrowCursor

    # 9. Sin dimensiones (metadatos sin leer), un vídeo o una foto que ya cabe: sin lupa
    zoom.track(2, "photo", AVAILABLE)
    zoom.set_shown(SHOWN, BIG)
    click(500, 300)
    assert not zoom.active
    zoom.track(1, "video", AVAILABLE)  # mismo id, otro tipo: no se piden dimensiones
    zoom.track(4, "video", AVAILABLE)
    zoom.set_shown(SHOWN, BIG)
    click(500, 300)
    assert not zoom.active
    zoom.track(1, "photo", AVAILABLE)
    zoom.set_shown(QRectF(0, 0, 6000, 4000), BIG)  # ya se ve a su tamaño
    click(100, 100)
    assert not zoom.active

    # 10. Caché pequeña (un DNG con una vista previa de 1024 px, aunque el catálogo diga
    #     6000 × 4000): no hay nada mayor que leer; a su tamaño ya se ve entera: sin lupa
    zoom.track(5, "photo", AVAILABLE)
    zoom._on_file(5, MediaFile(5, Path("e.dng"), (6000, 4000), AVAILABLE))
    natural = QRectF(38, 0, 1024, 683)
    zoom.set_shown(natural, QSize(1024, 683))
    mouse(QEvent.Type.MouseMove, 500, 300, Qt.MouseButton.NoButton)
    assert shape() == Qt.CursorShape.ArrowCursor, shape()
    click(500, 300)
    assert not zoom.active
    # La misma caché pequeña en un espacio menor (reducida para caber): sí se amplía, a 1024
    zoom.set_shown(QRectF(100, 100, 600, 400), QSize(1024, 683))
    click(400, 300)
    assert zoom.active and zoom._zoomed == (1024, 683), zoom._zoomed
    click(400, 300)
    # Mientras se ve la miniatura de la cuadrícula (sin imagen de la caché): sin lupa
    zoom.track(6, "photo", AVAILABLE)
    zoom._on_file(6, MediaFile(6, Path("f.jpg"), (6000, 4000), AVAILABLE))
    zoom.set_shown(SHOWN)
    click(500, 300)
    assert not zoom.active
    # Llega un original que no es mayor que la ajustada: vuelve a ella, y ya sin lupa
    zoom.set_shown(SHOWN, BIG)
    click(500, 300)
    assert zoom.active
    loader.loaded.emit(6, QImage(900, 600, QImage.Format.Format_RGB32))
    assert not zoom.active and zoom._file.pixels == (900, 600)
    click(500, 300)
    assert not zoom.active and shape() == Qt.CursorShape.ArrowCursor

    # 11. Rueda: Ctrl + rueda amplía en el punto del ratón y vuelve; a 1:1 la rueda mueve la
    #     foto (Mayús: en horizontal); la rueda sola en la ajustada no es del zoom
    def wheel(dy: int, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
              x: float = 500, y: float = 300) -> bool:  # fmt: skip
        point = QPointF(x, y)
        event = QWheelEvent(point, point, QPoint(0, 0), QPoint(0, dy), Qt.MouseButton.NoButton,
                            modifiers, Qt.ScrollPhase.NoScrollPhase, False)  # fmt: skip
        return zoom.eventFilter(view, event)

    zoom.track(1, "photo", AVAILABLE)
    zoom.set_shown(SHOWN, BIG)
    assert wheel(-120) is False and not zoom.active  # sin Ctrl, en la ajustada: de la vista
    CTRL = Qt.KeyboardModifier.ControlModifier
    assert wheel(-120, CTRL) and not zoom.active  # hacia atrás, en la ajustada: nada
    assert wheel(40, CTRL) and not zoom.active  # menos de un clic (panel táctil): aún nada
    assert wheel(80, CTRL, 500, 300) and zoom.active  # completa el clic: 1:1 en el ratón
    assert zoom._offset == (500 - 3000, 300 - 2000), zoom._offset
    assert wheel(-120) and zoom._offset == (500 - 3000, 300 - 2000 - 120)  # baja 120 px
    assert wheel(120) and zoom._offset == (500 - 3000, 300 - 2000)  # y vuelve a subir
    assert wheel(-120, Qt.KeyboardModifier.ShiftModifier)  # Mayús: en horizontal
    assert zoom._offset == (500 - 3000 - 120, 300 - 2000), zoom._offset
    assert wheel(120, CTRL) and zoom.active  # hacia delante, a 1:1: nada más (de momento)
    assert wheel(-120, CTRL) and not zoom.active  # hacia atrás: a la ajustada
    # Fuera de la foto (en el margen): desde el centro
    assert wheel(120, CTRL, 10, 10) and zoom._offset == (500 - 3000, 300 - 2000)
    zoom.reset()

    # 12. La lupa: transparente fuera del dibujo y con el trazo claro en la lente
    cursor = magnifier_cursor(1.0).pixmap().toImage()
    assert cursor.width() == _CURSOR_SIZE and cursor.pixelColor(0, 23).alpha() == 0
    # Arriba de la lente (centro 9,5 y radio 6: el trazo pasa por el píxel 9, 3), claro
    assert cursor.pixelColor(9, 3).lightness() > 200, cursor.pixelColor(9, 3).name()
    print("Autoprueba finalizada correctamente.")
