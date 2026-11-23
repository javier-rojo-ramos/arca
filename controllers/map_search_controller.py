"""Caja de búsqueda del mapa: buscar un lugar y llevar el mapa allí (GEN 8.4).

Une la caja ('MapSearchBox', en la barra de filtros) con el mapa ('MapPage.map_view') y con
el servicio de búsqueda ('core/maps/geocoding_client.py'). Decidido por el autor el
23/11/2026 (docs/DECISIONES.md):
    - La caja solo se ve con la vista Mapa, en cualquier módulo que la tenga.
    - Intro (o la lupa) busca lo escrito y el mapa encuadra el PRIMER lugar que da el
      servicio, como Lightroom; los lugares que se ven en el mapa salen antes. Si no es el
      que se quería, se busca con más detalle («Santiago de Chile»).
    - Las 10 últimas búsquedas, con su lugar, en la lista de la caja (settings.json,
      'map_search_history'). Elegir una, o volver a escribirla, encuadra su lugar SIN
      preguntar a internet. «Borrar las búsquedas recientes» las quita todas.
    - En la barra de estado: «Buscando «…»…» mientras se espera; después, el nombre
      completo del lugar encontrado (así se ve si es el que se quería), «No se ha
      encontrado «…»», «Sin conexión: no se puede buscar» o «No se ha podido buscar: el
      servicio no responde».
    - Al buscar (y con Esc), el teclado vuelve al mapa: sus atajos siguen funcionando.

La petición va en un hilo aparte: bloquea hasta 10 s, más la espera de su turno (una por
segundo para toda la aplicación: 'geocoding_client.SHARED_GATE'). Si mientras tanto se
busca otra cosa, lo que llegue tarde no mueve el mapa ni da su aviso (su lugar sí queda en
la lista); si se deja el mapa, da su aviso pero no lo mueve. No se vuelve a pedir una
búsqueda igual a la que está en marcha, ni una que en esta sesión no encontró nada: las
condiciones de Nominatim piden no repetir la misma consulta.

El servicio: el de settings.json ('geocoding_url'; sin opción en la interfaz) o Nominatim.

Uso (en el controlador principal, solo la conexión):
    box = MapSearchBox(bar)
    bar.add_right_widget(box)
    self.map_search = MapSearchController(module_host, box=box, map_page=map_page,
                                          center_views=center_views, config=config,
                                          window=self, parent=self)

1.0.0 Primera versión (GEN 8.4b).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana ni usa la red):
    python -m controllers.map_search_controller
"""

__version__ = "1.0.0"
__all__ = [
    "FALLBACK_ZOOM",
    "NOT_FOUND_TEXT",
    "OFFLINE_TEXT",
    "SEARCHING_TEXT",
    "SERVICE_ERROR_TEXT",
    "MapSearchController",
    "Searcher",
]

# Librerías estándar
import threading
from collections.abc import Callable
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from config.app_constants import (
    SETTING_GEOCODING_URL,
    SETTING_MAP_SEARCH_HISTORY,
    STATUSBAR_DURATION,
    AppIcons,
)
from config.app_paths import APP_VERSION
from controllers.app_modules.center_views import CenterView
from core.maps.geocoding import (
    Bounds,
    GeocodingError,
    HistoryEntry,
    Place,
    history_from_settings,
    history_to_settings,
    normalize_query,
    recall_search,
    remember_search,
    service_url_from_settings,
)
from core.maps.geocoding_client import GeocodingClient, GeocodingNetworkError
from core.maps.tile_layers import user_agent
from ui_helpers.helpers.ui_status import message_bar
from ui_helpers.map.map_types import MapBounds
from ui_helpers.widgets.map_search_box import MapSearchBox

# Textos de la interfaz (los tres primeros, acordados con el autor el 23/11/2026)
NOT_FOUND_TEXT = "No se ha encontrado «{query}»"
OFFLINE_TEXT = "Sin conexión: no se puede buscar"
SERVICE_ERROR_TEXT = "No se ha podido buscar: el servicio no responde"
SEARCHING_TEXT = "Buscando «{query}»…"

# Un lugar sin rectángulo se centra con este zoom (el mismo tope que al encuadrar: los
# rectángulos diminutos de una dirección tampoco se acercan más; 'arca_map.js', FIT_MAX_ZOOM)
FALLBACK_ZOOM = 16

