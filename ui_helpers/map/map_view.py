"""MapView: el mapa de la aplicación. Lo ÚNICO del mapa que conocen los módulos.

Un solo componente para el Catálogo, Imagen y Tracks (docs/MAPA.md, §2). Recibe datos
sencillos ('map_types.py': marcadores, rectángulos...), avisa con señales y NUNCA cambia
datos ni consulta el catálogo: quien lo usa (el futuro 'MapController') decide qué hacer
con cada aviso. Todo va por 'media_items.id'.

Por dentro tiene un FONDO ('MapBackend'), que es quien pinta: hoy, 'WebMapBackend'
(QtWebEngine + Leaflet). 'MapView' guarda lo que se le pide (marcadores, selección, capa,
encuadre) y se lo pasa al fondo cuando está listo: el fondo tarda en arrancar (carga una
página) y puede reiniciarse, así que se puede llamar a 'MapView' en cualquier momento y
en cualquier orden.

Uso:
    view = MapView(parent)
    view.set_thumbnail_provider(funcion)       # id -> ruta de su miniatura, o None
    view.set_markers([MapMarker(id, lat, lon), ...])
    view.set_selected_ids([...])
    view.fit_content()
    view.selection_requested.connect(...)      # (ids, SelectionMode)

Lo que TODAVÍA NO tiene: tracks (paso 1.4 de docs/MAPA.md) y soltar tarjetas, mover
marcadores y menú contextual (paso 1.5).

1.0.0 Primera versión (docs/MAPA.md, paso 1.3): capas, marcadores, selección y encuadre.

Prueba rápida (desde la raíz del proyecto; sin ventana, con un fondo simulado):
    python -m ui_helpers.map.map_view
Con el mapa de verdad (abre una ventana y se queda abierta):
    python -m ui_helpers.map.map_view --ventana
"""

__version__ = "1.0.0"
__all__ = ["MapView"]

# Librerías estándar
from collections.abc import Callable, Sequence
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.maps.tile_layers import DEFAULT_LAYER_KEY, TILE_LAYERS, TileLayer
from ui_helpers.map.map_backend import MapBackend
from ui_helpers.map.map_types import MapBounds, MapMarker, MapViewport, bounds_of


