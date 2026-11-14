"""El recorrido COMPLETO del track activo, en el mapa.

El mapa pinta todos los tracks con su contorno (el resumen que guarda el catálogo: pocos
puntos, para ver cientos a la vez). Del track ACTIVO (el seleccionado) se quiere el
recorrido entero, para verlo nítido al acercarse: esta pieza lo lee de su archivo GPX en
segundo plano y, cuando llega, se lo cambia al mapa por el contorno
('MapView.set_track_geometry', con 'MapTrack.detailed = True').

Qué hace (docs/MAPA.md, paso 4.3):
    - 'show(view, id, nombre)': el track activo es ese. Si su recorrido está en la memoria
      (los últimos 'CACHE_SIZE' leídos), se pone ya; si no, se pide ('load_track_path':
      busca la ruta en el catálogo y lee el GPX, todo en el hilo de la base de datos).
    - Las respuestas tardías se descartan: si entre tanto se eligió otro track, se cerró el
      catálogo o se abrió otro, el recorrido se guarda en la memoria (si es del mismo
      catálogo) pero no se pinta.
    - Si el archivo no está (ausente, disco desconectado) o no se puede leer, el track se
      queda con su contorno: se ve igual, con menos detalle. Se anota en el registro.
    - Con el recorrido van los PUNTOS DE INTERÉS del GPX (waypoints; paso 4.3b): se ven
      los del track activo y solo esos ('MapView.set_waypoints'); al elegir otro track, o
      ninguno, los anteriores se quitan al momento.

La usa 'MapController', que decide cuál es el track activo. No toca la selección ni el
encuadre.

Uso:
    detail = TrackDetailController(parent)
    detail.attach(db)                       # al abrir un catálogo
    detail.show(view, track_id, "Ordesa")   # al pasar a ser el activo
    detail.detach()                         # al cerrarlo (olvida la memoria)

1.1.0 Los puntos de interés del track activo, con su recorrido (paso 4.3b).
1.0.0 Primera versión (14/11/2026).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.track_detail_controller
"""

__version__ = "1.1.0"
__all__ = [
    "CACHE_SIZE",
    "TrackDetailController",
    "load_track_path",
    "path_segments",
    "path_waypoints",
]

# Librerías estándar
import sqlite3
from collections import OrderedDict
from collections.abc import Sequence
from functools import partial
from typing import Any, Protocol

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject

# Módulos del proyecto
from core.catalog.media_queries import AVAILABLE, fetch_media_file
from core.metadata.track.gpx_reader import GpxError
from core.tracks.gpx_document import TrackPath, read_gpx_path
from ui_helpers.map.map_types import MapTrack, MapWaypoint, is_valid_position

# Recorridos completos que se guardan en memoria (los últimos leídos): volver a un track
# visto hace poco no relee su archivo
CACHE_SIZE = 5


class _TrackView(Protocol):
    """Lo que se necesita del mapa ('MapView' lo cumple)."""

    def set_track_geometry(self, track: MapTrack) -> None: ...

    def set_waypoints(self, waypoints: Sequence[MapWaypoint]) -> None: ...


def load_track_path(conn: sqlite3.Connection, track_id: int) -> TrackPath | None:
    """Lee el recorrido completo de un track del catálogo (para 'execute_async').

    Returns:
        El recorrido, o None si el track no está en el catálogo, su archivo no está
        disponible (ausente o en un disco desconectado) o no se puede leer.
    """
    media = fetch_media_file(conn, track_id)
    if media is None or media.availability != AVAILABLE:
        return None
    try:
        return read_gpx_path(media.path)
    except (GpxError, OSError) as error:
        logger.warning(f"No se pudo leer el recorrido de {media.path.name}: {error}")
        return None


