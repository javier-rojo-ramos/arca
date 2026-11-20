# Librerías estándar
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
)
from qtpy.QtGui import (
    QAction,
    QCloseEvent,
    QMoveEvent,
    QShowEvent,
)
from qtpy.QtWidgets import QAbstractItemView, QListView, QMainWindow, QToolButton

# Módulos del proyecto
from config import app_paths
from config.app_config import config
from config.app_constants import (
    SETTING_GPU_RENDERING,
    SETTING_MAIN_SPLITTER_STATE,
    SETTING_MAP_GPU_RENDERING,
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
from controllers.file_actions import FileActions
from controllers.filter_controller import FilterController
from controllers.filter_preset_controller import FilterPresetController
from controllers.folder_actions import FolderActions
from controllers.folder_import import FolderImport
from controllers.inspector_controller import InspectorController
from controllers.job_coordinator import JobCoordinator
from controllers.locate_actions import LocateActions
from controllers.map_controller import MapController
from controllers.metadata_filter_controller import MetadataFilterController
from controllers.remove_actions import RemoveActions
from controllers.sidebar_visibility import SidebarVisibility
from controllers.undo_history import UndoHistory
from core.catalog.availability import AvailabilityCheck, check_availability
from core.catalog.catalog_builder import CatalogBuilder, CatalogError
from core.catalog.catalog_opener import open_catalog
from core.catalog.grid_source import ALL_ITEMS, SourceKind
from core.catalog.libraries import (
    classify_pending_videos,
    set_library,
)
from core.catalog.media_queries import (
    clear_quick_selection,
    set_quick_selection,
    update_user_field,
)
from core.catalog.storage_locations import refresh_location_status
from core.database.db_manager import CatalogDatabaseManager

# UI generada, helpers, mixins
from ui.main_window import Ui_MainWindow
from ui_helpers.delegates.thumbnails_delegate import ThumbnailsDelegate
from ui_helpers.dialogs.settings_dialog import SettingsDialog
from ui_helpers.helpers.app_icon import build_app_icon
from ui_helpers.helpers.gpu_composition import enable_gpu_composition, gpu_allowed
from ui_helpers.helpers.grid_actions import GridActions
from ui_helpers.helpers.mode_toolbar import toolbar_accent_color
from ui_helpers.helpers.ui_file_dialogs import select_folder
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar
from ui_helpers.helpers.ui_theme import TOOLBAR_ICON_SIZE, TOOLBAR_MARGIN
from ui_helpers.inspector.inspector_panel import InspectorPanel
from ui_helpers.layout.section_layout_model import SectionLayoutModel
from ui_helpers.layout.section_registry import SECTION_REGISTRY
from ui_helpers.mixins.window_snap import WindowSnapMixin
from ui_helpers.models.media_grid_model import QUICK_SELECTION_FIELD, MediaGridModel
from ui_helpers.widgets.attribute_filter_row import AttributeFilterRow
from ui_helpers.widgets.map_page import MapPage
from ui_helpers.widgets.metadata_filter_panel import MetadataFilterPanel
from ui_helpers.widgets.text_filter_row import TextFilterRow

# Los trabajos en segundo plano (nombres, títulos, encadenado, escritura diferida...) están
# en 'controllers/job_coordinator.py' (GEN 15.1); añadir y sincronizar carpetas, en
# 'controllers/folder_import.py' (GEN 15.2), y eliminar, en 'controllers/remove_actions.py'
# (GEN 15.3)

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


class MainWindowController(QMainWindow, Ui_MainWindow, WindowSnapMixin):
    """Controlador principal de la ventana de Arca Media."""

    def __init__(self) -> None:
        super().__init__()

        WindowSnapMixin.__init__(self)
        self.setupUi(self)

        self.message_box = MessageBoxHelper(self)
        self.config = config

        # La ventana, dibujada con la GPU desde que se abre (antes de mostrarla: ver
        # 'gpu_composition'). Opción de Opciones > General (sin elegir, según el sistema);
        # '--sin-gpu' para arrancar sin ella
        if gpu_allowed(self.config.get(SETTING_GPU_RENDERING)):
            enable_gpu_composition(self)

        # --- Estado del Mosaico de Miniaturas ---
        # El modelo lee la lista de la base de datos del catálogo y las miniaturas de su caché
        self.mosaico_model = MediaGridModel(self)
        self.mosaico_delegate = ThumbnailsDelegate(self)

        # --- Estado del catálogo activo ---
        # Gestor de la base de datos (None mientras no haya catálogo abierto)
        self.db: CatalogDatabaseManager | None = None
        # Carpeta del catálogo activo (la que contiene 'catalogo.db')
        self.catalog_dir: Path | None = None
        # Trabajos en segundo plano del catálogo activo (metadatos, miniaturas, escritura en
        # los archivos, eliminar): qué se lanza, cuándo y qué espera a qué. Lo que toca la
        # cuadrícula lo pide con señales (ver 'controllers/job_coordinator.py')
        self.job_coordinator = JobCoordinator(self, self.message_box, self.config, parent=self)
        self.job_coordinator.thumbnails_progressed.connect(self.mosaico_model.retry_missing)
        self.job_coordinator.thumbnails_generated.connect(self._on_thumbnails_generated)
        self.job_coordinator.metadata_read.connect(self._on_metadata_read)
        # Añadir y sincronizar carpetas, con su resumen y «Quitar archivos ausentes» (ver
        # 'controllers/folder_import.py'; las acciones y la barra lateral, en '_conectar_senales')
        self.folder_import = FolderImport(
            self,
            self.message_box,
            self.config,
            action=self.action_add_folder,
            get_db=lambda: self.db,
            get_catalog_dir=lambda: self.catalog_dir,
            start_metadata=self.job_coordinator.start_metadata,
            reload_grid=self.mosaico_model.reload,
            parent=self,
        )
        # «Eliminar...» y lo que se hace al terminar cualquier trabajo de quitar (ver
        # 'controllers/remove_actions.py'; la cuadrícula lo pide en '_configurar_grid_mosaico')
        self.remove_actions = RemoveActions(
            self,
            self.message_box,
            self.job_coordinator,
            get_db=lambda: self.db,
            is_adding_folder=lambda: self.folder_import.is_running,
            reload_grid=self.mosaico_model.reload,
            refresh_counts=self._refresh_sidebar_counts,
            parent=self,
        )
        # «Cambiar nombre...» de un archivo (ver 'controllers/file_actions.py'; la cuadrícula
        # lo pide en '_configurar_grid_mosaico')
        self.file_actions = FileActions(
            self,
            self.message_box,
            self.job_coordinator,
            get_db=lambda: self.db,
            busy_reason=self.remove_actions.busy_reason,
            reload_grid=self.mosaico_model.reload,
            refresh_counts=self._refresh_sidebar_counts,
            # Tras renombrar una carpeta, cada módulo pone al día su barra (lo elegido)
            folder_renamed=lambda *args: (
                self.module_host.folder_renamed(*args) if self.module_host is not None else None
            ),
            # Las tarjetas soltadas de otro catálogo (otra ventana) no se mueven
            get_catalog_key=lambda: str(self.catalog_dir) if self.catalog_dir else "",
            # «Nueva carpeta» con lo elegido dentro; al crearla, se despliega la de encima
            get_selected_ids=lambda: self.grid_actions.selected_ids(),
            folder_created=lambda *args: self.widget_catalog_sidebar.expand_to_folder(*args),
            parent=self,
        )

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
        # Panel «Metadatos» de la barra de filtros (recuentos): se crea en '_conectar_filtros'
        self.metadata_filters: MetadataFilterController | None = None
        # Vista «Mapa» del centro: se crea en '_conectar_vistas'
        self.map_controller: MapController | None = None
        # Deshacer (Ctrl+Z en toda la ventana; hoy, lo hecho en el mapa)
        self.undo_history = UndoHistory(self)
        self.undo_history.undone.connect(lambda text: message_bar(self, f"Deshecho: {text}"))
        self.undo_history.nothing_to_undo.connect(
            lambda: message_bar(self, "No hay nada que deshacer.")
        )

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
            # Y la barra: el árbol de «Carpetas» mira qué carpetas ya no están en el disco
            # (borradas o recuperadas de la Papelera fuera de la aplicación; CAT 6.2)
            # (getattr: Qt puede avisar de la activación antes de terminar el __init__)
            if getattr(self, "db", None) is not None:
                self._sidebar_refresh_timer.start()

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
        self.action_load_folder.triggered.connect(self.folder_import.request_add)

        # Acciones del menú relacionadas con el catálogo
        self.action_new_catalog.triggered.connect(self._on_new_catalog)
        self.action_open_catalog.triggered.connect(self._on_new_catalog)
        self.action_add_folder.triggered.connect(self.folder_import.request_add)

        # "Salir" (Ctrl+Q): cierra la ventana por el mismo camino que la X, así que pasa por
        # 'closeEvent' (cancela los trabajos, guarda el estado y libera el catálogo)
        self.action_exit.triggered.connect(self.close)

        # Acciones de regeneración de miniaturas (creadas en _crear_acciones_miniaturas)
        self.action_regenerate_failed_thumbnails.triggered.connect(
            self.job_coordinator.regenerate_failed_thumbnails
        )
        self.action_regenerate_all_thumbnails.triggered.connect(
            self.job_coordinator.regenerate_all_thumbnails
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
        self.widget_catalog_sidebar.add_folder_requested.connect(self.folder_import.request_add)
        # Menú contextual de las carpetas
        self.widget_catalog_sidebar.sync_folder_requested.connect(self.folder_import.request_sync)
        self.widget_catalog_sidebar.remove_missing_requested.connect(
            self.folder_import.request_remove_missing
        )
        # "Quitar del catálogo..." y "Mostrar en el Explorador" de una carpeta: los atiende
        # 'controllers/folder_actions.py'; el trabajo de quitar va por el mismo camino que
        # "Eliminar" ('RemoveActions.start_removal_job')
        self._folder_actions = FolderActions(
            self,
            self.widget_catalog_sidebar,
            self.message_box,
            get_db=lambda: self.db,
            busy_reason=self.remove_actions.busy_reason,
            start_removal=self.remove_actions.start_removal_job,
        )
        # «Localizar...» de una ubicación desconectada (CAT 6.3): 'controllers/locate_actions.py'
        self._locate_actions = LocateActions(
            self,
            self.widget_catalog_sidebar,
            self.message_box,
            get_db=lambda: self.db,
            busy_reason=self.remove_actions.busy_reason,
            reload_grid=self.mosaico_model.reload,
        )
        # "Cambiar nombre..." de una carpeta: lo atiende 'controllers/file_actions.py'
        self.widget_catalog_sidebar.rename_folder_requested.connect(
            self.file_actions.request_folder_rename
        )
        # Tarjetas soltadas sobre una carpeta del árbol: moverlas a ella (CAT 4.4b)
        self.widget_catalog_sidebar.media_dropped_on_folder.connect(self.file_actions.request_move)
        # "Crear nueva carpeta..." de una carpeta del árbol (CAT 4.4a)
        self.widget_catalog_sidebar.new_folder_requested.connect(
            self.file_actions.request_new_folder
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
        self.grid_actions.regenerate_requested.connect(self.job_coordinator.regenerate_thumbnails)
        # Menú "Biblioteca": clasificar vídeos a mano (clip personal o película)
        self.grid_actions.library_change_requested.connect(self._on_library_change_requested)
        # "Eliminar..." (menú de la tarjeta y Supr fuera de las colecciones estáticas)
        self.grid_actions.remove_requested.connect(self.remove_actions.request_remove)
        # "Cambiar nombre..." (menú de la tarjeta y F2)
        self.grid_actions.rename_requested.connect(self.file_actions.request_rename)

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
        self.job_coordinator.schedule_write()
        self._sidebar_refresh_timer.start()  # si ya estaba en marcha, vuelve a empezar

    def _on_grid_save_error(self, error: Exception) -> None:
        """No se pudo guardar un cambio de la cuadrícula: se avisa y se vuelve a leer del catálogo."""
        logger.error(f"No se pudo guardar el cambio en el catálogo: {error}")
        message_bar(
            self, "No se pudo guardar el cambio en el catálogo.", AppIcons.ERROR
        )
        self.mosaico_model.reload()  # la cuadrícula vuelve a mostrar lo que hay realmente guardado

    # -------------------------------------------------------------------------
    # Ventana de opciones
    # -------------------------------------------------------------------------

    def _on_open_settings(self) -> None:
        """Abre la ventana de opciones y aplica lo que haya cambiado."""
        # Mientras está abierta, el icono del botón se queda en el color de acento
        changed: set[str] = set()
        self.btn_settings.setIcon(self.icon_settings_active)
        try:
            active = self.module_host.active_module if self.module_host is not None else None
            dialog = SettingsDialog(
                self.config,
                context={
                    "catalog_dir": self.catalog_dir,
                    # Para la página «Paneles»: el modelo de la colocación de las secciones
                    # y el módulo que se enseña al abrir
                    "section_layout": getattr(self, "section_layout", None),
                    "active_mode": active.key if active is not None else None,
                },
                parent=self,
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
        # La aceleración por GPU (la de la ventana y la de los mapas) se aplica al volver a
        # abrir la aplicación: se avisa
        if changed & {SETTING_GPU_RENDERING, SETTING_MAP_GPU_RENDERING}:
            self.message_box.info(
                "El cambio de la aceleración por GPU se aplicará al volver a abrir la aplicación."
            )

        # El mapa: capas propias y tope de la caché de teselas
        if self.map_controller is not None:
            self.map_controller.apply_settings(changed)

        # Si se acaba de activar la escritura en los archivos, se escribe lo pendiente (el
        # usuario lo ha pedido expresamente: no se vuelve a preguntar)
        if SETTING_WRITE_USER_DATA_TO_FILES in changed:
            self.job_coordinator.write_option_changed()

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
        # Colocación de las secciones de las dos barras (orden, visibles, plegadas), por
        # modo: la comparten las barras de los módulos y el inspector
        self.section_layout = SectionLayoutModel(SECTION_REGISTRY, self.config, parent=self)
        context = ModuleContext(
            window=self,
            config=self.config,
            message_box=self.message_box,
            grid_view=self.list_view_grid,
            grid_model=self.mosaico_model,
            grid_actions=self.grid_actions,
            section_layout=self.section_layout,
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
        self._conectar_filtros()
        self._configurar_inspector()
        # Mostrar u ocultar las barras laterales (menú «Ver», F7, F8 y Tab): después de crear
        # las barras de los módulos y el inspector (pone «Ocultar barra» en sus menús)
        self.sidebar_visibility = SidebarVisibility(
            left=self.widget_sidebar_catalog,
            right=self.widget_sidebar_metadata,
            left_action=self.action_show_left_sidebar,
            right_action=self.action_show_right_sidebar,
            config=self.config,
            focus_view=self.center_views.focus_view,
            parent=self,
        )

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
        # La página del mapa (el mapa se crea la primera vez que se ve: ver 'MapPage')
        map_page = MapPage(self.stacked_widget_main)
        self.stacked_widget_main.addWidget(map_page)
        self.center_views = CenterViewController(
            self.module_host,
            buttons=buttons,
            stack=self.stacked_widget_main,
            pages={
                CenterView.GRID: self.page_grid,
                CenterView.SINGLE: page_single,
                CenterView.MAP: map_page,
            },
            size_slider=self.slider_thumbnails,
            grid=self.list_view_grid,
            single=single_view,
            map_page=map_page,
            parent=self,
        )
        # Los atajos de clasificación (estrellas, color, marca, B, Supr), también en ellas
        self.grid_actions.watch(single_view)
        self.grid_actions.watch(map_page)
        self.grid_actions.watch(map_page.filmstrip)
        # La tira de fotos del mapa: G a la cuadrícula, Intro a la vista individual
        self.center_views.watch_map_widget(map_page.filmstrip)
        # El mapa: lo mismo que la cuadrícula, con su selección (ver 'MapController')
        self.map_controller = MapController(
            self.module_host,
            page=map_page,
            grid=self.list_view_grid,
            model=self.mosaico_model,
            center_views=self.center_views,
            layer_bar=self.layout_bottom_right,
            config=self.config,
            message_box=self.message_box,
            parent=self,
        )

    def _conectar_filtros(self) -> None:
        """Barra de filtros de la franja superior (ver 'FilterController')."""
        bar = getattr(self, "widget_filter_bar", None)
        if bar is None or self.module_host is None:
            logger.warning(
                "Falta 'widget_filter_bar' en la ventana: ejecuta scripts/build_ui.py para "
                "regenerar ui/main_window.py desde el .ui."
            )
            return
        # El panel «Metadatos» y sus recuentos en segundo plano (ver 'MetadataFilterController')
        self.metadata_filters = MetadataFilterController(
            self.module_host,
            panel=MetadataFilterPanel(bar),
            model=self.mosaico_model,
            config=self.config,
            parent=self,
        )
        # Tras los cambios del usuario (estrellas, palabras clave...), sus recuentos también
        self._sidebar_refresh_timer.timeout.connect(self.metadata_filters.refresh_counts)
        # Ajustes personalizados: el desplegable antes del candado (ver 'FilterPresetController')
        presets = FilterPresetController(
            self.module_host,
            button=bar.preset_button,
            config=self.config,
            window=self,
            parent=self,
        )
        self.filters = FilterController(
            self.module_host,
            bar=bar,
            frame=self.frame_main_top,
            window=self,
            text_row=TextFilterRow(bar),
            attribute_row=AttributeFilterRow(bar),
            metadata=self.metadata_filters,
            presets=presets,
            parent=self,
        )

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
        # ...y el mapa (p. ej. tras cambiar el GPS de una foto, su marcador va a su sitio)
        if self.map_controller is not None:
            self.inspector.edit_finished.connect(self.map_controller.refresh)
            # Las fotos ubicadas en el mapa se guardan por la misma cola que el inspector y
            # se pueden deshacer
            self.map_controller.set_edit_queue(self.inspector.request_edit)
            self.map_controller.set_undo_history(self.undo_history)
        # El inspector es el mismo en todos los módulos (sus secciones dependen de la
        # selección, no del módulo)
        if self.module_host is not None:
            # ...pero cada módulo tiene su colocación de las secciones (orden, visibles y
            # plegadas): el panel la toma del modelo y la cambia con el módulo
            active = self.module_host.active_module
            panel.bind_layout(self.section_layout, active.key if active is not None else "")
            self.module_host.module_changed.connect(panel.set_layout_mode)
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
        que un botón nuevo en el .ui se centra solo. Sus iconos, de 'TOOLBAR_ICON_SIZE'
        (ui_theme.py; manda sobre el tamaño del .ui). Qué hace cada botón de módulo (icono,
        barra lateral...) lo deciden los módulos: ver '_configurar_modulos'.
        """
        all_buttons = self.frame_toolbar.findChildren(QToolButton)
        button_width = max(button.minimumSize().width() for button in all_buttons)
        self.frame_toolbar.setFixedWidth(button_width + 2 * TOOLBAR_MARGIN)
        # Los lados ya los da el ancho fijo (botones centrados): aquí, arriba y abajo
        self.layout_toolbar.setContentsMargins(0, TOOLBAR_MARGIN, 0, TOOLBAR_MARGIN)
        for button in all_buttons:
            self.layout_toolbar.setAlignment(button, Qt.AlignmentFlag.AlignHCenter)
            button.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))

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
        # El icono de la ventana (y de la barra de tareas), con el juego de cada sistema
        self.setWindowIcon(build_app_icon())

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
        if self.folder_import.is_running:
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

        # Trabajos en segundo plano de este catálogo
        self.job_coordinator.attach(self.db)
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
            if self.map_controller is not None:  # el encuadre del mapa de cada módulo
                self.map_controller.restore_state(self.module_host.saved_entry(self.catalog_dir))
            self.module_host.attach(self.db, self.catalog_dir)
        if self.inspector is not None:
            self.inspector.attach(self.db)
        if self.metadata_filters is not None:
            self.metadata_filters.attach(self.db)
        if self.map_controller is not None:
            self.map_controller.attach(self.db)

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
        self.job_coordinator.start_metadata()
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
        """Comprueba en segundo plano los discos, las carpetas que faltan y los archivos
        de las tarjetas visibles.

        Las carpetas y los archivos solo se miran si la ventana está activa (si no, nadie
        los está viendo); los discos, siempre (es una consulta por ubicación).
        """
        # (getattr: Qt puede avisar de la activación antes de terminar el __init__)
        if getattr(self, "db", None) is None or getattr(
            self, "_availability_check_running", True
        ):
            return
        active = self.isActiveWindow()
        media_ids = self._visible_media_ids() if active else []
        self._availability_check_running = True
        self.db.execute_async(
            check_availability,
            media_ids,
            active,
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
            self.job_coordinator.start_metadata()
        if (result.switched_locations or result.missing_folders) and self.db is not None:
            # Un disco se ha conectado o desconectado, o falta una carpeta: el árbol de
            # «Carpetas» lo muestra (atenuado y con su aviso); sin esto, solo cambiaban las
            # tarjetas
            self._sidebar_refresh_timer.start()

    def _on_availability_check_finished(self) -> None:
        self._availability_check_running = False

    def _close_catalog(self) -> None:
        """Cierra el catálogo activo, si lo hay, cancelando lo que esté en marcha."""
        # Añadir una carpeta se detiene en cuanto puede: lo ya guardado se conserva
        self.folder_import.cancel()

        # Los trabajos paran en cuanto pueden ('db.shutdown()', más abajo, espera a que
        # acaben); lo que quede sin escribir sigue pendiente en el catálogo
        self.job_coordinator.detach()
        self._availability_timer.stop()
        self._availability_check_running = False
        self._sidebar_refresh_timer.stop()

        # Lo desplegado en las barras laterales se guarda ANTES de vaciarlas
        # (getattr: Qt puede cerrar la ventana antes de terminar 'iniciar')
        module_host = getattr(self, "module_host", None)
        if module_host is not None and self.catalog_dir is not None:
            # Con lo del inspector (lo desplegado de su árbol de palabras clave) y el
            # encuadre del mapa de cada módulo
            inspector = getattr(self, "inspector", None)
            extra = dict(inspector.save_state()) if inspector is not None else {}
            map_controller = getattr(self, "map_controller", None)
            if map_controller is not None:
                extra.update(map_controller.save_state())
            module_host.save_state(self.catalog_dir, extra=extra or None)

        self.mosaico_model.detach()  # vacía la cuadrícula y deja de pedir datos a la base
        if module_host is not None:
            # Cada módulo olvida el catálogo y vacía su barra ("Todos los archivos" y sin
            # contadores, en el Catálogo)
            module_host.detach()
        inspector = getattr(self, "inspector", None)
        if inspector is not None:
            inspector.detach()  # se descartan los resúmenes pendientes y se vacía el panel
        if self.metadata_filters is not None:
            self.metadata_filters.detach()  # se descartan los recuentos pendientes
        if self.map_controller is not None:
            self.map_controller.detach()  # se descarta lo pedido y se vacía el mapa
        self.undo_history.clear()  # lo hecho en este catálogo no se deshace en otro

        if self.db is not None:
            # 'shutdown' espera a las tareas en curso (rápido, porque se han cancelado)
            self.db.shutdown()
            self.db.deleteLater()
            self.db = None

        # Sus callbacks ya no se ejecutarán, así que el estado se restablece aquí
        self.folder_import.finish()
        self.catalog_dir = None

    # -------------------------------------------------------------------------
    # Avisos de los trabajos en segundo plano ('controllers/job_coordinator.py')
    # -------------------------------------------------------------------------

    def _on_thumbnails_generated(self, media_ids: object) -> None:
        """Las miniaturas recién generadas (o regeneradas) se vuelven a leer de la caché."""
        self.mosaico_model.refresh_thumbnails(media_ids)
        self.mosaico_model.retry_missing()

    def _on_metadata_read(self) -> None:
        """Terminó la lectura de metadatos: la rejilla se vuelve a leer.

        Valoración, marca y color pueden haberse rellenado desde el XMP de los archivos.
        Antes, los vídeos que siguen sin biblioteca se clasifican con los metadatos recién
        leídos (cámara, GPS, duración): así la cuadrícula se recarga una sola vez, ya con todo.
        """
        if self.db is None:
            return
        self.db.execute_async(
            classify_pending_videos,
            on_result=lambda count: self._on_videos_classified(count, reload_always=True),
            on_error=lambda error: (
                logger.warning(f"No se pudieron clasificar los vídeos: {error}"),
                self.mosaico_model.reload(),
            ),
        )
