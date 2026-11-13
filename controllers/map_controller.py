"""Vista «Mapa» del centro: une el mapa con la cuadrícula, la selección y el catálogo.

El mapa ('MapView', en la página 'MapPage') muestra LO MISMO que la cuadrícula: lo elegido
a la izquierda y el filtro de la barra de filtros (lo lee del modelo de la cuadrícula). Lo
pide en segundo plano ('core/catalog/map_queries.fetch_map_items') y lo pinta: las fotos
con coordenadas, como marcadores; los tracks, como líneas. Diseño en docs/MAPA.md (§2.6).

Qué hace (decidido por el autor el 13/11/2026):
    - Solo trabaja con el mapa a la vista: si cambia lo elegido o el filtro con el mapa
      oculto, lo apunta y lo pide al volver a él.
    - Encuadre: al elegir otra cosa a la izquierda, el mapa encuadra todo lo que hay; al
      cambiar el filtro o la selección, no se mueve; al volver al mapa con lo mismo
      elegido, sigue donde estaba.
    - Selección: la MISMA que la cuadrícula (su 'selectionModel'), en los dos sentidos.
      Clic en una foto o en un grupo: solo eso; Ctrl+clic: se añade o se quita; clic en
      el mapa vacío: nada seleccionado. Clic en un track: solo ese track. El track
      seleccionado se ve resaltado (el «activo» del mapa).
    - Doble clic en una foto: la vista individual (Esc vuelve al mapa: lo lleva el
      'CenterViewController').
    - Aviso encima del mapa: «12 fotos sin ubicación» (fotos y vídeos que no salen), o
      «Ninguno de estos archivos tiene ubicación», o «No hay archivos».
    - Capa: un desplegable en la barra inferior, a la derecha (solo con el mapa a la
      vista); la elegida se recuerda para toda la aplicación (settings.json, 'map_layer').
    - Capas: las de la aplicación y, detrás, las propias (Opciones > Mapa).
    - Caché de teselas: al crear el mapa (y al cambiar su tamaño máximo en Opciones), si
      pasa del tope se borran las descargadas hace más tiempo, en segundo plano.
    - Tras un cambio hecho desde el inspector (p. ej. el GPS de una foto), lo que se
      pinta se vuelve a pedir ('refresh'), sin moverse: el marcador va a su sitio nuevo.
    - Miniaturas de los marcadores: las de 160 px de la caché del catálogo.

Lo que TODAVÍA NO hace: soltar fotos ni moverlas (el Catálogo solo mira; llega con el
módulo Imagen, fase 3 de docs/MAPA.md) ni guardar el encuadre al cerrar.

Uso (en el controlador principal, que solo lo crea y le pasa el catálogo):
    controlador = MapController(module_host, page=..., grid=..., model=..., center_views=...,
                                layer_bar=layout_bottom_right, config=config, parent=window)
    controlador.attach(db)      # al abrir un catálogo
    controlador.detach()        # al cerrarlo
    controlador.refresh()       # tras un cambio del inspector
    controlador.apply_settings(claves_cambiadas)   # tras la ventana de opciones

1.1.0 Paso 2.4: capas propias, tope de la caché de teselas, 'apply_settings' y 'refresh'
      (el mapa, al día tras un cambio del inspector).
1.0.0 Primera versión (docs/MAPA.md, paso 2.3).
"""

__version__ = "1.1.0"
__all__ = ["MapController", "notice_text"]

# Librerías estándar
import threading
from functools import partial
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QItemSelection, QItemSelectionModel, QObject, Qt, QTimer
from qtpy.QtWidgets import QBoxLayout, QComboBox, QListView

# Módulos del proyecto
from config import app_paths
from config.app_constants import SETTING_MAP_CACHE_MB, SETTING_MAP_LAYER, SETTING_MAP_USER_LAYERS
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.module_host import ModuleHost
from controllers.center_view_controller import CenterViewController
from core.catalog.grid_source import GridSource
from core.catalog.map_queries import MapItems, fetch_map_items
from core.maps.tile_layers import all_layers, user_layers_from_settings
from core.maps.tile_store import DEFAULT_MAX_BYTES, TileStorageError, TileStore
from core.thumbnails.sizes import ThumbnailSize
from ui_helpers.map.map_types import MapMarker, MapTrack, SelectionMode
from ui_helpers.map.map_view import MapView
from ui_helpers.models.media_grid_model import MediaGridModel
from ui_helpers.widgets.map_page import MapPage

