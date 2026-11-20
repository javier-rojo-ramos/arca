"""Vista «Mapa» del centro: une el mapa con la cuadrícula, la selección y el catálogo.

El mapa ('MapView', en la página 'MapPage') muestra LO MISMO que la cuadrícula: lo elegido
a la izquierda y el filtro de la barra de filtros (lo lee del modelo de la cuadrícula). Lo
pide en segundo plano ('core/catalog/map_queries.fetch_map_items') y lo pinta: las fotos
con coordenadas, como marcadores; los tracks, como líneas. Diseño en docs/MOD_TRACKS.md (§2.6).

Qué hace (decidido por el autor el 13/11/2026):
    - Solo trabaja con el mapa a la vista: si cambia lo elegido o el filtro con el mapa
      oculto, lo apunta y lo pide al volver a él.
    - Encuadre: al elegir otra cosa a la izquierda, el mapa encuadra todo lo que hay; al
      cambiar el filtro o la selección, no se mueve; al volver al mapa con lo mismo
      elegido, sigue donde estaba. Cada módulo recuerda su encuadre con lo que tenía
      elegido (15/11/2026): al arrancar o al volver de otro módulo con lo mismo, el mapa
      vuelve a él; se guarda por catálogo, al cerrar ('map_framing.py').
    - Botón «Encuadrar» (encima del zoom; 15/11/2026): lo seleccionado que sale en el
      mapa (fotos y tracks juntos); si no hay nada seleccionado, o nada de ello tiene
      ubicación, todo lo que muestra; y si no muestra nada, el encuadre de partida.
    - Chincheta de las tarjetas (15/11/2026): en la cuadrícula, solo en los módulos con
      mapa (en la tira, siempre). Al pulsarla, en la cuadrícula o en la tira, queda
      seleccionado solo ese archivo, se pasa al mapa (si no se está viendo) y se
      encuadra como con «Encuadrar». Si lo que se pinta hay que pedirlo, el encuadre
      espera a que llegue y sustituye al de todo. En un módulo sin vista individual
      (Tracks), el doble clic, Intro y «adelante» en la cuadrícula hacen lo mismo
      (19/11/2026; «atrás» vuelve a la cuadrícula).
    - Selección: la MISMA que la cuadrícula (su 'selectionModel'), en los dos sentidos.
      Clic en una foto o en un grupo: solo eso; Ctrl+clic: se añade o se quita; clic en
      el mapa vacío: nada seleccionado. Clic en un track: solo ese track. El track
      seleccionado se ve resaltado (el «activo» del mapa).
    - Track activo (paso 4.3 de docs/MOD_TRACKS.md): su recorrido COMPLETO sustituye a su
      contorno en cuanto se lee del GPX, en segundo plano ('TrackDetailController'); los
      demás tracks se ven atenuados. Si se elige FUERA del mapa (en la tira o en la
      cuadrícula), el mapa lo encuadra; si se pulsa en el propio mapa, no se mueve.
    - Doble clic en una foto: la vista individual (Esc vuelve al mapa: lo lleva el
      'CenterViewController').
    - Aviso encima del mapa: «12 fotos sin ubicación» (fotos y vídeos que no salen), o
      «Ninguno de estos archivos tiene ubicación», o «No hay archivos».
    - Capa: un desplegable en la barra inferior, a la derecha (solo con el mapa a la
      vista); la elegida se recuerda para toda la aplicación (settings.json, 'map_layer').
    - Capas: las de la aplicación y, detrás, las propias (Opciones > Mapa).
    - Colores de los tracks: los elegidos en Opciones > Tracks (o los del tema), al crear
      el mapa y al aceptar las opciones ('track_appearance.track_colors').
    - Caché de teselas: al crear el mapa (y al cambiar su tamaño máximo en Opciones), si
      pasa del tope se borran las descargadas hace más tiempo, en segundo plano.
    - Tras un cambio hecho desde el inspector (p. ej. el GPS de una foto), lo que se
      pinta se vuelve a pedir ('refresh'), sin moverse: el marcador va a su sitio nuevo.
      Con el mapa oculto, se pide igual, pero solo para la chincheta de las tarjetas de
      la cuadrícula (si la llevan); el mapa se pinta al volver a él.
    - Miniaturas de los marcadores: las de 160 px de la caché del catálogo.
    - Tira de fotos debajo del mapa ('MapFilmstrip'): el modelo y la selección de la
      cuadrícula; se muestra u oculta con su botón (barra inferior, a la derecha del todo,
      solo con el mapa) o con F9 (hasta el 15/11/2026, F6, como Lightroom); si se ve (POR MÓDULO desde el 15/11/2026:
      en Tracks empieza oculta, 'MapOptions.filmstrip_starts_visible') y su alto (común)
      se guardan (settings.json, 'map_filmstrip'). Doble clic en una tarjeta: la vista
      individual (Esc vuelve al mapa). La tarjeta actual se mantiene a la vista.
    - Perfil de elevación entre el mapa y la tira, en los módulos que lo tienen
      ('MapOptions.show_profile': Tracks): lo lleva 'TrackProfileController' (también su
      sincronización con el mapa: punto ámbar y tramo); aquí solo se le da el mapa al
      crearse y se le dice cuándo se puede ver y qué tracks hay seleccionados.

Ubicar fotos (paso 3.2; decidido por el autor el 13/11/2026; solo en los módulos cuyo
'map_options().allow_geotag' lo permite, hoy Imagen: el Catálogo solo mira):
    - Soltar tarjetas (de la tira) en el mapa las pone en ese punto; arrastrar una foto
      suelta ya ubicada la mueve. Las que ya tenían ubicación se mueven sin preguntar,
      como Lightroom; a partir de 50 fotos de golpe se pide confirmación.
    - Solo fotos y vídeos (lo que puede tener coordenadas propias); la altitud y la
      dirección no se tocan (D7).
    - Se guarda por la cola de cambios del inspector ('update_metadata_fields'): queda
      pendiente de escribir en los archivos, con la regla del GPS (D1), y al terminar el
      mapa se pone al día ('refresh'). El marcador se pinta ya en su sitio, sin esperar.

    - Botón derecho sobre una foto o un grupo: «Quitar la ubicación» (de esa foto o de
      las del grupo; a partir de 50, se pregunta antes).
    - Deshacer (Ctrl+Z, el historial de toda la aplicación, 'UndoHistory'): cada cambio
      guarda las coordenadas que tenían ('geotagging.set_media_position') y deja un paso
      que las vuelve a poner por la misma cola ('restore_media_positions').

Uso (en el controlador principal, que solo lo crea y le pasa el catálogo):
    controlador = MapController(module_host, page=..., grid=..., model=..., center_views=...,
                                layer_bar=layout_bottom_right, config=config, parent=window)
    controlador.attach(db)      # al abrir un catálogo
    controlador.detach()        # al cerrarlo
    controlador.refresh()       # tras un cambio del inspector
    controlador.restore_state(entrada)   # al abrir un catálogo (antes de 'attach')
    extra = controlador.save_state()     # al cerrarlo, con lo de los módulos
    controlador.apply_settings(claves_cambiadas)   # tras la ventana de opciones

1.12.0 Con el mapa oculto, 'refresh' pone al día la chincheta de las tarjetas de la
       cuadrícula ('_load_pins'): tras pegar unas coordenadas en el inspector no salía
       hasta pasar por el mapa o recargar la cuadrícula (el autor, 20/11/2026).
1.11.0 En un módulo sin vista individual (Tracks), doble clic, Intro y «adelante» en la
       cuadrícula hacen lo mismo que la chincheta ('CenterViewController.map_requested').
1.10.0 Cada módulo vuelve a su encuadre del mapa (al arrancar, al volver de otro módulo)
       si tiene elegido lo mismo ('map_framing.MapFraming'); se guarda por catálogo
       ('save_state' / 'restore_state'). Si se encuadra al pintar, el track elegido no
       se encuadra además.
1.9.3 La tira, con F9 (antes F6: F7 y F8 son ahora las barras laterales).
1.9.2 El icono del botón de la tira, de 'BAR_ICON_SIZE' (el común: 18 px; antes, 16).
1.9.1 Con la tira a la vista, el icono de su botón en el color de acento (el autor).
1.9.0 La chincheta de las tarjetas: en la cuadrícula de los módulos con mapa y, al
      pulsarla (cuadrícula o tira), ese archivo seleccionado, en el mapa y encuadrado.
1.8.0 El botón «Encuadrar» del mapa: lo seleccionado en la cuadrícula ('fit_preferred').
1.7.0 Los colores de los tracks elegidos en Opciones > Tracks, al crear el mapa y al
      cambiarlos ('apply_settings'); los cambios de opciones, también a la banda del perfil.
1.6.1 Paso 5.3b: el mapa, recién creado, a la banda del perfil ('attach_map'), que lo
      sincroniza con el perfil.
1.6.0 Paso 5.3a: la banda del perfil de elevación ('TrackProfileController', creado aquí);
      la tira de fotos, recordada por módulo ('visible_by_module' en 'map_filmstrip').
1.5.0 Pasos 3.3 y 3.4: «Quitar la ubicación» con el botón derecho sobre una foto o un
      grupo; cada cambio (ubicar, mover, quitar) se apunta en el historial de deshacer
      ('set_undo_history'; Ctrl+Z). Se guarda con 'geotagging.set_media_position', que
      recuerda las coordenadas de antes.
1.4.0 Paso 3.2: ubicar fotos soltándolas en el mapa y mover las ubicadas, en los módulos
      que lo permiten ('map_options().allow_geotag': Imagen); por la cola de cambios del
      inspector ('set_edit_queue'), con confirmación a partir de 50 fotos.
1.3.0 Cada vez que se pone al día, dice al modelo quién tiene coordenadas (la chincheta
      de la tira: al día tras editar el GPS o, en el paso 3.2, soltar fotos).
1.2.0 Paso 3.1: la tira de fotos (modelo y selección de la cuadrícula; botón de la barra
      inferior y F6 para mostrarla u ocultarla; si se ve y su alto, en settings.json; doble
      clic en una tarjeta, la vista individual; la tarjeta actual, siempre a la vista).
1.1.0 Paso 2.4: capas propias, tope de la caché de teselas, 'apply_settings' y 'refresh'
      (el mapa, al día tras un cambio del inspector).
1.0.0 Primera versión (docs/MOD_TRACKS.md, paso 2.3).
"""

