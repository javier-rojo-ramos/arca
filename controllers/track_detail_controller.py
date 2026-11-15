"""El recorrido COMPLETO del track activo, en el mapa.

El mapa pinta todos los tracks con su contorno (el resumen que guarda el catálogo: pocos
puntos, para ver cientos a la vez). Del track ACTIVO (el seleccionado) se quiere el
recorrido entero, para verlo nítido al acercarse: esta pieza lo lee de su archivo GPX en
segundo plano y, cuando llega, se lo cambia al mapa por el contorno
('MapView.set_track_geometry', con 'MapTrack.detailed = True').

Qué hace (docs/MAPA.md, paso 4.3):
    - 'show(view, id, nombre)': el track activo es ese. Si su recorrido está en la memoria
      (los últimos 'CACHE_SIZE' leídos), se pone ya; si no, se pide ('load_track_detail':
      busca la ruta en el catálogo, lee el GPX y calcula el perfil, todo en el hilo de la
      base de datos).
    - Las respuestas tardías se descartan: si entre tanto se eligió otro track, se cerró el
      catálogo o se abrió otro, el recorrido se guarda en la memoria (si es del mismo
      catálogo) pero no se pinta.
    - Si el archivo no está (ausente, disco desconectado) o no se puede leer, el track se
      queda con su contorno: se ve igual, con menos detalle. Se anota en el registro.
    - Con el recorrido van los PUNTOS DE INTERÉS del GPX (waypoints; paso 4.3b): se ven
      los del track activo y solo esos ('MapView.set_waypoints'); al elegir otro track, o
      ninguno, los anteriores se quitan al momento.
    - Con el recorrido se calcula también su PERFIL DE ELEVACIÓN (paso 5.3a), en el mismo
      trabajo en segundo plano: lo que se guarda y se entrega es un 'TrackDetail'
      (recorrido y perfil). Quien no es el mapa (la banda del perfil) lo pide con
      'request(id)' y lo recibe con 'detail_ready(id, detalle)' (al momento si está en la
      memoria) o 'detail_failed(id)'. Un recorrido que llega se avisa siempre, sea del
      track activo o no: cada uno mira si es el suyo.

La usa 'MapController', que decide cuál es el track activo. No toca la selección ni el
encuadre.

Uso:
    detail = TrackDetailController(parent)
    detail.attach(db)                       # al abrir un catálogo
    detail.show(view, track_id, "Ordesa")   # al pasar a ser el activo
    detail.request(track_id)                # el detalle, para otro (-> detail_ready)
    detail.detach()                         # al cerrarlo (olvida la memoria)

1.3.0 Por qué no se pudo leer ('DetailFailure': ausente, sin conexión, GPX ilegible, sin
      puntos), en 'load_track_detail' y en 'detail_failed'; 'detail_shown' al poner el
      recorrido completo en el mapa (paso 5.3b: desde ahí, los índices del mapa son los
      del perfil).
1.2.0 El perfil de elevación, con el recorrido ('TrackDetail', 'load_track_detail'); para
      la banda del perfil, 'request' y las señales 'detail_ready' y 'detail_failed'
      (paso 5.3a).
1.1.0 Los puntos de interés del track activo, con su recorrido (paso 4.3b).
1.0.0 Primera versión (14/11/2026).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.track_detail_controller
"""

__version__ = "1.3.0"
__all__ = [
    "CACHE_SIZE",
    "DetailFailure",
    "TrackDetail",
    "TrackDetailController",
    "load_track_detail",
    "load_track_path",
    "path_segments",
    "path_waypoints",
]

# Librerías estándar
import sqlite3
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from typing import Any, Protocol

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal

# Módulos del proyecto
from core.catalog.media_queries import AVAILABLE, OFFLINE, fetch_media_file
from core.metadata.track.gpx_reader import GpxError
from core.tracks.gpx_document import TrackPath, read_gpx_path
from core.tracks.profile import ElevationProfileData, build_profile
from ui_helpers.map.map_types import MapTrack, MapWaypoint, is_valid_position

# Recorridos completos que se guardan en memoria (los últimos leídos): volver a un track
# visto hace poco no relee su archivo
CACHE_SIZE = 5


class _TrackView(Protocol):
    """Lo que se necesita del mapa ('MapView' lo cumple)."""

    def set_track_geometry(self, track: MapTrack) -> None: ...

    def set_waypoints(self, waypoints: Sequence[MapWaypoint]) -> None: ...


class DetailFailure(StrEnum):
    """Por qué no se ha podido leer el recorrido de un track (para decírselo al usuario)."""

    NOT_IN_CATALOG = "not_in_catalog"  # ese id no está en el catálogo
    MISSING = "missing"  # ausente: su unidad está, pero el archivo no
    OFFLINE = "offline"  # sin conexión: su disco no está conectado
    UNREADABLE = "unreadable"  # no es un GPX, está dañado o no se puede abrir
    EMPTY = "empty"  # un GPX sin ningún punto de recorrido
    ERROR = "error"  # un error inesperado al leerlo