class MapView(QWidget):
    """El mapa (ver el docstring del archivo).

    Signals:
        ready(): el mapa ya pinta (lo pedido antes se aplica justo antes de avisar).
        load_failed(str): el mapa no arranca; el texto es para el registro.
        viewport_changed(MapViewport): se ha movido o ha cambiado el zoom (en reposo).
        selection_requested(list, SelectionMode): clic en una foto o en un grupo (sus
            id), o en el mapa vacío (lista vacía). El mapa NO cambia su selección: la
            pone quien lo usa, con 'set_selected_ids'.
        marker_activated(int): doble clic en una foto.
        layer_changed(str): se ve otra capa (su clave).
    """

    ready = Signal()
    load_failed = Signal(str)
    viewport_changed = Signal(object)
    selection_requested = Signal(list, object)
    marker_activated = Signal(int)
    layer_changed = Signal(str)

    def __init__(
        self, parent: QWidget | None = None, *, backend: MapBackend | None = None
    ) -> None:
        """
        Args:
            parent: Widget padre.
            backend: Fondo que pinta. Por defecto, el de QtWebEngine (se importa aquí
                dentro: así el motor web solo se carga si de verdad se crea un mapa).
        """
        super().__init__(parent)
        if backend is None:
            from ui_helpers.map.web_backend import WebMapBackend

            backend = WebMapBackend(self)
        else:
            backend.setParent(self)
        self._backend = backend
        self._ready = False
        # Lo que se quiere ver (se repite al fondo cada vez que arranca)
        self._markers: dict[int, MapMarker] = {}
        self._selected: tuple[int, ...] = ()
        self._layers: tuple[TileLayer, ...] = TILE_LAYERS
        self._layer_key = DEFAULT_LAYER_KEY
        # Último encuadre pedido antes de estar listo: ("bounds", rectángulo, animar) o
        # ("center", latitud, longitud, zoom)
        self._pending_view: tuple | None = None
        self._last_viewport: MapViewport | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(backend)
        # El mapa no coge el teclado: los atajos siguen en las fotos
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        backend.ready.connect(self._on_backend_ready)
        backend.load_failed.connect(self._on_backend_failed)
        backend.viewport_changed.connect(self._on_viewport_changed)
        backend.selection_requested.connect(self.selection_requested)
        backend.marker_activated.connect(self.marker_activated)

    # -------------------------------------------------------------------------
    # Marcadores y selección
    # -------------------------------------------------------------------------

    def set_markers(self, markers: Sequence[MapMarker]) -> None:
        """Sustituye todos los marcadores. Lo seleccionado que ya no esté deja de estarlo."""
        self._markers = {marker.media_id: marker for marker in markers}
        self._selected = tuple(i for i in self._selected if i in self._markers)
        if self._ready:
            self._backend.set_markers(list(self._markers.values()))
            self._backend.set_selected_ids(self._selected)

    def update_markers(self, markers: Sequence[MapMarker]) -> None:
        """Añade unos marcadores o mueve los que ya estén (por su id), sin tocar el resto."""
        if not markers:
            return
        for marker in markers:
            self._markers[marker.media_id] = marker
        if self._ready:
            self._backend.update_markers(list(markers))

    def remove_markers(self, media_ids: Sequence[int]) -> None:
        """Quita unos marcadores (y los saca de la selección)."""
        removed = [media_id for media_id in media_ids if self._markers.pop(media_id, None)]
        if not removed:
            return
        gone = set(removed)
        self._selected = tuple(i for i in self._selected if i not in gone)
        if self._ready:
            self._backend.remove_markers(removed)

    def markers(self) -> tuple[MapMarker, ...]:
        """Los marcadores que hay."""
        return tuple(self._markers.values())

    def set_selected_ids(self, media_ids: Sequence[int]) -> None:
        """Resalta los marcadores seleccionados (los id sin marcador se ignoran)."""
        selected = tuple(dict.fromkeys(i for i in media_ids if i in self._markers))
        if selected == self._selected:
            return
        self._selected = selected
        if self._ready:
            self._backend.set_selected_ids(selected)

    def selected_ids(self) -> tuple[int, ...]:
        """Los id resaltados."""
        return self._selected

    def set_thumbnail_provider(self, provider: Callable[[int], Path | None] | None) -> None:
        """De dónde salen las miniaturas: una función rápida (se la llama en el hilo
        principal) que da la ruta de la imagen de un id, o None si no tiene. None = sin
        miniaturas (al cerrar el catálogo)."""
        self._backend.set_thumbnail_provider(provider)

    # -------------------------------------------------------------------------
    # Encuadre
    # -------------------------------------------------------------------------

    def fit_bounds(self, bounds: MapBounds, *, animate: bool = True) -> None:
        """Encuadra un rectángulo."""
        if self._ready:
            self._backend.fit_bounds(bounds, animate=animate)
        else:
            self._pending_view = ("bounds", bounds, animate)

    def fit_content(self, *, animate: bool = True) -> bool:
        """Encuadra todo lo que hay. False si no hay nada que encuadrar."""
        return self._fit(self._markers.values(), animate)

    def fit_selection(self, *, animate: bool = True) -> bool:
        """Encuadra lo seleccionado. False si no hay nada seleccionado."""
        return self._fit((self._markers[i] for i in self._selected), animate)

    def _fit(self, markers: object, animate: bool) -> bool:
        bounds = bounds_of((marker.latitude, marker.longitude) for marker in markers)
        if bounds is None:
            return False
        self.fit_bounds(bounds, animate=animate)
        return True

    def center_on(self, latitude: float, longitude: float, zoom: float | None = None) -> None:
        """Centra el mapa en un punto (sin 'zoom', no lo cambia)."""
        if self._ready:
            self._backend.set_view(latitude, longitude, zoom)
        else:
            self._pending_view = ("center", latitude, longitude, zoom)

    def viewport(self) -> MapViewport | None:
        """Lo que se ve (None si el mapa aún no ha dicho nada)."""
        return self._last_viewport

    # -------------------------------------------------------------------------
    # Capas
    # -------------------------------------------------------------------------

    def layers(self) -> tuple[TileLayer, ...]:
        """Las capas que se pueden elegir, en su orden."""
        return self._layers

    def set_layers(self, layers: Sequence[TileLayer]) -> None:
        """Cambia las capas que se pueden elegir. Si la que se ve ya no está, la primera."""
        if not layers:
            raise ValueError("El mapa necesita al menos una capa")
        self._layers = tuple(layers)
        if self._ready:
            self._backend.set_layers(self._layers)
        if self._layer_key not in {layer.key for layer in self._layers}:
            self.set_base_layer(self._layers[0].key)

    def base_layer(self) -> str:
        """Clave de la capa que se ve."""
        return self._layer_key

    def set_base_layer(self, key: str) -> bool:
        """Elige la capa que se ve. False (y no cambia nada) si esa clave no existe."""
        if key not in {layer.key for layer in self._layers}:
            logger.warning(f"Mapa: no existe la capa {key!r}.")
            return False
        if key == self._layer_key:
            return True
        self._layer_key = key
        if self._ready:
            self._backend.set_base_layer(key)
        self.layer_changed.emit(key)
        return True

    # -------------------------------------------------------------------------
    # Ciclo de vida
    # -------------------------------------------------------------------------

    def is_ready(self) -> bool:
        """True si el mapa ya pinta."""
        return self._ready

    def clear(self) -> None:
        """Quita marcadores y selección (al cerrar el catálogo). La capa y el encuadre siguen."""
        self._markers = {}
        self._selected = ()
        if self._ready:
            self._backend.clear()

    def save_state(self) -> dict:
        """La capa y el encuadre, para guardarlos en JSON."""
        state: dict = {"layer": self._layer_key}
        if self._last_viewport is not None:
            view = self._last_viewport
            state["view"] = [round(view.latitude, 6), round(view.longitude, 6), round(view.zoom, 2)]
        return state

    def restore_state(self, state: object) -> None:
        """Recupera lo guardado con 'save_state'. Lo que no se entienda, se ignora."""
        if not isinstance(state, dict):
            return
        layer = state.get("layer")
        if isinstance(layer, str) and layer in {item.key for item in self._layers}:
            self.set_base_layer(layer)
        view = state.get("view")
        if (
            isinstance(view, list)
            and len(view) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in view)
            and -90 <= view[0] <= 90
            and -180 <= view[1] <= 180
            and 0 <= view[2] <= 22
        ):
            self.center_on(view[0], view[1], view[2])

    # -------------------------------------------------------------------------
    # Avisos del fondo
    # -------------------------------------------------------------------------

    def _on_backend_ready(self) -> None:
        """El fondo ya pinta: se le pasa todo lo que se quiere ver."""
        self._ready = True
        self._backend.set_layers(self._layers)
        self._backend.set_base_layer(self._layer_key)
        if self._markers:
            self._backend.set_markers(list(self._markers.values()))
        if self._selected:
            self._backend.set_selected_ids(self._selected)
        pending, self._pending_view = self._pending_view, None
        if pending is not None:
            if pending[0] == "bounds":
                # Sin animación: es el encuadre de partida, no un movimiento
                self._backend.fit_bounds(pending[1], animate=False)
            else:
                self._backend.set_view(pending[1], pending[2], pending[3])
        self.ready.emit()

    def _on_backend_failed(self, reason: str) -> None:
        self._ready = False
        self.load_failed.emit(reason)

    def _on_viewport_changed(self, viewport: MapViewport) -> None:
        self._last_viewport = viewport
        self.viewport_changed.emit(viewport)