# Quien busca de verdad: (dirección del servicio, texto, lo que se ve) -> lugares. Bloquea;
# se llama desde un hilo aparte. El de verdad es '_search_online'; la autoprueba pone otro
Searcher = Callable[[str, str, Bounds | None], list[Place]]


class _Relay(QObject):
    """Lleva al hilo principal lo que responde la búsqueda del hilo aparte."""

    done = Signal(object)


class MapSearchController(QObject):
    """La caja de búsqueda del mapa (ver el docstring del archivo)."""

    def __init__(
        self,
        host: Any,
        *,
        box: MapSearchBox,
        map_page: Any,
        center_views: Any,
        config: Any,
        window: QWidget,
        search: Searcher | None = None,
        run_in_background: Callable[[Callable[[], None]], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Args:
            host: El 'ModuleHost' (la vista activa: 'active_view' y 'view_changed').
            box: La caja, ya puesta en la barra de filtros.
            map_page: La página del mapa ('MapPage': 'has_map', 'map_view').
            center_views: El 'CenterViewController' ('focus_view': el teclado, al mapa).
            config: Los ajustes ('get', 'set').
            window: La ventana principal (su barra de estado, para los avisos).
            search: Quién busca (de partida, Nominatim por internet).
            run_in_background: Cómo se lanza la búsqueda (de partida, en un hilo aparte).
            parent: Padre Qt.
        """
        super().__init__(parent)
        self._host = host
        self._box = box
        self._page = map_page
        self._center_views = center_views
        self._config = config
        self._window = window
        self._search = search if search is not None else _search_online
        self._run = run_in_background if run_in_background is not None else _start_thread
        self._relay = _Relay(self)
        self._relay.done.connect(self._on_done)
        # Cada búsqueda lleva su número: lo que llega de una que no es la última no cuenta
        self._generation = 0
        self._pending: str | None = None  # la que está en marcha (en minúsculas)
        self._not_found: set[str] = set()  # las que no encontraron nada en esta sesión
        self._history: tuple[HistoryEntry, ...] = history_from_settings(
            config.get(SETTING_MAP_SEARCH_HISTORY)
        )
        self._show_history()

        box.search_requested.connect(self.search)
        box.clear_history_requested.connect(self.clear_history)
        box.escape_pressed.connect(self._back_to_map)
        host.view_changed.connect(self._on_view_changed)
        self._on_view_changed()

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def search(self, text: str) -> None:
        """Busca un lugar y lleva allí el mapa (ver el docstring del archivo)."""
        query = normalize_query(text)
        if not query or not self._shown():
            return
        self._back_to_map()
        key = query.casefold()
        if key == self._pending:
            return  # ya se está buscando: llegará enseguida
        self._generation += 1
        place = recall_search(self._history, query)
        if place is not None:  # una búsqueda reciente: sin preguntar a internet
            self._remember(query, place)
            self._go_to(place)
            return
        if key in self._not_found:
            self._say(NOT_FOUND_TEXT.format(query=query), AppIcons.WARNING)
            return
        self._start(query, self._generation)

    def clear_history(self) -> None:
        """Quita todas las búsquedas recientes (también de settings.json)."""
        self._history = ()
        self._show_history()
        self._config.set(SETTING_MAP_SEARCH_HISTORY, [])

    def history(self) -> tuple[HistoryEntry, ...]:
        """Las búsquedas recientes, la última primero."""
        return self._history

    # -------------------------------------------------------------------------
    # La búsqueda
    # -------------------------------------------------------------------------

    def _start(self, query: str, generation: int) -> None:
        """Lanza la búsqueda en segundo plano; lo que responda llega a '_on_done'."""
        self._pending = query.casefold()
        service = service_url_from_settings(self._config.get(SETTING_GEOCODING_URL))
        viewbox = self._viewbox()
        self._say(SEARCHING_TEXT.format(query=query), AppIcons.INFO, duration=0)
        search, relay = self._search, self._relay

        def task() -> None:
            try:
                result: object = search(service, query, viewbox)
            # Cualquier fallo vuelve al hilo principal: si no, la búsqueda se quedaría en
            # marcha para siempre (y el aviso «Buscando...», fijo)
            except Exception as error:  # noqa: BLE001
                result = error
            try:
                relay.done.emit((generation, query, result))
            except RuntimeError:
                pass  # la ventana ya no existe

        self._run(task)

    def _on_done(self, payload: tuple[int, str, object]) -> None:
        """Lo que ha respondido una búsqueda (en el hilo principal)."""
        generation, query, result = payload
        if self._pending == query.casefold():
            self._pending = None
        latest = generation == self._generation  # si no, se ha buscado otra cosa después
        if isinstance(result, BaseException):
            if isinstance(result, GeocodingError):
                logger.warning(f"Mapa: no se ha podido buscar «{query}»: {result}")
            else:
                logger.opt(exception=result).error(f"Mapa: fallo al buscar «{query}»")
            if latest:
                offline = isinstance(result, GeocodingNetworkError)
                self._say(OFFLINE_TEXT if offline else SERVICE_ERROR_TEXT, AppIcons.WARNING)
            return
        places = list(result) if isinstance(result, list) else []
        if not places:
            self._not_found.add(query.casefold())
            if latest:
                self._say(NOT_FOUND_TEXT.format(query=query), AppIcons.WARNING)
            return
        place = places[0]
        logger.info(f"Mapa: «{query}» -> {place.label}")
        self._remember(query, place)
        if latest:
            if self._shown():
                self._go_to(place)
            else:
                self._say(place.label, AppIcons.CHECK_CIRCLE)  # el mapa ya no se ve

    def _go_to(self, place: Place) -> None:
        """Encuadra el lugar (su rectángulo o, si no lo tiene, su punto) y dice cuál es."""
        view = self._page.map_view()
        if place.bounds is not None:
            view.fit_bounds(MapBounds(*place.bounds))
        else:
            view.center_on(place.latitude, place.longitude, FALLBACK_ZOOM)
        self._say(place.label, AppIcons.CHECK_CIRCLE)

    def _viewbox(self) -> Bounds | None:
        """Lo que se ve en el mapa (sur, oeste, norte, este): sus lugares salen antes."""
        if not self._page.has_map():
            return None
        viewport = self._page.map_view().viewport()
        if viewport is None:
            return None
        box = viewport.bounds
        return (box.south, box.west, box.north, box.east)

    # -------------------------------------------------------------------------
    # Lo demás
    # -------------------------------------------------------------------------

    def _remember(self, query: str, place: Place) -> None:
        """La búsqueda, arriba de la lista (y en settings.json)."""
        self._history = remember_search(self._history, query, place)
        self._show_history()
        self._config.set(SETTING_MAP_SEARCH_HISTORY, history_to_settings(self._history))

    def _show_history(self) -> None:
        self._box.set_history([(entry.query, entry.place.label) for entry in self._history])

    def _shown(self) -> bool:
        return self._host.active_view == CenterView.MAP

    def _on_view_changed(self, _view: object = None) -> None:
        """La caja, solo con el mapa a la vista."""
        self._box.setVisible(self._shown())

    def _back_to_map(self) -> None:
        """El teclado, a la vista del centro (el mapa): ahí van sus atajos."""
        self._center_views.focus_view()

    def _say(self, text: str, icon: str, *, duration: int = STATUSBAR_DURATION) -> None:
        message_bar(self._window, text, icon, duration)


def _search_online(service_url: str, query: str, viewbox: Bounds | None) -> list[Place]:
    """La búsqueda de verdad, por internet (bloquea: desde el hilo aparte)."""
    client = GeocodingClient(user_agent(APP_VERSION), service_url=service_url)
    return client.search(query, viewbox=viewbox)


def _start_thread(task: Callable[[], None]) -> None:
    threading.Thread(target=task, name="map-search", daemon=True).start()


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen') y sin red: el módulo, el mapa y los
    # ajustes son de mentira (no se toca settings.json).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.map_search_controller
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication, QLabel, QMainWindow

    from core.maps.geocoding import DEFAULT_SERVICE_URL
    from core.maps.geocoding_client import GeocodingServiceError
    from ui_helpers.map.map_types import MapViewport

    app = QApplication([])
    window = QMainWindow()  # nunca se muestra: solo da su barra de estado

    class FakeHost(QObject):
        view_changed = Signal(object)

        def __init__(self) -> None:
            super().__init__()
            self.active_view = CenterView.GRID

        def show(self, view: CenterView) -> None:
            self.active_view = view
            self.view_changed.emit(view)

    class FakeMapView:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def fit_bounds(self, bounds: MapBounds) -> None:
            self.calls.append(("fit", bounds))

        def center_on(self, latitude: float, longitude: float, zoom: float | None) -> None:
            self.calls.append(("center", latitude, longitude, zoom))

        def viewport(self) -> MapViewport:
            return MapViewport(40.4, -3.7, 6.0, MapBounds(36.0, -9.5, 43.8, 3.3))

    class FakePage:
        def __init__(self) -> None:
            self.view = FakeMapView()

        def has_map(self) -> bool:
            return True

        def map_view(self) -> FakeMapView:
            return self.view

    class FakeCenterViews:
        def __init__(self) -> None:
            self.focused = 0

        def focus_view(self) -> None:
            self.focused += 1

    class FakeConfig:
        def __init__(self, data: dict) -> None:
            self.data = data

        def get(self, key: str, default: object = None) -> object:
            return self.data.get(key, default)

        def set(self, key: str, value: object) -> None:
            self.data[key] = value

    TORLA = Place("Torla-Ordesa", "Torla-Ordesa, Sobrarbe, Huesca, Aragón, España",
                  42.6277, -0.1121, (42.5954, -0.2076, 42.7984, 0.0214))
    PRADO = Place("Museo del Prado", "Museo del Prado, Madrid, España", 40.4138, -3.6920)
    answers: dict[str, object] = {
        "torla": [TORLA], "museo del prado": [PRADO], "nada": [],
        "sin red": GeocodingNetworkError("sin conexión"),
        "saturado": GeocodingServiceError(429, "Too Many Requests"),
        "fallo": ValueError("un error de programación"),
    }
    asked: list[tuple[str, str, object]] = []

    def fake_search(service: str, query: str, viewbox: object) -> list[Place]:
        asked.append((service, query, viewbox))
        answer = answers[query.casefold()]
        if isinstance(answer, Exception):
            raise answer
        return answer  # type: ignore[return-value]

    # Las búsquedas se lanzan cuando la prueba quiere (como si tardaran)
    queued: list[Callable[[], None]] = []

    def run_now(task: Callable[[], None]) -> None:
        task()

    def status() -> str:
        label = window.statusBar().findChild(QLabel, "CustomMessageText")
        return label.text() if label is not None else ""

    def make(config: FakeConfig, runner: Callable[[Callable[[], None]], None] = run_now):
        host, page, views = FakeHost(), FakePage(), FakeCenterViews()
        box = MapSearchBox(window)
        controller = MapSearchController(host, box=box, map_page=page, center_views=views,
                                         config=config, window=window, search=fake_search,
                                         run_in_background=runner)
        return controller, host, page, views, box

    # 1. La caja, solo con el mapa a la vista; fuera del mapa no se busca
    config = FakeConfig({})
    controller, host, page, views, box = make(config)
    assert box.isHidden()
    controller.search("Torla")
    assert asked == [] and page.view.calls == []
    host.show(CenterView.MAP)
    assert not box.isHidden()
    host.show(CenterView.SINGLE)
    assert box.isHidden()
    host.show(CenterView.MAP)

    # 2. Encontrado: encuadra su rectángulo, dice cuál es, lo recuerda y el teclado, al mapa
    controller.search("  Torla ")
    assert asked == [(DEFAULT_SERVICE_URL, "Torla", (36.0, -9.5, 43.8, 3.3))], asked
    assert page.view.calls == [("fit", MapBounds(42.5954, -0.2076, 42.7984, 0.0214))]
    assert status() == TORLA.label and views.focused == 1
    assert [entry.query for entry in controller.history()] == ["Torla"]
    assert config.data[SETTING_MAP_SEARCH_HISTORY][0]["name"] == "Torla-Ordesa"
    assert box.history() == ["Torla"]

    # 3. Otra vez (con otras mayúsculas): sin preguntar a internet
    controller.search("TORLA")
    assert len(asked) == 1 and page.view.calls[-1][0] == "fit" and len(page.view.calls) == 2
    assert [entry.query for entry in controller.history()] == ["TORLA"]

    # 4. Un lugar sin rectángulo: se centra con el zoom de reserva; arriba de la lista
    controller.search("Museo del Prado")
    assert page.view.calls[-1] == ("center", 40.4138, -3.6920, FALLBACK_ZOOM)
    assert box.history() == ["Museo del Prado", "TORLA"]

    # 5. No encontrado: el aviso; la segunda vez, sin volver a pedirlo; el mapa no se mueve
    calls_before = len(page.view.calls)
    controller.search("Nada")
    assert status() == NOT_FOUND_TEXT.format(query="Nada") == "No se ha encontrado «Nada»"
    controller.search("nada")
    assert sum(1 for item in asked if item[1].casefold() == "nada") == 1
    assert len(page.view.calls) == calls_before and box.history()[0] == "Museo del Prado"

    # 6. Errores: sin conexión, el servicio, y uno inesperado (se registra y no se cuelga)
    controller.search("sin red")
    assert status() == OFFLINE_TEXT
    controller.search("saturado")
    assert status() == SERVICE_ERROR_TEXT
    print("Un error de programación, a propósito (sale en el registro con su traza):")
    controller.search("fallo")
    assert status() == SERVICE_ERROR_TEXT and controller._pending is None
    # Un error no se apunta como «no encontrado»: se puede volver a intentar
    controller.search("sin red")
    assert sum(1 for item in asked if item[1] == "sin red") == 2

    # 7. Borrar las búsquedas recientes
    controller.clear_history()
    assert controller.history() == () and config.data[SETTING_MAP_SEARCH_HISTORY] == []
    assert box.history() == []

    # 8. Lo guardado se lee al empezar; el servicio, el de los ajustes
    config = FakeConfig({
        SETTING_MAP_SEARCH_HISTORY: history_to_settings([HistoryEntry("Torla", TORLA)]),
        SETTING_GEOCODING_URL: "http://localhost:8080/",
    })
    asked.clear()
    controller, host, page, views, box = make(config, runner=queued.append)
    host.show(CenterView.MAP)
    assert box.history() == ["Torla"]
    controller.search("Museo del Prado")
    assert status() == SEARCHING_TEXT.format(query="Museo del Prado")
    assert len(queued) == 1 and asked == []  # en marcha (aún no ha respondido)

    # 9. La misma, otra vez mientras está en marcha: no se vuelve a pedir
    controller.search("museo del prado")
    assert len(queued) == 1
    queued.pop()()
    assert asked[0][0] == "http://localhost:8080"
    assert page.view.calls == [("center", 40.4138, -3.6920, FALLBACK_ZOOM)]

    # 10. Se busca otra cosa antes de que llegue la primera: la que llega tarde no mueve el
    # mapa (pero queda en la lista); la última, sí
    answers["madrid"] = [Place("Madrid", "Madrid, España", 40.4, -3.7, (40.3, -3.8, 40.6, -3.5))]
    controller.clear_history()
    page.view.calls.clear()
    answers["valencia"] = [Place("Valencia", "Valencia, España", 39.47, -0.38)]
    controller.search("Madrid")
    controller.search("Valencia")
    first, second = queued.pop(0), queued.pop(0)
    first()
    assert page.view.calls == [] and box.history() == ["Madrid"]
    assert status() == SEARCHING_TEXT.format(query="Valencia")  # sigue esperando la última
    second()
    assert page.view.calls == [("center", 39.47, -0.38, FALLBACK_ZOOM)]
    assert box.history() == ["Valencia", "Madrid"] and status() == "Valencia, España"

    # 11. Se deja el mapa antes de que llegue: da su aviso, pero no lo mueve
    answers["sevilla"] = [Place("Sevilla", "Sevilla, España", 37.39, -5.99)]
    page.view.calls.clear()
    controller.search("Sevilla")
    host.show(CenterView.GRID)
    queued.pop()()
    assert page.view.calls == [] and status() == "Sevilla, España"
    assert box.history()[0] == "Sevilla"

    # 12. Esc en la caja: el teclado, al mapa
    host.show(CenterView.MAP)
    focused = views.focused
    box.escape_pressed.emit()
    assert views.focused == focused + 1

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