# Espera tras un cambio de selección antes de pasarlo al mapa (varios cambios seguidos,
# p. ej. con las flechas en la cuadrícula, se pasan de una vez)
_SELECTION_DELAY_MS = 40

# Textos del aviso de encima del mapa (decididos por el autor el 13/11/2026)
_NO_FILES = "No hay archivos"
_NOTHING_LOCATED = "Ninguno de estos archivos tiene ubicación"
_UNLOCATED_ONE = "1 foto sin ubicación"
_UNLOCATED_MANY = "{count} fotos sin ubicación"
_LOAD_FAILED = "No se ha podido cargar el mapa"

# Para comparar el origen con «ninguno todavía» (None es un valor posible de nada aquí)
_NO_SOURCE = object()


def notice_text(rows: int, items: MapItems) -> str:
    """El aviso de encima del mapa para lo que se ve ("" = ninguno).

    Args:
        rows: Archivos que muestra la cuadrícula (lo elegido, con el filtro).
        items: Lo que se pinta en el mapa.
    """
    if rows == 0:
        return _NO_FILES
    if not items.points and not any(track.segments for track in items.tracks):
        return _NOTHING_LOCATED
    if items.unlocated == 1:
        return _UNLOCATED_ONE
    if items.unlocated > 1:
        # Con el separador de miles en español (punto): «1.234 fotos»
        return _UNLOCATED_MANY.format(count=f"{items.unlocated:,}".replace(",", "."))
    return ""


