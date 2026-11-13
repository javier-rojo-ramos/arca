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

Lo que TODAVÍA NO hace (lanza 'NotImplementedError', como la clase base): tracks
(paso 1.4), soltar tarjetas, mover marcadores, vista previa y menú contextual (paso 1.5).

1.0.0 Primera versión (docs/MAPA.md, paso 1.3): capas, marcadores agrupados con
      miniatura, selección, encuadre.
"""

__version__ = "1.0.0"
__all__ = ["DEFAULT_VIEW", "WebMapBackend", "css_color", "marker_payload"]

# Librerías estándar
import json
from collections.abc import Callable, Sequence
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, Qt, QTimer, QUrl
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
from ui_helpers.map.map_types import MapBounds, MapMarker, MapMode, MapViewport
from ui_helpers.map.web_bridge import MapBridge

# Encuadre con el que empieza el mapa mientras nadie pida otro: la península ibérica
DEFAULT_VIEW: tuple[float, float, int] = (40.2, -3.7, 6)

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
    }


def marker_payload(markers: Sequence[MapMarker]) -> list[list]:
    """Los marcadores como los espera la página: [id, lat, lon, tipo, miniatura (1/0)]."""
    return [
        [m.media_id, m.latitude, m.longitude, m.media_type, 1 if m.has_thumbnail else 0]
        for m in markers
    ]


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
    """Vista web que no coge el teclado, ni ella ni los widgets que crea por dentro."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seen: set[int] = set()
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

    def childEvent(self, event: QEvent) -> None:  # nombre de Qt
        super().childEvent(event)
        if event.type() == QEvent.Type.ChildAdded:
            # El hijo aún no está construido del todo: se mira al volver al bucle de eventos
            QTimer.singleShot(0, self.watch_children)


class WebMapBackend(MapBackend):
    """El mapa con QtWebEngine + Leaflet (ver el docstring del archivo)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ready = False
        self._viewport: MapViewport | None = None
        self._handler = shared_handler()

        self._view = _WebView(self)
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

    def set_thumbnail_provider(self, provider: Callable[[int], Path | None] | None) -> None:
        self._handler.set_thumbnail_provider(provider)

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

    def clear(self) -> None:
        self._call("clear")

    # Para que nadie piense que falta por descuido: el resto del contrato (tracks, soltar,
    # mover, vista previa) llega con los pasos 1.4 y 1.5 y, hasta entonces, vale la
    # versión de la clase base, que lanza 'NotImplementedError'.