def path_segments(path: TrackPath) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Los segmentos de un recorrido como los quiere 'MapTrack': tuplas de (latitud,
    longitud)."""
    return tuple(
        tuple(zip(segment.latitudes, segment.longitudes, strict=True)) for segment in path.segments
    )


def path_waypoints(path: TrackPath) -> tuple[MapWaypoint, ...]:
    """Los puntos de interés de un recorrido, como los quiere el mapa (los que estén en
    0, 0, que el mapa toma por «sin coordenadas», se dejan fuera)."""
    return tuple(
        MapWaypoint(w.latitude, w.longitude, w.name or "", w.description or "")
        for w in path.waypoints
        if is_valid_position(w.latitude, w.longitude)
    )


class TrackDetailController(QObject):
    """Pone en el mapa el recorrido completo del track activo (ver el docstring del archivo)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db: Any = None
        # Sube con cada 'attach' y 'detach': lo leído de un catálogo anterior se descarta
        self._generation = 0
        # El track cuyo recorrido se quiere ver ahora (None = ninguno)
        self._wanted: int | None = None
        # Los que se están leyendo (para no pedirlos dos veces)
        self._loading: set[int] = set()
        # id -> recorrido, del más antiguo al más reciente
        self._cache: OrderedDict[int, TrackPath] = OrderedDict()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def attach(self, db: Any) -> None:
        """Se ha abierto un catálogo."""
        self.detach()
        self._db = db

    def detach(self) -> None:
        """Se cierra el catálogo: se olvida todo (los 'id' son de cada catálogo)."""
        self._db = None
        self._generation += 1
        self._wanted = None
        self._loading.clear()
        self._cache.clear()

    def show(self, view: _TrackView, track_id: int | None, name: str = "") -> None:
        """El track activo es 'track_id' (None = ninguno): su recorrido completo, al mapa
        en cuanto se tenga."""
        changed = track_id != self._wanted
        self._wanted = track_id
        path = self._cache.get(track_id) if track_id is not None and self._db is not None else None
        if path is None and changed:
            # Otro track (o ninguno) y aún sin su recorrido: fuera los puntos de interés
            # del anterior; los suyos llegarán con su recorrido
            view.set_waypoints(())
        if track_id is None or self._db is None:
            return
        if path is not None:
            self._cache.move_to_end(track_id)  # el más reciente
            self._apply(view, track_id, name, path)
        elif track_id not in self._loading:
            self._loading.add(track_id)
            self._db.execute_async(
                load_track_path,
                track_id,
                on_result=partial(self._on_loaded, self._generation, view, track_id, name),
                on_error=partial(self._on_error, self._generation, track_id),
            )

    def forget(self, track_id: int) -> None:
        """Olvida el recorrido guardado de un track (p. ej. si su archivo ha cambiado)."""
        self._cache.pop(track_id, None)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_loaded(
        self, generation: int, view: _TrackView, track_id: int, name: str, path: TrackPath | None
    ) -> None:
        """Ha llegado un recorrido (o None si no se pudo leer)."""
        if generation != self._generation or self._db is None:
            return  # de un catálogo que ya no está abierto
        self._loading.discard(track_id)
        if path is None or path.point_count == 0:
            return  # se queda con su contorno
        self._cache[track_id] = path
        self._cache.move_to_end(track_id)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)  # fuera el más antiguo
        if track_id == self._wanted:  # si entre tanto se eligió otro, no se pinta
            self._apply(view, track_id, name, path)

    def _on_error(self, generation: int, track_id: int, error: Exception) -> None:
        if generation == self._generation:
            self._loading.discard(track_id)
            logger.error(f"Mapa: no se ha podido leer el recorrido del track {track_id}: {error}")

    @staticmethod
    def _apply(view: _TrackView, track_id: int, name: str, path: TrackPath) -> None:
        """Cambia en el mapa el contorno del track por su recorrido completo, y pone sus
        puntos de interés."""
        view.set_track_geometry(MapTrack(track_id, name, path_segments(path), detailed=True))
        view.set_waypoints(path_waypoints(path))