class MapController(QObject):
    """Une el mapa con la cuadrícula, su selección y el catálogo (ver el docstring del archivo)."""

    def __init__(
        self,
        host: ModuleHost,
        *,
        page: MapPage,
        grid: QListView,
        model: MediaGridModel,
        center_views: CenterViewController,
        layer_bar: QBoxLayout,
        config: Any,
        parent: QObject | None = None,
    ) -> None:
        """
        Args:
            host: Coordinador de los módulos (qué vista se ve).
            page: La página del mapa (en la pila del centro).
            grid: La cuadrícula (su selección es la del mapa).
            model: El modelo de la cuadrícula (lo elegido, el filtro y las miniaturas).
            center_views: Para abrir la vista individual con un doble clic.
            layer_bar: Layout de la barra inferior donde va el desplegable de la capa.
            config: Configuración de la aplicación (la capa elegida).
            parent: Objeto padre (la ventana principal).
        """
        super().__init__(parent)
        self._host = host
        self._page = page
        self._grid = grid
        self._model = model
        self._center_views = center_views
        self._config = config
        self._db: Any = None
        self._generation = 0  # las respuestas de una petición vieja se descartan
        self._dirty = True  # hay que volver a pedir lo que se pinta
        self._fitted_source: object = _NO_SOURCE  # el origen que se encuadró la última vez
        self._items: MapItems | None = None
        self._media_types: dict[int, str] = {}  # id -> tipo (para buscar su miniatura)
        self._track_ids: set[int] = set()

        # Desplegable de la capa (barra inferior, a la derecha; solo con el mapa a la vista)
        self._layer_box = QComboBox()
        self._layer_box.setObjectName("combo_map_layer")
        self._layer_box.setToolTip("Capa del mapa")
        self._layer_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # el teclado, en las fotos
        self._layer_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._layer_box.hide()
        layer_bar.addWidget(self._layer_box)
        self._layer_box.currentIndexChanged.connect(self._on_layer_chosen)

        self._selection_timer = QTimer(self)
        self._selection_timer.setSingleShot(True)
        self._selection_timer.setInterval(_SELECTION_DELAY_MS)
        self._selection_timer.timeout.connect(self._push_selection)

        host.view_changed.connect(self._on_view_changed)
        model.modelReset.connect(self._on_model_reset)
        grid.selectionModel().selectionChanged.connect(self._on_grid_selection_changed)
        page.map_created.connect(self._on_map_created)
        self._on_view_changed()  # el módulo inicial ya está activo

    # -------------------------------------------------------------------------
    # Catálogo
    # -------------------------------------------------------------------------

    def attach(self, db: Any) -> None:
        """Se ha abierto un catálogo."""
        self._db = db
        self._dirty = True
        self._fitted_source = _NO_SOURCE
        if self._shown():
            self._load()

    def refresh(self) -> None:
        """Vuelve a pedir lo que se pinta, sin moverse (p. ej. tras cambiar el GPS de una
        foto en el inspector). Con el mapa oculto, se pedirá al volver a él."""
        self._dirty = True
        if self._shown():
            self._load()

    def apply_settings(self, changed: set[str]) -> None:
        """Se han cambiado opciones (ventana de opciones): capas propias y tope de la caché."""
        if SETTING_MAP_USER_LAYERS in changed and self._page.has_map():
            self._apply_layers(self._page.map_view())
        if SETTING_MAP_CACHE_MB in changed:
            self._prune_cache()

    def detach(self) -> None:
        """Se cierra el catálogo: se olvida todo y se vacía el mapa."""
        self._db = None
        self._generation += 1  # lo que estuviera pidiéndose ya no se pinta
        self._dirty = True
        self._fitted_source = _NO_SOURCE
        self._items = None
        self._media_types = {}
        self._track_ids = set()
        if self._page.has_map():
            self._page.map_view().clear()
        self._page.set_notice("")

    # -------------------------------------------------------------------------
    # Vista a la vista
    # -------------------------------------------------------------------------

    def _shown(self) -> bool:
        return self._host.active_view == CenterView.MAP

    def _on_view_changed(self, _view: object = None) -> None:
        """Otra vista u otro módulo: con el mapa a la vista, se pone al día."""
        shown = self._shown()
        self._layer_box.setVisible(shown)
        if not shown:
            return
        self._page.map_view()  # la primera vez, lo crea
        if self._dirty:
            self._load()
        else:
            self._push_selection()  # pudo cambiar con el mapa oculto

    def _on_model_reset(self) -> None:
        """La cuadrícula se ha recargado (otro origen, otro filtro, otro orden...)."""
        self._dirty = True
        if self._shown():
            self._load()

    # -------------------------------------------------------------------------
    # Lo que se pinta
    # -------------------------------------------------------------------------

    def _load(self) -> None:
        """Pide en segundo plano lo que hay que pintar (lo mismo que la cuadrícula)."""
        if self._db is None:
            return
        self._dirty = False
        self._generation += 1
        source = self._model.source
        self._db.execute_async(
            fetch_map_items,
            source,
            self._model.filter_rules,
            on_result=partial(self._on_items, self._generation, source),
            on_error=partial(self._on_error, self._generation),
        )

    def _on_items(self, generation: int, source: GridSource, items: MapItems) -> None:
        if self._db is None or generation != self._generation:
            return  # el catálogo se cerró o ya se pidió otra cosa
        view = self._page.map_view()
        self._items = items
        self._media_types = {point.media_id: point.media_type for point in items.points}
        self._track_ids = {track.track_id for track in items.tracks}
        view.set_markers(
            [
                MapMarker(p.media_id, p.latitude, p.longitude, p.media_type, p.has_thumbnail, p.direction)
                for p in items.points
            ]
        )
        view.set_tracks([MapTrack(t.track_id, t.name, t.segments) for t in items.tracks])
        self._push_selection()
        self._page.set_notice(notice_text(self._model.rowCount(), items))
        # Encuadre: solo al elegir otra cosa a la izquierda (no con el filtro ni al volver)
        if source != self._fitted_source:
            self._fitted_source = source
            view.fit_content(animate=False)

    def _on_error(self, generation: int, error: Exception) -> None:
        if generation == self._generation:
            logger.error(f"Mapa: no se ha podido leer lo que se pinta: {error}")

    def _thumbnail(self, media_id: int) -> Path | None:
        """La miniatura de 160 px de un marcador (None si no tiene)."""
        cache = self._model.thumbnail_cache
        media_type = self._media_types.get(media_id)
        if cache is None or media_type is None:
            return None
        return cache.resolve(media_type, media_id, ThumbnailSize.THUMBNAIL)

    # -------------------------------------------------------------------------
    # El mapa, recién creado: capas y avisos
    # -------------------------------------------------------------------------

    def _on_map_created(self, view: MapView) -> None:
        view.set_thumbnail_provider(self._thumbnail)
        view.layer_changed.connect(self._on_layer_changed)
        self._apply_layers(view)
        saved = self._config.get(SETTING_MAP_LAYER)
        if isinstance(saved, str):
            view.set_base_layer(saved)  # si ya no existe, se queda la que había
        self._prune_cache()
        view.selection_requested.connect(self._on_selection_requested)
        view.track_clicked.connect(lambda track_id: self._select_ids([track_id], SelectionMode.REPLACE))
        view.marker_activated.connect(self._on_marker_activated)
        view.load_failed.connect(lambda _reason: self._page.set_notice(_LOAD_FAILED))

    def _apply_layers(self, view: MapView) -> None:
        """Las capas de la aplicación y las propias, en el mapa y en el desplegable. Si la
        que se veía ya no está (una propia quitada), el mapa pasa a la primera."""
        user = user_layers_from_settings(self._config.get(SETTING_MAP_USER_LAYERS))
        view.set_layers(all_layers(user))
        self._layer_box.blockSignals(True)
        try:
            self._layer_box.clear()
            for layer in view.layers():
                self._layer_box.addItem(layer.name, layer.key)
            self._layer_box.setCurrentIndex(max(0, self._layer_box.findData(view.base_layer())))
        finally:
            self._layer_box.blockSignals(False)

    def _prune_cache(self) -> None:
        """Si la caché de teselas pasa del tope, borra las más antiguas (en otro hilo:
        recorre la carpeta entera)."""
        megabytes = self._config.get(SETTING_MAP_CACHE_MB)
        valid = isinstance(megabytes, int) and not isinstance(megabytes, bool) and megabytes > 0
        store = TileStore(
            app_paths.TILE_CACHE_DIR,
            max_bytes=megabytes * 1024 * 1024 if valid else DEFAULT_MAX_BYTES,
        )
        threading.Thread(target=_prune_quietly, args=(store,), daemon=True).start()

    def _on_layer_chosen(self, _index: int) -> None:
        key = self._layer_box.currentData()
        if isinstance(key, str) and self._page.has_map():
            self._page.map_view().set_base_layer(key)

    def _on_layer_changed(self, key: str) -> None:
        self._config.set(SETTING_MAP_LAYER, key)
        index = self._layer_box.findData(key)
        if index >= 0 and index != self._layer_box.currentIndex():
            self._layer_box.blockSignals(True)
            self._layer_box.setCurrentIndex(index)
            self._layer_box.blockSignals(False)

    # -------------------------------------------------------------------------
    # Selección: la de la cuadrícula, en los dos sentidos
    # -------------------------------------------------------------------------

    def _on_grid_selection_changed(self, *_args: object) -> None:
        if self._shown():
            self._selection_timer.start()

    def _selected_ids(self) -> list[int]:
        """Los 'id' seleccionados en la cuadrícula (por tramos: rápido con un Ctrl+A)."""
        spans = self._grid.selectionModel().selection()
        rows = [row for span in spans for row in range(span.top(), span.bottom() + 1)]
        return self._model.media_ids(rows)

    def _push_selection(self) -> None:
        """La selección de la cuadrícula, al mapa (y el track seleccionado, resaltado)."""
        if not self._page.has_map() or not self._shown():
            return
        ids = self._selected_ids()
        view = self._page.map_view()
        view.set_selected_ids(ids)
        view.set_active_track(next((i for i in ids if i in self._track_ids), None))

    def _on_selection_requested(self, media_ids: list[int], mode: SelectionMode) -> None:
        self._select_ids(media_ids, mode)

    def _select_ids(self, media_ids: list[int], mode: SelectionMode) -> None:
        """Lo pulsado en el mapa pasa a ser la selección de la cuadrícula."""
        selection_model = self._grid.selectionModel()
        rows = sorted({row for row in map(self._model.row_of_id, media_ids) if row is not None})
        if not rows:
            if mode is SelectionMode.REPLACE and not media_ids:
                selection_model.clearSelection()  # clic en el mapa vacío
            return
        selection = QItemSelection()
        start = end = rows[0]
        for row in rows[1:]:
            if row != end + 1:  # fin de un tramo seguido
                selection.select(self._model.index(start, 0), self._model.index(end, 0))
                start = row
            end = row
        selection.select(self._model.index(start, 0), self._model.index(end, 0))
        flags = QItemSelectionModel.SelectionFlag
        if mode is SelectionMode.TOGGLE:
            selection_model.select(selection, flags.Toggle)
        else:
            selection_model.select(selection, flags.ClearAndSelect)
            selection_model.setCurrentIndex(self._model.index(rows[0], 0), flags.NoUpdate)

    def _on_marker_activated(self, media_id: int) -> None:
        """Doble clic en una foto: la vista individual (Esc vuelve al mapa)."""
        row = self._model.row_of_id(media_id)
        if row is not None:
            self._center_views.open_single(row)


def _prune_quietly(store: TileStore) -> None:
    """Limpia la caché de teselas; lo que haga (o por qué no puede), solo al registro."""
    try:
        result = store.prune()
    except (OSError, TileStorageError) as error:
        logger.warning(f"Mapa: no se ha podido limpiar la caché de teselas: {error}")
        return
    if result.files_removed:
        logger.info(
            f"Mapa: caché de teselas limpiada ({result.files_removed} teselas, "
            f"{result.bytes_removed // (1024 * 1024)} MB)."
        )
