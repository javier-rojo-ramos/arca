"""Modelo de la cuadrícula de miniaturas, alimentado por la base de datos del catálogo.

Sustituye al 'QStandardItemModel' del prototipo. Qué hace:

    - Pide a la base de datos (en un hilo secundario) las filas a mostrar
      ('core.catalog.media_queries.fetch_grid_rows') y las guarda en una lista ligera.
      QUÉ filas lo decide el origen ('GridSource') que elige la barra lateral del
      catálogo: todo el catálogo, una carpeta, una colección... ('set_source'). La barra
      de filtros lo acota sin cambiarlo ('set_filter', un 'GridFilter').
    - Entrega al delegado, por roles, lo necesario para pintar: nombre, miniatura,
      estrellas, marca, etiqueta de color y si el archivo está disponible en disco
      (ausente o en una ubicación desconectada: se sigue mostrando, con su miniatura).
    - Carga las miniaturas desde la caché en disco (JPEG) SOLO de las tarjetas que se
      están pintando, en hilos secundarios, y las guarda en una caché de QPixmap acotada.
      Elige el tamaño de la escalera con 'smallest_covering' según los píxeles físicos
      de la tarjeta.
    - Cuando el usuario cambia rating/marca/etiqueta o la selección rápida, actualiza la
      fila al instante y emite 'user_field_changed' para que el controlador lo guarde en
      la base de datos (el modelo no toca la base de datos para escribir).
    - Permite ARRASTRAR tarjetas (p. ej. a una colección de la barra lateral): empaqueta
      sus 'id' con el formato de 'media_mime.py'. Solo se copian: nunca se mueven.

Reglas de hilos: todo lo de este módulo se usa desde el hilo principal, salvo
'_LoadTask.run', que solo lee un archivo y devuelve una QImage por señal.

1.15.0 'request_media_file': ruta completa y dimensiones de UN archivo, en segundo plano
       (las pide la vista individual para ampliar a 1:1; la lista no lleva rutas).
1.14.0 'set_view(..., grid_filter)': origen, orden y filtro a la vez, con una sola recarga
       (al cambiar de módulo; paso A.3).
1.13.0 Filtro de la barra de filtros: 'set_filter', propiedades 'grid_filter' y
       'filter_rules' (las reglas que aplican; las usa también el inspector). Solo recarga
       si cambian las reglas (el candado o un texto con su pestaña apagada, no). Paso A.3.
1.12.0 'row_of_id': fila de un elemento (la vista individual vuelve a él tras recargar).
1.11.0 Para la vista individual: propiedad 'thumbnail_cache' y señales
       'thumbnails_refreshed' (miniaturas regeneradas) y 'missing_retried'.
1.10.0 'set_view': origen y orden a la vez, con una sola recarga (al cambiar de módulo);
       'set_order(..., reload=False)' para fijarlo antes de la primera carga.
1.9.0 El orden es un 'GridOrder' (campo y dirección; 'core/catalog/grid_orders.py'); por
      defecto, por nombre. 'set_order' no recarga si el orden no cambia; propiedad 'order'.
1.8.1 'catalog_key()': el catálogo abierto (para comprobar tarjetas soltadas en el inspector).
1.8.0 Roles del tipo, la duración, la biblioteca y el estado de la miniatura (marcador de
      las tarjetas sin miniatura e insignia de duración).
1.7.0 'set_library_values': biblioteca de las tarjetas cargadas (no se pinta: la usa el
      submenú «Biblioteca» para marcar la actual).
1.6.0 'set_data_rows': lo mismo que 'setData' (por rol) pero en varias filas a la vez; el
      delegado lo usa para que un clic en una tarjeta seleccionada cambie toda la selección.
1.5.1 'forget_quick_selection': quita el círculo a todas las tarjetas cargadas (tras
      vaciar la selección rápida en la base de datos), sin volver a guardarlo.
1.5.0 Selección rápida: rol 'ROLE_QUICK_SELECTION' y campo 'in_quick_selection'
      (se cambia como los demás, con 'setData' o 'set_field').
1.4.0 Arrastrar tarjetas ('flags', 'mimeTypes', 'mimeData', 'supportedDragActions').
1.3.0 Origen de la cuadrícula ('set_source', 'source'): lo que se elige en la barra
      lateral del catálogo decide qué filas se cargan.
"""

