"""Prueba de concepto del mapa (docs/MAPA.md, fase 0). NO es código de la aplicación.

Sirve para decidir, con datos y en la máquina del autor, si el componente de mapa se
hace con QtWebEngine + Leaflet (plan A) o con Qt Location (plan B). No importa nada del
proyecto ni lo toca: se puede borrar entera cuando se haya decidido.

Qué monta: una ventana con una lista de «tarjetas» a la izquierda (se arrastran con el
mismo formato que la cuadrícula, 'application/x-arca-media-ids') y, a la derecha, dos
páginas: una FOTO grande que se arrastra con el ratón (dibujada con QPainter, como la
vista individual a 1:1) y el MAPA, que no se crea hasta que se pulsa «Mapa».

Qué hay que mirar (los números salen en la consola):
    1. Foto: arrastrarla deprisa ANTES de crear el mapa y otra vez DESPUÉS. ¿Cambian los
       cortes horizontales? (Al crear la vista web, la ventana pasa a componerse con la GPU.)
    2. «Mapa»: ¿parpadea la ventana al crearlo? Tiempo hasta que está listo.
    3. Capa del IGN y de OpenTopoMap (desplegable). Segunda ejecución con --offline:
       lo ya visto se sigue viendo (caché en la carpeta temporal del sistema).
    4. «Track»: un GPX (los pasados como argumento, o uno inventado de 10 000 puntos). Al
       pasar el ratón por la línea, un punto la sigue y la barra dice su índice.
    5. «Marcadores»: 20 000 agrupados. Mover y hacer zoom: ¿va fluido? Clic en un grupo.
    6. «Marcador arrastrable»: al soltarlo, la consola dice su latitud y longitud.
    7. Arrastrar tarjetas de la lista al mapa: la consola dice los id, la coordenada, por
       dónde llegó el evento (subclase, filtro o capa) y el error en píxeles (mover un
       poco el ratón después de soltar, sin pulsar).
    8. Teclado: con el ratón sobre el mapa (también tras un clic en él), las flechas
       siguen moviendo la selección de la lista. La consola avisa de cada cambio de foco.
    9. «Ida y vuelta» (latencia Python <-> página) y «Medidas» (memoria y teselas).

Uso (desde la raíz del proyecto, con el Python de .venv):
    .venv\\Scripts\\python.exe scripts/poc_map/poc_map.py [ruta.gpx ...]
        --points N     puntos del track inventado (por defecto, 10000)
        --markers N    marcadores de la prueba (por defecto, 20000)
        --photo RUTA   una foto propia para la página «Foto» (por defecto, una inventada)
        --overlay      recibir la soltada con una capa transparente sobre el mapa
        --offline      no descargar teselas: solo la caché
        --selftest     sin intervención: crea el mapa, lo prueba unos segundos y sale

1.0.0 Primera versión (13/11/2026).
"""

__version__ = "1.0.0"
__all__ = ["main"]

# Librerías estándar
import argparse
import colorsys
import json
import math
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from functools import partial
from pathlib import Path

# Librerías de terceros
from defusedxml.ElementTree import iterparse