__version__ = "1.12.0"
__all__ = ["MapController", "notice_text"]

# Librerías estándar
import threading
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QObject, QSize, Qt, QTimer
from qtpy.QtGui import QKeySequence, QShortcut
from qtpy.QtWidgets import QAbstractItemView, QBoxLayout, QComboBox, QListView, QMenu, QToolButton

# Módulos del proyecto
from config import app_paths
from config.app_constants import (
    SETTING_MAP_CACHE_MB,
    SETTING_MAP_FILMSTRIP,
    SETTING_MAP_LAYER,
    SETTING_MAP_TRACK_COLORS,
    SETTING_MAP_USER_LAYERS,
    AppIcons,
)
from controllers.app_modules.center_views import CenterView, MapOptions
from controllers.app_modules.module_host import ModuleHost
from controllers.center_view_controller import CenterViewController
from controllers.map_framing import FRAMING_STATE_KEY, MapFraming
from controllers.track_detail_controller import TrackDetailController
from controllers.track_profile_controller import TrackProfileController
from controllers.undo_history import UndoHistory, UndoStep
from core.catalog.geotagging import PositionChange, restore_media_positions, set_media_position
from core.catalog.grid_source import GridSource
from core.catalog.map_queries import LOCATABLE_MEDIA_TYPES, MapItems, fetch_map_items
from core.maps.tile_layers import all_layers, user_layers_from_settings
from core.maps.tile_store import DEFAULT_MAX_BYTES, TileStorageError, TileStore
from core.thumbnails.sizes import ThumbnailSize
from ui_helpers.helpers.track_appearance import track_colors
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_theme import BAR_ICON_SIZE, COLORS
from ui_helpers.map.map_types import (
    HitKind,
    MapHit,
    MapMarker,
    MapTrack,
    MapViewport,
    SelectionMode,
)
from ui_helpers.map.map_view import MapView
from ui_helpers.models.media_grid_model import MediaGridModel
from ui_helpers.models.media_mime import MediaDrag
from ui_helpers.models.media_roles import ROLE_MEDIA_TYPE, ROLE_THUMBNAIL_STATUS
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
# Textos del botón de la tira (con su atajo, como Lightroom)
_FILMSTRIP_SHOW = "Mostrar la tira de fotos (F9)"
_FILMSTRIP_HIDE = "Ocultar la tira de fotos (F9)"
# Medidas del botón de la tira: las de los botones de vista (ui_helpers/widgets/view_buttons.py)
_BUTTON_SIZE = 22
_ICON_SIZE = BAR_ICON_SIZE
# A partir de cuántas fotos soltadas de golpe se pide confirmación (D1; el autor, 13/11/2026)
_CONFIRM_FROM = 50
# Decimales de las coordenadas que se guardan: 6, unos 10 cm (de sobra para un clic)
_COORDINATE_DECIMALS = 6
# Textos al ubicar fotos
_CONFIRM_TITLE = "Ubicar fotos"
_CONFIRM_TEXT = "¿Ubicar estas {count} fotos en este punto?"
_CONFIRM_YES = "Ubicar"
_CONFIRM_NO = "Cancelar"
_OTHER_CATALOG = "Esas fotos son de otro catálogo: no se pueden ubicar aquí."
# Quitar la ubicación (botón derecho)
_REMOVE_ONE = "Quitar la ubicación"
_REMOVE_MANY = "Quitar la ubicación de las {count} fotos"
_REMOVE_TITLE = "Quitar la ubicación"
_REMOVE_CONFIRM = "¿Quitar la ubicación de estas {count} fotos?"
_REMOVE_YES = "Quitar"
# Lo que se deshace con Ctrl+Z («Deshecho: …»)
_UNDO_PLACE = ("ubicar una foto", "ubicar {count} fotos")
_UNDO_MOVE = ("mover una foto", "mover {count} fotos")
_UNDO_REMOVE = ("quitar la ubicación de una foto", "quitar la ubicación de {count} fotos")
# Espera tras arrastrar el separador de la tira antes de guardar su alto
_SAVE_DELAY_MS = 600

