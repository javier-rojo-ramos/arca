"""Puente entre la página del mapa y Python (QWebChannel).

'MapBridge' es el objeto que la página ve como 'bridge' (resources/map/arca_map.js): sus
ranuras ('on_...') son lo ÚNICO que la página puede decirle a la aplicación. Cada ranura
comprueba lo que llega, lo convierte a los tipos de 'map_types.py' y lo reenvía como una
señal de Qt, que recoge 'WebMapBackend'.

Las listas viajan como texto JSON: es lo que QWebChannel pasa sin sorpresas.

1.2.0 Paso 1.5: fotos arrastradas a otro sitio y botón derecho ('MapHit').
1.1.0 Tracks (paso 1.4): clic en un track y punto bajo el ratón.
1.0.0 Primera versión (docs/MAPA.md, paso 1.3): arranque, encuadre, selección y doble clic.
"""

__version__ = "1.2.0"
__all__ = ["MapBridge"]

# Librerías estándar
import json

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal, Slot

# Módulos del proyecto
from ui_helpers.map.map_types import (
    HitKind,
    MapBounds,
    MapHit,
    MapViewport,
    SelectionMode,
    is_valid_position,
)


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
        markers_moved(list, float, float): fotos (sus id) arrastradas a (latitud, longitud).
        context_menu_requested(MapHit, int, int): botón derecho; qué hay debajo y el
            píxel de la página.
    """

    loaded = Signal()
    ready = Signal()
    viewport_changed = Signal(object)
    selection_requested = Signal(list, object)
    marker_activated = Signal(int)
    track_clicked = Signal(int)
    track_hovered = Signal(int, int)
    markers_moved = Signal(list, float, float)
    context_menu_requested = Signal(object, int, int)

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

    @Slot(str, float, float)
    def on_markers_moved(self, ids_json: str, latitude: float, longitude: float) -> None:
        try:
            media_ids = [int(media_id) for media_id in json.loads(ids_json)]
        except (TypeError, ValueError):
            logger.warning("El mapa ha enviado un movimiento que no se entiende.")
            return
        if media_ids and is_valid_position(latitude, longitude):
            self.markers_moved.emit(media_ids, latitude, longitude)

    @Slot(str, float, float)
    def on_context_menu(self, hit_json: str, x: float, y: float) -> None:
        try:
            data = json.loads(hit_json)
            track = data.get("track")
            index = data.get("index")
            hit = MapHit(
                HitKind(data["kind"]),
                float(data["lat"]),
                float(data["lon"]),
                media_ids=tuple(int(media_id) for media_id in data.get("ids", ())),
                track_id=None if track is None else int(track),
                point_index=None if index is None else int(index),
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.warning("El mapa ha enviado un clic derecho que no se entiende.")
            return
        self.context_menu_requested.emit(hit, round(x), round(y))