def _read_path(conn: sqlite3.Connection, track_id: int) -> TrackPath | DetailFailure:
    """El recorrido completo de un track del catálogo, o por qué no se puede leer."""
    media = fetch_media_file(conn, track_id)
    if media is None:
        return DetailFailure.NOT_IN_CATALOG
    if media.availability == OFFLINE:
        return DetailFailure.OFFLINE
    if media.availability != AVAILABLE:
        return DetailFailure.MISSING
    try:
        return read_gpx_path(media.path)
    except FileNotFoundError:
        return DetailFailure.MISSING  # desapareció después de la última comprobación
    except (GpxError, OSError) as error:
        logger.warning(f"No se pudo leer el recorrido de {media.path.name}: {error}")
        return DetailFailure.UNREADABLE


def load_track_path(conn: sqlite3.Connection, track_id: int) -> TrackPath | None:
    """Lee el recorrido completo de un track del catálogo (para 'execute_async').

    Returns:
        El recorrido, o None si el track no está en el catálogo, su archivo no está
        disponible (ausente o en un disco desconectado) o no se puede leer.
    """
    path = _read_path(conn, track_id)
    return path if isinstance(path, TrackPath) else None


@dataclass(frozen=True, slots=True)
class TrackDetail:
    """El detalle de un track: su recorrido completo y su perfil de elevación."""

    path: TrackPath
    profile: ElevationProfileData