def _run_logic_selftest() -> None:
    """Autoprueba sin ventana: MapView con un fondo simulado que apunta lo que recibe."""
    from qtpy.QtWidgets import QApplication

    from core.maps.tile_layers import layer_for
    from ui_helpers.map.map_types import SelectionMode

    app = QApplication.instance() or QApplication([])

    class FakeBackend(MapBackend):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[tuple] = []

        def take(self) -> list[tuple]:
            calls, self.calls = self.calls, []
            return calls

        def set_markers(self, markers: Sequence[MapMarker]) -> None:
            self.calls.append(("markers", [m.media_id for m in markers]))

        def update_markers(self, markers: Sequence[MapMarker]) -> None:
            self.calls.append(("update", [m.media_id for m in markers]))

        def remove_markers(self, media_ids: Sequence[int]) -> None:
            self.calls.append(("remove", list(media_ids)))

        def set_selected_ids(self, media_ids: Sequence[int]) -> None:
            self.calls.append(("selected", list(media_ids)))

        def set_thumbnail_provider(self, provider: object) -> None:
            self.calls.append(("thumbs", provider is not None))

        def fit_bounds(self, bounds: MapBounds, *, animate: bool = True) -> None:
            self.calls.append(("fit", bounds, animate))

        def set_view(self, latitude: float, longitude: float, zoom: float | None = None) -> None:
            self.calls.append(("view", latitude, longitude, zoom))

        def set_layers(self, layers: Sequence[TileLayer]) -> None:
            self.calls.append(("layers", [layer.key for layer in layers]))

        def set_base_layer(self, key: str) -> None:
            self.calls.append(("layer", key))

        def clear(self) -> None:
            self.calls.append(("clear",))

    backend = FakeBackend()
    view = MapView(backend=backend)
    keys = [layer.key for layer in TILE_LAYERS]
    seen: list[tuple] = []
    view.layer_changed.connect(lambda key: seen.append(("layer_changed", key)))
    view.selection_requested.connect(lambda ids, mode: seen.append(("select", ids, mode)))
    view.marker_activated.connect(lambda media_id: seen.append(("activate", media_id)))
    view.ready.connect(lambda: seen.append(("ready",)))

    # 1. Antes de estar listo no se le pide nada al fondo (salvo de dónde salen las miniaturas)
    a, b, c = MapMarker(1, 42.0, -1.0), MapMarker(2, 43.0, 0.5), MapMarker(3, 41.0, 0.0)
    view.set_thumbnail_provider(lambda _media_id: None)
    view.set_markers([a, b, c])
    view.set_selected_ids([2, 99, 2])  # el 99 no tiene marcador; el 2, repetido
    assert view.selected_ids() == (2,)
    assert view.fit_content() is True
    assert view.set_base_layer("opentopo") is True and view.base_layer() == "opentopo"
    assert view.set_base_layer("no_existe") is False and view.base_layer() == "opentopo"
    assert backend.take() == [("thumbs", True)]
    assert seen == [("layer_changed", "opentopo")] and not view.is_ready()

    # 2. Al estar listo recibe todo, en orden: capas, capa, marcadores, selección y encuadre
    backend.ready.emit()
    assert view.is_ready()
    assert backend.take() == [
        ("layers", keys),
        ("layer", "opentopo"),
        ("markers", [1, 2, 3]),
        ("selected", [2]),
        ("fit", MapBounds(41.0, -1.0, 43.0, 0.5), False),  # el de partida, sin animación
    ]
    assert seen[-1] == ("ready",)

    # 3. Ya listo, cada cambio va al fondo en el acto; lo que no cambia nada, no
    view.set_selected_ids([2])
    assert backend.take() == []
    view.set_selected_ids([3, 1])
    view.update_markers([MapMarker(4, 40.0, -3.0)])
    view.update_markers([])
    view.remove_markers([1, 77])  # el 77 no existe; el 1 estaba seleccionado
    assert backend.take() == [("selected", [3, 1]), ("update", [4]), ("remove", [1])]
    assert view.selected_ids() == (3,) and [m.media_id for m in view.markers()] == [2, 3, 4]
    assert view.fit_selection() is True
    assert backend.take() == [("fit", MapBounds(41.0, 0.0, 41.0, 0.0), True)]
    view.center_on(40.0, -3.0)
    assert backend.take() == [("view", 40.0, -3.0, None)]

    # 4. Marcadores nuevos: lo seleccionado que ya no está deja de estarlo
    view.set_markers([a, b])
    assert backend.take() == [("markers", [1, 2]), ("selected", [])]
    assert view.selected_ids() == ()
    assert view.fit_selection() is False

    # 5. Los avisos del fondo se reenvían tal cual; el encuadre se recuerda
    backend.selection_requested.emit([1, 2], SelectionMode.TOGGLE)
    backend.marker_activated.emit(2)
    assert seen[-2:] == [("select", [1, 2], SelectionMode.TOGGLE), ("activate", 2)]
    assert view.selected_ids() == ()  # el mapa no se selecciona solo
    assert view.viewport() is None and view.save_state() == {"layer": "opentopo"}
    backend.viewport_changed.emit(MapViewport(42.1234567, -0.5, 11.0, MapBounds(41, -1, 43, 0)))
    assert view.save_state() == {"layer": "opentopo", "view": [42.123457, -0.5, 11.0]}

    # 6. Recuperar el estado: lo que no se entiende, se ignora
    for bad in (None, [], {"layer": 3}, {"layer": "no_existe"}, {"view": [1, 2]},
                {"view": [95, 0, 3]}, {"view": ["a", 0, 3]}, {"view": [1, 2, True]}):  # fmt: skip
        view.restore_state(bad)
    assert backend.take() == [] and view.base_layer() == "opentopo"
    view.restore_state({"layer": "ign_mtn", "view": [42.5, 0.1, 13]})
    assert backend.take() == [("layer", "ign_mtn"), ("view", 42.5, 0.1, 13)]

    # 7. Capas: si la que se ve desaparece de la lista, pasa a ser la primera
    view.set_layers([layer_for("osm"), layer_for("opentopo")])
    assert backend.take() == [("layers", ["osm", "opentopo"]), ("layer", "osm")]
    try:
        view.set_layers([])
    except ValueError:
        pass
    else:
        raise AssertionError("un mapa sin capas debe rechazarse")

    # 8. Vaciar (cerrar el catálogo): fuera marcadores y selección; la capa sigue
    view.set_selected_ids([1])
    backend.take()
    view.clear()
    assert backend.take() == [("clear",)]
    assert view.markers() == () and view.selected_ids() == () and view.base_layer() == "osm"

    # 9. Si el fondo falla y vuelve a arrancar, recibe otra vez lo que hay
    view.set_markers([a])
    backend.take()
    backend.load_failed.emit("prueba")
    assert not view.is_ready()
    view.set_markers([a, c])
    view.center_on(41.0, 0.0, 9)
    assert backend.take() == []
    backend.ready.emit()
    assert backend.take() == [
        ("layers", ["osm", "opentopo"]),
        ("layer", "osm"),
        ("markers", [1, 3]),
        ("view", 41.0, 0.0, 9),
    ]

    view.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")


