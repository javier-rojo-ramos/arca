# Librerías estándar
import threading
import time
from collections.abc import Callable
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import (
    QByteArray,
    QEvent,
    QPoint,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from qtpy.QtGui import (
    QAction,
    QCloseEvent,
    QIcon,
    QMoveEvent,
    QShowEvent,
)
from qtpy.QtWidgets import QAbstractItemView, QListView, QMainWindow, QToolButton

# Módulos del proyecto
from config import app_paths
from config.app_config import config
from config.app_constants import (
    SETTING_LAST_ADD_FOLDER_PARENT,
    SETTING_MAIN_SPLITTER_STATE,
    SETTING_WRITE_USER_DATA_TO_FILES,
    SIDEBAR_CATALOG_DEFAULT_WIDTH,
    SIDEBAR_METADATA_DEFAULT_WIDTH,
    THUMBNAIL_SIZE_DEFAULT,
    THUMBNAIL_SIZE_MAX,
    THUMBNAIL_SIZE_MIN,
    AppIcons,
)
from controllers.app_modules.base import ModuleContext
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.module_host import ModuleHost
from controllers.app_modules.registry import create_modules
from controllers.center_view_controller import CenterViewController
from controllers.folder_actions import FolderActions
from controllers.inspector_controller import InspectorController
from core.catalog.availability import AvailabilityCheck, check_availability
from core.catalog.catalog_builder import CatalogBuilder, CatalogError
from core.catalog.catalog_opener import open_catalog
from core.catalog.folder_importer import AddFolderProgress, AddFolderResult, add_folder
from core.catalog.folder_scanner import ScanError
from core.catalog.grid_source import ALL_ITEMS, SourceKind
from core.catalog.libraries import (
    FOLDER_AUTO,
    classify_pending_videos,
    folder_content_for,
    set_library,
)
from core.catalog.media_queries import (
    clear_quick_selection,
    set_quick_selection,
    update_user_field,
)
from core.catalog.media_removal import RemovalPlan, plan_removal, remove_media_items
from core.catalog.missing_items import (
    RemovedItems,
    count_missing_items,
    remove_missing_items,
)
from core.catalog.storage_locations import StorageLocationError, refresh_location_status
from core.database.db_manager import CatalogDatabaseManager
from core.jobs.progress import JobProgress
from core.metadata.processor import process_pending_metadata
from core.thumbnails.job import generate_pending_thumbnails, invalidate_thumbnails
from core.userdata.sync import count_pending_user_data, write_pending_user_data
from core.workers.job_manager import JobManager

# UI generada, helpers, mixins
from ui.main_window import Ui_MainWindow
from ui_helpers.delegates.thumbnails_delegate import ThumbnailsDelegate
from ui_helpers.dialogs.folder_content_dialog import FolderContentDialog
from ui_helpers.dialogs.remove_dialog import RemoveDialog
from ui_helpers.dialogs.settings_dialog import SettingsDialog
from ui_helpers.helpers.grid_actions import GridActions
from ui_helpers.helpers.mode_toolbar import toolbar_accent_color
from ui_helpers.helpers.ui_file_dialogs import select_folder
from ui_helpers.helpers.ui_file_manager import (
    FILE_MANAGER_NAME,
    move_to_trash,
    reveal_in_file_manager,
)
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar
from ui_helpers.helpers.ui_theme import TOOLBAR_MARGIN
from ui_helpers.inspector.inspector_panel import InspectorPanel
from ui_helpers.mixins.window_snap import WindowSnapMixin
from ui_helpers.models.media_grid_model import QUICK_SELECTION_FIELD, MediaGridModel
from ui_helpers.widgets.job_progress_widget import JobProgressWidget

# Nombres de los trabajos en segundo plano y texto con el que se muestran
JOB_METADATA = "metadata"
JOB_THUMBNAILS = "thumbnails"
JOB_USERDATA = "userdata"
JOB_REMOVE = "remove"
JOB_TITLES: dict[str, str] = {
    JOB_METADATA: "Leyendo metadatos",
    JOB_THUMBNAILS: "Generando miniaturas",
    JOB_USERDATA: "Guardando en los archivos",
    JOB_REMOVE: "Eliminando",
}

# Archivos que, como mucho, se enumeran en el aviso de los que no se pudieron eliminar
REMOVE_FAILED_LIST_MAX = 10

# Segundos que se espera tras el último cambio del usuario (estrellas, marca, color) antes
# de escribirlo en los archivos: así una ráfaga de clics se escribe de una vez
USERDATA_WRITE_DELAY_MS = 2000

# Por debajo de estos elementos, la escritura en los archivos y la eliminación no muestran
# barra de progreso (lo normal es tocar uno o pocos archivos en un instante)
USERDATA_PROGRESS_MIN_ITEMS = 20

# Cada cuánto se comprueba, con el catálogo abierto, si se ha desconectado un disco o si
# falta algún archivo de los que se ven (ver core/catalog/availability.py). También se
# comprueba al volver a la ventana (p. ej. después de borrar algo en el Explorador)
AVAILABILITY_CHECK_MS = 5000

# Máximo de tarjetas visibles que se comprueban cada vez (con miniaturas pequeñas y una
# pantalla grande caben muchas; más allá de esto no aporta)
AVAILABILITY_MAX_VISIBLE = 400

# Tras un cambio del usuario (estrellas, marca, color), los contadores de la barra lateral
# (colecciones Clasificación, Etiqueta...) se actualizan pasado este tiempo sin más cambios:
# así una ráfaga de teclas ('1', '2', '3'...) se cuenta una sola vez
SIDEBAR_REFRESH_DELAY_MS = 400

# Al abrir un catálogo con al menos estos elementos pendientes de escribir (p. ej. la
# primera vez tras actualizar la aplicación), se pregunta antes de modificar los archivos
USERDATA_CONFIRM_MIN_ITEMS = 100


class MainWindowController(QMainWindow, Ui_MainWindow, WindowSnapMixin):
    """Controlador principal de la ventana de Arca Media."""

    # Avance de 'add_folder'. Se emite desde un hilo secundario (por eso es una
    # señal): Qt la entrega en el hilo principal, donde sí se puede tocar la interfaz.
    scan_progress = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        WindowSnapMixin.__init__(self)
        self.setupUi(self)

        self.message_box = MessageBoxHelper(self)
        self.config = config

        # --- Estado del Mosaico de Miniaturas ---
        # El modelo lee la lista de la base de datos del catálogo y las miniaturas de su caché
        self.mosaico_model = MediaGridModel(self)
        self.mosaico_delegate = ThumbnailsDelegate(self)
        # Instante (time.monotonic) del último refresco de miniaturas durante su generación
        self._last_thumb_refresh = 0.0

        # --- Estado del catálogo activo ---
        # Gestor de la base de datos (None mientras no haya catálogo abierto)
        self.db: CatalogDatabaseManager | None = None
        # Carpeta del catálogo activo (la que contiene 'catalogo.db')
        self.catalog_dir: Path | None = None
        # Distinto de None mientras se está añadiendo una carpeta: es el evento que
        # cancela el proceso (add_folder lo consulta desde su hilo)
        self._add_folder_cancel: threading.Event | None = None
        # True si lo que está en marcha es "Sincronizar carpeta" (solo cambian los textos)
        self._add_folder_is_sync = False
        # Trabajos en segundo plano del catálogo activo (metadatos, miniaturas...)
        self.job_manager: JobManager | None = None
        # Widget de progreso (en la barra de estado) de cada trabajo en curso
        self._job_widgets: dict[str, JobProgressWidget] = {}
        # True si se pidió generar miniaturas mientras ya había una pasada en curso: al terminar
        # esa se hace otra (p. ej. una regeneración pedida a mitad de la pasada)
        self._thumbnail_rerun_requested = False

        # Escritura de los datos del usuario en los archivos: espera un poco tras el último
        # cambio (temporizador de un disparo que se reinicia con cada cambio) y, si llega
        # un cambio mientras escribe, repite al terminar
        self._userdata_timer = QTimer(self)
        self._userdata_timer.setSingleShot(True)
        self._userdata_timer.setInterval(USERDATA_WRITE_DELAY_MS)
        self._userdata_timer.timeout.connect(self._start_userdata_job)
        self._userdata_rerun_requested = False
        # La lectura de metadatos y la escritura en los archivos nunca van a la vez (una
        # podría leer un archivo mientras la otra lo escribe): si se pide leer mientras se
        # escribe, se lee al terminar
        self._metadata_after_userdata = False
        # Comprobación, una vez por catálogo abierto, de si hay muchos elementos pendientes
        # de escribir: "unchecked" (aún no), "checking" (preguntando), "ok" (se escribe) o
        # "postponed" (el usuario eligió "Más tarde": no se escribe en esta sesión)
        self._userdata_backlog_state = "unchecked"
        # Mientras se elimina (trabajo JOB_REMOVE) no se lanza ningún otro trabajo: lo que
        # se pida se anota aquí y se lanza al terminar (las miniaturas y la escritura en los
        # archivos usan sus propios indicadores de "repetir")
        self._metadata_after_removal = False
        self._thumbnails_after_removal = False

        # Comprobación periódica de discos desconectados y archivos que faltan (solo los
        # visibles). Nunca hay dos comprobaciones a la vez
        self._availability_timer = QTimer(self)
        self._availability_timer.setInterval(AVAILABILITY_CHECK_MS)
        self._availability_timer.timeout.connect(self._check_availability)
        self._availability_check_running = False

        # Recuento de la barra lateral tras los cambios del usuario (ver SIDEBAR_REFRESH_DELAY_MS)
        self._sidebar_refresh_timer = QTimer(self)
        self._sidebar_refresh_timer.setSingleShot(True)
        self._sidebar_refresh_timer.setInterval(SIDEBAR_REFRESH_DELAY_MS)
        self._sidebar_refresh_timer.timeout.connect(self._refresh_sidebar_counts)

        # Módulos (Catálogo, Imagen...): toolbar de modos y barras laterales. Se crea en
        # '_configurar_modulos', cuando ya existen la cuadrícula y sus atajos
        self.module_host: ModuleHost | None = None
        # Inspector (panel derecho): se crea en '_configurar_modulos'
        self.inspector: InspectorController | None = None

        self._configuracion_cargada = False
        self._crear_acciones_miniaturas()
        self._conectar_senales()

    def iniciar(self) -> None:
        """Función de inicio llamada desde main.py."""
        logger.info("Inicializando la ventana principal...")

        try:
            self._cargar_datos_iniciales()
            self._establecer_estilos_estados_iniciales()
            self._configurar_grid_mosaico()
            self._configurar_modulos()  # después de la cuadrícula: los módulos la usan
            self._configurar_validadores()
        except Exception as e:
            logger.exception("Error fatal al inicializar la interfaz gráfica.")
            mensaje = f"Error al iniciar, la aplicación se cerrará.\n\nDetalle: {e}"
            self.message_box.critical(mensaje)
            raise

        self.show()

        if not self._configuracion_cargada:
            QTimer.singleShot(0, self._cargar_configuracion_inicial_rutas)

    # -------------------------------------------------------------------------
    # Eventos de Qt
    # -------------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        """Gestiona el evento de mostrar la ventana."""
        super().showEvent(event)
        if not self.is_fully_loaded:
            geometria = self.config.get("window_geometry")
            if geometria:
                self.restoreGeometry(QByteArray.fromHex(geometria.encode("utf-8")))
            else:
                self.resize(1000, 700)
            # Anchos de las barras laterales: cuando la ventana ya tiene su tamaño definitivo
            # (en el siguiente ciclo de eventos), para que no se repartan mal
            QTimer.singleShot(0, self._restore_splitter_state)

        self.is_fully_loaded = True

    def changeEvent(self, event: QEvent) -> None:
        """Al volver a la ventana (p. ej. desde el Explorador), se comprueba lo que se ve."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._check_availability()

    def moveEvent(self, event: QMoveEvent) -> None:
        """Gestiona el evento de mover la ventana."""
        super().moveEvent(event)
        self.check_snap_and_move(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Gestiona el cierre de la ventana limpiando hilos pendientes."""
        logger.info(f"Cerrando {app_paths.APP_NAME.lower()}...")

        # Cancela lo que esté en marcha (p. ej. añadir una carpeta) y libera la base
        # de datos ANTES de seguir: así el cierre no espera a que termine un escaneo
        self._close_catalog()

        # Cancelar y esperar la finalización de la lectura de miniaturas de la cuadrícula
        # (y de la imagen grande de la vista individual)
        self.mosaico_model.shutdown()
        single_view = getattr(self, "widget_single_view", None)
        if single_view is not None:
            single_view.shutdown()

        geometria_hex = self.saveGeometry().data().hex()
        self.config.set("window_geometry", geometria_hex)

        # Guardar los anchos de las barras laterales que haya dejado el usuario
        splitter_hex = self.splitter_main.saveState().data().hex()
        self.config.set(SETTING_MAIN_SPLITTER_STATE, splitter_hex)

        # Guardar el tamaño de miniaturas que haya dejado el usuario en el slider
        self.config.set("thumbnail_size", self.slider_thumbnails.value())

        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Anchos de las barras laterales (splitter_main)
    # -------------------------------------------------------------------------

    def _restore_splitter_state(self) -> None:
        """Pone los anchos de las barras laterales: los guardados o, si no hay, los de por defecto.

        'splitter_main' tiene tres partes: barra lateral izquierda (catálogo), zona central
        (cuadrícula) y barra lateral derecha (metadatos).
        """
        splitter = self.splitter_main

        # Al agrandar o encoger la ventana, solo cambia la zona central: las barras
        # laterales conservan su ancho (como en Lightroom)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        # 1. Anchos guardados al cerrar la última vez (hexadecimal, como 'window_geometry')
        saved = self.config.get(SETTING_MAIN_SPLITTER_STATE)
        if isinstance(saved, str) and saved:
            try:
                restored = splitter.restoreState(QByteArray.fromHex(saved.encode("ascii")))
            except UnicodeEncodeError:
                restored = False  # el JSON se editó a mano con algo que no es hexadecimal
            if restored:
                return
            logger.warning(
                f"'{SETTING_MAIN_SPLITTER_STATE}' no válido en la configuración. "
                "Se usan los anchos por defecto."
            )

        # 2. Anchos por defecto: la zona central se queda con todo lo demás
        left = SIDEBAR_CATALOG_DEFAULT_WIDTH
        right = SIDEBAR_METADATA_DEFAULT_WIDTH
        center = max(1, splitter.width() - left - right - 2 * splitter.handleWidth())
        splitter.setSizes([left, center, right])

    # -------------------------------------------------------------------------
    # Conexión de señales y configuración inicial
    # -------------------------------------------------------------------------

    def _crear_acciones_miniaturas(self) -> None:
        """Crea (en código, no en el .ui) las acciones de regenerar miniaturas y las añade al menú.

        Son provisionales: cuando la cuadrícula lea de la base de datos tendrá un menú contextual
        para regenerar la selección, y estas dos se quedarán como opciones de todo el catálogo.
        """
        self.action_regenerate_failed_thumbnails = QAction(
            "Regenerar miniaturas con error", self
        )
        self.action_regenerate_all_thumbnails = QAction(
            "Regenerar todas las miniaturas...", self
        )
        # Justo antes de "Convertir formato", con su propio separador
        anchor = self.action_convert_format
        self.menu_file.insertAction(anchor, self.action_regenerate_failed_thumbnails)
        self.menu_file.insertAction(anchor, self.action_regenerate_all_thumbnails)
        self.menu_file.insertSeparator(anchor)

    def _conectar_senales(self) -> None:
        """Conexión centralizada de señales a slots."""
        # "Cargar carpeta" del menú: ahora añade la carpeta al catálogo (la cuadrícula lee del catálogo)
        self.action_load_folder.triggered.connect(self._on_add_folder)

        # Acciones del menú relacionadas con el catálogo
        self.action_new_catalog.triggered.connect(self._on_new_catalog)
        self.action_open_catalog.triggered.connect(self._on_new_catalog)
        self.action_add_folder.triggered.connect(self._on_add_folder)
        self.scan_progress.connect(self._on_add_folder_progress)

        # "Salir" (Ctrl+Q): cierra la ventana por el mismo camino que la X, así que pasa por
        # 'closeEvent' (cancela los trabajos, guarda el estado y libera el catálogo)
        self.action_exit.triggered.connect(self.close)

        # Acciones de regeneración de miniaturas (creadas en _crear_acciones_miniaturas)
        self.action_regenerate_failed_thumbnails.triggered.connect(
            self._on_regenerate_failed_thumbnails
        )
        self.action_regenerate_all_thumbnails.triggered.connect(
            self._on_regenerate_all_thumbnails
        )

        # Conexión del slider de miniaturas
        self.slider_thumbnails.setRange(THUMBNAIL_SIZE_MIN, THUMBNAIL_SIZE_MAX)
        # Valor inicial leído de settings.json. Se asigna ANTES de conectar
        # valueChanged, así que aquí no se dispara ningún redimensionado: el
        # tamaño se aplica a la vista en _configurar_grid_mosaico()
        self.slider_thumbnails.setValue(self._leer_tamano_miniatura_guardado())
        self.slider_thumbnails.valueChanged.connect(self._actualizar_tamano_mosaico)

        # Cuadrícula: lo que el usuario cambia (estrellas, marca, color) se guarda en el catálogo
        self.mosaico_model.user_field_changed.connect(self._on_grid_user_field_changed)
        self.mosaico_model.load_failed.connect(self._on_grid_load_failed)

        # Barra lateral del catálogo: las operaciones con el catálogo entero que se piden
        # desde ella (lo que se elige en la barra lo atiende su módulo: ver
        # '_configurar_modulos' y 'controllers/app_modules/catalog_module.py')
        # Botón "+" de la sección Carpetas: lo mismo que "Añadir carpeta al catálogo"
        self.widget_catalog_sidebar.add_folder_requested.connect(self._on_add_folder)
        # Menú contextual de las carpetas
        self.widget_catalog_sidebar.sync_folder_requested.connect(self._on_sync_folder)
        self.widget_catalog_sidebar.reveal_folder_requested.connect(self._on_reveal_folder)
        self.widget_catalog_sidebar.remove_missing_requested.connect(
            self._on_remove_missing_requested
        )
        # "Quitar del catálogo..." de una carpeta: lo atiende 'controllers/folder_actions.py'
        # y el trabajo se lanza aquí, como el de "Eliminar" ('_start_removal_job')
        self._folder_actions = FolderActions(
            self,
            self.widget_catalog_sidebar,
            self.message_box,
            get_db=lambda: self.db,
            busy_reason=self._busy_reason,
            start_removal=self._start_removal_job,
        )
        # Menú de la fila «Selección rápida»: vaciarla
        self.widget_catalog_sidebar.clear_quick_selection_requested.connect(
            self._on_clear_quick_selection
        )
        # Cada vez que la cuadrícula se recarga (carpeta añadida, metadatos leídos...), se
        # actualizan los contadores de la barra lateral del módulo activo
        self.mosaico_model.rows_loaded.connect(self._refresh_sidebar_counts)

        # Botón de opciones de la barra lateral
        self.btn_settings.clicked.connect(self._on_open_settings)

    def _configurar_grid_mosaico(self) -> None:
        """Configura el QListView para comportarse como un Grid interactivo."""
        # 'list_view_grid' es un 'MediaGridView' (promocionado en el .ui): imagen de
        # arrastre pequeña y semitransparente
        view = self.list_view_grid
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setMovement(QListView.Movement.Static)
        view.setSpacing(0)
        view.setUniformItemSizes(True)
        view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        view.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        # Habilita el rastreo del ratón sin necesidad de mantener un botón presionado
        view.setMouseTracking(True)

        # Asignar delegado y modelo
        view.setItemDelegate(self.mosaico_delegate)
        view.setModel(self.mosaico_model)

        # Arrastrar tarjetas (p. ej. a una colección de la barra lateral). OJO: va DESPUÉS de
        # 'setMovement(Static)', que desactiva el arrastre por su cuenta. Solo se arrastra
        # HACIA FUERA (las tarjetas no se recolocan) y solo se copia, nunca se mueve
        view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        view.setDefaultDropAction(Qt.DropAction.CopyAction)

        # Atajos de teclado y menú contextual (actúan sobre la selección)
        self.grid_actions = GridActions(view, self.mosaico_model)
        self.grid_actions.regenerate_requested.connect(self.regenerate_thumbnails)
        # Menú "Biblioteca": clasificar vídeos a mano (clip personal o película)
        self.grid_actions.library_change_requested.connect(self._on_library_change_requested)
        # "Eliminar..." (menú de la tarjeta y Supr fuera de las colecciones estáticas)
        self.grid_actions.remove_requested.connect(self._on_remove_requested)

        # Barra inferior: marca, valoración, color y selección rápida de lo seleccionado
        # (widget promocionado del .ui). Escribe por el modelo, como la tarjeta y el teclado
        organize_bar = getattr(self, "widget_organize_bar", None)
        if organize_bar is not None:
            organize_bar.attach(view, self.mosaico_model)
        else:
            logger.warning(
                "Falta 'widget_organize_bar' en la ventana: ejecuta build_ui.py para "
                "regenerar ui/main_window.py desde el .ui."
            )

        # (Las colecciones del usuario las conecta el módulo Catálogo: ver '_configurar_modulos')

        # Ajuste dimensional inicial
        self._actualizar_tamano_mosaico(self.slider_thumbnails.value())

    def _actualizar_tamano_mosaico(self, tamano: int) -> None:
        """Ajusta dinámicamente el tamaño de las tarjetas en la vista."""
        # Alto: miniatura + márgenes + banda inferior (nombre, estrellas y marca)
        self.mosaico_delegate.item_size = QSize(tamano + 16, tamano + 56)
        self.list_view_grid.setIconSize(QSize(tamano, tamano))
        # El modelo elige el tamaño de miniatura que cubre los píxeles FÍSICOS de la tarjeta
        self.mosaico_model.set_target_pixels(round(tamano * self.devicePixelRatioF()))

    def _leer_tamano_miniatura_guardado(self) -> int:
        """Lee 'thumbnail_size' de settings.json y lo valida para el slider.

        Si el valor guardado no es un entero (p. ej. el JSON se editó a mano) se
        usa el valor por defecto; si queda fuera del rango del slider, se ajusta
        al límite más cercano.
        """
        tamano = self.config.get("thumbnail_size", THUMBNAIL_SIZE_DEFAULT)

        # bool es subclase de int en Python, por eso se excluye explícitamente
        if not isinstance(tamano, int) or isinstance(tamano, bool):
            logger.warning(
                f"'thumbnail_size' no válido en la configuración: {tamano!r}. "
                "Se usa el valor por defecto."
            )
            tamano = THUMBNAIL_SIZE_DEFAULT

        return max(THUMBNAIL_SIZE_MIN, min(THUMBNAIL_SIZE_MAX, tamano))

    def _on_grid_user_field_changed(
        self, media_ids: list, field: str, value: object
    ) -> None:
        """El usuario cambió rating, marca, etiqueta o selección rápida en la cuadrícula: se
        guarda en el catálogo.

        'update_user_field' los deja además pendientes de escribir en los archivos; esa
        escritura se programa en cuanto el catálogo confirma el cambio. La selección rápida
        no se escribe en los archivos: solo se guarda y se actualizan los contadores.
        """
        if self.db is None:
            return
        if field == QUICK_SELECTION_FIELD:
            self.db.execute_async(
                set_quick_selection,
                media_ids,
                bool(value),
                on_result=lambda _count: self._sidebar_refresh_timer.start(),
                on_error=self._on_grid_save_error,
            )
            return
        self.db.execute_async(
            update_user_field,
            media_ids,
            field,
            value,
            on_result=self._on_user_field_saved,
            on_error=self._on_grid_save_error,
        )

    def _on_clear_quick_selection(self) -> None:
        """"Vaciar selección rápida": pide confirmación y la vacía en el catálogo.

        Se pregunta porque no se puede deshacer (una selección rápida puede llevar rato
        hacerla). Los archivos no se tocan.
        """
        if self.db is None:
            return
        answer = self.message_box.question(
            "¿Vaciar la selección rápida?\n\nLos archivos no se tocan: solo dejan de "
            "estar en la selección rápida.",
            buttons=["Vaciar", "Cancelar"],
        )
        if answer != "Vaciar":
            return
        self.db.execute_async(
            clear_quick_selection,
            on_result=self._on_quick_selection_cleared,
            on_error=self._on_grid_save_error,
        )

    def _on_library_change_requested(self, media_ids: list, library: str | None) -> None:
        """Menú de la cuadrícula > "Biblioteca": guarda la elección en el catálogo.

        'library' None = "Detectar automáticamente" (deshace la corrección manual).
        """
        if self.db is None or not media_ids:
            return
        self.db.execute_async(
            set_library,
            media_ids,
            library,
            on_result=lambda changes: self._on_library_changed(changes, library),
            on_error=self._on_grid_save_error,
        )

    def _on_library_changed(
        self, changes: dict[int, tuple[str | None, int]], library: str | None
    ) -> None:
        """La biblioteca ya está guardada: se informa y se actualiza lo que se ve.

        Las tarjetas cargadas reciben su biblioteca nueva (para que el submenú marque la
        correcta). Si la cuadrícula muestra una colección inteligente (p. ej. «Sin
        clasificar», o una con la regla «Biblioteca»), se vuelve a leer para que salgan o
        entren los vídeos; si muestra otra cosa (una carpeta...), solo cambian los
        contadores.

        Args:
            changes: Lo que ha cambiado ('id' -> (biblioteca, manual)), de 'set_library'.
            library: Lo elegido en el menú (None = "Detectar automáticamente").
        """
        count = len(changes)
        if count == 0:
            message_bar(self, "No había nada que cambiar.", AppIcons.INFO)
            return
        self.mosaico_model.set_library_values(changes)
        if library is None:
            text = f"{count} vídeos vuelven a la detección automática."
        else:
            text = f"Biblioteca cambiada: {count} vídeos."
        message_bar(self, text, AppIcons.CHECK_CIRCLE)
        if self.mosaico_model.source.kind == SourceKind.SMART:
            self.mosaico_model.reload()  # al terminar, la barra lateral se actualiza sola
        else:
            self._sidebar_refresh_timer.start()
        if self.inspector is not None:
            self.inspector.refresh()  # la fila «Biblioteca» de lo seleccionado

    def _on_videos_classified(self, count: int, *, reload_always: bool = False) -> None:
        """Se han clasificado vídeos sin biblioteca (al abrir, o tras leer metadatos).

        Args:
            count: Vídeos clasificados.
            reload_always: True tras leer metadatos (la cuadrícula se recarga siempre, para
                mostrar lo leído); si no, solo se recarga si se ha clasificado alguno.
        """
        if self.db is None:
            return  # el catálogo se cerró mientras tanto
        if count:
            logger.info(f"Vídeos clasificados automáticamente: {count}")
        if count or reload_always:
            self.mosaico_model.reload()

    def _on_quick_selection_cleared(self, count: int) -> None:
        """La selección rápida ya está vacía en el catálogo: se refleja en la interfaz.

        Si se está viendo la propia selección rápida, la cuadrícula se recarga (queda
        vacía); si no, solo se quita el círculo a las tarjetas cargadas. Después, los
        contadores.
        """
        logger.info(f"Selección rápida vaciada ({count} elementos).")
        # La del Catálogo o la de un módulo (p. ej. la de Imagen: 'quick_source("image")')
        if self.mosaico_model.source.kind == SourceKind.QUICK:
            self.mosaico_model.reload()
        else:
            self.mosaico_model.forget_quick_selection()
        self._sidebar_refresh_timer.start()

    def _on_user_field_saved(self, _count: int) -> None:
        """El catálogo ya tiene el cambio del usuario: se escribirá en los archivos y se
        actualizarán los contadores de la barra lateral (las colecciones dependen de él).

        La cuadrícula NO se recarga: si se muestra una colección (p. ej. "Clasificación 3")
        y una foto deja de cumplirla, sigue a la vista hasta volver a elegir la colección
        (así no se pierden la selección ni la posición mientras se valora).
        """
        self._schedule_userdata_write()
        self._sidebar_refresh_timer.start()  # si ya estaba en marcha, vuelve a empezar

    def _on_grid_save_error(self, error: Exception) -> None:
        """No se pudo guardar un cambio de la cuadrícula: se avisa y se vuelve a leer del catálogo."""
        logger.error(f"No se pudo guardar el cambio en el catálogo: {error}")
        message_bar(
            self, "No se pudo guardar el cambio en el catálogo.", AppIcons.ERROR
        )
        self.mosaico_model.reload()  # la cuadrícula vuelve a mostrar lo que hay realmente guardado

    # -------------------------------------------------------------------------
    # Escritura de los datos del usuario en los archivos (XMP, sidecar, archivo de carpeta)
    # -------------------------------------------------------------------------

    def _write_to_files_enabled(self) -> bool:
        """Lee la opción "Escribir los cambios en los archivos" (por defecto, activada)."""
        value = self.config.get(SETTING_WRITE_USER_DATA_TO_FILES, True)
        if not isinstance(value, bool):
            logger.warning(
                f"'{SETTING_WRITE_USER_DATA_TO_FILES}' no válido en la configuración: "
                f"{value!r}. Se usa el valor por defecto (activada)."
            )
            return True
        return value

    def _schedule_userdata_write(self) -> None:
        """Programa la escritura en los archivos tras un momento sin cambios del usuario."""
        if self.job_manager is not None and self._write_to_files_enabled():
            self._userdata_timer.start()  # si ya estaba en marcha, vuelve a empezar la cuenta

    def _start_userdata_job(self) -> None:
        """Lanza la escritura de los datos del usuario pendientes, si procede.

        Espera a que termine la lectura de metadatos (así no se lee y se escribe a la vez
        el mismo archivo). Si ya hay una escritura en curso, se repite al terminar.
        """
        if (
            self.job_manager is None
            or self.db is None
            or not self._write_to_files_enabled()
        ):
            return
        if self._userdata_backlog_state == "unchecked":
            # Primera escritura desde que se abrió el catálogo: antes se mira cuánto hay
            # pendiente (si es mucho, se pregunta; ver _on_userdata_backlog_counted)
            self._userdata_backlog_state = "checking"
            self.db.execute_async(
                count_pending_user_data,
                on_result=self._on_userdata_backlog_counted,
                on_error=lambda _error: self._on_userdata_backlog_counted(0),
            )
            return
        if self._userdata_backlog_state != "ok":
            return  # preguntando, o el usuario lo aplazó en esta sesión
        if self.job_manager.is_running(JOB_REMOVE):
            self._userdata_rerun_requested = True  # se lanza al terminar de eliminar
            return
        if self.job_manager.is_running(JOB_METADATA):
            self._userdata_rerun_requested = True  # se lanza al terminar los metadatos
            return
        if not self.job_manager.start(JOB_USERDATA, write_pending_user_data):
            self._userdata_rerun_requested = True

    def _on_userdata_backlog_counted(self, count: int) -> None:
        """Si hay muchos elementos pendientes de escribir, pregunta antes de empezar.

        Ocurre sobre todo la primera vez que se abre un catálogo tras actualizar la
        aplicación: los valores que ya tenía el catálogo quedan pendientes de escribirse
        en los archivos (solo se modifican los que no los tengan ya).
        """
        if self.job_manager is None or self._userdata_backlog_state != "checking":
            return  # el catálogo se cerró mientras se contaba
        if count >= USERDATA_CONFIRM_MIN_ITEMS:
            answer = self.message_box.question(
                f"Hay {count} elementos cuya valoración, marca o color solo están en el "
                "catálogo.\n\n"
                "¿Escribirlos ahora en los archivos (XMP de las fotos, sidecar .xmp de los "
                "RAW y archivo .arca.json de cada carpeta)? Solo se modifican los archivos "
                "que no tengan ya esos valores.\n\n"
                "Con «Más tarde» no se toca ningún archivo en esta sesión: los cambios se "
                "guardan en el catálogo y se volverá a preguntar al abrirlo.",
                buttons=["Escribir ahora", "Más tarde"],
            )
            if answer != "Escribir ahora":
                self._userdata_backlog_state = "postponed"
                message_bar(
                    self,
                    "Escritura en los archivos aplazada: los cambios quedan en el catálogo.",
                    AppIcons.INFO,
                )
                return
        self._userdata_backlog_state = "ok"
        self._start_userdata_job()

    # -------------------------------------------------------------------------
    # Ventana de opciones
    # -------------------------------------------------------------------------

    def _on_open_settings(self) -> None:
        """Abre la ventana de opciones y aplica lo que haya cambiado."""
        # Mientras está abierta, el icono del botón se queda en el color de acento
        changed: set[str] = set()
        self.btn_settings.setIcon(self.icon_settings_active)
        try:
            dialog = SettingsDialog(
                self.config, context={"catalog_dir": self.catalog_dir}, parent=self
            )
            dialog.exec()
            changed = dialog.changed_keys
            dialog.deleteLater()  # se crea una nueva cada vez: esta ya no hace falta
        finally:
            self.btn_settings.setIcon(self.icon_settings)

        # Cada módulo aplica lo suyo (p. ej. el Catálogo, las carpetas con o sin sus
        # subcarpetas: rehace el árbol y, si hay una carpeta elegida, la cuadrícula se
        # recarga sola)
        if self.module_host is not None:
            self.module_host.apply_settings(changed)

        # Se acaba de activar la escritura en los archivos: se escribe lo pendiente (el
        # usuario lo ha pedido expresamente: no se vuelve a preguntar)
        if (
            SETTING_WRITE_USER_DATA_TO_FILES in changed
            and self._write_to_files_enabled()
        ):
            if self._userdata_backlog_state != "checking":
                self._userdata_backlog_state = "ok"
            self._start_userdata_job()

    def _on_grid_load_failed(self, error: Exception) -> None:
        """Falló la lectura de la lista de la cuadrícula."""
        logger.error(f"No se pudo leer la lista de la cuadrícula: {error}")
        message_bar(self, "No se pudo leer el catálogo.", AppIcons.ERROR)

    # -------------------------------------------------------------------------
    # Módulos (toolbar de modos y barras laterales)
    # -------------------------------------------------------------------------

    def _configurar_modulos(self) -> None:
        """Crea los módulos (Catálogo, Imagen, Vídeo, Audio) y su coordinador.

        Va DESPUÉS de '_configurar_grid_mosaico': los módulos usan la cuadrícula y sus
        atajos (p. ej. el Catálogo crea 'CollectionActions'). La lista de módulos está en
        'controllers/app_modules/registry.py'; cada uno trae su barra lateral, y el
        'ModuleHost' decide cuál se ve y cuál manda en la cuadrícula.
        """
        context = ModuleContext(
            window=self,
            config=self.config,
            message_box=self.message_box,
            grid_view=self.list_view_grid,
            grid_model=self.mosaico_model,
            grid_actions=self.grid_actions,
        )
        self.module_host = ModuleHost(
            create_modules(self, context),
            config=self.config,
            grid_model=self.mosaico_model,
            sidebar_stack=self.stacked_widget_sidebar_catalog,
            info_stack=self.stacked_widget_sidebar_metadata,
            info_default_page=self.page_metadata_default,
            parent=self,
        )
        self._conectar_orden()
        self._conectar_vistas()
        self._configurar_inspector()

    def _conectar_vistas(self) -> None:
        """Vistas del centro (cuadrícula, individual...): botones de vista, página de la pila,
        deslizador del tamaño y navegación entre archivos (ver 'CenterViewController')."""
        buttons = getattr(self, "widget_view_buttons", None)
        page_single = getattr(self, "page_single", None)
        single_view = getattr(self, "widget_single_view", None)
        if buttons is None or single_view is None or self.module_host is None:
            logger.warning(
                "Faltan 'widget_view_buttons' o 'widget_single_view' en la ventana: ejecuta "
                "scripts/build_ui.py para regenerar ui/main_window.py desde el .ui."
            )
            return
        # La vista individual usa el modelo y la selección de la cuadrícula
        single_view.attach(self.list_view_grid, self.mosaico_model)
        self.center_views = CenterViewController(
            self.module_host,
            buttons=buttons,
            stack=self.stacked_widget_main,
            pages={CenterView.GRID: self.page_grid, CenterView.SINGLE: page_single},
            size_slider=self.slider_thumbnails,
            grid=self.list_view_grid,
            single=single_view,
            parent=self,
        )
        # Los atajos de clasificación (estrellas, color, marca, B, Supr), también en ella
        self.grid_actions.watch(single_view)

    def _conectar_orden(self) -> None:
        """Conecta el control «Orden:» de la barra inferior con el orden del módulo activo.

        El control solo muestra y pide; el 'ModuleHost' decide y guarda (ver su docstring).
        """
        sort_control = getattr(self, "widget_sort_control", None)
        if sort_control is None or self.module_host is None:
            logger.warning(
                "Falta 'widget_sort_control' en la ventana: ejecuta scripts/build_ui.py para "
                "regenerar ui/main_window.py desde el .ui."
            )
            return
        host = self.module_host

        def show_active_order(_order: object = None) -> None:
            sort_control.set_options(host.active_sort_fields(), host.active_order)

        sort_control.order_requested.connect(host.set_order)
        host.order_changed.connect(show_active_order)
        show_active_order()  # el módulo inicial ya se activó al crear el host

    def _configurar_inspector(self) -> None:
        """Pone el inspector en el panel derecho por defecto y lo conecta con la cuadrícula.

        El panel por defecto ('page_metadata_default' del .ui) es el de los módulos que no
        tienen uno propio: de momento, todos. El texto provisional del .ui se oculta.
        """
        self.lbl_metadata_placeholder.hide()
        panel = InspectorPanel(self.page_metadata_default)
        self.layout_page_metadata_default.addWidget(panel)
        self.inspector = InspectorController(
            panel,
            self.list_view_grid,
            self.mosaico_model,
            self.message_box,
            parent=self,
        )
        # Lo que se cambia desde el inspector (p. ej. las palabras clave del módulo Imagen)
        # se trata como los demás cambios del usuario: escritura diferida y contadores
        self.inspector.user_data_changed.connect(self._on_user_field_saved)
        # Tras cualquier cambio (también crear o purgar palabras, que no tocan archivos),
        # la barra lateral se relee (el árbol de palabras clave)
        self.inspector.edit_finished.connect(self._sidebar_refresh_timer.start)
        # El inspector es el mismo en todos los módulos (sus secciones dependen de la
        # selección, no del módulo)
        if self.module_host is not None:
            # Cambios pedidos desde la barra de un módulo (p. ej. el menú del árbol de
            # palabras clave): por la misma cola que los del inspector
            self.module_host.catalog_edit_requested.connect(self.inspector.request_edit)
            # Flecha «ver sus fotos» del inspector: lo muestra el módulo activo en su barra
            self.inspector.navigate_requested.connect(self.module_host.show_source)

    def _configurar_toolbar(self) -> None:
        """Reparte el espacio de la toolbar de modos ('frame_toolbar').

        La franja mide lo que el botón más ancho más 'TOOLBAR_MARGIN' a cada lado y los
        botones van centrados; arriba y abajo queda el mismo margen. Así el aire es igual
        en los cuatro lados (sin línea separadora: la zona se nota por el fondo).

        Se toman TODOS los botones de la franja (los de cada módulo y el de ajustes), así
        que un botón nuevo en el .ui se centra solo. Qué hace cada botón de módulo (icono,
        barra lateral...) lo deciden los módulos: ver '_configurar_modulos'.
        """
        all_buttons = self.frame_toolbar.findChildren(QToolButton)
        button_width = max(button.minimumSize().width() for button in all_buttons)
        self.frame_toolbar.setFixedWidth(button_width + 2 * TOOLBAR_MARGIN)
        # Los lados ya los da el ancho fijo (botones centrados): aquí, arriba y abajo
        self.layout_toolbar.setContentsMargins(0, TOOLBAR_MARGIN, 0, TOOLBAR_MARGIN)
        for button in all_buttons:
            self.layout_toolbar.setAlignment(button, Qt.AlignmentFlag.AlignHCenter)

    def _refresh_sidebar_counts(self, _row_count: int = 0) -> None:
        """Actualiza en segundo plano la barra lateral del módulo activo (contadores, árboles).

        Se llama cada vez que la cuadrícula termina de cargar (señal 'rows_loaded'): al
        abrir el catálogo, al añadir una carpeta, al terminar de leer metadatos, al elegir
        otra fila de la barra... y tras los cambios del usuario ('_sidebar_refresh_timer').
        Las barras de los demás módulos se actualizan al volver a ellos (ver 'ModuleHost').
        """
        if self.module_host is not None:
            self.module_host.refresh()

    # -------------------------------------------------------------------------
    # Configuración inicial
    # -------------------------------------------------------------------------

    def _cargar_datos_iniciales(self) -> None:
        """Carga inicial de datos de la interfaz."""

    def _establecer_estilos_estados_iniciales(self) -> None:
        """Aplica estilos e iconos iniciales."""
        self.setWindowTitle(app_paths.APP_NAME_COMERCIAL)
        ruta_icono = str(app_paths.RESOURCES_DIR / "icons" / "icon_128.ico")
        self.setWindowIcon(QIcon(ruta_icono))

        # El tema (paleta y hoja de estilos) ya se aplicó en main.py, antes de crear la
        # ventana: ver 'ui_helpers/helpers/ui_theme.apply_theme'

        # Toolbar: botones de modo (Catálogo, Imagen, Vídeo, Audio), con su icono en el
        # color de acento al pasar el ratón y mientras su modo está activo
        self._configurar_toolbar()

        # Icono de ajustes: dos versiones del mismo SVG, con el mismo acento que los modos
        #   - normal: sigue la paleta (también con el ratón encima, como los modos)
        #   - activo: acento fijo; se usa mientras la ventana de ajustes está abierta
        accent = toolbar_accent_color()
        self.icon_settings = tinted_icon(AppIcons.SETTINGS)
        self.icon_settings_active = tinted_icon(AppIcons.SETTINGS, accent)
        self.btn_settings.setIcon(self.icon_settings)

    def _configurar_validadores(self) -> None:
        """Asigna validadores."""

    def _cargar_configuracion_inicial_rutas(self) -> None:
        """Carga la configuración inicial: reabre el último catálogo que se usó."""
        self._configuracion_cargada = True

        last_catalog = self.config.get("catalogo_ruta", "")
        if not last_catalog:
            return

        catalog_dir = Path(last_catalog)
        if not (catalog_dir / CatalogBuilder.DB_FILENAME).is_file():
            # P. ej. el catálogo está en un disco externo que no está conectado
            logger.warning(f"El último catálogo ya no está disponible: {catalog_dir}")
            message_bar(
                self, "No se encontró el último catálogo usado.", AppIcons.WARNING
            )
            return

        self._open_catalog(catalog_dir)

    # -------------------------------------------------------------------------
    # Catálogo activo: crear, abrir y cerrar
    # -------------------------------------------------------------------------

    def _on_new_catalog(self) -> None:
        """Crea un catálogo en la carpeta elegida y lo abre.

        Si la carpeta ya contiene un catálogo, se ofrece abrirlo: así este mismo
        diálogo sirve también para abrir catálogos que ya existen.
        """
        if self._add_folder_cancel is not None:
            self.message_box.info(
                "Se está añadiendo una carpeta al catálogo actual.\n\n"
                "Espera a que termine antes de cambiar de catálogo."
            )
            return

        folder = select_folder(
            parent=self, title="Seleccionar la carpeta del catálogo", force_dialog=True
        )
        if not folder:
            return

        builder = CatalogBuilder(folder)

        # Ya hay un catálogo en la carpeta: se ofrece abrirlo
        if builder.already_exists():
            answer = self.message_box.question(
                "Ya existe un catálogo en esta carpeta.\n\n¿Quieres abrirlo?",
                buttons=["Abrir", "Cancelar"],
            )
            if answer == "Abrir":
                self._open_catalog(builder.catalog_path)
            return

        if not self._confirm_catalog_folder(builder.catalog_path):
            return

        try:
            builder.build()
        except CatalogError as error:
            self.message_box.critical(str(error))
            return

        self._open_catalog(builder.catalog_path)

    def _confirm_catalog_folder(self, folder: Path) -> bool:
        """Pide confirmación si la carpeta elegida para el catálogo no está vacía.

        El catálogo crea su base de datos y varias subcarpetas directamente dentro
        de la carpeta elegida, así que conviene avisar si ya hay cosas en ella.
        """
        try:
            is_empty = not folder.exists() or not any(folder.iterdir())
        except OSError as error:
            self.message_box.critical(
                f"No se pudo acceder a la carpeta:\n{folder}\n\n{error}"
            )
            return False

        if is_empty:
            return True

        answer = self.message_box.question(
            "La carpeta elegida no está vacía.\n\n"
            "El catálogo crea en ella su base de datos y varias subcarpetas "
            "(cache, media_assets, export). ¿Crearlo aquí de todas formas?",
            buttons=["Crear aquí", "Cancelar"],
        )
        return answer == "Crear aquí"

    def _open_catalog(self, catalog_dir: Path) -> bool:
        """Abre un catálogo existente y lo deja como catálogo activo.

        Primero lo comprueba y migra su esquema (síncrono, tarda milisegundos) y solo
        entonces crea el gestor asíncrono de la base de datos.

        Returns:
            True si se abrió; False si falló (el usuario ya ha visto el motivo).
        """
        try:
            db_path = open_catalog(catalog_dir)
        except CatalogError as error:
            logger.warning(f"No se pudo abrir el catálogo: {error}")
            self.message_box.critical(str(error))
            return False

        # Se cierra el catálogo anterior (si lo había) antes de abrir el nuevo
        self._close_catalog()

        self.db = CatalogDatabaseManager(db_path, parent=self)
        self.catalog_dir = db_path.parent

        # Trabajos en segundo plano: sus señales llegan al hilo principal
        self.job_manager = JobManager(self.db, parent=self)
        self.job_manager.job_progress.connect(self._on_job_progress)
        self.job_manager.job_finished.connect(self._on_job_finished)
        self.job_manager.job_failed.connect(self._on_job_failed)
        self.config.set("catalogo_ruta", str(self.catalog_dir))

        self.setWindowTitle(f"{app_paths.APP_NAME_COMERCIAL} - {self.catalog_dir.name}")
        message_bar(self, f"Catálogo abierto: {self.catalog_dir.name}")
        logger.info(f"Catálogo activo: {self.catalog_dir}")

        # 1. La cuadrícula se asocia al catálogo ANTES de restaurar la barra lateral:
        #    'attach' empieza mostrando todo ('detach' deja el origen en ALL_ITEMS), así
        #    que si se hiciera después, borraría la carpeta o colección restaurada
        self.mosaico_model.attach(self.db, self.catalog_dir)

        # 2. Lo desplegado en las barras laterales y lo elegido la última vez que se usó
        #    este catálogo. En el módulo activo, una carpeta, una colección estática o una
        #    fila fija se emiten ya ('source_selected' -> 'set_source', que carga la
        #    cuadrícula con ese origen); una colección inteligente del usuario, al llegar
        #    el árbol de colecciones
        # 3. Los módulos empiezan a trabajar con el catálogo (el Catálogo pide el árbol de
        #    colecciones en segundo plano: llega después de haber restaurado su barra, así
        #    la colección inteligente guardada se encuentra)
        if self.module_host is not None:
            self.module_host.restore_state(self.catalog_dir)
            if self.inspector is not None:
                self.inspector.restore_state(self.module_host.saved_entry(self.catalog_dir))
            self.module_host.attach(self.db, self.catalog_dir)
        if self.inspector is not None:
            self.inspector.attach(self.db)

        # 4. Si no se restauró nada (o se espera a una colección inteligente), se carga el
        #    catálogo completo (en el orden del módulo activo, fijado en 'restore_state').
        #    Si ya se restauró un origen, 'set_source' lo ha cargado: no se repite la consulta
        if self.mosaico_model.source == ALL_ITEMS:
            self.mosaico_model.reload()

        # ¿Qué ubicaciones están conectadas? (un disco externo puede no estarlo). Se mira en
        # segundo plano (una unidad de red caída puede tardar en responder) y, si algo
        # cambió, la cuadrícula se vuelve a leer para marcar sus tarjetas
        self.db.execute_async(
            refresh_location_status,
            on_result=self._on_location_status_refreshed,
            on_error=lambda error: logger.warning(
                f"No se comprobaron las ubicaciones: {error}"
            ),
        )
        # Vídeos que siguen sin clasificar (p. ej. catalogados antes de existir la detección):
        # se clasifican los que lo digan su nombre o sus metadatos ya leídos, sin reescanear
        self.db.execute_async(
            classify_pending_videos,
            on_result=self._on_videos_classified,
            on_error=lambda error: logger.warning(
                f"No se pudieron clasificar los vídeos pendientes: {error}"
            ),
        )
        # A partir de aquí, se comprueba cada pocos segundos (discos y tarjetas visibles)
        self._availability_timer.start()

        # Si en una sesión anterior quedó trabajo a medias (o archivos sin leer),
        # se retoma ahora
        self._start_metadata_job()
        return True

    def _on_location_status_refreshed(self, changed: int) -> None:
        """Si alguna ubicación se conectó o desconectó, la cuadrícula se vuelve a leer."""
        if changed and self.db is not None:
            self.mosaico_model.reload()

    # -------------------------------------------------------------------------
    # Archivos y discos que desaparecen (o vuelven) con el catálogo abierto
    # -------------------------------------------------------------------------

    def _visible_media_ids(self) -> list[int]:
        """'id' de las tarjetas que se ven ahora en la cuadrícula (como mucho, unas 400).

        En modo iconos las filas van de izquierda a derecha y de arriba abajo, así que
        basta con la primera y la última tarjeta visibles.
        """
        view = self.list_view_grid
        model = self.mosaico_model
        if model.rowCount() == 0:
            return []
        area = view.viewport().rect()
        first = view.indexAt(area.topLeft() + QPoint(2, 2))
        last = view.indexAt(area.bottomRight() - QPoint(2, 2))
        start = first.row() if first.isValid() else 0
        # La última fila puede estar a medias (hueco a la derecha): entonces, hasta el final
        end = last.row() if last.isValid() else model.rowCount() - 1
        end = min(end, start + AVAILABILITY_MAX_VISIBLE - 1)
        return model.media_ids_in_rows(start, end)

    def _check_availability(self) -> None:
        """Comprueba en segundo plano los discos y los archivos de las tarjetas visibles.

        Los archivos solo se miran si la ventana está activa (si no, nadie los está
        viendo); los discos, siempre (es una consulta por ubicación).
        """
        # (getattr: Qt puede avisar de la activación antes de terminar el __init__)
        if getattr(self, "db", None) is None or getattr(
            self, "_availability_check_running", True
        ):
            return
        media_ids = self._visible_media_ids() if self.isActiveWindow() else []
        self._availability_check_running = True
        self.db.execute_async(
            check_availability,
            media_ids,
            on_result=self._on_availability_checked,
            on_error=lambda error: logger.warning(
                f"No se pudo comprobar la disponibilidad: {error}"
            ),
            on_finished=self._on_availability_check_finished,
        )

    def _on_availability_checked(self, result: AvailabilityCheck) -> None:
        """Repinta las tarjetas que han cambiado (sin recargar la cuadrícula)."""
        if result.changes:
            self.mosaico_model.set_availability(result.changes)
        if result.rescan_needed:
            # Han vuelto archivos que cambiaron mientras faltaban: se releen
            self._start_metadata_job()

    def _on_availability_check_finished(self) -> None:
        self._availability_check_running = False

    def _close_catalog(self) -> None:
        """Cierra el catálogo activo, si lo hay, cancelando lo que esté en marcha."""
        if self._add_folder_cancel is not None:
            # add_folder se detiene en cuanto puede: lo ya guardado se conserva
            self._add_folder_cancel.set()

        if self.job_manager is not None:
            # Los trabajos paran en cuanto pueden; 'db.shutdown()' espera a que acaben
            self.job_manager.cancel_all()
            self.job_manager.deleteLater()
            self.job_manager = None
        self._clear_job_widgets()
        self._thumbnail_rerun_requested = False
        # Lo que quede sin escribir sigue pendiente en el catálogo: se escribirá al reabrirlo
        self._userdata_timer.stop()
        self._userdata_rerun_requested = False
        self._metadata_after_userdata = False
        self._metadata_after_removal = False
        self._thumbnails_after_removal = False
        self._userdata_backlog_state = (
            "unchecked"  # el próximo catálogo se comprueba de nuevo
        )
        self._availability_timer.stop()
        self._availability_check_running = False
        self._sidebar_refresh_timer.stop()

        # Lo desplegado en las barras laterales se guarda ANTES de vaciarlas
        # (getattr: Qt puede cerrar la ventana antes de terminar 'iniciar')
        module_host = getattr(self, "module_host", None)
        if module_host is not None and self.catalog_dir is not None:
            # Con lo del inspector (lo desplegado de su árbol de palabras clave)
            inspector = getattr(self, "inspector", None)
            extra = inspector.save_state() if inspector is not None else None
            module_host.save_state(self.catalog_dir, extra=extra)

        self.mosaico_model.detach()  # vacía la cuadrícula y deja de pedir datos a la base
        if module_host is not None:
            # Cada módulo olvida el catálogo y vacía su barra ("Todos los archivos" y sin
            # contadores, en el Catálogo)
            module_host.detach()
        inspector = getattr(self, "inspector", None)
        if inspector is not None:
            inspector.detach()  # se descartan los resúmenes pendientes y se vacía el panel

        if self.db is not None:
            # 'shutdown' espera a las tareas en curso (rápido, porque se han cancelado)
            self.db.shutdown()
            self.db.deleteLater()
            self.db = None

        # Sus callbacks ya no se ejecutarán, así que el estado se restablece aquí
        self._finish_add_folder()
        self.catalog_dir = None

    # -------------------------------------------------------------------------
    # Añadir una carpeta al catálogo
    # -------------------------------------------------------------------------

    def _on_add_folder(self) -> None:
        """Pide una carpeta y qué contiene, y la añade al catálogo activo en segundo plano.

        Pasos: elegir la carpeta -> mirar en segundo plano qué contiene según el catálogo
        (si está dentro de una carpeta ya declarada, hereda lo suyo) -> preguntar "¿Qué
        contiene esta carpeta?" con eso ya elegido -> añadirla (ver '_ask_folder_content').
        """
        if self.db is None:
            self.message_box.warning(
                "Primero hay que crear o abrir un catálogo.\n\n"
                "Usa «Nuevo catálogo» del menú Archivo."
            )
            return

        # Se abre donde estaba la última carpeta añadida (si ya no existe, 'select_folder'
        # abre la carpeta personal)
        folder = select_folder(
            parent=self,
            title="Seleccionar la carpeta que se añadirá al catálogo",
            initial_path=self.config.get(SETTING_LAST_ADD_FOLDER_PARENT, "") or None,
            force_dialog=True,
        )
        if not folder:
            return
        # 'folder_content_for(conn, carpeta)' solo lee: es rápido, pero toca la BD, así que
        # va en segundo plano. Si falla, se pregunta igual con "Detectar automáticamente"
        self.db.execute_async(
            folder_content_for,
            folder,
            on_result=lambda current: self._ask_folder_content(folder, current),
            on_error=lambda _error: self._ask_folder_content(folder, FOLDER_AUTO),
        )

    def _ask_folder_content(self, folder: str, current: str) -> None:
        """Pregunta qué contiene la carpeta y, si se acepta, la añade (hilo principal).

        Args:
            folder: Carpeta elegida.
            current: Tipo de contenido que ya tiene (declarado o heredado), para
                preseleccionarlo.
        """
        if self.db is None:
            return  # el catálogo se cerró mientras se consultaba
        if self._add_folder_cancel is not None:
            self.message_box.info(
                "Ya se está añadiendo o sincronizando una carpeta.\n\n"
                "Espera a que termine antes de añadir otra."
            )
            return
        content = FolderContentDialog.ask(self, folder, current=current)
        if content is None:
            return  # cancelado
        # La próxima vez, «Añadir carpeta» se abre en la carpeta que contiene esta
        self.config.set(SETTING_LAST_ADD_FOLDER_PARENT, Path(folder).parent.as_posix())
        self._start_add_folder(folder, sync=False, content=content)

    def _on_sync_folder(self, folder: str) -> None:
        """Menú de una carpeta > "Sincronizar carpeta": la vuelve a recorrer.

        Es la misma operación que añadirla (ver 'add_folder'): incorpora los archivos
        nuevos, relee los cambiados y marca los que han desaparecido. Como "Sincronizar
        carpeta" de Lightroom.
        """
        if self.db is None:
            return
        if self._add_folder_cancel is not None:
            self.message_box.info(
                "Ya se está añadiendo o sincronizando una carpeta.\n\n"
                "Espera a que termine antes de sincronizar otra."
            )
            return
        self._start_add_folder(folder, sync=True)

    def _on_reveal_folder(self, folder: str) -> None:
        """Menú de una carpeta > "Mostrar en el Explorador" (el Finder en macOS)."""
        if not Path(folder).is_dir():
            self.message_box.warning(
                f"La carpeta no existe (¿se ha movido, renombrado o borrado?):\n{folder}\n\n"
                "Si se ha borrado fuera de la aplicación, «Sincronizar carpeta» en su carpeta "
                "padre marcará sus archivos como ausentes."
            )
            return
        if not reveal_in_file_manager(folder):
            self.message_box.warning(f"No se pudo abrir {FILE_MANAGER_NAME}:\n{folder}")

    def _start_add_folder(
        self, folder: str | Path, *, sync: bool, content: str | None = None
    ) -> None:
        """Añade (o sincroniza) una carpeta del catálogo en un hilo secundario.

        Args:
            folder: Carpeta a añadir o sincronizar.
            sync: True si viene de "Sincronizar carpeta" (solo cambian los textos).
            content: Qué contiene la carpeta ('auto' o una biblioteca), elegido en
                "¿Qué contiene esta carpeta?". None = no cambiar lo declarado (al
                sincronizar).
        """
        if self.db is None:
            return

        # Mientras dure, la acción queda desactivada: solo una importación a la vez
        self._add_folder_cancel = threading.Event()
        self._add_folder_is_sync = sync
        self.action_add_folder.setEnabled(False)
        verb = "Sincronizando carpeta" if sync else "Añadiendo carpeta al catálogo"
        message_bar(self, f"{verb}...", duracion=0)

        # 'add_folder' recibe la conexión como primer parámetro (la pone el gestor)
        self.db.execute_async(
            add_folder,
            folder,
            content=content,
            cancel_event=self._add_folder_cancel,
            progress=self.scan_progress.emit,
            on_result=self._on_add_folder_result,
            on_error=self._on_add_folder_error,
            on_finished=self._finish_add_folder,
        )

    def _on_add_folder_progress(self, progress: AddFolderProgress) -> None:
        """Actualiza la barra de estado con el avance (hilo principal)."""
        # Puede llegar una señal rezagada cuando el proceso ya terminó o se canceló
        if self._add_folder_cancel is None:
            return
        verb = (
            "Sincronizando carpeta" if self._add_folder_is_sync else "Añadiendo carpeta al catálogo"
        )
        message_bar(
            self,
            f"{verb}... {progress.saved_items} archivos procesados",
            duracion=0,
        )

    def _on_add_folder_result(self, result: AddFolderResult) -> None:
        """Muestra el resultado de añadir la carpeta (hilo principal)."""
        logger.info(f"Carpeta añadida al catálogo:\n{result.summary()}")

        # Lo recién añadido queda pendiente de leer: se empieza ya, mientras el usuario
        # lee el resumen (el cuadro de aviso no detiene el trabajo en segundo plano)
        if not result.cancelled:
            self._start_metadata_job()

        # Los archivos nuevos ya están en el catálogo: aparecen en la cuadrícula
        self.mosaico_model.reload()

        sync = self._add_folder_is_sync
        title = "Carpeta sincronizada" if sync else "Carpeta añadida"

        # Al SINCRONIZAR, si el recorrido fue completo y fiable, se mira cuántos archivos
        # de la carpeta están ausentes (los de ahora y los que ya lo estaban) para ofrecer
        # quitarlos del catálogo, como Lightroom
        reliable = not result.cancelled and result.missing_check_skipped is None
        if sync and reliable and self.db is not None:
            self.db.execute_async(
                count_missing_items,
                result.location.id,
                result.relative_folder,
                on_result=lambda count: self._show_add_folder_summary(result, title, count),
                on_error=lambda _error: self._show_add_folder_summary(result, title),
            )
            return
        self._show_add_folder_summary(result, title)

    def _show_add_folder_summary(
        self, result: AddFolderResult, title: str, missing_to_remove: int = 0
    ) -> None:
        """Muestra el resumen de añadir o sincronizar una carpeta.

        Si hay archivos ausentes que se pueden quitar, el resumen se convierte en una
        pregunta: quitarlos del catálogo o mantenerlos como ausentes.
        """
        needs_attention = bool(
            result.cancelled or result.stats.issues or result.missing_check_skipped
        )
        if needs_attention:
            message_bar(self, f"{title}, con avisos.", AppIcons.WARNING)
        else:
            message_bar(
                self,
                f"{title}: {result.new_items} archivos nuevos.",
                AppIcons.CHECK_CIRCLE,
            )

        if missing_to_remove > 0:
            answer = self.message_box.question(
                f"{result.summary()}\n\n"
                f"Hay {missing_to_remove} archivos que ya no están en la carpeta. "
                "¿Quitarlos del catálogo?\n\n"
                "Los archivos del disco no se tocan. Si alguno solo se ha movido o "
                "renombrado, se perderán su valoración y sus datos en el catálogo (salvo "
                "lo que ya esté escrito en el propio archivo).",
                title=title,
                buttons=["Quitar del catálogo", "Mantener como ausentes"],
            )
            if answer == "Quitar del catálogo":
                self._remove_missing(result.location.id, result.relative_folder)
        elif needs_attention:
            self.message_box.warning(result.summary(), title=title)
        else:
            self.message_box.info(result.summary(), title=title)

    # -------------------------------------------------------------------------
    # Quitar del catálogo los archivos ausentes
    # -------------------------------------------------------------------------

    def _on_remove_missing_requested(self, location_id: int, folder: str) -> None:
        """Menú de una carpeta > "Quitar archivos ausentes del catálogo...": cuenta y pregunta."""
        if self.db is None:
            return
        if self._add_folder_cancel is not None:
            self.message_box.info(
                "Se está añadiendo o sincronizando una carpeta.\n\n"
                "Espera a que termine antes de quitar archivos del catálogo."
            )
            return
        self.db.execute_async(
            count_missing_items,
            location_id,
            folder,
            on_result=lambda count: self._confirm_remove_missing(location_id, folder, count),
            on_error=lambda error: self.message_box.critical(
                f"No se pudieron contar los archivos ausentes.\n\nDetalle: {error}"
            ),
        )

    def _confirm_remove_missing(self, location_id: int, folder: str, count: int) -> None:
        """Pregunta antes de quitar del catálogo los ausentes de una carpeta."""
        if count == 0:
            self.message_box.info("En esta carpeta no hay archivos ausentes.")
            return
        answer = self.message_box.question(
            f"Hay {count} archivos de esta carpeta que ya no están en el disco.\n\n"
            "¿Quitarlos del catálogo? Los archivos del disco no se tocan. Si alguno solo se "
            "ha movido o renombrado, se perderán su valoración y sus datos en el catálogo "
            "(salvo lo que ya esté escrito en el propio archivo).",
            buttons=["Quitar del catálogo", "Cancelar"],
        )
        if answer == "Quitar del catálogo":
            self._remove_missing(location_id, folder)

    def _remove_missing(self, location_id: int, folder: str) -> None:
        """Quita del catálogo (en segundo plano) los ausentes de una carpeta."""
        if self.db is None:
            return
        self.db.execute_async(
            remove_missing_items,
            location_id,
            folder,
            catalog_dir=self.catalog_dir,
            on_result=self._on_missing_removed,
            on_error=lambda error: self.message_box.critical(
                f"No se pudieron quitar los archivos ausentes.\n\nDetalle: {error}"
            ),
        )

    def _on_missing_removed(self, result: RemovedItems) -> None:
        """Los ausentes ya no están en el catálogo: se recargan la cuadrícula y la barra lateral."""
        message_bar(
            self, f"Quitados del catálogo: {result.count} archivos ausentes.", AppIcons.CHECK_CIRCLE
        )
        # Al recargar, la barra lateral actualiza sola sus contadores y su árbol
        self.mosaico_model.reload()

    def _on_add_folder_error(self, error: Exception) -> None:
        """Informa de que no se pudo añadir la carpeta (hilo principal)."""
        message_bar(self, "No se pudo añadir la carpeta.", AppIcons.ERROR)

        if isinstance(error, (StorageLocationError, ScanError)):
            # Carpeta no válida, solapada con otra del catálogo...: el mensaje ya
            # está redactado para el usuario
            self.message_box.warning(str(error))
        else:
            self.message_box.critical(
                f"No se pudo añadir la carpeta al catálogo.\n\nDetalle: {error}"
            )

    def _finish_add_folder(self) -> None:
        """Restablece el estado tras añadir una carpeta (con éxito, error o cancelación)."""
        self._add_folder_cancel = None
        self.action_add_folder.setEnabled(True)

    # -------------------------------------------------------------------------
    # Eliminar (quitar del catálogo o enviar a la papelera)
    # -------------------------------------------------------------------------

    def _busy_reason(self) -> str | None:
        """Por qué ahora no se puede eliminar (algo en marcha), o None si se puede.

        Eliminar mientras se añade una carpeta o corre un trabajo podría dejar miniaturas
        de elementos ya quitados o escribir en un archivo que va a la papelera.
        """
        if self._add_folder_cancel is not None:
            return "Se está añadiendo una carpeta al catálogo."
        if self.job_manager is not None:
            for name, title in JOB_TITLES.items():
                if self.job_manager.is_running(name):
                    return f"Hay un trabajo en marcha: «{title}»."
        return None

    def _on_remove_requested(self, media_ids: list[int]) -> None:
        """«Eliminar...» de la cuadrícula: primero se calcula qué puede ir a la papelera."""
        if self.db is None or self.job_manager is None or not media_ids:
            return
        busy = self._busy_reason()
        if busy:
            self.message_box.info(f"{busy}\n\nEspera a que termine para eliminar archivos.")
            return
        ids = list(media_ids)
        self.db.execute_async(
            plan_removal,
            ids,
            on_result=lambda plan: self._on_removal_planned(ids, plan),
            on_error=lambda error: (
                logger.error(f"No se pudo preparar la eliminación: {error}"),
                message_bar(self, "No se pudo preparar la eliminación.", AppIcons.ERROR),
            ),
        )

    def _on_removal_planned(self, media_ids: list[int], plan: RemovalPlan) -> None:
        """Pregunta qué hacer (quitar del catálogo o papelera) y lanza el trabajo."""
        if self.db is None or self.job_manager is None or plan.total == 0:
            return  # el catálogo se cerró mientras tanto, o ya no existen
        # Mientras la ventana está abierta no debe arrancar la escritura diferida (su
        # temporizador sigue corriendo durante un diálogo modal): se para y, si no se
        # elimina, se vuelve a programar
        self._userdata_timer.stop()
        to_trash = RemoveDialog.ask(self, plan)
        busy = self._busy_reason() if to_trash is not None else None
        if to_trash is None or busy or self.job_manager is None:
            if busy:
                self.message_box.info(f"{busy}\n\nNo se ha eliminado nada; inténtalo al terminar.")
            self._schedule_userdata_write()
            return

        # Con la papelera no se escribe antes lo pendiente: el archivo se va
        self.job_manager.start(
            JOB_REMOVE,
            remove_media_items,
            media_ids,
            to_trash=to_trash,
            trash=move_to_trash if to_trash else None,
            write_pending=None if to_trash else self._pending_writer(),
        )

    def _pending_writer(self) -> Callable[..., object] | None:
        """Función que escribe lo pendiente antes de quitar algo del catálogo, o None.

        Antes de quitar del catálogo se escribe en los archivos lo pendiente (p. ej. unas
        estrellas puestas hace un instante), si la escritura en los archivos está activa y
        ya confirmada en esta sesión: así vuelve con el archivo si se sincroniza otra vez.
        """
        if self._write_to_files_enabled() and self._userdata_backlog_state == "ok":
            return write_pending_user_data
        return None

    def _start_removal_job(self, job: Callable[..., object], *args: object) -> None:
        """Lanza un trabajo de quitar del catálogo (p. ej. una carpeta) como "Eliminar".

        Con el mismo nombre (JOB_REMOVE): misma barra de progreso y, al terminar, lo mismo
        que tras eliminar ('_on_removal_finished'). Se vuelve a comprobar que no haya nada
        en marcha: puede haber empezado algo mientras se preguntaba al usuario.
        """
        if self.job_manager is None:
            return
        busy = self._busy_reason()
        if busy:
            self.message_box.info(f"{busy}\n\nNo se ha quitado nada; inténtalo al terminar.")
            return
        self.job_manager.start(JOB_REMOVE, job, *args, write_pending=self._pending_writer())

    def _on_removal_finished(self, result: object) -> None:
        """Terminó de eliminar: cuadrícula, contadores, aviso de fallos y trabajos en espera."""
        # Lo quitado desaparece de la cuadrícula (se pierde la selección, como al añadir)
        self.mosaico_model.reload()
        self._refresh_sidebar_counts()

        failed = list(getattr(result, "failed", ()))
        if failed:
            shown = "\n".join(Path(path).name for path, _message in failed[:REMOVE_FAILED_LIST_MAX])
            more = len(failed) - REMOVE_FAILED_LIST_MAX
            if more > 0:
                shown += f"\n... y {more} más"
            head = (
                "No se pudo enviar a la papelera 1 archivo (sigue en el catálogo y en su "
                "carpeta; quizá esté abierto en otro programa):"
                if len(failed) == 1
                else f"No se pudieron enviar a la papelera {len(failed)} archivos (siguen en "
                "el catálogo y en su carpeta; quizá estén abiertos en otro programa):"
            )
            self.message_box.warning(f"{head}\n\n{shown}\n\nEl detalle está en el registro.")
        self._resume_after_removal()

    def _resume_after_removal(self) -> None:
        """Lanza lo que se pidió mientras se eliminaba (metadatos, miniaturas, escritura)."""
        if self._metadata_after_removal:
            self._metadata_after_removal = False
            self._start_metadata_job()
        if self._thumbnails_after_removal:
            self._thumbnails_after_removal = False
            self._start_thumbnail_job()
        # Los cambios del usuario de los elementos que siguen en el catálogo, a los archivos
        self._userdata_rerun_requested = False
        self._schedule_userdata_write()

    # -------------------------------------------------------------------------
    # Trabajos en segundo plano (metadatos, miniaturas...)
    # -------------------------------------------------------------------------

    def _start_metadata_job(self) -> None:
        """Lanza la lectura de metadatos de los archivos pendientes, si no está ya en curso.

        Si se están escribiendo datos del usuario en los archivos, espera a que termine.
        """
        if self.job_manager is None:
            return
        if self.job_manager.is_running(JOB_USERDATA):
            self._metadata_after_userdata = True  # se lanza al terminar la escritura
            return
        if self.job_manager.is_running(JOB_REMOVE):
            self._metadata_after_removal = True  # se lanza al terminar de eliminar
            return
        self.job_manager.start(JOB_METADATA, process_pending_metadata)

    def _start_thumbnail_job(self) -> None:
        """Lanza la generación de miniaturas de los archivos pendientes, si no está ya en curso."""
        if self.job_manager is None:
            return
        if self.job_manager.is_running(JOB_REMOVE):
            # Generar a la vez dejaría miniaturas de elementos ya quitados del catálogo
            self._thumbnails_after_removal = True
            return
        if not self.job_manager.start(JOB_THUMBNAILS, generate_pending_thumbnails):
            # Ya hay una pasada en curso. Puede haber empezado antes de que se marcaran más
            # archivos como pendientes (p. ej. una regeneración): se repetirá al terminar
            self._thumbnail_rerun_requested = True

    def regenerate_thumbnails(
        self, media_ids: list[int] | None = None, *, only_errors: bool = False
    ) -> None:
        """Regenera miniaturas a demanda: las marca como pendientes y lanza el trabajo.

        Es la función a la que llamará el menú contextual de la cuadrícula con los 'id' de la
        selección. Con 'media_ids=None' afecta a todo el catálogo; con 'only_errors=True', solo
        a los archivos cuya miniatura falló. Los metadatos no se tocan.
        """
        if self.db is None:
            self.message_box.warning("Primero hay que crear o abrir un catálogo.")
            return
        self.db.execute_async(
            invalidate_thumbnails,
            media_ids,
            only_errors=only_errors,
            on_result=self._on_thumbnails_invalidated,
            on_error=self._on_regenerate_thumbnails_error,
        )

    def _on_thumbnails_invalidated(self, count: int) -> None:
        """Los archivos ya están marcados como pendientes: se lanza el trabajo (hilo principal)."""
        if count == 0:
            message_bar(self, "No hay miniaturas que regenerar.", AppIcons.INFO)
            return
        self._start_thumbnail_job()

    def _on_regenerate_thumbnails_error(self, error: Exception) -> None:
        """No se pudieron marcar las miniaturas como pendientes (hilo principal)."""
        message_bar(self, "No se pudo preparar la regeneración.", AppIcons.ERROR)
        self.message_box.critical(
            f"No se pudo preparar la regeneración de miniaturas.\n\nDetalle: {error}"
        )

    def _on_regenerate_failed_thumbnails(self) -> None:
        """Acción del menú: regenera solo las miniaturas que fallaron."""
        self.regenerate_thumbnails(only_errors=True)

    def _on_regenerate_all_thumbnails(self) -> None:
        """Acción del menú: regenera las miniaturas de todo el catálogo (pide confirmación)."""
        if self.db is None:
            self.message_box.warning("Primero hay que crear o abrir un catálogo.")
            return
        answer = self.message_box.question(
            "Se volverán a generar las miniaturas de todos los archivos del catálogo.\n\n"
            "Puede tardar bastante. ¿Continuar?",
            buttons=["Regenerar", "Cancelar"],
        )
        if answer == "Regenerar":
            self.regenerate_thumbnails()

    def _on_job_progress(self, name: str, progress: JobProgress) -> None:
        """Muestra el avance de un trabajo en la barra de estado (hilo principal)."""
        # Puede llegar un aviso rezagado de un trabajo que ya terminó o se canceló
        if self.job_manager is None or not self.job_manager.is_running(name):
            return

        # Mientras se generan miniaturas, las tarjetas que estaban vacías se reintentan cada
        # poco: así van apareciendo sin esperar a que termine toda la pasada
        if name == JOB_THUMBNAILS:
            now = time.monotonic()
            if now - self._last_thumb_refresh >= 1.5:
                self._last_thumb_refresh = now
                self.mosaico_model.retry_missing()

        widget = self._job_widgets.get(name)
        if widget is None:
            if progress.total == 0:
                return  # no hay nada que hacer: no se muestra la barra
            if name in (JOB_USERDATA, JOB_REMOVE) and progress.total < USERDATA_PROGRESS_MIN_ITEMS:
                # Escritura breve tras unos clics, o eliminar unos pocos archivos: sin barra
                # que aparezca y desaparezca en un instante
                return
            widget = JobProgressWidget(JOB_TITLES.get(name, name))
            widget.cancel_requested.connect(lambda: self._on_job_cancel_requested(name))
            self.statusBar().addPermanentWidget(widget)
            self._job_widgets[name] = widget

        widget.set_progress(progress.done, progress.total)

    def _on_job_cancel_requested(self, name: str) -> None:
        """El usuario pulsó "Cancelar" en la barra de progreso de un trabajo."""
        if self.job_manager is not None:
            self.job_manager.cancel(name)

    def _on_job_finished(self, name: str, result: object) -> None:
        """Un trabajo terminó (o se canceló): se retira su barra y se informa (hilo principal)."""
        self._remove_job_widget(name)

        # Cada resultado ofrece 'status_text()' y 'has_warnings' (ver core.jobs.progress)
        text = result.status_text()
        if text:  # vacío = no había nada que hacer: no se molesta al usuario
            icon = AppIcons.WARNING if result.has_warnings else AppIcons.CHECK_CIRCLE
            message_bar(self, text, icon)

        # Eliminar: la cuadrícula y los contadores, al día; lo que esperaba, se lanza
        if name == JOB_REMOVE:
            self._on_removal_finished(result)
            return

        # Las miniaturas recién generadas (o regeneradas) se vuelven a leer de la caché
        if name == JOB_THUMBNAILS:
            self.mosaico_model.refresh_thumbnails(getattr(result, "generated_ids", ()))
            self.mosaico_model.retry_missing()

        # Al terminar los metadatos, la rejilla se vuelve a leer: valoración, marca y color
        # pueden haberse rellenado desde el XMP de los archivos. Antes, los vídeos que siguen
        # sin biblioteca se clasifican con los metadatos recién leídos (cámara, GPS,
        # duración): así la cuadrícula se recarga una sola vez, ya con todo
        if name == JOB_METADATA and self.db is not None:
            self.db.execute_async(
                classify_pending_videos,
                on_result=lambda count: self._on_videos_classified(count, reload_always=True),
                on_error=lambda error: (
                    logger.warning(f"No se pudieron clasificar los vídeos: {error}"),
                    self.mosaico_model.reload(),
                ),
            )

        # Encadenado: las miniaturas se generan al terminar los metadatos (salvo que el usuario
        # los haya cancelado), y se repite la pasada si se pidió una regeneración mientras corría
        if name == JOB_METADATA and not getattr(result, "cancelled", False):
            self._start_thumbnail_job()
        elif name == JOB_THUMBNAILS and self._thumbnail_rerun_requested:
            self._thumbnail_rerun_requested = False
            self._start_thumbnail_job()

        # Escritura de los datos del usuario y lectura de metadatos, siempre por turnos:
        #   - Al terminar los metadatos se escribe lo pendiente (al abrir el catálogo, lo
        #     que quedó de la sesión anterior).
        #   - Al terminar de escribir, si se pidió leer metadatos mientras tanto, o si se
        #     vio que algún archivo había cambiado fuera (p. ej. en Lightroom), se leen;
        #     al acabar esa lectura se volverá a escribir lo que siga pendiente.
        #   - Si no, y hubo cambios mientras escribía, se escribe otra vez.
        if name == JOB_METADATA:
            self._userdata_rerun_requested = False
            self._start_userdata_job()
        elif name == JOB_USERDATA:
            if self._metadata_after_userdata or getattr(result, "rescan_requested", 0):
                self._metadata_after_userdata = False
                self._userdata_rerun_requested = False  # se escribirá tras la lectura
                self._start_metadata_job()
            elif self._userdata_rerun_requested:
                self._userdata_rerun_requested = False
                self._start_userdata_job()

    def _on_job_failed(self, name: str, error: Exception) -> None:
        """Un trabajo falló con una excepción (hilo principal)."""
        self._remove_job_widget(name)
        title = JOB_TITLES.get(name, name)
        message_bar(self, f"Error en el trabajo: {title}", AppIcons.ERROR)
        if name == JOB_REMOVE:
            # Lo que se llegó a quitar está confirmado por lotes: se muestra lo que hay
            self.mosaico_model.reload()
            self._refresh_sidebar_counts()
            self._resume_after_removal()
        # Las miniaturas no dependen de los metadatos: se generan igualmente (antes del cuadro
        # modal), y lo pendiente de escribir en los archivos, también
        if name == JOB_METADATA:
            self._start_thumbnail_job()
            self._start_userdata_job()
        elif name == JOB_USERDATA and self._metadata_after_userdata:
            self._metadata_after_userdata = False
            self._start_metadata_job()  # la lectura que esperaba a la escritura
        self.message_box.critical(
            f"Ha fallado el trabajo «{title}».\n\nDetalle: {error}"
        )

    def _remove_job_widget(self, name: str) -> None:
        """Quita de la barra de estado el widget de progreso de un trabajo."""
        widget = self._job_widgets.pop(name, None)
        if widget is not None:
            self.statusBar().removeWidget(widget)
            widget.deleteLater()

    def _clear_job_widgets(self) -> None:
        """Quita todos los widgets de progreso (al cerrar el catálogo)."""
        for name in list(self._job_widgets):
            self._remove_job_widget(name)