if __name__ == "__main__":
    # Autoprueba sin ventana: un catálogo en memoria, GPX en una carpeta temporal y un
    # gestor de base de datos de mentira que entrega las respuestas cuando se le dice.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.track_detail_controller
    import tempfile
    from collections.abc import Callable
    from pathlib import Path

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    def _gpx(first_latitude: float, count: int) -> str:
        points = "".join(
            f'<trkpt lat="{first_latitude + i * 0.001:.3f}" lon="-3.0"><ele>{100 + i}</ele></trkpt>'
            for i in range(count)
        )
        # Cada GPX, con tantos puntos de interés como puntos tiene su primer segmento
        marks = "".join(
            f'<wpt lat="{first_latitude + i * 0.001:.3f}" lon="-3.0"><name>W{i}</name></wpt>'
            for i in range(count)
        )
        return (
            f'<gpx version="1.1" creator="x">{marks}<trk><trkseg>'
            f"{points}</trkseg><trkseg><trkpt lat=\"50\" lon=\"1\"/></trkseg></trk></gpx>"
        )

    class _FakeDb:
        """'execute_async' que guarda las peticiones y las entrega con 'deliver'."""

        def __init__(self, conn: sqlite3.Connection) -> None:
            self.conn = conn
            self.pending: list[tuple[Callable, tuple, Callable, Callable]] = []
            self.requests = 0

        def execute_async(self, function: Callable, *args: Any, on_result: Callable,
                          on_error: Callable) -> None:  # fmt: skip
            self.requests += 1
            self.pending.append((function, args, on_result, on_error))

        def deliver(self) -> None:
            pending, self.pending = self.pending, []
            for function, args, on_result, on_error in pending:
                try:
                    result = function(self.conn, *args)
                except Exception as error:  # noqa: BLE001 - como el gestor de verdad
                    on_error(error)
                else:
                    on_result(result)

    class _FakeView:
        def __init__(self) -> None:
            self.shown: list[tuple[int, str, bool, int, int]] = []

            # Los puntos de interés que se ven ahora (None = nadie los ha puesto aún)
            self.waypoints: list[str] | None = None

        def set_track_geometry(self, track: MapTrack) -> None:
            self.shown.append(
                (track.track_id, track.name, track.detailed, len(track.segments), track.point_count)
            )

        def set_waypoints(self, waypoints: Sequence[MapWaypoint]) -> None:
            self.waypoints = [w.name for w in waypoints]

        def take(self) -> list:
            shown, self.shown = self.shown, []
            return shown

    logger.remove()  # los avisos esperados no ensucian la salida

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        conn = sqlite3.connect(":memory:")
        configure_connection(conn)
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO storage_locations(name, absolute_path) VALUES ('P', ?)", (str(base),)
        )
        # 1 a 7: GPX que existen (de 3 a 9 puntos + 1 en otro segmento); 8: ausente;
        # 9: no es un GPX; 10: marcado como ausente en el catálogo
        for number in range(1, 11):
            name = f"t{number}.gpx"
            if number <= 7:
                (base / name).write_text(_gpx(40.0 + number, number + 2), encoding="utf-8")
            elif number == 9:
                (base / name).write_text("<kml/>", encoding="utf-8")
            elif number == 10:
                (base / name).write_text(_gpx(41.0, 3), encoding="utf-8")
            conn.execute(
                "INSERT INTO media_items(id, storage_location_id, relative_path, file_name, title, "
                "file_extension, media_type, mime_type, file_size, file_mtime_ns, is_missing) "
                "VALUES (?, 1, ?, ?, ?, 'gpx', 'track', 'application/gpx+xml', 1, 1, ?)",
                (number, name, name, name, 1 if number == 10 else 0),
            )

        # --- La lectura: el recorrido, o None si no se puede
        loaded = load_track_path(conn, 1)
        assert loaded is not None and [len(s) for s in loaded.segments] == [3, 1]
        assert path_segments(loaded) == (((41.0, -3.0), (41.001, -3.0), (41.002, -3.0)), ((50.0, 1.0),))
        for missing in (8, 9, 10, 999):
            assert load_track_path(conn, missing) is None, missing
        assert [(w.name, w.latitude) for w in path_waypoints(loaded)] == [
            ("W0", 41.0), ("W1", 41.001), ("W2", 41.002)]  # fmt: skip

        db = _FakeDb(conn)
        view = _FakeView()
        detail = TrackDetailController()

        # --- Sin catálogo no se pide nada
        detail.show(view, 1, "Uno")
        assert db.requests == 0 and view.take() == []

        # --- Se pide en segundo plano y, al llegar, se pone el recorrido completo
        detail.attach(db)
        detail.show(view, 1, "Uno")
        assert db.requests == 1 and view.take() == []  # aún no ha llegado
        detail.show(view, 1, "Uno")
        assert db.requests == 1  # ya se está leyendo: no se pide otra vez
        assert view.waypoints == []  # mientras llega, sin puntos de interés
        db.deliver()
        assert view.take() == [(1, "Uno", True, 2, 4)]
        assert view.waypoints == ["W0", "W1", "W2"]  # los suyos, con su recorrido
        # La segunda vez sale de la memoria, al momento
        detail.show(view, 1, "Uno")
        assert db.requests == 1 and view.take() == [(1, "Uno", True, 2, 4)]

        # --- Cambiar de track deprisa: solo se pinta el último elegido; los otros, a la memoria
        detail.show(view, 2, "Dos")
        assert view.waypoints == []  # los del track anterior se quitan al momento
        detail.show(view, 3, "Tres")
        assert db.requests == 3
        db.deliver()
        assert view.take() == [(3, "Tres", True, 2, 6)]
        assert view.waypoints == ["W0", "W1", "W2", "W3", "W4"]  # los del 3, no los del 2
        detail.show(view, 2, "Dos")
        assert db.requests == 3 and view.take() == [(2, "Dos", True, 2, 5)]
        assert view.waypoints == ["W0", "W1", "W2", "W3"]
        # Ningún track activo: lo que llegue después no se pinta
        detail.show(view, 4, "Cuatro")
        detail.show(view, None)
        db.deliver()
        assert view.take() == [] and view.waypoints == []

        # --- Lo que no se puede leer se queda con su contorno (y se puede volver a pedir)
        for missing in (8, 9, 10):
            detail.show(view, missing, "x")
            db.deliver()
            assert view.take() == [], missing
        requests = db.requests
        detail.show(view, 8, "x")
        assert db.requests == requests + 1
        db.deliver()

        # --- La memoria guarda los últimos CACHE_SIZE: el más antiguo sin usar se relee
        for number in (5, 6, 7):  # con 1, 3, 2 y 4, ya van siete leídos
            detail.show(view, number, "x")
            db.deliver()
        view.take()
        requests = db.requests
        detail.show(view, 7, "x")
        detail.show(view, 2, "x")
        assert db.requests == requests and len(view.take()) == 2  # siguen en la memoria
        detail.show(view, 1, "x")  # el primero que se leyó ya no está
        assert db.requests == requests + 1
        db.deliver()
        assert view.take() == [(1, "x", True, 2, 4)]
        # Olvidar uno a propósito
        detail.forget(1)
        detail.show(view, 1, "x")
        assert db.requests == requests + 2
        db.deliver()
        view.take()

        # --- Cerrar el catálogo: lo que llegue después se descarta y la memoria se vacía
        detail.show(view, 5, "x")  # en la memoria
        view.take()
        detail.forget(5)
        detail.show(view, 5, "x")  # pedido
        detail.detach()
        db.deliver()
        assert view.take() == []
        detail.attach(db)
        requests = db.requests
        detail.show(view, 2, "x")
        assert db.requests == requests + 1  # la memoria era del catálogo anterior
        db.deliver()
        assert view.take() == [(2, "x", True, 2, 5)]
        conn.close()

    print("Autoprueba finalizada correctamente.")