# Para comparar el origen con «ninguno todavía» (None es un valor posible de nada aquí)
_NO_SOURCE = object()


def _count_text(count: int) -> str:
    """Un número con el separador de miles en español (punto): «1.234»."""
    return f"{count:,}".replace(",", ".")


def _describe(texts: tuple[str, str], count: int) -> str:
    """El texto en singular o en plural."""
    return texts[0] if count == 1 else texts[1].format(count=_count_text(count))


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


def _located_ids(items: MapItems) -> list[int]:
    """Lo que lleva la chincheta: lo que sale en el mapa (los tracks, si tienen recorrido)."""
    return [p.media_id for p in items.points] + [t.track_id for t in items.tracks if t.segments]


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
        message_box: Any = None,
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
            message_box: Ayudante de mensajes ('MessageBoxHelper'; la confirmación al
                ubicar muchas fotos y los avisos).
            parent: Objeto padre (la ventana principal).
        """
        super().__init__(parent)
        self._host = host
        self._page = page
        self._grid = grid
        self._model = model
        self._center_views = center_views
        self._config = config
        self._message_box = message_box
        # Cola de cambios del inspector ('set_edit_queue'): por ella se guarda lo ubicado
        self._request_edit: Callable[..., None] | None = None
        # Historial de deshacer de la aplicación ('set_undo_history')
        self._undo: UndoHistory | None = None
        self._db: Any = None
        self._generation = 0  # las respuestas de una petición vieja se descartan
        # Lo mismo para lo pedido solo por la chincheta, con el mapa oculto ('_load_pins')
        self._pins_generation = 0
        self._dirty = True  # hay que volver a pedir lo que se pinta
        self._fitted_source: object = _NO_SOURCE  # el origen que se encuadró la última vez
        self._items: MapItems | None = None
        self._media_types: dict[int, str] = {}  # id -> tipo (para buscar su miniatura)
        self._track_ids: set[int] = set()
        self._track_names: dict[int, str] = {}
        # El recorrido completo del track activo (lo lee en segundo plano y lo pone)
        self._track_detail = TrackDetailController(self)
        # El track cuyo recorrido completo ya se ha pedido para lo que hay pintado (al
        # volver a pintar los tracks vuelven a su contorno: se pide otra vez)
        self._detailed_track: int | None = None
        # Lo último que se eligió pulsando EN el mapa: si el track activo sale de ahí, el
        # mapa no se mueve (ya se está viendo)
        self._map_pick: frozenset[int] = frozenset()
        # Lo pulsado con la chincheta de una tarjeta, por encuadrar en cuanto el mapa esté
        # a la vista y al día
        self._pending_fit: tuple[int, ...] = ()
        # El encuadre de cada módulo, con lo que tenía elegido: al volver a pintarlo (también
        # al arrancar) con lo mismo, el mapa vuelve a él ('map_framing.py')
        self._framing = MapFraming()
        # De qué módulo y origen es lo pintado (None = nada): solo entonces se apunta el
        # encuadre del mapa quieto
        self._painted: tuple[str, GridSource] | None = None

        # Desplegable de la capa (barra inferior, a la derecha; solo con el mapa a la vista)
        self._layer_box = QComboBox()
        self._layer_box.setObjectName("combo_map_layer")
        self._layer_box.setToolTip("Capa del mapa")
        self._layer_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # el teclado, en las fotos
        self._layer_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._layer_box.hide()
        layer_bar.addWidget(self._layer_box)
        self._layer_box.currentIndexChanged.connect(self._on_layer_chosen)

        # La banda del perfil del track activo (en Tracks; su botón, delante del de la tira)
        self._profile = TrackProfileController(page, layer_bar, config, self._track_detail, self)

        # Botón de la tira (barra inferior, a la derecha del todo; solo con el mapa) y F9
        self._filmstrip_button = QToolButton()
        self._filmstrip_button.setObjectName("btn_map_filmstrip")  # estilo en ui_theme.py
        self._filmstrip_button.setAutoRaise(True)
        self._filmstrip_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._filmstrip_button.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        self._filmstrip_button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._filmstrip_button.hide()
        self._filmstrip_button.clicked.connect(self._toggle_filmstrip)
        layer_bar.addWidget(self._filmstrip_button)
        self._filmstrip_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F9), page)
        self._filmstrip_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._filmstrip_shortcut.activated.connect(self._toggle_filmstrip)
        self._filmstrip_save_timer = QTimer(self)
        self._filmstrip_save_timer.setSingleShot(True)
        self._filmstrip_save_timer.setInterval(_SAVE_DELAY_MS)
        self._filmstrip_save_timer.timeout.connect(self._save_filmstrip)
        # La tira: lo mismo que la cuadrícula, con su selección
        page.filmstrip.attach(model, grid.selectionModel())
        page.filmstrip.doubleClicked.connect(lambda index: center_views.open_single(index.row()))
        # La chincheta de las tarjetas (cuadrícula y tira): ese archivo, en el mapa
        for delegate in (grid.itemDelegate(), page.filmstrip.itemDelegate()):
            location_clicked = getattr(delegate, "location_clicked", None)
            if location_clicked is not None:
                location_clicked.connect(self._on_location_clicked)
        # Doble clic, Intro o «adelante» en la cuadrícula de un módulo sin vista individual
        # (Tracks): ese archivo, en el mapa, como con la chincheta
        center_views.map_requested.connect(self._on_map_requested)
        page.filmstrip_resized.connect(lambda _height: self._filmstrip_save_timer.start())
        grid.selectionModel().currentChanged.connect(self._on_current_changed)
        self._restore_filmstrip()

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
        self._track_detail.attach(db)
        self._profile.reset()
        if self._shown():
            self._load()

    def set_edit_queue(self, request_edit: Callable[..., None]) -> None:
        """La cola de cambios del inspector ('InspectorController.request_edit'): por ella se
        guardan las fotos ubicadas en el mapa (avisa de los errores, escribe en los archivos
        y, al terminar, pone al día el mapa y la barra)."""
        self._request_edit = request_edit

    def set_undo_history(self, history: UndoHistory) -> None:
        """El historial de deshacer de la aplicación: cada cambio hecho en el mapa deja ahí
        un paso (Ctrl+Z)."""
        self._undo = history

    def refresh(self) -> None:
        """Vuelve a pedir lo que se pinta, sin moverse (p. ej. tras cambiar el GPS de una
        foto en el inspector). Con el mapa oculto, se pedirá al volver a él; mientras,
        se pone al día la chincheta de las tarjetas de la cuadrícula."""
        self._dirty = True
        if self._shown():
            self._load()
        else:
            self._load_pins()

    def apply_settings(self, changed: set[str]) -> None:
        """Se han cambiado opciones (ventana de opciones): capas propias, tope de la caché,
        colores de los tracks y, en la banda del perfil, cómo se ve la pendiente."""
        if SETTING_MAP_USER_LAYERS in changed and self._page.has_map():
            self._apply_layers(self._page.map_view())
        if SETTING_MAP_CACHE_MB in changed:
            self._prune_cache()
        if SETTING_MAP_TRACK_COLORS in changed and self._page.has_map():
            self._apply_track_colors(self._page.map_view())
        self._profile.apply_settings(changed)

    def save_state(self) -> dict:
        """El encuadre de cada módulo, para la entrada del catálogo en settings.json (lo
        guarda el controlador principal con lo de los módulos, al cerrar el catálogo)."""
        return {FRAMING_STATE_KEY: self._framing.to_state()}

    def restore_state(self, entry: object) -> None:
        """Recupera el encuadre de cada módulo de la entrada del catálogo (al abrirlo, antes
        de 'attach')."""
        saved = entry.get(FRAMING_STATE_KEY) if isinstance(entry, dict) else None
        self._framing = MapFraming.from_state(saved)

    def detach(self) -> None:
        """Se cierra el catálogo: se olvida todo y se vacía el mapa."""
        self._db = None
        self._generation += 1  # lo que estuviera pidiéndose ya no se pinta
        self._pins_generation += 1
        self._dirty = True
        self._fitted_source = _NO_SOURCE
        self._items = None
        self._media_types = {}
        self._track_ids = set()
        self._track_names = {}
        self._detailed_track = None
        self._pending_fit = ()
        self._painted = None
        self._framing.clear()  # ya guardado ('save_state', antes de cerrar)
        self._track_detail.detach()
        self._profile.reset()
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
        options = self._map_options()
        self._layer_box.setVisible(shown)
        self._filmstrip_button.setVisible(shown)
        self._update_grid_pins()
        # La banda del perfil, solo con el mapa a la vista en un módulo que la tiene
        self._profile.set_available(shown and options.show_profile)
        if not shown:
            return
        self._apply_module_filmstrip(options)  # cada módulo, la suya
        view = self._page.map_view()  # la primera vez, lo crea
        # Ubicar fotos, solo donde el módulo lo permite (Imagen; el Catálogo solo mira)
        view.set_drop_enabled(self._geotag_allowed())
        if self._dirty:
            self._load()  # lo pulsado con la chincheta se encuadra al llegar
        else:
            self._push_selection()  # pudo cambiar con el mapa oculto
            self._fit_pending()

    def _on_model_reset(self) -> None:
        """La cuadrícula se ha recargado (otro origen, otro filtro, otro orden...)."""
        # Las filas nuevas ya traen su chincheta: lo pedido para las de antes, fuera
        self._pins_generation += 1
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
        self._track_names = {track.track_id: track.name for track in items.tracks}
        # Los tracks se van a pintar otra vez con su contorno: el recorrido completo del
        # activo se vuelve a poner después ('_push_selection')
        self._detailed_track = None
        view.set_markers(
            [
                MapMarker(p.media_id, p.latitude, p.longitude, p.media_type, p.has_thumbnail, p.direction)
                for p in items.points
            ]
        )
        view.set_tracks([MapTrack(t.track_id, t.name, t.segments) for t in items.tracks])
        # La chincheta de las tarjetas: lo que sale en el mapa
        self._model.set_located(_located_ids(items))
        # Encuadre, antes de la selección (si se encuadra aquí, el track elegido no se
        # encuadra además):
        #   - lo pulsado con la chincheta de una tarjeta (sin animación: el mapa acaba de
        #     aparecer);
        #   - otro origen: el encuadre que recordaba el módulo con ese mismo origen (al
        #     arrancar, al volver de otro módulo) o, si no, todo;
        #   - el mismo origen (otro filtro, al volver al mapa): no se mueve
        module = self._module_key()
        framed = False
        pending, self._pending_fit = self._pending_fit, ()
        if pending and view.fit_ids(pending, animate=False):
            framed = True
        elif source != self._fitted_source:
            remembered = self._framing.view_for(module, source)
            if remembered is not None:
                view.center_on(*remembered)
            else:
                view.fit_content(animate=False)
            framed = True
        if framed:
            self._fitted_source = source
        self._painted = (module, source)
        self._push_selection(fit=not framed)
        self._page.set_notice(notice_text(self._model.rowCount(), items))

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
        view.media_dropped.connect(self._on_media_dropped)
        view.markers_moved.connect(lambda ids, lat, lon: self._place(ids, lat, lon, confirm=False))
        view.context_menu_requested.connect(self._on_context_menu)
        # Botón «Encuadrar»: lo seleccionado en la cuadrícula (también varios tracks: el
        # mapa solo conoce el activo)
        view.fit_requested.connect(lambda: view.fit_preferred(self._selected_ids()))
        view.load_failed.connect(lambda _reason: self._page.set_notice(_LOAD_FAILED))
        view.viewport_changed.connect(self._on_viewport)
        # El perfil y el mapa, sincronizados (punto ámbar y tramo; paso 5.3b)
        self._profile.attach_map(view)
        self._apply_track_colors(view)

    def _on_viewport(self, viewport: MapViewport) -> None:
        """El mapa se ha quedado quieto: su encuadre, para el módulo que se ve (solo si lo
        pintado es de ese módulo y de lo que muestra ahora la cuadrícula)."""
        if self._painted is None or not self._shown():
            return
        module, source = self._painted
        if module != self._module_key() or source != self._model.source:
            return  # se está cambiando de módulo o de origen: lo de antes no vale
        self._framing.remember(
            module, source, viewport.latitude, viewport.longitude, viewport.zoom
        )

    def _apply_track_colors(self, view: MapView) -> None:
        """Los colores de los tracks elegidos en Opciones > Tracks (o los del tema)."""
        colors = track_colors(self._config)
        view.set_track_colors(colors.track, colors.active)

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

    # -------------------------------------------------------------------------
    # La chincheta de las tarjetas
    # -------------------------------------------------------------------------

    def _update_grid_pins(self) -> None:
        """La chincheta en las tarjetas de la cuadrícula, solo si el módulo tiene mapa."""
        delegate = self._grid.itemDelegate()
        wanted = CenterView.MAP in self._host.active_views()
        if getattr(delegate, "location_pin", wanted) != wanted:
            delegate.location_pin = wanted
            self._grid.viewport().update()

    def _load_pins(self) -> None:
        """Con el mapa oculto: pide lo mismo que pintaría el mapa, pero solo para poner al
        día la chincheta de las tarjetas de la cuadrícula (p. ej. tras pegar unas
        coordenadas en el inspector). Solo si la cuadrícula la lleva; el mapa sigue
        pendiente de pintar ('_dirty') para cuando se vea."""
        if self._db is None or not getattr(self._grid.itemDelegate(), "location_pin", False):
            return
        self._pins_generation += 1
        self._db.execute_async(
            fetch_map_items,
            self._model.source,
            self._model.filter_rules,
            on_result=partial(self._on_pins, self._pins_generation),
            on_error=partial(self._on_pins_error, self._pins_generation),
        )

    def _on_pins(self, generation: int, items: MapItems) -> None:
        if self._db is None or generation != self._pins_generation:
            return  # el catálogo se cerró, la cuadrícula se recargó o ya se pidió otra vez
        self._model.set_located(_located_ids(items))

    def _on_pins_error(self, generation: int, error: Exception) -> None:
        if generation == self._pins_generation:
            logger.error(f"Mapa: no se ha podido saber qué tarjetas tienen ubicación: {error}")

    def _on_location_clicked(self, index: QModelIndex) -> None:
        """Chincheta de una tarjeta (cuadrícula o tira): queda seleccionado solo ese archivo,
        se pasa al mapa (si no se está viendo) y se encuadra como con el botón «Encuadrar»
        (decidido por el autor el 15/11/2026)."""
        if self._db is None or not index.isValid():
            return
        if CenterView.MAP not in self._host.active_views():
            return
        media_ids = self._model.media_ids([index.row()])
        if not media_ids:
            return
        self._grid.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self._pending_fit = tuple(media_ids)
        if self._shown():
            self._fit_pending()  # la tira: ya se ve el mapa
        else:
            self._host.set_view(CenterView.MAP)  # al verse, '_on_view_changed'

    def _on_map_requested(self, row: int) -> None:
        """Doble clic, Intro o «adelante» en la cuadrícula de un módulo sin vista individual
        pero con mapa (Tracks; decidido por el autor el 19/11/2026): lo mismo que la
        chincheta de esa tarjeta. «Atrás» (o G) vuelve a la cuadrícula."""
        self._on_location_clicked(self._model.index(row, 0))

    def _fit_pending(self) -> None:
        """Encuadra lo pulsado con la chincheta, como el botón «Encuadrar» (animado)."""
        pending, self._pending_fit = self._pending_fit, ()
        if pending and self._page.has_map():
            self._page.map_view().fit_preferred(pending)

    # -------------------------------------------------------------------------
    # Tira de fotos
    # -------------------------------------------------------------------------

    def _filmstrip_setting(self) -> dict:
        """Lo guardado de la tira (una copia; vacío si no hay nada o no se entiende)."""
        saved = self._config.get(SETTING_MAP_FILMSTRIP)
        return dict(saved) if isinstance(saved, dict) else {}

    def _module_key(self) -> str:
        """La clave del módulo activo ('catalog', 'image', 'tracks'...; "" si ninguno)."""
        return getattr(getattr(self._host, "active_module", None), "key", "") or ""

    def _restore_filmstrip(self) -> None:
        """Su alto, como se dejó (settings.json); si se ve, lo decide cada módulo."""
        height = self._filmstrip_setting().get("height")
        if isinstance(height, int) and not isinstance(height, bool):
            self._page.set_filmstrip_height(height)
        self._apply_module_filmstrip(self._map_options())

    def _module_filmstrip_visible(self, options: MapOptions) -> bool:
        """Si la tira se ve en el módulo activo: la que guardó al mostrarla u ocultarla;
        si no la tiene, la de partida (la de antes, común, salvo en los módulos donde
        empieza oculta, como Tracks)."""
        saved = self._filmstrip_setting()
        by_module = saved.get("visible_by_module")
        if isinstance(by_module, dict) and isinstance(by_module.get(self._module_key()), bool):
            return by_module[self._module_key()]
        if not options.filmstrip_starts_visible:
            return False
        common = saved.get("visible", True)
        return common if isinstance(common, bool) else True

    def _apply_module_filmstrip(self, options: MapOptions) -> None:
        """La tira, como la tiene el módulo activo."""
        self._page.set_filmstrip_visible(self._module_filmstrip_visible(options))
        self._update_filmstrip_button()

    def _toggle_filmstrip(self) -> None:
        """El botón o F9: muestra u oculta la tira (solo con el mapa a la vista)."""
        if not self._shown():
            return
        visible = not self._page.filmstrip_visible()
        self._page.set_filmstrip_visible(visible)
        if visible:
            self._scroll_filmstrip_to(self._grid.currentIndex())
        self._update_filmstrip_button()
        self._save_filmstrip()

    def _update_filmstrip_button(self) -> None:
        visible = self._page.filmstrip_visible()
        # A la vista, el icono en el acento (como el del perfil); oculta, el de siempre
        icon = AppIcons.FILMSTRIP_HIDE if visible else AppIcons.FILMSTRIP_SHOW
        self._filmstrip_button.setIcon(tinted_icon(icon, COLORS.accent if visible else None))
        self._filmstrip_button.setToolTip(_FILMSTRIP_HIDE if visible else _FILMSTRIP_SHOW)

    def _save_filmstrip(self) -> None:
        """Guarda el alto (común) y si se ve en el módulo activo. Lo demás que hubiera (la
        de partida de antes, la de otros módulos) se conserva."""
        saved = self._filmstrip_setting()
        by_module = saved.get("visible_by_module")
        by_module = dict(by_module) if isinstance(by_module, dict) else {}
        if self._module_key():
            by_module[self._module_key()] = self._page.filmstrip_visible()
        saved.update({"height": self._page.filmstrip_height(), "visible_by_module": by_module})
        self._config.set(SETTING_MAP_FILMSTRIP, saved)

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """La tarjeta actual (elegida en el mapa, con las flechas...), a la vista en la tira."""
        if self._shown():
            self._scroll_filmstrip_to(current)

    def _scroll_filmstrip_to(self, index: QModelIndex) -> None:
        if index.isValid() and self._page.filmstrip_visible():
            self._page.filmstrip.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

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

    def _push_selection(self, fit: bool = True) -> None:
        """La selección de la cuadrícula, al mapa (y el track seleccionado, resaltado).

        Con 'fit' False, el track elegido no se encuadra (el mapa ya se ha encuadrado al
        pintar: '_on_items')."""
        if not self._page.has_map() or not self._shown():
            return
        ids = self._selected_ids()
        view = self._page.map_view()
        view.set_selected_ids(ids)
        tracks = [i for i in ids if i in self._track_ids]
        # El perfil, antes que el mapa: si el track está en la memoria, llega al momento
        self._profile.show_tracks(tracks)
        active = tracks[0] if tracks else None
        changed = active != view.active_track()
        view.set_active_track(active)
        picked, self._map_pick = self._map_pick, frozenset()
        if active is None:
            self._detailed_track = None
            self._track_detail.show(view, None)
            return
        # Elegido fuera del mapa (la tira, la cuadrícula): se encuadra. Pulsado en el
        # mapa, ya se está viendo: no se mueve
        if fit and changed and active not in picked:
            view.fit_track(active)
        # Su recorrido completo, en lugar del contorno (llega en segundo plano)
        if active != self._detailed_track:
            self._detailed_track = active
            self._track_detail.show(view, active, self._track_names.get(active, ""))

    def _on_selection_requested(self, media_ids: list[int], mode: SelectionMode) -> None:
        self._select_ids(media_ids, mode)

    def _select_ids(self, media_ids: list[int], mode: SelectionMode) -> None:
        """Lo pulsado en el mapa pasa a ser la selección de la cuadrícula."""
        self._map_pick = frozenset(media_ids)  # viene del mapa: no hará falta encuadrarlo
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

    # -------------------------------------------------------------------------
    # Ubicar fotos: soltarlas en el mapa o mover las ya ubicadas (paso 3.2)
    # -------------------------------------------------------------------------

    def _map_options(self) -> MapOptions:
        """Lo que permite el mapa del módulo activo (ubicar fotos, el perfil...)."""
        module = getattr(self._host, "active_module", None)
        return module.map_options() if hasattr(module, "map_options") else MapOptions()

    def _geotag_allowed(self) -> bool:
        """True si el módulo activo deja ubicar fotos en su mapa ('MapOptions')."""
        return self._map_options().allow_geotag

    def _on_media_dropped(self, drag: MediaDrag, latitude: float, longitude: float) -> None:
        """Tarjetas soltadas en el mapa: a ese punto (si son de este catálogo)."""
        if drag.catalog != self._model.catalog_key():
            # P. ej. tarjetas arrastradas desde otra ventana con otro catálogo
            if self._message_box is not None:
                self._message_box.warning(_OTHER_CATALOG)
            return
        self._place(list(drag.ids), latitude, longitude, confirm=True)

    def _place(
        self, media_ids: Sequence[int], latitude: float, longitude: float, *, confirm: bool
    ) -> None:
        """Pone unas fotos en un punto: se guarda por la cola de cambios del inspector.

        Solo fotos y vídeos de la lista que se ve; la altitud y la dirección no cambian.
        Con 'confirm', a partir de '_CONFIRM_FROM' fotos se pregunta antes.
        """
        if self._db is None or self._request_edit is None or not self._geotag_allowed():
            return
        placeable: list[tuple[int, str, bool]] = []  # (id, tipo, miniatura lista)
        for media_id in dict.fromkeys(media_ids):
            row = self._model.row_of_id(media_id)
            if row is None:
                continue
            index = self._model.index(row, 0)
            media_type = index.data(ROLE_MEDIA_TYPE)
            if media_type in LOCATABLE_MEDIA_TYPES:
                placeable.append((media_id, media_type, index.data(ROLE_THUMBNAIL_STATUS) == 1))
        if not placeable:
            return
        if confirm and len(placeable) >= _CONFIRM_FROM and self._message_box is not None:
            answer = self._message_box.question(
                _CONFIRM_TEXT.format(count=_count_text(len(placeable))),
                _CONFIRM_TITLE,
                buttons=[_CONFIRM_YES, _CONFIRM_NO],
            )
            if answer != _CONFIRM_YES:
                return
        latitude = round(latitude, _COORDINATE_DECIMALS)
        longitude = round(longitude, _COORDINATE_DECIMALS)
        # El marcador, ya en su sitio (el mapa se pone al día al guardarse: 'refresh')
        if self._page.has_map():
            for media_id, media_type, _thumb in placeable:
                self._media_types[media_id] = media_type
            self._page.map_view().update_markers(
                [MapMarker(i, latitude, longitude, kind, thumb) for i, kind, thumb in placeable]
            )
        ids = [media_id for media_id, _kind, _thumb in placeable]
        description = _describe(_UNDO_PLACE if confirm else _UNDO_MOVE, len(ids))
        self._request_edit(
            set_media_position,
            (ids, latitude, longitude),
            partial(self._remember, description),
        )

    def _on_context_menu(self, hit: MapHit, point: object) -> None:
        """Botón derecho sobre una foto o un grupo: «Quitar la ubicación» (donde se ubican
        fotos: Imagen)."""
        if not self._geotag_allowed() or hit.kind not in (HitKind.MARKER, HitKind.CLUSTER):
            return
        ids = list(hit.media_ids)
        if not ids:
            return
        menu = QMenu(self._page)
        text = _REMOVE_ONE if len(ids) == 1 else _REMOVE_MANY.format(count=_count_text(len(ids)))
        menu.addAction(text, lambda: self._remove_location(ids))
        menu.exec(point)
        menu.deleteLater()

    def _remove_location(self, media_ids: Sequence[int]) -> None:
        """Quita la ubicación de unas fotos (a partir de 50, se pregunta antes)."""
        if self._db is None or self._request_edit is None or not media_ids:
            return
        ids = list(dict.fromkeys(media_ids))
        if len(ids) >= _CONFIRM_FROM and self._message_box is not None:
            answer = self._message_box.question(
                _REMOVE_CONFIRM.format(count=_count_text(len(ids))),
                _REMOVE_TITLE,
                buttons=[_REMOVE_YES, _CONFIRM_NO],
            )
            if answer != _REMOVE_YES:
                return
        if self._page.has_map():
            self._page.map_view().remove_markers(ids)  # ya fuera (el mapa se pone al día)
        self._request_edit(
            set_media_position,
            (ids, None, None),
            partial(self._remember, _describe(_UNDO_REMOVE, len(ids))),
        )

    def _remember(self, description: str, change: object) -> None:
        """Un cambio guardado: se apunta en el historial para poder deshacerlo."""
        if self._undo is None or not isinstance(change, PositionChange) or not change.count:
            return
        previous = dict(change.previous)
        self._undo.push(UndoStep(description, partial(self._restore, previous)))

    def _restore(self, previous: dict) -> None:
        """Deshacer: cada foto vuelve a sus coordenadas de antes (por la misma cola)."""
        if self._db is not None and self._request_edit is not None:
            self._request_edit(restore_media_positions, (previous,))

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
