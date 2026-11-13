"""Fondo del mapa con QtWebEngine + Leaflet: el que pinta de verdad.

Cumple el contrato de 'map_backend.MapBackend' con una página local (resources/map/)
dentro de un 'QWebEngineView'. Python llama a las funciones de la página ('arca.xxx',
siempre con los argumentos en JSON) y la página avisa por 'MapBridge' (QWebChannel).
Decidido tras la prueba de concepto del 13/11/2026 (docs/MAPA.md, §1 y §10).

Arranque: se carga 'arca-map://app/index.html' -> la página avisa ('loaded') -> se le
pasan los colores del tema, los textos y el encuadre inicial ('arca.init') -> crea el
mapa y avisa ('ready'). Hasta 'ready' no se le puede pedir nada: de guardar lo que se
pida antes se encarga 'MapView'.

Cosas que no son evidentes (comprobadas en la prueba de concepto):
    - La vista web y sus widgets internos van SIN foco ('NoFocus'): el teclado sigue en
      las fotos, como con las barras (docs/DECISIONES.md, 12/11/2026). Los widgets
      internos aparecen después de crear la vista: se vigilan los hijos que se añaden.
    - Los colores de la página salen del tema: se le pasan como variables CSS. Los
      translúcidos de Qt ('#aarrggbb') se convierten al orden de CSS ('#rrggbbaa').
    - La página solo puede navegar dentro de su esquema: nunca abre una web.

Soltar tarjetas (comprobado en la fase 0): los eventos de arrastre NO llegan a la vista
web ni a la página, sino a un widget interno de la vista. Se recogen con un filtro de
eventos en sus hijos ('_WebView'); si el arrastre trae tarjetas de la cuadrícula
('application/x-arca-media-ids') y está permitido, se acepta sin pasarlo a Chromium, se
pinta en la página dónde caería y, al soltar, la página traduce el píxel a coordenadas.

1.2.1 La revisión de los widgets internos ya no falla si la vista se destruye antes
      (al cerrar la aplicación).
1.2.0 Paso 1.5: soltar tarjetas, arrastrar las fotos sueltas, vista previa y botón
      derecho. Con esto cumple todo el contrato de 'MapBackend'.
1.1.0 Tracks (paso 1.4): líneas con borde claro, track activo, punto señalado y avisos
      de clic y de punto bajo el ratón; colores de los tracks y del texto emergente.
1.0.0 Primera versión (docs/MAPA.md, paso 1.3): capas, marcadores agrupados con
      miniatura, selección, encuadre.
"""

__version__ = "1.2.1"
__all__ = ["DEFAULT_VIEW", "WebMapBackend", "css_color", "marker_payload", "track_payload"]

# Librerías estándar
import json
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QObject, QPoint, Qt, QTimer, QUrl
from qtpy.QtGui import QColor
from qtpy.QtWebChannel import QWebChannel
from qtpy.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.maps.tile_layers import TileLayer
from ui_helpers.helpers.ui_theme import CARD_COLORS, COLORS
from ui_helpers.map.map_backend import MapBackend
from ui_helpers.map.map_scheme import SCHEME, START_URL, shared_handler
from ui_helpers.map.map_types import (
    MapBounds,
    MapHit,
    MapMarker,
    MapMode,
    MapTrack,
    MapViewport,
    is_valid_position,
)
from ui_helpers.map.web_bridge import MapBridge
from ui_helpers.models.media_mime import MediaDrag, decode_media_ids

# Encuadre con el que empieza el mapa mientras nadie pida otro: la península ibérica
DEFAULT_VIEW: tuple[float, float, int] = (40.2, -3.7, 6)

# Eventos de un arrastre
_DRAG_EVENTS = (
    QEvent.Type.DragEnter,
    QEvent.Type.DragMove,
    QEvent.Type.DragLeave,
    QEvent.Type.Drop,
)

# Textos de los botones de zoom (al pasar el ratón)
_TEXTS = {"zoom_in": "Acercar", "zoom_out": "Alejar"}