# Librerías de terceros (Qt)
from qtpy.QtCore import (
    QBuffer,
    QByteArray,
    QCoreApplication,
    QEvent,
    QFile,
    QIODevice,
    QMimeData,
    QObject,
    QPoint,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from qtpy.QtGui import QColor, QFont, QImage, QPainter, QPixmap, QStandardItem, QStandardItemModel
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qtpy.QtWebChannel import QWebChannel
from qtpy.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

PAGE_DIR = Path(__file__).resolve().parent / "page"
CACHE_DIR = Path(tempfile.gettempdir()) / "arca_poc_map_cache"

SCHEME = b"arca-map"
START_URL = "arca-map://app/index.html"
# Identificación ante los servidores de teselas: sin datos personales
USER_AGENT = b"ArcaMedia-PoC/1.0 (prueba de concepto)"

# El mismo formato con el que arrastra la cuadrícula (ui_helpers/models/media_mime.py);
# copiado aquí para que la prueba no importe nada del proyecto
MEDIA_IDS_MIME = "application/x-arca-media-ids"

# Capas de la prueba: (texto, plantilla de la dirección, tipo MIME, extensión).
# Direcciones a comprobar aquí mismo: si una capa no se ve, la consola dice el error.
LAYERS: dict[str, tuple[str, str, bytes, str]] = {
    "ign_mtn": (
        "IGN España (MTN)",
        (
            "https://www.ign.es/wmts/mapa-raster?layer=MTN&style=default"
            "&tilematrixset=GoogleMapsCompatible&Service=WMTS&Request=GetTile&Version=1.0.0"
            "&Format=image/jpeg&TileMatrix={z}&TileCol={x}&TileRow={y}"
        ),
        b"image/jpeg",
        "jpg",
    ),
    "opentopo": (
        "OpenTopoMap",
        "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        b"image/png",
        "png",
    ),
}

_MIME_BY_SUFFIX = {
    ".html": b"text/html",
    ".js": b"text/javascript",
    ".css": b"text/css",
    ".png": b"image/png",
}

_DRAG_EVENTS = (
    QEvent.Type.DragEnter,
    QEvent.Type.DragMove,
    QEvent.Type.DragLeave,
    QEvent.Type.Drop,
)


def say(text: str) -> None:
    """Escribe en la consola en el acto (la ventana sigue abierta mientras tanto)."""
    print(text, flush=True)


# -----------------------------------------------------------------------------
# Esquema arca-map:// (recursos de la página, teselas con caché y miniaturas)
# -----------------------------------------------------------------------------


def register_scheme() -> None:
    """Da de alta el esquema. Qt lo exige ANTES de crear QApplication."""
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class MapSchemeHandler(QWebEngineUrlSchemeHandler):
    """Atiende arca-map://app/... (recursos), /tiles/... (teselas) y /thumb/... (miniaturas)."""

    def __init__(self, *, offline: bool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._offline = offline
        self._network = QNetworkAccessManager(self)
        self._thumbs: dict[int, bytes] = {}
        self.stats = {"cache": 0, "red": 0, "error": 0, "bytes": 0, "miniaturas": 0}
        self.tile_ms: list[float] = []  # tiempo de cada descarga
        self._errors_shown = 0

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # nombre de Qt
        url = job.requestUrl()
        host, parts = url.host(), [p for p in url.path().split("/") if p]
        try:
            if host == "app":
                self._serve_asset(job, parts)
            elif host == "tiles" and len(parts) == 4:
                self._serve_tile(job, parts[0], int(parts[1]), int(parts[2]), int(parts[3]))
            elif host == "thumb" and len(parts) == 1:
                self._serve_thumb(job, int(parts[0]))
            else:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
        except (ValueError, KeyError):
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)

    @staticmethod
    def _reply(job: QWebEngineUrlRequestJob, mime: bytes, data: bytes) -> None:
        """Responde con unos bytes. El búfer es hijo de la petición: se borra con ella."""
        try:
            buffer = QBuffer(job)
            buffer.setData(QByteArray(data))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            job.reply(QByteArray(mime), buffer)
        except RuntimeError:
            pass  # la página ya no espera esa petición (se canceló al mover el mapa)

    @staticmethod
    def _fail(job: QWebEngineUrlRequestJob) -> None:
        try:
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
        except RuntimeError:
            pass

    def _serve_asset(self, job: QWebEngineUrlRequestJob, parts: list[str]) -> None:
        if parts == ["qwebchannel.js"]:
            # Viene dentro de Qt (recurso del módulo QtWebChannel)
            resource = QFile(":/qtwebchannel/qwebchannel.js")
            if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            self._reply(job, b"text/javascript", bytes(resource.readAll()))
            return
        path = PAGE_DIR.joinpath(*parts).resolve()
        if PAGE_DIR not in path.parents or not path.is_file():  # nada de fuera de la carpeta
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), b"application/octet-stream")
        self._reply(job, mime, path.read_bytes())

    def _serve_tile(self, job: QWebEngineUrlRequestJob, layer: str, z: int, x: int, y: int) -> None:
        _text, template, mime, extension = LAYERS[layer]
        path = CACHE_DIR / layer / str(z) / str(x) / f"{y}.{extension}"
        if path.is_file():
            self.stats["cache"] += 1
            self._reply(job, mime, path.read_bytes())
            return
        if self._offline:
            self._fail(job)
            return
        request = QNetworkRequest(QUrl(template.format(z=z, x=x, y=y)))
        # Con 'setRawHeader': 'setHeader' no acepta bytes desde Python (avisa y no la pone)
        request.setRawHeader(b"User-Agent", USER_AGENT)
        reply = self._network.get(request)
        reply.finished.connect(partial(self._on_tile, reply, job, path, mime, time.perf_counter()))

    def _on_tile(
        self,
        reply: QNetworkReply,
        job: QWebEngineUrlRequestJob,
        path: Path,
        mime: bytes,
        started: float,
    ) -> None:
        reply.deleteLater()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        data = bytes(reply.readAll())
        if reply.error() != QNetworkReply.NetworkError.NoError or status != 200 or not data:
            self.stats["error"] += 1
            if self._errors_shown < 5:  # sin llenar la consola
                self._errors_shown += 1
                say(f"  [tesela] error {status}: {reply.errorString()} · {reply.url().toString()}")
            self._fail(job)
            return
        self.stats["red"] += 1
        self.stats["bytes"] += len(data)
        self.tile_ms.append((time.perf_counter() - started) * 1000)
        # Escritura atómica: nunca queda una tesela a medias en la caché
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)
        self._reply(job, mime, data)

    def _serve_thumb(self, job: QWebEngineUrlRequestJob, media_id: int) -> None:
        """Una «miniatura» inventada (en la aplicación saldrá de la caché del catálogo)."""
        data = self._thumbs.get(media_id)
        if data is None:
            data = _png_bytes(_fake_thumbnail(media_id, 64))
            self._thumbs[media_id] = data
        self.stats["miniaturas"] += 1
        self._reply(job, b"image/png", data)


