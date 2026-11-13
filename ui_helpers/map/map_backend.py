"""Contrato del FONDO del mapa: lo que 'MapView' le pide a la tecnología que lo pinta.

'MapView' (la fachada que conocen los módulos y los controladores) no pinta nada: tiene
dentro un 'MapBackend', que es el widget que dibuja de verdad. Hoy habrá uno solo,
'WebMapBackend' (QtWebEngine + Leaflet; docs/MAPA.md, paso 1.3). Si un día esa
tecnología deja de servir (el plan alternativo es Qt Location), se escribe otro fondo
con este mismo contrato y nada más cambia.

Reglas del contrato:
    - El fondo SOLO pinta y avisa: nunca cambia datos ni consulta el catálogo.
    - Todo va por 'media_items.id' y con los tipos de 'map_types.py'.
    - Puede tardar en estar listo (una página que carga): avisa con 'ready'. Las llamadas
      anteriores las guarda 'MapView' y las repite al llegar 'ready': un fondo no tiene
      que guardar nada que le llegue antes.
    - No coge el teclado (como las barras: docs/DECISIONES.md, 12/11/2026).

Este módulo solo declara: no tiene lógica que probar (sin autoprueba).

1.1.0 'set_thumbnail_provider': de dónde salen las miniaturas de los marcadores.
1.0.0 Primera versión (docs/MAPA.md, paso 1.2): ver, seleccionar, soltar y mover. Lo de
      la edición de tracks se añadirá con la fase 7.
"""

__version__ = "1.1.0"
__all__ = ["MapBackend"]

# Librerías estándar
from collections.abc import Callable, Sequence
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from core.maps.tile_layers import TileLayer
from ui_helpers.map.map_types import MapBounds, MapMarker, MapMode, MapTrack, MapViewport


class MapBackend(QWidget):
    """Base de los fondos del mapa (ver el docstring del archivo).

    Una subclase implementa TODOS los métodos (aquí lanzan 'NotImplementedError') y emite
    estas señales, que 'MapView' reenvía con el mismo nombre.

    Signals:
        ready(): ya se puede pintar.
        load_failed(str): la tecnología no arranca; el texto es para el registro.
        viewport_changed(MapViewport): se ha movido o ha cambiado el zoom (ya en reposo).
        selection_requested(list, SelectionMode): clic en un marcador o en un grupo (sus
            id), o en vacío (lista vacía con REPLACE).
        marker_activated(int): doble clic en un marcador.
        media_dropped(MediaDrag, float, float): tarjetas soltadas en (latitud, longitud).
        markers_moved(list, float, float): marcadores (sus id) arrastrados a otro punto.
        track_clicked(int): clic en la línea de un track.
        track_hovered(int, int): (track, índice del punto) bajo el ratón en el track
            activo; índice -1 al salir.
        context_menu_requested(MapHit, QPoint): botón derecho; el punto, en coordenadas
            globales de pantalla.
    """

    ready = Signal()
    load_failed = Signal(str)
    viewport_changed = Signal(object)
    selection_requested = Signal(list, object)
    marker_activated = Signal(int)
    media_dropped = Signal(object, float, float)
    markers_moved = Signal(list, float, float)
    track_clicked = Signal(int)
    track_hovered = Signal(int, int)
    context_menu_requested = Signal(object, object)

    # --- Marcadores ---

    def set_markers(self, markers: Sequence[MapMarker]) -> None:
        """Sustituye todos los marcadores (lista vacía = ninguno)."""
        raise NotImplementedError

    def update_markers(self, markers: Sequence[MapMarker]) -> None:
        """Añade unos marcadores o cambia los que ya estén (por su id), sin tocar el resto."""
        raise NotImplementedError

    def remove_markers(self, media_ids: Sequence[int]) -> None:
        """Quita unos marcadores (los id que no estén se ignoran)."""
        raise NotImplementedError

    def set_selected_ids(self, media_ids: Sequence[int]) -> None:
        """Resalta los marcadores seleccionados (y los grupos que contienen alguno)."""
        raise NotImplementedError

    def set_preview_markers(self, markers: Sequence[MapMarker]) -> None:
        """Marcadores provisionales (la propuesta de la correlación); vacío = quitarlos."""
        raise NotImplementedError

    def set_thumbnail_provider(self, provider: Callable[[int], Path | None] | None) -> None:
        """De dónde salen las miniaturas: una función que da la ruta de la imagen de un
        'media_items.id' (None si no tiene). None = sin miniaturas (al cerrar el catálogo).
        Se la llama en el hilo principal: debe ser rápida (solo buscar un archivo)."""
        raise NotImplementedError

    # --- Tracks ---

    def set_tracks(self, tracks: Sequence[MapTrack]) -> None:
        """Sustituye todos los tracks (lista vacía = ninguno)."""
        raise NotImplementedError

    def set_track_geometry(self, track: MapTrack) -> None:
        """Cambia la geometría de un track ya puesto (p. ej. su contorno por el detalle)."""
        raise NotImplementedError

    def set_active_track(self, track_id: int | None) -> None:
        """Track resaltado, el único que avisa con 'track_hovered' (None = ninguno)."""
        raise NotImplementedError

    def set_track_cursor(self, track_id: int, point_index: int | None) -> None:
        """Señala un punto de un track (None = quitar la señal)."""
        raise NotImplementedError

    # --- Encuadre ---

    def fit_bounds(self, bounds: MapBounds, *, animate: bool = True) -> None:
        """Encuadra un rectángulo."""
        raise NotImplementedError

    def set_view(self, latitude: float, longitude: float, zoom: float | None = None) -> None:
        """Centra el mapa en un punto (None = sin cambiar el zoom)."""
        raise NotImplementedError

    def viewport(self) -> MapViewport | None:
        """Lo que se ve (None si aún no está listo)."""
        raise NotImplementedError

    # --- Capas ---

    def set_layers(self, layers: Sequence[TileLayer]) -> None:
        """Las capas que se pueden elegir."""
        raise NotImplementedError

    def set_base_layer(self, key: str) -> None:
        """Capa que se ve (una clave de las de 'set_layers')."""
        raise NotImplementedError

    # --- Interacción ---

    def set_mode(self, mode: MapMode) -> None:
        """Qué hace el ratón."""
        raise NotImplementedError

    def set_drop_enabled(self, enabled: bool) -> None:
        """Si acepta tarjetas soltadas y deja arrastrar los marcadores."""
        raise NotImplementedError

    def clear(self) -> None:
        """Quita marcadores, tracks y selección (al cerrar el catálogo)."""
        raise NotImplementedError
