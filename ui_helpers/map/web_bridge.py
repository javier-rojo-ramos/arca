"""Puente entre la página del mapa y Python (QWebChannel).

'MapBridge' es el objeto que la página ve como 'bridge' (resources/map/arca_map.js): sus
ranuras ('on_...') son lo ÚNICO que la página puede decirle a la aplicación. Cada ranura
comprueba lo que llega, lo convierte a los tipos de 'map_types.py' y lo reenvía como una
señal de Qt, que recoge 'WebMapBackend'.

Las listas viajan como texto JSON: es lo que QWebChannel pasa sin sorpresas.

1.1.0 Tracks (paso 1.4): clic en un track y punto bajo el ratón.
1.0.0 Primera versión (docs/MAPA.md, paso 1.3): arranque, encuadre, selección y doble clic.
"""

__version__ = "1.1.0"
__all__ = ["MapBridge"]

# Librerías estándar
import json

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal, Slot

# Módulos del proyecto
from ui_helpers.map.map_types import MapBounds, MapViewport, SelectionMode


class MapBridge(QObject):
    """Lo que la página del mapa le dice a Python.

    Signals:
        loaded(): la página ha cargado y espera 'arca.init'.
        ready(): el mapa está creado y se puede pintar.
        viewport_changed(MapViewport): encuadre nuevo, ya en reposo.
        selection_requested(list, SelectionMode): id pulsados (vacío = clic en el mapa).
        marker_activated(int): doble clic en una foto.
        track_clicked(int): clic en la línea de un track.
        track_hovered(int, int): (track, índice del punto) bajo el ratón en el track
            activo; índice -1 al salir de él.
    """

    loaded = Signal()
    ready = Signal()
    viewport_changed = Signal(object)
    selection_requested = Signal(list, object)
    marker_activated = Signal(int)
    track_clicked = Signal(int)
    track_hovered = Signal(int, int)

    @Slot()
    def on_loaded(self) -> None:
        self.loaded.emit()

    @Slot()
    def on_ready(self) -> None:
        self.ready.emit()

    @Slot(float, float, float, float, float, float, float)
    def on_viewport(
        self,
        latitude: float,
        longitude: float,
        zoom: float,
        south: float,
        west: float,
        north: float,
        east: float,
    ) -> None:
        try:
            viewport = MapViewport(latitude, longitude, zoom, MapBounds(south, west, north, east))
        except ValueError:
            return  # un encuadre imposible (p. ej. con la página a medio redimensionar)
        self.viewport_changed.emit(viewport)

    @Slot(str, bool)
    def on_select(self, ids_json: str, toggle: bool) -> None:
        try:
            media_ids = [int(media_id) for media_id in json.loads(ids_json)]
        except (TypeError, ValueError):
            logger.warning("El mapa ha enviado una selección que no se entiende.")
            return
        mode = SelectionMode.TOGGLE if toggle else SelectionMode.REPLACE
        self.selection_requested.emit(media_ids, mode)

    @Slot(int)
    def on_activate(self, media_id: int) -> None:
        self.marker_activated.emit(media_id)

    @Slot(int)
    def on_track_click(self, track_id: int) -> None:
        self.track_clicked.emit(track_id)

    @Slot(int, int)
    def on_track_hover(self, track_id: int, point_index: int) -> None:
        self.track_hovered.emit(track_id, point_index)