def css_color(color: str) -> str:
    """Un color del tema en el formato de CSS: Qt escribe los translúcidos '#aarrggbb'
    y CSS los quiere '#rrggbbaa'. Los opacos ('#rrggbb') no cambian."""
    if len(color) == 9 and color.startswith("#"):
        return f"#{color[3:]}{color[1:3]}"
    return color


def _theme_colors() -> dict[str, str]:
    """Variables CSS de la página ('--arca-<nombre>'), todas del tema."""
    return {
        "bg": css_color(CARD_COLORS.grid_bg),  # fondo sin tesela: el de la cuadrícula
        "panel": css_color(COLORS.bg_panel),
        "hover": css_color(COLORS.bg_hover),
        "line": css_color(COLORS.line),
        "text": css_color(COLORS.text),
        "text-dim": css_color(COLORS.text_dim),
        "text-disabled": css_color(COLORS.text_disabled),
        "accent": css_color(COLORS.accent),
        "text-on-accent": css_color(COLORS.text_on_accent),
        "shadow": css_color(COLORS.shadow),
        "tooltip": css_color(COLORS.bg_tooltip),
        "track": css_color(COLORS.map_track),
        "track-active": css_color(COLORS.map_track_active),
        "track-halo": css_color(COLORS.map_track_halo),
    }


def marker_payload(markers: Sequence[MapMarker]) -> list[list]:
    """Los marcadores como los espera la página: [id, lat, lon, tipo, miniatura (1/0)]."""
    return [
        [m.media_id, m.latitude, m.longitude, m.media_type, 1 if m.has_thumbnail else 0]
        for m in markers
    ]


def track_payload(track: MapTrack) -> dict:
    """Un track como lo espera la página: cada segmento, una lista plana
    [lat, lon, lat, lon...] con 6 decimales (unos 10 cm: de sobra, y la mitad de texto)."""
    return {
        "id": track.track_id,
        "name": track.name,
        "detailed": track.detailed,
        "segments": [
            [round(value, 6) for point in segment for value in point]
            for segment in track.segments
        ],
    }


class _MapPage(QWebEnginePage):
    """Página del mapa: sus mensajes van al registro y no sale de su esquema."""

    def javaScriptConsoleMessage(  # nombre de Qt
        self, level: object, message: str, line: int, source: str
    ) -> None:
        text = f"Mapa (página): {message} ({Path(source).name}:{line})"
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logger.error(text)
        else:
            logger.debug(text)

    def acceptNavigationRequest(  # nombre de Qt
        self, url: QUrl, _navigation_type: object, _is_main_frame: bool
    ) -> bool:
        return url.scheme() == SCHEME