def _run_window() -> None:
    """Ventana de prueba con el mapa de verdad (se queda abierta hasta que se cierra)."""
    import random
    import sys
    import tempfile

    from PIL import Image
    from qtpy.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton

    from ui_helpers.helpers.ui_theme import apply_theme
    from ui_helpers.map.map_scheme import register_map_scheme

    register_map_scheme()  # antes de QApplication (en la aplicación lo hace main.py)
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    apply_theme()

    # Miniaturas inventadas: 24 cuadrados de colores (colores sueltos: es una prueba)
    folder = Path(tempfile.mkdtemp(prefix="arca_map_view_"))
    generator = random.Random(3)
    for number in range(24):
        color = tuple(generator.randrange(60, 230) for _ in range(3))
        Image.new("RGB", (96, 96), color).save(folder / f"{number}.jpg", quality=80)

    def thumbnail(media_id: int) -> Path | None:
        # Una de cada diez, sin miniatura: se ve el recuadro vacío
        return None if media_id % 10 == 0 else folder / f"{media_id % 24}.jpg"

    def random_markers(count: int) -> list[MapMarker]:
        spots = [(generator.uniform(36.5, 43.5), generator.uniform(-8.5, 3.0)) for _ in range(30)]
        markers = []
        for media_id in range(1, count + 1):
            latitude, longitude = generator.choice(spots)
            markers.append(
                MapMarker(
                    media_id,
                    latitude + generator.gauss(0, 0.05),
                    longitude + generator.gauss(0, 0.07),
                    has_thumbnail=media_id % 10 != 0,
                )
            )
        return markers

    window = QWidget()
    window.setWindowTitle("MapView (prueba)")
    window.resize(1300, 850)
    view = MapView(window)
    view.set_thumbnail_provider(thumbnail)

    combo = QComboBox()
    for layer in view.layers():
        combo.addItem(layer.name, layer.key)
    combo.setCurrentIndex(combo.findData(view.base_layer()))
    combo.currentIndexChanged.connect(lambda _i: view.set_base_layer(combo.currentData()))
    status = QLabel("Cargando el mapa...")

    def add_markers() -> None:
        view.set_markers(random_markers(5000))
        view.fit_content()

    def select_some() -> None:
        ids = generator.sample([m.media_id for m in view.markers()], k=min(100, len(view.markers())))
        view.set_selected_ids(ids)
        view.fit_selection()

    def on_selection(media_ids: list[int], mode: object) -> None:
        # Lo que haría el controlador: aplicar la selección pedida y devolvérsela al mapa
        current = set(view.selected_ids())
        chosen = current ^ set(media_ids) if mode.value == "toggle" else set(media_ids)
        view.set_selected_ids(sorted(chosen))
        status.setText(f"Selección pedida ({mode.value}): {len(media_ids)} · seleccionadas: {len(chosen)}")
        print(f"selection_requested: {len(media_ids)} id, {mode.value}; primeros {media_ids[:8]}", flush=True)

    bar = QHBoxLayout()
    bar.addWidget(combo)
    for text, action in (
        ("5 000 marcadores", add_markers),
        ("Seleccionar 100", select_some),
        ("Encuadrar todo", view.fit_content),
        ("Quitar marcadores", view.clear),
    ):
        button = QPushButton(text)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(action)
        bar.addWidget(button)
    bar.addWidget(status, 1)
    layout = QVBoxLayout(window)
    layout.addLayout(bar)
    layout.addWidget(view, 1)

    view.ready.connect(lambda: status.setText("Mapa listo."))
    view.load_failed.connect(lambda reason: status.setText(f"El mapa no arranca: {reason}"))
    view.selection_requested.connect(on_selection)
    view.marker_activated.connect(lambda media_id: print(f"marker_activated: {media_id}", flush=True))
    view.layer_changed.connect(lambda key: print(f"layer_changed: {key}", flush=True))
    view.viewport_changed.connect(
        lambda v: print(f"viewport_changed: {v.latitude:.4f}, {v.longitude:.4f}, zoom {v.zoom}", flush=True)
    )
    window.show()
    app.exec()


if __name__ == "__main__":
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.map.map_view [--ventana]
    import sys

    if "--ventana" in sys.argv:
        _run_window()
    else:
        _run_logic_selftest()