def _fake_thumbnail(media_id: int, size: int) -> QImage:
    """Un cuadrado de color con el número (colores sueltos: es una prueba)."""
    image = QImage(size, size, QImage.Format.Format_RGB32)
    red, green, blue = colorsys.hsv_to_rgb((media_id * 0.618) % 1.0, 0.55, 0.85)
    image.fill(QColor.fromRgbF(red, green, blue))
    painter = QPainter(image)
    painter.setPen(QColor("#1a1a1a"))
    font = QFont()
    font.setPixelSize(max(9, size // 4))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, str(media_id))
    painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


# -----------------------------------------------------------------------------
# Puente con la página y vista web
# -----------------------------------------------------------------------------


class Bridge(QObject):
    """Lo que la página puede decirle a Python (QWebChannel)."""

    ready = Signal()
    hovered = Signal(int)
    pong = Signal(float)
    timing = Signal(str, float, int)

    @Slot()
    def on_ready(self) -> None:
        self.ready.emit()

    @Slot(str, int)
    def on_select(self, ids_json: str, total: int) -> None:
        say(f"  [selección] {total} elemento(s); los primeros: {ids_json}")

    @Slot(float, float)
    def on_marker_moved(self, latitude: float, longitude: float) -> None:
        say(f"  [marcador] soltado en {latitude:.6f}, {longitude:.6f}")

    @Slot(int)
    def on_track_hover(self, point_index: int) -> None:
        self.hovered.emit(point_index)

    @Slot(str, float, int)
    def on_timing(self, name: str, milliseconds: float, count: int) -> None:
        say(f"  [página] {name}: {count} elementos en {milliseconds:.0f} ms")
        self.timing.emit(name, milliseconds, count)

    @Slot(float)
    def on_drop_error(self, pixels: float) -> None:
        say(f"  [soltar] error entre el punto de Qt y el ratón en la página: {pixels:.1f} px")

    @Slot(float)
    def on_pong(self, token: float) -> None:
        self.pong.emit(token)


class MapPage(QWebEnginePage):
    """Página del mapa: enseña sus mensajes de consola y no sale del esquema propio."""

    def __init__(self, profile: QWebEngineProfile, parent: QObject | None = None) -> None:
        super().__init__(profile, parent)
        self.js_errors = 0

    def javaScriptConsoleMessage(  # nombre de Qt
        self, level: object, message: str, line: int, source: str
    ) -> None:
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.js_errors += 1
        say(f"  [js] {message} ({Path(source).name}:{line})")

    def acceptNavigationRequest(  # nombre de Qt
        self, url: QUrl, _navigation_type: object, _is_main_frame: bool
    ) -> bool:
        return url.scheme() == SCHEME.decode()


class MapWebView(QWebEngineView):
    """La vista web: intercepta las tarjetas arrastradas y no coge el teclado.

    El arrastre puede llegar por tres sitios, y la prueba dice por cuál llegó:
        'subclase'  los eventos de arrastre de esta clase;
        'filtro'    un filtro de eventos en los widgets internos de la vista web;
        'capa'      una capa transparente encima (solo con --overlay).
    """

    def __init__(self, profile: QWebEngineProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.created_at = time.perf_counter()
        self.bridge = Bridge(self)
        self.map_page = MapPage(profile, self)
        channel = QWebChannel(self.map_page)
        channel.registerObject("bridge", self.bridge)
        self.map_page.setWebChannel(channel)
        self.setPage(self.map_page)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._watched: set[int] = set()
        self._dragging = False
        self._origin_shown = ""
        self.loadFinished.connect(self._watch_children)
        self.load(QUrl(START_URL))
        self._watch_children()

    def js(self, code: str) -> None:
        self.map_page.runJavaScript(code)

    def call(self, function: str, *arguments: object) -> None:
        """Llama a una función de la página; los argumentos viajan SIEMPRE como JSON."""
        self.js(f"arca.{function}({', '.join(json.dumps(a) for a in arguments)})")

    # --- Widgets internos: sin teclado y con el filtro del arrastre ---

    def _watch_children(self, *_args: object) -> None:
        proxy = self.focusProxy()
        for child in [*self.findChildren(QWidget), *([proxy] if proxy is not None else [])]:
            if id(child) in self._watched:
                continue
            self._watched.add(id(child))
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            child.installEventFilter(self)

    def childEvent(self, event: QEvent) -> None:  # nombre de Qt
        super().childEvent(event)
        if event.type() == QEvent.Type.ChildAdded:
            QTimer.singleShot(0, self._watch_children)  # el hijo aún no está construido del todo

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # nombre de Qt
        if event.type() in _DRAG_EVENTS and isinstance(watched, QWidget):
            offset = watched.mapTo(self, QPoint(0, 0))
            if self.handle_drag(event, f"filtro ({type(watched).__name__})", offset):
                return True
        return super().eventFilter(watched, event)

    # --- Arrastre de tarjetas ---

    def handle_drag(self, event: QEvent, origin: str, offset: QPoint | None = None) -> bool:
        """Atiende un evento de arrastre si trae tarjetas. True = atendido."""
        kind = event.type()
        if kind == QEvent.Type.DragLeave:
            if not self._dragging:
                return False
            self._dragging = False
            self.call("setDropCursor", None)
            return True
        if not event.mimeData().hasFormat(MEDIA_IDS_MIME):
            return False
        position = event.position()
        x = position.x() + (offset.x() if offset else 0)
        y = position.y() + (offset.y() if offset else 0)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            self._dragging = True
            self.call("setDropCursor", x, y)
            return True
        # Soltada
        self._dragging = False
        if origin != self._origin_shown:
            self._origin_shown = origin
            say(f"  [soltar] el evento llega por: {origin}")
        data = json.loads(bytes(event.mimeData().data(MEDIA_IDS_MIME)).decode("utf-8"))
        ids = data.get("ids", [])
        # La respuesta vuelve como texto JSON (una lista de JavaScript no llega bien a Python)
        self.map_page.runJavaScript(
            f"JSON.stringify(arca.dropAt({json.dumps(x)}, {json.dumps(y)}))",
            0,
            lambda result: say(
                f"  [soltar] ids {ids} en el píxel ({x:.0f}, {y:.0f}) -> "
                + (_coordinates_text(result) or "sin respuesta de la página")
            ),
        )
        return True

    def dragEnterEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not self.handle_drag(event, "subclase"):
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not self.handle_drag(event, "subclase"):
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not self.handle_drag(event, "subclase"):
            super().dragLeaveEvent(event)

    def dropEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not self.handle_drag(event, "subclase"):
            super().dropEvent(event)


def _coordinates_text(result: object) -> str:
    """«42.650000, 0.030000» a partir del JSON '[lat, lon]' que devuelve la página ('' si no vale)."""
    try:
        latitude, longitude = json.loads(result)
        return f"{float(latitude):.6f}, {float(longitude):.6f}"
    except (TypeError, ValueError):
        return ""


class DropOverlay(QWidget):
    """Capa transparente sobre el mapa, visible solo mientras dura un arrastre (--overlay)."""

    def __init__(self, view: MapWebView, parent: QWidget) -> None:
        super().__init__(parent)
        self._view = view
        self.setAcceptDrops(True)
        self.hide()

    def event(self, event: QEvent) -> bool:  # nombre de Qt
        if event.type() in _DRAG_EVENTS and self._view.handle_drag(event, "capa transparente"):
            return True
        return super().event(event)


# -----------------------------------------------------------------------------
# Lista de tarjetas y página de la foto
# -----------------------------------------------------------------------------


class CardModel(QStandardItemModel):
    """Tarjetas de prueba que se arrastran con el formato de la cuadrícula."""

    def mimeTypes(self) -> list[str]:  # nombre de Qt
        return [MEDIA_IDS_MIME]

    def mimeData(self, indexes: list) -> QMimeData:  # nombre de Qt
        ids = [index.data(Qt.ItemDataRole.UserRole) for index in indexes]
        mime = QMimeData()
        payload = json.dumps({"catalog": "poc", "ids": ids})
        mime.setData(MEDIA_IDS_MIME, QByteArray(payload.encode("utf-8")))
        return mime

    def supportedDragActions(self) -> Qt.DropAction:  # nombre de Qt
        return Qt.DropAction.CopyAction


class CardList(QListView):
    """La lista; avisa antes y después de cada arrastre (para la capa transparente)."""

    drag_started = Signal()
    drag_finished = Signal()

    def startDrag(self, actions: Qt.DropAction) -> None:  # nombre de Qt
        self.drag_started.emit()
        super().startDrag(actions)  # no vuelve hasta que se suelta
        self.drag_finished.emit()


class PhotoPage(QWidget):
    """Una foto grande que se arrastra con el ratón, dibujada con QPainter (sin escalar),
    como la vista individual a 1:1: para ver los cortes horizontales al mover deprisa."""

    def __init__(self, photo: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = QImage(str(photo)) if photo else QImage()
        if self._image.isNull():
            self._image = self._striped_image()
        else:
            self._image = self._image.convertToFormat(QImage.Format.Format_RGB32)
        self._offset = QPoint(0, 0)
        self._last: QPoint | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    @staticmethod
    def _striped_image() -> QImage:
        """6000 × 4000 con franjas verticales muy contrastadas: los cortes se ven enseguida."""
        image = QImage(6000, 4000, QImage.Format.Format_RGB32)
        image.fill(QColor("#202020"))
        painter = QPainter(image)
        for x in range(0, image.width(), 80):
            painter.fillRect(x, 0, 40, image.height(), QColor("#e8e8e8"))
        painter.setPen(QColor("#eca531"))
        font = QFont()
        font.setPixelSize(120)
        painter.setFont(font)
        for row in range(0, image.height(), 500):
            painter.drawText(40, row + 300, f"Arrastra deprisa en horizontal · fila {row}")
        painter.end()
        return image

    def paintEvent(self, _event: QEvent) -> None:  # nombre de Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#161616"))
        painter.drawImage(self._offset, self._image)

    def mousePressEvent(self, event: QEvent) -> None:  # nombre de Qt
        self._last = event.position().toPoint()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QEvent) -> None:  # nombre de Qt
        if self._last is None:
            return
        position = event.position().toPoint()
        self._offset += position - self._last
        self._last = position
        self.update()

    def mouseReleaseEvent(self, _event: QEvent) -> None:  # nombre de Qt
        self._last = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)


# -----------------------------------------------------------------------------
# Datos de prueba y medidas
# -----------------------------------------------------------------------------


def read_gpx_points(path: Path) -> list[float]:
    """[lat, lon, lat, lon...] del recorrido de un GPX (o de su ruta, si no tiene track)."""
    track: list[float] = []
    route: list[float] = []
    for _event, element in iterparse(str(path)):
        name = element.tag.rsplit("}", 1)[-1]
        if name in ("trkpt", "rtept"):
            try:
                point = (round(float(element.get("lat")), 6), round(float(element.get("lon")), 6))
            except (TypeError, ValueError):
                continue
            (track if name == "trkpt" else route).extend(point)
            element.clear()
    return track or route


def synthetic_track(count: int) -> list[float]:
    """Un recorrido inventado por el Pirineo: pasos de unos 8 m con giros suaves."""
    generator = random.Random(7)
    latitude, longitude, heading = 42.650, -0.050, 0.6
    points: list[float] = []
    for _ in range(count):
        points.extend((round(latitude, 6), round(longitude, 6)))
        heading += generator.uniform(-0.25, 0.25)
        latitude += 0.00007 * math.cos(heading)
        longitude += 0.0001 * math.sin(heading)
    return points


def random_markers(count: int) -> list[list[float]]:
    """[[id, lat, lon], ...]: dos tercios en unos pocos «sitios» y el resto repartido."""
    generator = random.Random(11)
    spots = [(generator.uniform(42.3, 42.9), generator.uniform(-0.6, 0.8)) for _ in range(40)]
    markers: list[list[float]] = []
    for media_id in range(1, count + 1):
        if media_id % 3:
            latitude, longitude = generator.choice(spots)
            latitude += generator.gauss(0, 0.01)
            longitude += generator.gauss(0, 0.015)
        else:
            latitude, longitude = generator.uniform(42.3, 42.9), generator.uniform(-0.6, 0.8)
        markers.append([media_id, round(latitude, 6), round(longitude, 6)])
    return markers


def memory_report() -> str:
    """Memoria de este proceso y de los de QtWebEngine (solo Windows, con 'tasklist')."""
    if sys.platform != "win32":
        return "memoria: solo se mide en Windows"
    try:
        output = subprocess.run(  # comando fijo, sin shell
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False, timeout=20,
        ).stdout  # fmt: skip
    except (OSError, subprocess.SubprocessError) as error:
        return f"memoria: no se pudo medir ({error})"
    own = web = 0
    web_count = 0
    for line in output.splitlines():
        fields = [field.strip('"') for field in line.split('","')]
        if len(fields) < 5:
            continue
        kilobytes = int("".join(ch for ch in fields[4] if ch.isdigit()) or 0)
        if fields[1] == str(os.getpid()):
            own = kilobytes
        elif fields[0].lower().startswith("qtwebengineprocess"):
            web += kilobytes
            web_count += 1
    return (
        f"memoria: este proceso {own / 1024:.0f} MB + {web_count} proceso(s) de QtWebEngine "
        f"{web / 1024:.0f} MB = {(own + web) / 1024:.0f} MB"
    )


# -----------------------------------------------------------------------------
# Ventana
# -----------------------------------------------------------------------------


class Window(QWidget):
    """La ventana de la prueba (ver el docstring del archivo)."""

    def __init__(self, options: argparse.Namespace) -> None:
        super().__init__()
        self._options = options
        self._view: MapWebView | None = None
        self._overlay: DropOverlay | None = None
        self._handler = MapSchemeHandler(offline=options.offline, parent=self)
        self._profile = QWebEngineProfile.defaultProfile()
        self._profile.installUrlSchemeHandler(SCHEME, self._handler)
        self._pings: list[float] = []
        self._ping_started = 0.0
        self.ready_ms: float | None = None

        self.setWindowTitle("Prueba de concepto del mapa (docs/MAPA.md, fase 0)")
        self.resize(1500, 900)

        # Barra de botones
        self._photo_button = QPushButton("Foto")
        self._map_button = QPushButton("Mapa")
        self._layer_combo = QComboBox()
        for key, (text, *_rest) in LAYERS.items():
            self._layer_combo.addItem(text, key)
        buttons = [
            ("Track", self._show_track),
            (f"{options.markers} marcadores", self._show_markers),
            ("Marcador arrastrable", lambda: self._call("addDraggableMarker")),
            ("Ida y vuelta", self._start_pings),
            ("Medidas", self.report),
        ]
        bar = QHBoxLayout()
        bar.addWidget(self._photo_button)
        bar.addWidget(self._map_button)
        bar.addWidget(self._layer_combo)
        for text, action in buttons:
            button = QPushButton(text)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(action)
            bar.addWidget(button)
        self._status = QLabel("El mapa aún no se ha creado: arrastra la foto y después pulsa «Mapa».")
        bar.addWidget(self._status, 1)
        for widget in (self._photo_button, self._map_button, self._layer_combo):
            widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Lista de tarjetas
        self._list = CardList()
        model = CardModel(self._list)
        for media_id in range(1, 13):
            item = QStandardItem(f"Tarjeta {media_id}")
            item.setData(media_id, Qt.ItemDataRole.UserRole)
            item.setData(QPixmap.fromImage(_fake_thumbnail(media_id, 48)), Qt.ItemDataRole.DecorationRole)
            item.setEditable(False)
            model.appendRow(item)
        self._list.setModel(model)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setDragEnabled(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._list.setCurrentIndex(model.index(0, 0))
        self._list.drag_started.connect(self._on_drag_started)
        self._list.drag_finished.connect(self._on_drag_finished)

        # Páginas: la foto y el mapa (vacío hasta que se pide)
        self._stack = QStackedWidget()
        self._photo_page = PhotoPage(options.photo)
        self._map_holder = QWidget()
        holder_layout = QVBoxLayout(self._map_holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._photo_page)
        self._stack.addWidget(self._map_holder)

        splitter = QSplitter()
        splitter.addWidget(self._list)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 1280])

        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(splitter, 1)

        self._photo_button.clicked.connect(lambda: self._stack.setCurrentWidget(self._photo_page))
        self._map_button.clicked.connect(self.show_map)
        self._layer_combo.currentIndexChanged.connect(
            lambda _i: self._call("setLayer", self._layer_combo.currentData())
        )
        self._list.setFocus()

    # --- Mapa ---

    def show_map(self) -> None:
        """Muestra el mapa; la primera vez, lo crea (aquí arranca Chromium)."""
        if self._view is None:
            say("Creando la vista web...")
            self._view = MapWebView(self._profile, self._map_holder)
            self._map_holder.layout().addWidget(self._view)
            self._view.bridge.ready.connect(self._on_ready)
            self._view.bridge.hovered.connect(self._on_hovered)
            self._view.bridge.pong.connect(self._on_pong)
            if self._options.overlay:
                self._overlay = DropOverlay(self._view, self._map_holder)
        self._stack.setCurrentWidget(self._map_holder)

    def _call(self, function: str, *arguments: object) -> None:
        if self._view is None or self.ready_ms is None:
            self._status.setText("Antes hay que crear el mapa («Mapa») y esperar a que esté listo.")
            return
        self._view.call(function, *arguments)

    def _on_ready(self) -> None:
        self.ready_ms = (time.perf_counter() - self._view.created_at) * 1000
        say(f"Mapa listo en {self.ready_ms:.0f} ms desde que se creó la vista web.")
        self._status.setText("Mapa listo.")

    def _on_hovered(self, point_index: int) -> None:
        self._status.setText(
            f"Punto del track bajo el ratón: {point_index}" if point_index >= 0 else "Fuera del track."
        )

    def _show_track(self) -> None:
        points: list[float] = []
        for path in self._options.gpx:
            try:
                points = read_gpx_points(path)
            # No se puede leer, no es XML (ParseError es un SyntaxError) o XML peligroso
            except (OSError, ValueError, SyntaxError) as error:
                say(f"  No se pudo leer {path}: {error}")
                continue
            say(f"  Track de {path.name}: {len(points) // 2} puntos")
            break
        if not points:
            points = synthetic_track(self._options.points)
            say(f"  Track inventado: {len(points) // 2} puntos")
        self._call("setTrack", points)

    def _show_markers(self) -> None:
        self._call("setMarkers", random_markers(self._options.markers))

    # --- Ida y vuelta Python -> página -> Python ---

    def _start_pings(self) -> None:
        if self._view is None or self.ready_ms is None:
            self._call("ping", 0)  # solo para el aviso
            return
        self._pings = []
        self._send_ping()

    def _send_ping(self) -> None:
        self._ping_started = time.perf_counter()
        self._view.call("ping", float(len(self._pings)))

    def _on_pong(self, _token: float) -> None:
        self._pings.append((time.perf_counter() - self._ping_started) * 1000)
        if len(self._pings) < 30:
            self._send_ping()
            return
        say(
            f"  [ida y vuelta] 30 viajes: mediana {statistics.median(self._pings):.2f} ms, "
            f"máximo {max(self._pings):.2f} ms"
        )

    # --- Capa transparente (--overlay) ---

    def _on_drag_started(self) -> None:
        if self._overlay is not None and self._stack.currentWidget() is self._map_holder:
            self._overlay.setGeometry(self._view.geometry())
            self._overlay.show()
            self._overlay.raise_()

    def _on_drag_finished(self) -> None:
        if self._overlay is not None:
            self._overlay.hide()

    # --- Medidas ---

    def report(self) -> None:
        stats = self._handler.stats
        say("Medidas:")
        say(f"  {memory_report()}")
        say(
            f"  teselas: {stats['cache']} de la caché, {stats['red']} descargadas "
            f"({stats['bytes'] / 1024:.0f} kB), {stats['error']} con error; "
            f"miniaturas servidas: {stats['miniaturas']}"
        )
        if self._handler.tile_ms:
            say(f"  descarga de una tesela: mediana {statistics.median(self._handler.tile_ms):.0f} ms")
        say(f"  caché: {CACHE_DIR}")

    @property
    def js_errors(self) -> int:
        return self._view.map_page.js_errors if self._view is not None else 0

    @property
    def tile_stats(self) -> dict[str, int]:
        return self._handler.stats


def _run_selftest(app: QApplication, window: Window) -> None:
    """Sin intervención: crea el mapa, llama a todo y sale (código 1 si algo falla)."""
    state = {"timings": set()}

    def finish() -> None:
        window.report()
        stats = window.tile_stats
        problems = []
        if window.ready_ms is None:
            problems.append("la página no llegó a estar lista")
        if window.js_errors:
            problems.append(f"{window.js_errors} error(es) de JavaScript")
        if state["timings"] != {"set_track", "set_markers"}:
            problems.append(f"la página no respondió a todo: {sorted(state['timings'])}")
        if not window._options.offline and not stats["red"] + stats["cache"]:
            problems.append("no llegó ninguna tesela")
        if not stats["miniaturas"]:
            problems.append("no se pidió ninguna miniatura")
        if not state.get("drop"):
            problems.append("la página no devolvió la coordenada de un píxel")
        for problem in problems:
            say(f"FALLO: {problem}")
        if not problems:
            say("Autoprueba finalizada correctamente.")
        app.exit(1 if problems else 0)

    def on_ready() -> None:
        window._view.bridge.timing.connect(lambda name, _ms, _count: state["timings"].add(name))
        window._show_track()
        window._show_markers()
        window._call("addDraggableMarker")
        window._start_pings()
        QTimer.singleShot(3000, lambda: window._layer_combo.setCurrentIndex(1))
        QTimer.singleShot(
            5000,
            lambda: window._view.map_page.runJavaScript(
                "JSON.stringify(arca.dropAt(200, 200))",
                0,
                lambda r: state.update(drop=_coordinates_text(r))
                or say(f"  [soltar simulado] (200, 200) -> {state['drop'] or 'sin respuesta'}"),
            ),
        )
        QTimer.singleShot(8000, finish)

    window.show_map()
    window._view.bridge.ready.connect(on_ready)
    QTimer.singleShot(45000, finish)  # por si la página no llega a cargar


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba de concepto del mapa (fase 0)")
    parser.add_argument("gpx", nargs="*", type=Path, help="archivos GPX para el botón «Track»")
    parser.add_argument("--points", type=int, default=10_000)
    parser.add_argument("--markers", type=int, default=20_000)
    parser.add_argument("--photo", type=Path, default=None)
    parser.add_argument("--overlay", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # consolas que no conocen «» o ·

    # Las dos cosas que Qt exige ANTES de crear QApplication (irán a main.py y a TRAMPAS.md)
    register_scheme()
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    app.focusChanged.connect(
        lambda _old, new: say(f"  [foco] {type(new).__name__ if new is not None else 'nadie'}")
    )

    window = Window(options)
    window.show()
    say(f"PySide/Qt por qtpy · caché de teselas: {CACHE_DIR}")
    if options.selftest:
        _run_selftest(app, window)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