__version__ = "1.15.0"
__all__ = ["QUICK_SELECTION_FIELD", "MediaGridModel"]

# Librerías estándar
from collections import OrderedDict
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import (
    QAbstractListModel,
    QMimeData,
    QModelIndex,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
)
from qtpy.QtGui import QImage, QImageReader, QPixmap

# Módulos del proyecto
from core.catalog.color_labels import is_valid_color_label, normalize_color_label
from core.catalog.grid_filter import NO_FILTER, GridFilter
from core.catalog.grid_orders import NAME_ORDER, GridOrder
from core.catalog.grid_source import ALL_ITEMS, GridSource
from core.catalog.media_queries import (
    AVAILABLE,
    FLAG_NONE,
    FLAG_PICKED,
    FLAG_REJECTED,
    MediaFile,
    fetch_grid_rows,
    fetch_media_file,
)
from core.catalog.smart_rules import RuleSet
from core.thumbnails.cache import ThumbnailCache
from core.thumbnails.sizes import ThumbnailSize, smallest_covering
from ui_helpers.models.media_mime import MEDIA_IDS_MIME, encode_media_ids
from ui_helpers.models.media_roles import (
    ROLE_AVAILABILITY,
    ROLE_COLOR_LABEL,
    ROLE_DURATION,
    ROLE_FLAG,
    ROLE_FLAGGED,
    ROLE_LIBRARY,
    ROLE_MEDIA_ID,
    ROLE_MEDIA_TYPE,
    ROLE_QUICK_SELECTION,
    ROLE_RATING,
    ROLE_THUMBNAIL_STATUS,
)

_DISPLAY = Qt.ItemDataRole.DisplayRole
_DECORATION = Qt.ItemDataRole.DecorationRole

# Roles de usuario que cambian cuando se modifica cada campo (para 'dataChanged')
_ROLES_OF_FIELD: dict[str, list[int]] = {
    "rating": [ROLE_RATING],
    "flag": [ROLE_FLAG, ROLE_FLAGGED],
    "color_label": [ROLE_COLOR_LABEL],
    "in_quick_selection": [ROLE_QUICK_SELECTION],
}

# Campo de la selección rápida (columna de 'media_items'; 0 o 1). A diferencia de los
# otros tres, NO se escribe en los archivos: el controlador lo guarda aparte
QUICK_SELECTION_FIELD = "in_quick_selection"


class _LoadSignals(QObject):
    """Canal por el que los hilos devuelven las miniaturas leídas."""

    # (generación, id del elemento, lado largo del tamaño pedido, imagen; nula si no hay miniatura)
    loaded = Signal(int, int, int, QImage)


class _LoadTask(QRunnable):
    """Lee de la caché la miniatura de un elemento. Se ejecuta en un hilo del pool."""

    def __init__(
        self,
        cache: ThumbnailCache,
        media_type: str,
        media_id: int,
        wanted: ThumbnailSize,
        generation: int,
        signals: _LoadSignals,
    ) -> None:
        super().__init__()
        self._cache = cache
        self._media_type = media_type
        self._media_id = media_id
        self._wanted = wanted
        self._generation = generation
        self._signals = signals

    def run(self) -> None:
        """Busca el archivo (puede tocar el disco varias veces) y lo decodifica."""
        image = QImage()
        try:
            path = self._cache.resolve(self._media_type, self._media_id, self._wanted)
            if path is not None:
                # Las miniaturas de la caché ya están derechas: no hay que rotarlas
                image = QImageReader(str(path)).read()
        except (OSError, ValueError):
            image = QImage()  # tratado como "sin miniatura"; un hilo nunca debe lanzar
        self._signals.loaded.emit(
            self._generation, self._media_id, self._wanted.max_side, image
        )