def load_track_detail(conn: sqlite3.Connection, track_id: int) -> TrackDetail | DetailFailure:
    """Lee el recorrido de un track y calcula su perfil (para 'execute_async': las dos
    cosas, fuera del hilo de la interfaz).

    Returns:
        El detalle, o por qué no se ha podido leer (también si no tiene ningún punto).
    """
    path = _read_path(conn, track_id)
    if isinstance(path, DetailFailure):
        return path
    if path.point_count == 0:
        return DetailFailure.EMPTY
    return TrackDetail(path, build_profile(path))


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
    """Pone en el mapa el recorrido completo del track activo (ver el docstring del archivo).

    Signals:
        detail_ready(int, TrackDetail): ha llegado (o estaba en la memoria, si se pidió
            con 'request') el detalle de un track.
        detail_failed(int, str): no se ha podido leer el de ese track; el texto es el
            valor de su 'DetailFailure' (por qué).
        detail_shown(int): el recorrido completo de ese track se acaba de poner en el
            mapa: desde ahora, los índices de sus puntos en el mapa son los de su perfil.
    """

    detail_ready = Signal(int, object)
    detail_failed = Signal(int, str)
    detail_shown = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db: Any = None
        # Sube con cada 'attach' y 'detach': lo leído de un catálogo anterior se descarta
        self._generation = 0
        # El track cuyo recorrido se quiere ver ahora en el mapa (None = ninguno), con su
        # nombre y el mapa donde se pone
        self._wanted: int | None = None
        self._wanted_name = ""
        self._view: _TrackView | None = None
        # Los que se están leyendo (para no pedirlos dos veces)
        self._loading: set[int] = set()
        # id -> detalle, del más antiguo al más reciente
        self._cache: OrderedDict[int, TrackDetail] = OrderedDict()

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
        self._view = None
        self._loading.clear()
        self._cache.clear()

    def show(self, view: _TrackView, track_id: int | None, name: str = "") -> None:
        """El track activo es 'track_id' (None = ninguno): su recorrido completo, al mapa
        en cuanto se tenga."""
        changed = track_id != self._wanted
        self._wanted = track_id
        self._wanted_name = name
        self._view = view
        detail = self._cached(track_id)
        if detail is None and changed:
            # Otro track (o ninguno) y aún sin su recorrido: fuera los puntos de interés
            # del anterior; los suyos llegarán con su recorrido
            view.set_waypoints(())
        if track_id is None or self._db is None:
            return
        if detail is not None:
            self._apply(view, track_id, name, detail.path)
        else:
            self._load(track_id)

    def request(self, track_id: int) -> None:
        """Pide el detalle de un track para quien no es el mapa (la banda del perfil): llega
        con 'detail_ready' (ya, si está en la memoria) o falla con 'detail_failed'. Sin
        catálogo, nada."""
        if self._db is None:
            return
        detail = self._cached(track_id)
        if detail is not None:
            self.detail_ready.emit(track_id, detail)
        else:
            self._load(track_id)

    def forget(self, track_id: int) -> None:
        """Olvida el recorrido guardado de un track (p. ej. si su archivo ha cambiado)."""
        self._cache.pop(track_id, None)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _cached(self, track_id: int | None) -> TrackDetail | None:
        """El detalle de la memoria (pasa a ser el más reciente), o None."""
        if track_id is None or self._db is None:
            return None
        detail = self._cache.get(track_id)
        if detail is not None:
            self._cache.move_to_end(track_id)
        return detail

    def _load(self, track_id: int) -> None:
        """Lo pide en segundo plano (si no se está pidiendo ya)."""
        if track_id in self._loading:
            return
        self._loading.add(track_id)
        self._db.execute_async(
            load_track_detail,
            track_id,
            on_result=partial(self._on_loaded, self._generation, track_id),
            on_error=partial(self._on_error, self._generation, track_id),
        )

    def _on_loaded(
        self, generation: int, track_id: int, detail: TrackDetail | DetailFailure
    ) -> None:
        """Ha llegado un detalle (o por qué no se ha podido leer)."""
        if generation != self._generation or self._db is None:
            return  # de un catálogo que ya no está abierto
        self._loading.discard(track_id)
        if not isinstance(detail, TrackDetail):
            self.detail_failed.emit(track_id, str(detail))  # en el mapa, su contorno
            return
        self._cache[track_id] = detail
        self._cache.move_to_end(track_id)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)  # fuera el más antiguo
        # Al mapa, solo si sigue siendo el activo (si entre tanto se eligió otro, no)
        if track_id == self._wanted and self._view is not None:
            self._apply(self._view, track_id, self._wanted_name, detail.path)
        self.detail_ready.emit(track_id, detail)

    def _on_error(self, generation: int, track_id: int, error: Exception) -> None:
        if generation == self._generation:
            self._loading.discard(track_id)
            logger.error(f"Mapa: no se ha podido leer el recorrido del track {track_id}: {error}")
            self.detail_failed.emit(track_id, str(DetailFailure.ERROR))

    def _apply(self, view: _TrackView, track_id: int, name: str, path: TrackPath) -> None:
        """Cambia en el mapa el contorno del track por su recorrido completo, pone sus
        puntos de interés y avisa ('detail_shown')."""
        view.set_track_geometry(MapTrack(track_id, name, path_segments(path), detailed=True))
        view.set_waypoints(path_waypoints(path))
        self.detail_shown.emit(track_id)


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
        # Con el perfil (los mismos puntos), o por qué no se puede: 8, ausente en el disco
        # (el catálogo aún no lo sabe); 9, no es un GPX; 10, ausente según el catálogo; 11,
        # en un disco desconectado; 12, un GPX sin puntos; 999, no está en el catálogo
        conn.execute(
            "INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('Q', ?, 0)",
            (str(base / "desconectado"),),
        )
        (base / "t12.gpx").write_text('<gpx version="1.1" creator="x"><trk/></gpx>', encoding="utf-8")
        for number, location, name in ((11, 2, "t11.gpx"), (12, 1, "t12.gpx")):
            conn.execute(
                "INSERT INTO media_items(id, storage_location_id, relative_path, file_name, "
                "title, file_extension, media_type, mime_type, file_size, file_mtime_ns) "
                "VALUES (?, ?, ?, ?, ?, 'gpx', 'track', 'application/gpx+xml', 1, 1)",
                (number, location, name, name, name),
            )
        full = load_track_detail(conn, 1)
        assert isinstance(full, TrackDetail)
        assert full.profile.point_count == full.path.point_count == 4
        assert full.profile.totals.elevation_max_m == 102
        failures = {number: load_track_detail(conn, number) for number in (8, 9, 10, 11, 12, 999)}
        assert failures == {
            8: DetailFailure.MISSING, 9: DetailFailure.UNREADABLE, 10: DetailFailure.MISSING,
            11: DetailFailure.OFFLINE, 12: DetailFailure.EMPTY, 999: DetailFailure.NOT_IN_CATALOG,
        }, failures  # fmt: skip

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

        # --- Para la banda del perfil: 'request' y las señales (sin tocar el mapa)
        ready: list[tuple[int, int]] = []
        failed: list[tuple[int, str]] = []
        shown: list[int] = []
        detail.detail_ready.connect(lambda tid, got: ready.append((tid, got.profile.point_count)))
        detail.detail_failed.connect(lambda tid, why: failed.append((tid, why)))
        detail.detail_shown.connect(shown.append)
        requests = db.requests
        detail.request(2)  # en la memoria: al momento, sin pedir nada
        assert ready == [(2, 5)] and db.requests == requests and view.take() == []
        detail.request(3)  # no está: se pide
        detail.request(3)  # ya se está leyendo: no se pide otra vez
        assert db.requests == requests + 1 and ready == [(2, 5)]
        db.deliver()
        assert ready[-1] == (3, 6) and view.take() == []  # avisa; al mapa no (el activo es el 2)
        detail.request(8)  # ausente: con el motivo
        detail.request(11)  # en un disco desconectado
        db.deliver()
        assert failed == [(8, "missing"), (11, "offline")], failed
        assert shown == []  # nada de esto ha ido al mapa
        # Lo que pide el mapa también se avisa (la banda del perfil puede estar esperándolo)
        # y, al ponerlo en el mapa, 'detail_shown'
        detail.show(view, 4, "Cuatro")
        db.deliver()
        assert ready[-1] == (4, 7) and view.take() == [(4, "Cuatro", True, 2, 7)]
        assert shown == [4]
        detail.show(view, 3, "Tres")  # de la memoria: también
        assert shown == [4, 3]
        # Sin catálogo, 'request' no hace nada
        detail.detach()
        count = len(ready)
        detail.request(2)
        assert len(ready) == count
        conn.close()

    print("Autoprueba finalizada correctamente.")