class _WebView(QWebEngineView):
    """Vista web que no coge el teclado, ni ella ni los widgets que crea por dentro, y
    que enseña a 'drag_handler' los arrastres que llegan a esos widgets.

    'drag_handler(evento, desplazamiento)' devuelve True si se queda el evento; el
    desplazamiento es la esquina del widget que lo recibió, en coordenadas de la vista.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seen: set[int] = set()
        self.drag_handler: Callable[[QEvent, QPoint], bool] | None = None
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def watch_children(self, *_args: object) -> None:
        """Quita el foco a los widgets internos que aún no se hayan visto."""
        proxy = self.focusProxy()
        for child in [*self.findChildren(QWidget), *([proxy] if proxy is not None else [])]:
            if id(child) in self._seen:
                continue
            self._seen.add(id(child))
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            child.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # nombre de Qt
        if (
            event.type() in _DRAG_EVENTS
            and self.drag_handler is not None
            and isinstance(watched, QWidget)
            and self.drag_handler(event, watched.mapTo(self, QPoint(0, 0)))
        ):
            return True
        return super().eventFilter(watched, event)

    # Por si en otra versión de Qt o en otro sistema los arrastres llegan a la vista
    def dragEnterEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not (self.drag_handler and self.drag_handler(event, QPoint(0, 0))):
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not (self.drag_handler and self.drag_handler(event, QPoint(0, 0))):
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not (self.drag_handler and self.drag_handler(event, QPoint(0, 0))):
            super().dragLeaveEvent(event)

    def dropEvent(self, event: QEvent) -> None:  # nombre de Qt
        if not (self.drag_handler and self.drag_handler(event, QPoint(0, 0))):
            super().dropEvent(event)

    def childEvent(self, event: QEvent) -> None:  # nombre de Qt
        super().childEvent(event)
        if event.type() == QEvent.Type.ChildAdded:
            # El hijo aún no está construido del todo: se mira al volver al bucle de eventos.
            # Con 'self' como contexto, si la vista se destruye antes, no se llama
            QTimer.singleShot(0, self, self.watch_children)


class WebMapBackend(MapBackend):
    """El mapa con QtWebEngine + Leaflet (ver el docstring del archivo)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ready = False
        self._viewport: MapViewport | None = None
        self._drop_enabled = False
        self._dragging = False  # hay tarjetas arrastrándose por encima
        self._handler = shared_handler()

        self._view = _WebView(self)
        self._view.drag_handler = self._handle_drag
        self._page = _MapPage(QWebEngineProfile.defaultProfile(), self._view)
        # Fondo del tema mientras la página carga (sin esto, un destello blanco)
        self._page.setBackgroundColor(QColor(CARD_COLORS.grid_bg))
        self._bridge = MapBridge(self)
        channel = QWebChannel(self._page)
        channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(channel)
        self._view.setPage(self._page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._bridge.loaded.connect(self._on_page_loaded)
        self._bridge.ready.connect(self._on_map_ready)
        self._bridge.viewport_changed.connect(self._on_viewport)
        self._bridge.selection_requested.connect(self.selection_requested)
        self._bridge.marker_activated.connect(self.marker_activated)
        self._bridge.track_clicked.connect(self.track_clicked)
        self._bridge.track_hovered.connect(self.track_hovered)
        self._bridge.markers_moved.connect(self.markers_moved)
        self._bridge.context_menu_requested.connect(self._on_context_menu)
        self._page.loadFinished.connect(self._on_load_finished)
        self._page.renderProcessTerminated.connect(self._on_render_terminated)

        self._view.load(QUrl(START_URL))
        self._view.watch_children()

    # -------------------------------------------------------------------------
    # Arranque y fallos
    # -------------------------------------------------------------------------

    def _call(self, function: str, *arguments: object) -> None:
        """Llama a una función de la página. Los argumentos viajan SIEMPRE como JSON:
        nunca se compone JavaScript con textos que vengan de fuera."""
        code = f"arca.{function}({', '.join(json.dumps(argument) for argument in arguments)})"
        self._page.runJavaScript(code)

    def _on_page_loaded(self) -> None:
        self._call(
            "init", {"colors": _theme_colors(), "texts": _TEXTS, "view": list(DEFAULT_VIEW)}
        )

    def _on_map_ready(self) -> None:
        self._ready = True
        self._view.watch_children()
        self.ready.emit()

    def _on_load_finished(self, ok: bool) -> None:
        self._view.watch_children()
        if not ok:
            self._fail("la página del mapa no se ha podido cargar")

    def _on_render_terminated(self, _status: object, exit_code: int) -> None:
        self._fail(f"el proceso que pinta el mapa ha terminado (código {exit_code})")

    def _fail(self, reason: str) -> None:
        self._ready = False
        self._viewport = None
        logger.error(f"Mapa: {reason}.")
        self.load_failed.emit(reason)

    def _on_viewport(self, viewport: MapViewport) -> None:
        self._viewport = viewport
        self.viewport_changed.emit(viewport)

    def _on_context_menu(self, hit: MapHit, x: int, y: int) -> None:
        """Botón derecho en la página: el punto pasa a coordenadas de pantalla."""
        self.context_menu_requested.emit(hit, self._view.mapToGlobal(QPoint(x, y)))

    # -------------------------------------------------------------------------
    # Arrastre de tarjetas de la cuadrícula
    # -------------------------------------------------------------------------

    def _handle_drag(self, event: QEvent, offset: QPoint) -> bool:
        """Atiende un evento de arrastre si trae tarjetas y se pueden soltar. True = atendido
        (no pasa a Chromium); False = no es cosa del mapa."""
        kind = event.type()
        if kind == QEvent.Type.DragLeave:
            if not self._dragging:
                return False
            self._dragging = False
            self._call("setDropCursor", None, None)
            return True
        drag = decode_media_ids(event.mimeData())
        if drag is None:
            return False  # no son tarjetas: que lo decida la vista web
        if not (self._drop_enabled and self._ready):
            # Son tarjetas, pero aquí no se pueden soltar: se rechazan (cursor de
            # prohibido). Si pasaran a Chromium, las aceptaría sin hacer nada con ellas
            event.ignore()
            return True
        position = event.position()
        x, y = position.x() + offset.x(), position.y() + offset.y()
        event.acceptProposedAction()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            self._dragging = True
            self._call("setDropCursor", x, y)
            return True
        # Soltada: la página dice a qué coordenadas corresponde ese píxel. La respuesta
        # vuelve como texto JSON (una lista de JavaScript no llega bien a Python)
        self._dragging = False
        self._page.runJavaScript(
            f"JSON.stringify(arca.dropPoint({json.dumps(x)}, {json.dumps(y)}))",
            0,
            partial(self._on_drop_point, drag),
        )
        return True

    def _on_drop_point(self, drag: MediaDrag, result: object) -> None:
        try:
            latitude, longitude = (float(value) for value in json.loads(result))
        except (TypeError, ValueError):
            logger.warning("Mapa: no se ha podido saber dónde se han soltado las tarjetas.")
            return
        if is_valid_position(latitude, longitude):
            self.media_dropped.emit(drag, latitude, longitude)

    # -------------------------------------------------------------------------
    # Contrato de MapBackend
    # -------------------------------------------------------------------------

    def set_markers(self, markers: Sequence[MapMarker]) -> None:
        self._call("setMarkers", marker_payload(markers))

    def update_markers(self, markers: Sequence[MapMarker]) -> None:
        self._call("updateMarkers", marker_payload(markers))

    def remove_markers(self, media_ids: Sequence[int]) -> None:
        self._call("removeMarkers", [int(media_id) for media_id in media_ids])

    def set_selected_ids(self, media_ids: Sequence[int]) -> None:
        self._call("setSelected", [int(media_id) for media_id in media_ids])

    def set_preview_markers(self, markers: Sequence[MapMarker]) -> None:
        self._call("setPreviewMarkers", [[m.media_id, m.latitude, m.longitude] for m in markers])

    def set_thumbnail_provider(self, provider: Callable[[int], Path | None] | None) -> None:
        self._handler.set_thumbnail_provider(provider)

    def set_tracks(self, tracks: Sequence[MapTrack]) -> None:
        self._call("setTracks", [track_payload(track) for track in tracks])

    def set_track_geometry(self, track: MapTrack) -> None:
        self._call("setTrackGeometry", track_payload(track))

    def set_active_track(self, track_id: int | None) -> None:
        self._call("setActiveTrack", track_id)

    def set_track_cursor(self, track_id: int, point_index: int | None) -> None:
        self._call("setTrackCursor", track_id, point_index)

    def fit_bounds(self, bounds: MapBounds, *, animate: bool = True) -> None:
        self._call("fitBounds", bounds.south, bounds.west, bounds.north, bounds.east, animate)

    def set_view(self, latitude: float, longitude: float, zoom: float | None = None) -> None:
        self._call("setView", latitude, longitude, zoom)

    def viewport(self) -> MapViewport | None:
        return self._viewport

    def set_layers(self, layers: Sequence[TileLayer]) -> None:
        self._handler.set_layers(layers)
        self._call(
            "setLayers",
            [
                {
                    "key": layer.key,
                    "attribution": layer.attribution,
                    "min_zoom": layer.min_zoom,
                    "max_zoom": layer.max_zoom,
                }
                for layer in layers
            ],
        )

    def set_base_layer(self, key: str) -> None:
        self._call("setBaseLayer", key)

    def set_mode(self, mode: MapMode) -> None:
        if mode is not MapMode.BROWSE:
            raise NotImplementedError(f"Modo del mapa sin implementar: {mode}")

    def set_drop_enabled(self, enabled: bool) -> None:
        self._drop_enabled = enabled
        self._call("setDropEnabled", enabled)

    def clear(self) -> None:
        self._call("clear")