class MediaGridModel(QAbstractListModel):
    """Lista de elementos del catálogo para la cuadrícula de miniaturas.

    Signals:
        user_field_changed(list, str, object): el usuario cambió 'rating', 'flag',
            'color_label' o 'in_quick_selection' (0/1) de esos 'id'. El controlador debe
            guardarlo.
        rows_loaded(int): se cargó la lista (número de elementos).
        load_failed(object): falló la consulta (la excepción).
        thumbnails_refreshed(list): las miniaturas de esos 'id' se han generado o
            regenerado ('refresh_thumbnails'): quien guarde otras copias, que las relea.
        missing_retried(): se reintentan los que no tenían miniatura ('retry_missing').
    """

    user_field_changed = Signal(list, str, object)
    rows_loaded = Signal(int)
    load_failed = Signal(object)
    thumbnails_refreshed = Signal(list)
    missing_retried = Signal()

    # Miniaturas decodificadas que se conservan en memoria (una de 480 px ocupa ~1 MB)
    MAX_CACHED_PIXMAPS = 3000

    # Hilos para leer miniaturas (el disco es el cuello de botella, no la CPU)
    LOAD_THREADS = 3

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._row_of_id: dict[int, int] = {}

        # id -> (miniatura, lado largo para el que se leyó; 0 = obsoleta, hay que releerla)
        self._pixmaps: OrderedDict[int, tuple[QPixmap, int]] = OrderedDict()
        self._pending: set[int] = set()  # ids con una lectura en curso
        self._no_thumb: set[int] = set()  # ids sin miniatura (para no buscarlos en cada pintado)

        self._db: Any = None
        self._cache: ThumbnailCache | None = None
        # Carpeta del catálogo (en texto): viaja con las tarjetas que se arrastran
        self._catalog_key = ""
        # En qué orden (lo decide el módulo activo; ver 'grid_orders.py')
        self._order: GridOrder = NAME_ORDER
        # Qué elementos se muestran (todo el catálogo, una carpeta, una colección...)
        self._source: GridSource = ALL_ITEMS
        # Filtro de la barra de filtros (lo decide el módulo activo) y sus reglas, que son
        # lo que va a la consulta
        self._filter: GridFilter = NO_FILTER
        self._filter_rules: tuple[RuleSet, ...] = ()
        self._wanted: ThumbnailSize = ThumbnailSize.THUMBNAIL

        # Las lecturas de una generación anterior (otra carga o un cierre) se descartan
        self._generation = 0
        self._query_token = 0
        self._priority = 0

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(self.LOAD_THREADS)
        self._signals = _LoadSignals(self)
        self._signals.loaded.connect(
            self._on_image_loaded, Qt.ConnectionType.QueuedConnection
        )

    # -------------------------------------------------------------------------
    # Conexión con el catálogo
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Any) -> None:
        """Asocia el modelo al catálogo abierto (no carga nada: ver 'reload')."""
        self.detach()
        self._db = db
        self._cache = ThumbnailCache(catalog_dir)
        self._catalog_key = str(catalog_dir)

    def detach(self) -> None:
        """Desasocia el modelo del catálogo y vacía la cuadrícula."""
        self._db = None
        self._cache = None
        self._catalog_key = ""
        self._query_token += 1  # una consulta en curso ya no se aplicará
        self._invalidate_loads()
        self._set_rows([])
        self._pixmaps.clear()
        self._no_thumb.clear()
        self._source = ALL_ITEMS  # el próximo catálogo empieza mostrando todo
        self._filter, self._filter_rules = NO_FILTER, ()  # y sin filtro

    def shutdown(self) -> None:
        """Para las lecturas y espera a las que están en curso (al cerrar la aplicación)."""
        self._generation += 1
        self._pool.clear()
        self._pool.waitForDone()

    @property
    def order(self) -> GridOrder:
        """Orden que se usa ahora."""
        return self._order

    def set_order(self, order: GridOrder, *, reload: bool = True) -> None:
        """Cambia el orden (campo y dirección) y vuelve a cargar.

        Si es el mismo orden que ya se usa, no hace nada.

        Args:
            order: Orden nuevo.
            reload: False = solo lo apunta, sin cargar. Al abrir un catálogo, el orden del
                módulo activo se fija así ANTES de que las barras restauren su origen: la
                primera carga ya sale en su orden y no se repite la consulta.
        """
        if order == self._order:
            return
        self._order = order
        if reload:
            self.reload()

    def set_view(
        self, source: GridSource, order: GridOrder, grid_filter: GridFilter | None = None
    ) -> None:
        """Cambia a la vez QUÉ se muestra, en qué orden y con qué filtro, con una sola
        recarga.

        Lo usa el 'ModuleHost' al cambiar de módulo (cada módulo tiene su origen, su orden
        y su filtro). Si no cambia nada de lo que va a la consulta, no recarga.

        Args:
            source: Origen.
            order: Orden.
            grid_filter: Filtro de la barra de filtros (None = se queda el que hay).
        """
        rules = self._filter_rules
        if grid_filter is not None:
            self._filter = grid_filter
            rules = grid_filter.rule_sets()
        if source == self._source and order == self._order and rules == self._filter_rules:
            return
        self._source = source
        self._order = order
        self._filter_rules = rules
        self.reload()

    @property
    def source(self) -> GridSource:
        """Origen que se muestra ahora (lo elige la barra lateral del catálogo)."""
        return self._source

    def set_source(self, source: GridSource) -> None:
        """Cambia QUÉ se muestra (lo elige la barra lateral) y vuelve a cargar.

        Si es el mismo origen que ya se muestra, no hace nada (así no se recarga al
        volver a pulsar la misma fila).
        """
        if source == self._source:
            return
        self._source = source
        self.reload()

    @property
    def grid_filter(self) -> GridFilter:
        """Filtro de la barra de filtros que se usa ahora (con lo escrito aunque no aplique)."""
        return self._filter

    @property
    def filter_rules(self) -> tuple[RuleSet, ...]:
        """Las reglas del filtro que aplican ahora (vacío = sin filtro). El inspector las usa
        para resumir lo mismo que se ve."""
        return self._filter_rules

    def set_filter(self, grid_filter: GridFilter, *, reload: bool = True) -> None:
        """Cambia el filtro de la barra de filtros y, si cambian sus reglas, vuelve a cargar.

        Cambiar algo que no filtra (el candado, o el texto con su pestaña apagada) solo se
        apunta: la cuadrícula no se recarga.

        Args:
            grid_filter: Filtro nuevo.
            reload: False = solo lo apunta, sin cargar (como en 'set_order').
        """
        self._filter = grid_filter
        rules = grid_filter.rule_sets()
        if rules == self._filter_rules:
            return
        self._filter_rules = rules
        if reload:
            self.reload()

    def reload(self) -> None:
        """Vuelve a leer de la base de datos la lista de elementos (asíncrono)."""
        if self._db is None:
            return
        self._query_token += 1
        token = self._query_token
        # 'fetch_grid_rows(conn, order, source, filters)': la conexión la pone el gestor
        self._db.execute_async(
            fetch_grid_rows,
            self._order,
            self._source,
            self._filter_rules,
            on_result=partial(self._on_rows, token),
            on_error=partial(self._on_rows_error, token),
        )

    def _on_rows(self, token: int, rows: list[dict[str, Any]]) -> None:
        if token != self._query_token:
            return  # llegó tarde: se pidió otra carga o se cerró el catálogo
        self._invalidate_loads()
        self._set_rows(rows)
        self.rows_loaded.emit(len(rows))

    def request_media_file(
        self, media_id: int, on_result: Callable[[MediaFile | None], None]
    ) -> bool:
        """Pide en segundo plano la ruta completa y las dimensiones de UN archivo
        ('media_queries.fetch_media_file'): la lista de la cuadrícula no lleva rutas.

        'on_result' recibe el 'MediaFile' (None si ya no está en el catálogo o si falla
        la consulta). No se llama si el catálogo se cierra mientras tanto.

        Returns:
            False si no hay catálogo (no se pide nada).
        """
        if self._db is None:
            return False
        catalog_key = self._catalog_key

        def deliver(result: MediaFile | None) -> None:
            if self._db is not None and self._catalog_key == catalog_key:
                on_result(result)

        self._db.execute_async(
            fetch_media_file, media_id, on_result=deliver, on_error=lambda _error: deliver(None)
        )
        return True

    def _on_rows_error(self, token: int, error: Exception) -> None:
        if token == self._query_token:
            self.load_failed.emit(error)

    def _set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self._row_of_id = {row["id"]: i for i, row in enumerate(rows)}
        self.endResetModel()

    # -------------------------------------------------------------------------
    # Miniaturas
    # -------------------------------------------------------------------------

    def set_target_pixels(self, physical_pixels: int) -> None:
        """Indica cuántos píxeles FÍSICOS de lado largo ocupa la miniatura en pantalla.

        Elige el tamaño de la escalera que los cubre. Si cambia de tamaño, las miniaturas ya
        cargadas se siguen mostrando mientras llegan las nuevas (no hay parpadeo).
        """
        wanted = smallest_covering(max(1, physical_pixels))
        if wanted is not self._wanted:
            self._wanted = wanted
            self._notify_all([_DECORATION])

    def set_availability(self, changes: dict[int, int]) -> None:
        """Actualiza si los archivos están en disco y repinta SOLO esas tarjetas.

        Lo llama el controlador con lo que ha visto 'check_availability' (archivo borrado
        o que vuelve, disco desconectado...). No recarga la lista: se conservan la
        selección y la posición.

        Args:
            changes: 'media_items.id' -> AVAILABLE, MISSING u OFFLINE.
        """
        rows: list[int] = []
        for media_id, availability in changes.items():
            row = self._row_of_id.get(media_id)
            if row is None or self._rows[row].get("availability") == availability:
                continue
            self._rows[row]["availability"] = availability
            rows.append(row)
        if len(rows) > 200:
            self._notify_all([ROLE_AVAILABILITY])
        else:
            for row in rows:
                self._notify_row(row, [ROLE_AVAILABILITY])

    def set_library_values(self, changes: dict[int, tuple[str | None, int]]) -> None:
        """Actualiza la biblioteca de las tarjetas cargadas (tras cambiarla en el catálogo).

        No se pinta en la tarjeta, así que no hace falta repintar: solo se guarda para que
        el submenú «Biblioteca» marque la actual sin recargar la lista.

        Args:
            changes: 'media_items.id' -> (biblioteca o None, 1 si es manual).
        """
        for media_id, (library, manual) in changes.items():
            row = self._row_of_id.get(media_id)
            if row is not None:
                self._rows[row]["library"] = library
                self._rows[row]["library_manual"] = manual

    def media_ids_in_rows(self, first: int, last: int) -> list[int]:
        """'id' de las filas entre 'first' y 'last' (ambas incluidas; se recortan al rango)."""
        first = max(0, first)
        last = min(len(self._rows) - 1, last)
        return [self._rows[row]["id"] for row in range(first, last + 1)]

    def refresh_thumbnails(self, media_ids: Iterable[int]) -> None:
        """Vuelve a leer las miniaturas de estos elementos (se han generado o regenerado)."""
        rows: list[int] = []
        for media_id in media_ids:
            row = self._row_of_id.get(media_id)
            if row is None:
                continue
            self._no_thumb.discard(media_id)
            if media_id in self._pixmaps:
                self._pixmaps[media_id] = (self._pixmaps[media_id][0], 0)  # obsoleta
            rows.append(row)
        if len(rows) > 200:
            self._notify_all([_DECORATION])
        else:
            for row in rows:
                self._notify_row(row, [_DECORATION])
        self.thumbnails_refreshed.emit([self._rows[row]["id"] for row in rows])

    def retry_missing(self) -> None:
        """Reintenta las tarjetas que no tenían miniatura (se llama mientras se generan)."""
        if self._no_thumb:
            self._no_thumb.clear()
            self._notify_all([_DECORATION])
        # Siempre: la vista individual puede tener sus propios «sin miniatura»
        self.missing_retried.emit()

    def _invalidate_loads(self) -> None:
        """Descarta las lecturas encoladas o en curso."""
        self._generation += 1
        self._pool.clear()
        self._pending.clear()

    def _thumbnail_for(self, row: dict[str, Any]) -> QPixmap | None:
        """Miniatura de una fila (puede ser la anterior mientras llega la nueva) o None."""
        media_id = row["id"]
        cached = self._pixmaps.get(media_id)
        if cached is not None:
            self._pixmaps.move_to_end(media_id)  # el más recientemente usado, al final

        up_to_date = cached is not None and cached[1] == self._wanted.max_side
        if (
            not up_to_date
            and media_id not in self._pending
            and media_id not in self._no_thumb
            and self._cache is not None
        ):
            self._pending.add(media_id)
            # Prioridad creciente: lo último que se pidió (lo que se ve ahora al hacer scroll)
            # se lee antes que lo que se pidió hace rato y ya no está a la vista
            self._priority += 1
            self._pool.start(
                _LoadTask(
                    self._cache,
                    row["media_type"],
                    media_id,
                    self._wanted,
                    self._generation,
                    self._signals,
                ),
                self._priority,
            )
        return cached[0] if cached is not None else None

    def _on_image_loaded(
        self, generation: int, media_id: int, loaded_side: int, image: QImage
    ) -> None:
        if generation != self._generation:
            return
        self._pending.discard(media_id)
        row = self._row_of_id.get(media_id)
        if row is None:
            return
        if image.isNull():
            self._no_thumb.add(media_id)  # aún no existe (o falló): se queda el hueco
            return
        self._pixmaps[media_id] = (QPixmap.fromImage(image), loaded_side)
        self._pixmaps.move_to_end(media_id)
        while len(self._pixmaps) > self.MAX_CACHED_PIXMAPS:
            self._pixmaps.popitem(last=False)
        self._notify_row(row, [_DECORATION])

    # -------------------------------------------------------------------------
    # Interfaz de QAbstractListModel
    # -------------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = _DISPLAY) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == _DISPLAY:
            return row["file_name"]
        if role == _DECORATION:
            return self._thumbnail_for(row)
        if role == ROLE_RATING:
            return row["rating"]
        if role == ROLE_FLAG:
            return row["flag"]
        if role == ROLE_FLAGGED:
            return row["flag"] == FLAG_PICKED
        if role == ROLE_COLOR_LABEL:
            return row["color_label"]
        if role == ROLE_MEDIA_ID:
            return row["id"]
        if role == ROLE_AVAILABILITY:
            return row.get("availability", AVAILABLE)
        if role == ROLE_QUICK_SELECTION:
            return bool(row.get(QUICK_SELECTION_FIELD, 0))
        if role == ROLE_MEDIA_TYPE:
            return row.get("media_type")
        if role == ROLE_DURATION:
            return row.get("duration")
        if role == ROLE_LIBRARY:
            return row.get("library")
        if role == ROLE_THUMBNAIL_STATUS:
            return row.get("thumbnail_status", 0)
        return None

    # -------------------------------------------------------------------------
    # Arrastrar tarjetas (solo se COPIAN sus 'id': nunca se mueve ni se borra nada)
    # -------------------------------------------------------------------------

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Las tarjetas se pueden seleccionar y arrastrar."""
        flags = super().flags(index)
        if index.isValid():
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def mimeTypes(self) -> list[str]:  # nombre de Qt
        return [MEDIA_IDS_MIME]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # nombre de Qt
        """Empaqueta los 'id' de las tarjetas arrastradas (en el orden de la cuadrícula)."""
        rows = sorted({index.row() for index in indexes if index.isValid()})
        return encode_media_ids(self._catalog_key, self.media_ids(rows))

    def supportedDragActions(self) -> Qt.DropAction:  # nombre de Qt
        return Qt.DropAction.CopyAction

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """Cambia rating, marca, etiqueta o selección rápida de UNA tarjeta."""
        if not index.isValid():
            return False
        return self.set_data_rows([index.row()], value, role)

    def set_data_rows(self, rows: Iterable[int], value: Any, role: int) -> bool:
        """Como 'setData', pero en varias filas a la vez (el campo lo decide el rol).

        Lo usa el delegado: un clic en una estrella, la marca o el círculo de una tarjeta
        que forma parte de una selección múltiple cambia TODAS las seleccionadas.
        Se guarda con una sola emisión de 'user_field_changed' (una sola escritura).
        """
        if role == ROLE_RATING:
            field, new = "rating", value
        elif role == ROLE_FLAG:
            field, new = "flag", value
        elif role == ROLE_FLAGGED:  # compatibilidad con el prototipo: bool
            field, new = "flag", FLAG_PICKED if value else FLAG_NONE
        elif role == ROLE_COLOR_LABEL:
            field, new = "color_label", value
        elif role == ROLE_QUICK_SELECTION:  # bool (o 0/1)
            field, new = QUICK_SELECTION_FIELD, 1 if value else 0
        else:
            return False
        return self.set_field(field, new, rows)

    # -------------------------------------------------------------------------
    # Edición de los datos del usuario
    # -------------------------------------------------------------------------

    def set_field(self, field: str, value: Any, rows: Iterable[int]) -> bool:
        """Cambia 'rating', 'flag', 'color_label' o 'in_quick_selection' de varias filas.

        Actualiza la lista al instante y emite 'user_field_changed' con los 'id' que
        realmente cambiaron (los que ya tenían ese valor se ignoran).

        Returns:
            False si el campo o el valor no son válidos (no se cambia nada).
        """
        if field == "rating":
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
                return False
        elif field == "flag":
            if isinstance(value, bool) or value not in (FLAG_REJECTED, FLAG_NONE, FLAG_PICKED):
                return False
        elif field == "color_label":
            if value is not None:
                value = normalize_color_label(value)  # acepta 'Azul', 'blue'...
                if value is None or not is_valid_color_label(value):
                    return False  # color desconocido: se rechaza, NO se interpreta como "sin etiqueta"
        elif field == QUICK_SELECTION_FIELD:
            if value not in (0, 1):  # True/False también valen (son 1 y 0)
                return False
            value = int(value)
        else:
            return False

        changed_ids: list[int] = []
        for row_number in rows:
            if not 0 <= row_number < len(self._rows):
                continue
            row = self._rows[row_number]
            if row.get(field) == value:
                continue
            row[field] = value
            changed_ids.append(row["id"])
            self._notify_row(row_number, _ROLES_OF_FIELD[field])

        if changed_ids:
            self.user_field_changed.emit(changed_ids, field, value)
        return True

    def forget_quick_selection(self) -> None:
        """Quita la selección rápida de todas las tarjetas cargadas.

        Lo llama el controlador DESPUÉS de vaciarla en la base de datos
        ('clear_quick_selection'): por eso no emite 'user_field_changed' (no hay nada que
        guardar). No recarga la lista: se conservan la selección y la posición.
        """
        rows = [i for i, row in enumerate(self._rows) if row.get(QUICK_SELECTION_FIELD)]
        for row in rows:
            self._rows[row][QUICK_SELECTION_FIELD] = 0
        if len(rows) > 200:
            self._notify_all([ROLE_QUICK_SELECTION])
        else:
            for row in rows:
                self._notify_row(row, [ROLE_QUICK_SELECTION])

    @property
    def thumbnail_cache(self) -> ThumbnailCache | None:
        """Caché de miniaturas del catálogo abierto (None sin catálogo)."""
        return self._cache

    def catalog_key(self) -> str:
        """Carpeta del catálogo abierto, en texto ("" sin catálogo): la que viaja al
        arrastrar tarjetas ('media_mime.MediaDrag.catalog')."""
        return self._catalog_key

    def row_of_id(self, media_id: int) -> int | None:
        """Fila de un elemento en la lista cargada (None si no está)."""
        return self._row_of_id.get(media_id)

    def media_ids(self, rows: Iterable[int]) -> list[int]:
        """'id' de los elementos de esas filas."""
        return [self._rows[r]["id"] for r in rows if 0 <= r < len(self._rows)]

    def field_values(self, field: str, rows: Iterable[int]) -> list[Any]:
        """Valor de un campo ('rating', 'flag', 'color_label', 'in_quick_selection') en esas filas."""
        return [self._rows[r].get(field) for r in rows if 0 <= r < len(self._rows)]

    # -------------------------------------------------------------------------
    # Avisos a las vistas
    # -------------------------------------------------------------------------

    def _notify_row(self, row: int, roles: list[int]) -> None:
        index = self.index(row)
        self.dataChanged.emit(index, index, roles)

    def _notify_all(self, roles: list[int]) -> None:
        if self._rows:
            self.dataChanged.emit(self.index(0), self.index(len(self._rows) - 1), roles)
