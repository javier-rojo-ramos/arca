"""Los trabajos en segundo plano del catálogo abierto: qué se lanza, cuándo y qué espera a qué.

Sacado de 'main_window_controller.py' (docs/PENDIENTE.md, GEN 15.1) SIN CAMBIAR lo que
hace: el código se movió tal cual; solo cambia cómo se habla con la ventana (lo que toca
la cuadrícula se pide con señales).

Trabajos (su nombre en el 'JobManager' y el título de su barra en la barra de estado):
    metadata    «Leyendo metadatos»          'process_pending_metadata'
    thumbnails  «Generando miniaturas»       'generate_pending_thumbnails'
    userdata    «Guardando en los archivos»  'write_pending_user_data'
    remove      «Eliminando»                 lo que pida quien elimina ('start_removal')
    files       «Moviendo archivos»          renombrar o mover archivos ('start_file_job';
                                             'core/file_ops/moves.execute_file_moves')

Reglas del encadenado:
    - Al abrir un catálogo, al añadir o sincronizar una carpeta y al volver archivos que
      cambiaron mientras faltaban, se leen los metadatos pendientes ('start_metadata').
    - Al terminar la lectura (salvo que se cancele) se generan las miniaturas, y se
      escribe en los archivos lo pendiente (al abrir, lo que quedó de la sesión anterior).
    - La lectura y la escritura nunca van a la vez (una podría leer un archivo mientras la
      otra lo escribe): lo que se pide mientras corre la otra se lanza al terminar. Si la
      escritura ve archivos cambiados fuera (p. ej. en Lightroom), se releen.
    - Mientras se elimina, o se renombran o mueven archivos, no se lanza nada más (los
      otros trabajos usan las rutas): lo pedido se lanza al terminar.
    - Un cambio del usuario se escribe tras USERDATA_WRITE_DELAY_MS sin más cambios
      ('schedule_write'); si llega uno mientras escribe, se repite al terminar.
    - La primera escritura de cada catálogo cuenta lo pendiente: con
      USERDATA_CONFIRM_MIN_ITEMS o más, pregunta antes («Más tarde» = nada en esta sesión).
    - «Regenerar miniaturas» las marca como pendientes y lanza su trabajo; si ya hay una
      pasada en curso, se repite al terminar.
    - Avance: la lectura de metadatos, en su ventana ('metadata_progress.py', que bloquea
      la aplicación); los demás, en la barra de estado (la escritura y eliminar, solo con
      USERDATA_PROGRESS_MIN_ITEMS o más).

Uso (en el controlador principal, que solo lo crea, lo conecta y le pasa cada catálogo):
    self.job_coordinator = JobCoordinator(self, self.message_box, self.config, parent=self)
    self.job_coordinator.thumbnails_progressed.connect(self.mosaico_model.retry_missing)
    self.job_coordinator.thumbnails_generated.connect(...)   # ver las señales de la clase
    ...
    self.job_coordinator.attach(self.db)      # al abrir un catálogo
    self.job_coordinator.start_metadata()
    self.job_coordinator.detach()             # al cerrarlo (cancela lo que haya en marcha)

1.2.0 La escritura de los datos del usuario lleva la etiqueta preferida de los MP3 de las
      Opciones (Opciones > Música), leída al lanzarla ('_userdata_writer'; también la de
      'pending_writer'): la que se crea en un MP3 al que le falta el ID3v2 (MUS 6.2b).
1.1.0 Trabajo 'files' («Moviendo archivos», CAT 4.2): renombrar o mover archivos, con las
      mismas reglas que eliminar ('start_file_job', 'files_finished', 'files_failed').
1.0.0 Primera versión (GEN 15.1): el código de 'main_window_controller.py', movido.

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.job_coordinator
"""

__version__ = "1.2.0"
__all__ = [
    "JOB_FILES",
    "JOB_METADATA",
    "JOB_REMOVE",
    "JOB_THUMBNAILS",
    "JOB_TITLES",
    "JOB_USERDATA",
    "USERDATA_CONFIRM_MIN_ITEMS",
    "USERDATA_PROGRESS_MIN_ITEMS",
    "USERDATA_WRITE_DELAY_MS",
    "JobCoordinator",
]

# Librerías estándar
import time
from collections.abc import Callable
from functools import partial
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QTimer, Signal
from qtpy.QtWidgets import QMainWindow

# Módulos del proyecto
from config.app_constants import (
    SETTING_AUDIO_ID3_VERSION,
    SETTING_AUDIO_INCLUDE_ID3V1,
    SETTING_WRITE_USER_DATA_TO_FILES,
    AppIcons,
)
from controllers.metadata_progress import MetadataProgress
from core.audio.tag_set import mp3_tags_from_settings
from core.jobs.progress import JobProgress
from core.metadata.processor import process_pending_metadata
from core.thumbnails.job import generate_pending_thumbnails, invalidate_thumbnails
from core.userdata.sync import count_pending_user_data, write_pending_user_data
from core.userdata.writers import default_writers
from core.workers.job_manager import JobManager
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar
from ui_helpers.widgets.job_progress_widget import JobProgressWidget

# Nombres de los trabajos en segundo plano y texto con el que se muestran
JOB_METADATA = "metadata"
JOB_THUMBNAILS = "thumbnails"
JOB_USERDATA = "userdata"
JOB_REMOVE = "remove"
JOB_FILES = "files"
JOB_TITLES: dict[str, str] = {
    JOB_METADATA: "Leyendo metadatos",
    JOB_THUMBNAILS: "Generando miniaturas",
    JOB_USERDATA: "Guardando en los archivos",
    JOB_REMOVE: "Eliminando",
    JOB_FILES: "Moviendo archivos",
}
# Trabajos durante los que no se lanza ningún otro (cambian qué archivos hay y dónde)
_EXCLUSIVE_JOBS = (JOB_REMOVE, JOB_FILES)

# Segundos que se espera tras el último cambio del usuario (estrellas, marca, color) antes
# de escribirlo en los archivos: así una ráfaga de clics se escribe de una vez
USERDATA_WRITE_DELAY_MS = 2000

# Por debajo de estos elementos, la escritura en los archivos y la eliminación no muestran
# barra de progreso (lo normal es tocar uno o pocos archivos en un instante)
USERDATA_PROGRESS_MIN_ITEMS = 20

# Al abrir un catálogo con al menos estos elementos pendientes de escribir (p. ej. la
# primera vez tras actualizar la aplicación), se pregunta antes de modificar los archivos
USERDATA_CONFIRM_MIN_ITEMS = 100

# Mientras se generan miniaturas, cada cuánto (segundos) se reintentan las tarjetas vacías
_THUMB_REFRESH_SECONDS = 1.5


class JobCoordinator(QObject):
    """Lanza los trabajos en segundo plano del catálogo abierto y los encadena.

    Signals:
        thumbnails_progressed(): avanza la generación de miniaturas (como mucho, cada
            1,5 s): la cuadrícula reintenta las tarjetas que estaban vacías, para que
            vayan apareciendo sin esperar a que termine toda la pasada.
        thumbnails_generated(object): terminó una pasada de miniaturas (los 'id'
            generados o regenerados): la cuadrícula los vuelve a leer de la caché.
        metadata_read(): terminó la lectura de metadatos (también si se canceló): la
            ventana clasifica los vídeos y vuelve a leer la cuadrícula (valoración, marca
            y color pueden haberse rellenado desde los archivos).
        removal_finished(object): terminó de eliminar (el resultado): la ventana pone al
            día la cuadrícula y los contadores y avisa de lo que no se pudo; DESPUÉS de
            atenderla se lanza lo que esperaba.
        removal_failed(): eliminar falló con una excepción: la ventana muestra lo que hay
            (lo quitado está confirmado por lotes); después se lanza lo que esperaba.
        files_finished(object): terminó de renombrar o mover archivos (el resultado),
            como 'removal_finished'.
        files_failed(): renombrar o mover falló con una excepción, como 'removal_failed'.
    """

    thumbnails_progressed = Signal()
    thumbnails_generated = Signal(object)
    metadata_read = Signal()
    removal_finished = Signal(object)
    removal_failed = Signal()
    files_finished = Signal(object)
    files_failed = Signal()

    def __init__(
        self,
        window: QMainWindow,
        message_box: MessageBoxHelper,
        config: Any,
        *,
        write_delay_ms: int = USERDATA_WRITE_DELAY_MS,
        job_manager_factory: Callable[..., Any] = JobManager,
        metadata_progress: MetadataProgress | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Prepara el coordinador (aún sin catálogo: ver 'attach').

        Args:
            window: Ventana principal (su barra de estado y sus mensajes).
            message_box: Ayudante de mensajes de la ventana (preguntas y errores).
            config: La configuración ('settings.json'): la opción «Escribir los cambios
                en los archivos».
            write_delay_ms: Espera tras el último cambio antes de escribirlo.
            job_manager_factory: Crea el gestor de trabajos de cada catálogo (para las
                pruebas, uno de mentira).
            metadata_progress: La ventana «Leyendo metadatos» (None = la de siempre; para
                las pruebas, una que no llegue a abrirse).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._window = window
        self._message_box = message_box
        self._config = config
        self._job_manager_factory = job_manager_factory
        # Gestor de la base de datos del catálogo abierto (None si no hay)
        self._db: Any = None
        # Trabajos en segundo plano del catálogo activo (metadatos, miniaturas...)
        self._jobs: Any = None
        # Widget de progreso (en la barra de estado) de cada trabajo en curso
        self._job_widgets: dict[str, JobProgressWidget] = {}
        # Instante (time.monotonic) del último refresco de miniaturas durante su generación
        self._last_thumb_refresh = 0.0
        # Mientras se leen los metadatos, una ventana con el avance bloquea la aplicación
        # (GEN 20.2; recibe cada gestor de trabajos en 'attach')
        self._metadata_progress = metadata_progress or MetadataProgress(
            window, job_name=JOB_METADATA, parent=self
        )
        # True si se pidió generar miniaturas mientras ya había una pasada en curso: al terminar
        # esa se hace otra (p. ej. una regeneración pedida a mitad de la pasada)
        self._thumbnail_rerun_requested = False

        # Escritura de los datos del usuario en los archivos: espera un poco tras el último
        # cambio (temporizador de un disparo que se reinicia con cada cambio) y, si llega
        # un cambio mientras escribe, repite al terminar
        self._userdata_timer = QTimer(self)
        self._userdata_timer.setSingleShot(True)
        self._userdata_timer.setInterval(write_delay_ms)
        self._userdata_timer.timeout.connect(self._start_write)
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

    # -------------------------------------------------------------------------
    # Catálogo abierto
    # -------------------------------------------------------------------------

    @property
    def is_attached(self) -> bool:
        """True si hay un catálogo abierto (con su gestor de trabajos)."""
        return self._jobs is not None

    def attach(self, db: Any) -> None:
        """Crea el gestor de trabajos del catálogo que se acaba de abrir."""
        self.detach()
        self._db = db
        # Trabajos en segundo plano: sus señales llegan al hilo principal
        self._jobs = self._job_manager_factory(db, parent=self)
        # Antes que lo demás: al terminar la lectura, su ventana se cierra antes de otro aviso
        self._metadata_progress.attach(self._jobs)
        self._jobs.job_progress.connect(self._on_job_progress)
        self._jobs.job_finished.connect(self._on_job_finished)
        self._jobs.job_failed.connect(self._on_job_failed)

    def detach(self) -> None:
        """Cierra el catálogo: cancela lo que esté en marcha y olvida lo pendiente."""
        if self._jobs is not None:
            # Los trabajos paran en cuanto pueden; 'db.shutdown()' espera a que acaben
            self._jobs.cancel_all()
            self._jobs.deleteLater()
            self._jobs = None
        self._db = None
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

    def busy_reason(self) -> str | None:
        """El trabajo que hay en marcha, dicho para el usuario, o None si no hay ninguno."""
        if self._jobs is not None:
            for name, title in JOB_TITLES.items():
                if self._jobs.is_running(name):
                    return f"Hay un trabajo en marcha: «{title}»."
        return None

    # -------------------------------------------------------------------------
    # Escritura de los datos del usuario en los archivos (XMP, sidecar, archivo de carpeta)
    # -------------------------------------------------------------------------

    def _write_to_files_enabled(self) -> bool:
        """Lee la opción "Escribir los cambios en los archivos" (por defecto, activada)."""
        value = self._config.get(SETTING_WRITE_USER_DATA_TO_FILES, True)
        if not isinstance(value, bool):
            logger.warning(
                f"'{SETTING_WRITE_USER_DATA_TO_FILES}' no válido en la configuración: "
                f"{value!r}. Se usa el valor por defecto (activada)."
            )
            return True
        return value

    def schedule_write(self) -> None:
        """Programa la escritura en los archivos tras un momento sin cambios del usuario."""
        if self._jobs is not None and self._write_to_files_enabled():
            self._userdata_timer.start()  # si ya estaba en marcha, vuelve a empezar la cuenta

    def stop_scheduled_write(self) -> None:
        """Detiene la escritura programada (p. ej. mientras se pregunta si eliminar)."""
        self._userdata_timer.stop()

    def write_option_changed(self) -> None:
        """Opciones > «Escribir los cambios en los archivos» ha cambiado.

        Si se acaba de activar, se escribe lo pendiente (el usuario lo ha pedido
        expresamente: no se vuelve a preguntar).
        """
        if not self._write_to_files_enabled():
            return
        if self._userdata_backlog_state != "checking":
            self._userdata_backlog_state = "ok"
        self._start_write()

    def pending_writer(self) -> Callable[..., object] | None:
        """Función que escribe lo pendiente antes de quitar algo del catálogo, o None.

        Antes de quitar del catálogo se escribe en los archivos lo pendiente (p. ej. unas
        estrellas puestas hace un instante), si la escritura en los archivos está activa y
        ya confirmada en esta sesión: así vuelve con el archivo si se sincroniza otra vez.
        """
        if self._write_to_files_enabled() and self._userdata_backlog_state == "ok":
            return self._userdata_writer()
        return None

    def _userdata_writer(self) -> Callable[..., object]:
        """La escritura de los datos del usuario, con la etiqueta preferida de los MP3 de
        las Opciones leída ahora (Opciones > Música: así vale lo último que se eligió).

        Cada llamada, sus escritores nuevos ('default_writers'): uno por trabajo.
        """
        preferred = mp3_tags_from_settings(
            self._config.get(SETTING_AUDIO_ID3_VERSION),
            self._config.get(SETTING_AUDIO_INCLUDE_ID3V1),
        )
        return partial(write_pending_user_data, writers=default_writers(preferred_mp3=preferred))

    def _start_write(self) -> None:
        """Lanza la escritura de los datos del usuario pendientes, si procede.

        Espera a que termine la lectura de metadatos (así no se lee y se escribe a la vez
        el mismo archivo). Si ya hay una escritura en curso, se repite al terminar.
        """
        if (
            self._jobs is None
            or self._db is None
            or not self._write_to_files_enabled()
        ):
            return
        if self._userdata_backlog_state == "unchecked":
            # Primera escritura desde que se abrió el catálogo: antes se mira cuánto hay
            # pendiente (si es mucho, se pregunta; ver _on_userdata_backlog_counted)
            self._userdata_backlog_state = "checking"
            self._db.execute_async(
                count_pending_user_data,
                on_result=self._on_userdata_backlog_counted,
                on_error=lambda _error: self._on_userdata_backlog_counted(0),
            )
            return
        if self._userdata_backlog_state != "ok":
            return  # preguntando, o el usuario lo aplazó en esta sesión
        if self._exclusive_job_running():
            self._userdata_rerun_requested = True  # se lanza al terminar de eliminar
            return
        if self._jobs.is_running(JOB_METADATA):
            self._userdata_rerun_requested = True  # se lanza al terminar los metadatos
            return
        if not self._jobs.start(JOB_USERDATA, self._userdata_writer()):
            self._userdata_rerun_requested = True

    def _on_userdata_backlog_counted(self, count: int) -> None:
        """Si hay muchos elementos pendientes de escribir, pregunta antes de empezar.

        Ocurre sobre todo la primera vez que se abre un catálogo tras actualizar la
        aplicación: los valores que ya tenía el catálogo quedan pendientes de escribirse
        en los archivos (solo se modifican los que no los tengan ya).
        """
        if self._jobs is None or self._userdata_backlog_state != "checking":
            return  # el catálogo se cerró mientras se contaba
        if count >= USERDATA_CONFIRM_MIN_ITEMS:
            answer = self._message_box.question(
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
                    self._window,
                    "Escritura en los archivos aplazada: los cambios quedan en el catálogo.",
                    AppIcons.INFO,
                )
                return
        self._userdata_backlog_state = "ok"
        self._start_write()

    # -------------------------------------------------------------------------
    # Lanzar los trabajos
    # -------------------------------------------------------------------------

    def start_metadata(self) -> None:
        """Lanza la lectura de metadatos de los archivos pendientes, si no está ya en curso.

        Si se están escribiendo datos del usuario en los archivos, espera a que termine.
        """
        if self._jobs is None:
            return
        if self._jobs.is_running(JOB_USERDATA):
            self._metadata_after_userdata = True  # se lanza al terminar la escritura
            return
        if self._exclusive_job_running():
            self._metadata_after_removal = True  # se lanza al terminar de eliminar
            return
        self._jobs.start(JOB_METADATA, process_pending_metadata)

    def start_thumbnails(self) -> None:
        """Lanza la generación de miniaturas de los archivos pendientes, si no está ya en curso."""
        if self._jobs is None:
            return
        if self._exclusive_job_running():
            # Generar a la vez dejaría miniaturas de elementos ya quitados del catálogo
            self._thumbnails_after_removal = True
            return
        if not self._jobs.start(JOB_THUMBNAILS, generate_pending_thumbnails):
            # Ya hay una pasada en curso. Puede haber empezado antes de que se marcaran más
            # archivos como pendientes (p. ej. una regeneración): se repetirá al terminar
            self._thumbnail_rerun_requested = True

    def start_removal(self, job: Callable[..., object], *args: object, **kwargs: object) -> None:
        """Lanza un trabajo de quitar del catálogo («Eliminar», quitar una carpeta...).

        Con el nombre JOB_REMOVE: mientras dura, lo demás espera, y al terminar se avisa
        con 'removal_finished' y se lanza lo que esperaba. Quien lo pide comprueba antes
        que no haya nada en marcha ('busy_reason').
        """
        if self._jobs is not None:
            self._jobs.start(JOB_REMOVE, job, *args, **kwargs)

    def start_file_job(self, job: Callable[..., object], *args: object, **kwargs: object) -> None:
        """Lanza un trabajo de renombrar o mover archivos ('execute_file_moves').

        Con el nombre JOB_FILES y las mismas reglas que eliminar: mientras dura, lo demás
        espera, y al terminar se avisa con 'files_finished' y se lanza lo que esperaba.
        Quien lo pide comprueba antes que no haya nada en marcha ('busy_reason').
        """
        if self._jobs is not None:
            self._jobs.start(JOB_FILES, job, *args, **kwargs)

    def _exclusive_job_running(self) -> bool:
        """True mientras se elimina o se renombran o mueven archivos (lo demás espera)."""
        return self._jobs is not None and any(
            self._jobs.is_running(name) for name in _EXCLUSIVE_JOBS
        )

    def _resume_after_removal(self) -> None:
        """Lanza lo que se pidió mientras se eliminaba o se movían archivos (metadatos,
        miniaturas, escritura)."""
        if self._metadata_after_removal:
            self._metadata_after_removal = False
            self.start_metadata()
        if self._thumbnails_after_removal:
            self._thumbnails_after_removal = False
            self.start_thumbnails()
        # Los cambios del usuario de los elementos que siguen en el catálogo, a los archivos
        self._userdata_rerun_requested = False
        self.schedule_write()

    # -------------------------------------------------------------------------
    # Regenerar miniaturas (menú Archivo y menú de la cuadrícula)
    # -------------------------------------------------------------------------

    def regenerate_thumbnails(
        self, media_ids: list[int] | None = None, *, only_errors: bool = False
    ) -> None:
        """Regenera miniaturas a demanda: las marca como pendientes y lanza el trabajo.

        La llama el menú contextual de la cuadrícula con los 'id' de la selección. Con
        'media_ids=None' afecta a todo el catálogo; con 'only_errors=True', solo a los
        archivos cuya miniatura falló. Los metadatos no se tocan.
        """
        if self._db is None:
            self._message_box.warning("Primero hay que crear o abrir un catálogo.")
            return
        self._db.execute_async(
            invalidate_thumbnails,
            media_ids,
            only_errors=only_errors,
            on_result=self._on_thumbnails_invalidated,
            on_error=self._on_regenerate_thumbnails_error,
        )

    def regenerate_failed_thumbnails(self) -> None:
        """Acción del menú: regenera solo las miniaturas que fallaron."""
        self.regenerate_thumbnails(only_errors=True)

    def regenerate_all_thumbnails(self) -> None:
        """Acción del menú: regenera las miniaturas de todo el catálogo (pide confirmación)."""
        if self._db is None:
            self._message_box.warning("Primero hay que crear o abrir un catálogo.")
            return
        answer = self._message_box.question(
            "Se volverán a generar las miniaturas de todos los archivos del catálogo.\n\n"
            "Puede tardar bastante. ¿Continuar?",
            buttons=["Regenerar", "Cancelar"],
        )
        if answer == "Regenerar":
            self.regenerate_thumbnails()

    def _on_thumbnails_invalidated(self, count: int) -> None:
        """Los archivos ya están marcados como pendientes: se lanza el trabajo (hilo principal)."""
        if count == 0:
            message_bar(self._window, "No hay miniaturas que regenerar.", AppIcons.INFO)
            return
        self.start_thumbnails()

    def _on_regenerate_thumbnails_error(self, error: Exception) -> None:
        """No se pudieron marcar las miniaturas como pendientes (hilo principal)."""
        message_bar(self._window, "No se pudo preparar la regeneración.", AppIcons.ERROR)
        self._message_box.critical(
            f"No se pudo preparar la regeneración de miniaturas.\n\nDetalle: {error}"
        )

    # -------------------------------------------------------------------------
    # Señales del gestor de trabajos
    # -------------------------------------------------------------------------

    def _on_job_progress(self, name: str, progress: JobProgress) -> None:
        """Muestra el avance de un trabajo en la barra de estado (hilo principal)."""
        # Puede llegar un aviso rezagado de un trabajo que ya terminó o se canceló
        if self._jobs is None or not self._jobs.is_running(name):
            return
        # La lectura de metadatos muestra su avance en su propia ventana (GEN 20.2,
        # 'controllers/metadata_progress.py'): aquí no se repite
        if name == JOB_METADATA:
            return

        # Mientras se generan miniaturas, las tarjetas que estaban vacías se reintentan cada
        # poco: así van apareciendo sin esperar a que termine toda la pasada
        if name == JOB_THUMBNAILS:
            now = time.monotonic()
            if now - self._last_thumb_refresh >= _THUMB_REFRESH_SECONDS:
                self._last_thumb_refresh = now
                self.thumbnails_progressed.emit()

        widget = self._job_widgets.get(name)
        if widget is None:
            if progress.total == 0:
                return  # no hay nada que hacer: no se muestra la barra
            brief = progress.total < USERDATA_PROGRESS_MIN_ITEMS
            if name in (JOB_USERDATA, *_EXCLUSIVE_JOBS) and brief:
                # Escritura breve tras unos clics, o eliminar o mover unos pocos archivos:
                # sin barra que aparezca y desaparezca en un instante
                return
            widget = JobProgressWidget(JOB_TITLES.get(name, name))
            widget.cancel_requested.connect(lambda: self._on_job_cancel_requested(name))
            self._window.statusBar().addPermanentWidget(widget)
            self._job_widgets[name] = widget

        widget.set_progress(progress.done, progress.total)

    def _on_job_cancel_requested(self, name: str) -> None:
        """El usuario pulsó "Cancelar" en la barra de progreso de un trabajo."""
        if self._jobs is not None:
            self._jobs.cancel(name)

    def _on_job_finished(self, name: str, result: object) -> None:
        """Un trabajo terminó (o se canceló): se retira su barra y se informa (hilo principal)."""
        self._remove_job_widget(name)

        # Cada resultado ofrece 'status_text()' y 'has_warnings' (ver core.jobs.progress)
        text = result.status_text()
        if text:  # vacío = no había nada que hacer: no se molesta al usuario
            icon = AppIcons.WARNING if result.has_warnings else AppIcons.CHECK_CIRCLE
            message_bar(self._window, text, icon)

        # Eliminar: la ventana pone al día la cuadrícula y los contadores; después, lo que
        # esperaba se lanza
        if name == JOB_REMOVE:
            self.removal_finished.emit(result)
            self._resume_after_removal()
            return
        if name == JOB_FILES:
            self.files_finished.emit(result)
            self._resume_after_removal()
            return

        # Las miniaturas recién generadas (o regeneradas) se vuelven a leer de la caché
        if name == JOB_THUMBNAILS:
            self.thumbnails_generated.emit(getattr(result, "generated_ids", ()))

        # Al terminar los metadatos, la ventana vuelve a leer la rejilla (valoración, marca
        # y color pueden haberse rellenado desde el XMP de los archivos), tras clasificar
        # los vídeos que siguen sin biblioteca
        if name == JOB_METADATA and self._db is not None:
            self.metadata_read.emit()

        # Encadenado: las miniaturas se generan al terminar los metadatos (salvo que el usuario
        # los haya cancelado), y se repite la pasada si se pidió una regeneración mientras corría
        if name == JOB_METADATA and not getattr(result, "cancelled", False):
            self.start_thumbnails()
        elif name == JOB_THUMBNAILS and self._thumbnail_rerun_requested:
            self._thumbnail_rerun_requested = False
            self.start_thumbnails()

        # Escritura de los datos del usuario y lectura de metadatos, siempre por turnos:
        #   - Al terminar los metadatos se escribe lo pendiente (al abrir el catálogo, lo
        #     que quedó de la sesión anterior).
        #   - Al terminar de escribir, si se pidió leer metadatos mientras tanto, o si se
        #     vio que algún archivo había cambiado fuera (p. ej. en Lightroom), se leen;
        #     al acabar esa lectura se volverá a escribir lo que siga pendiente.
        #   - Si no, y hubo cambios mientras escribía, se escribe otra vez.
        if name == JOB_METADATA:
            self._userdata_rerun_requested = False
            self._start_write()
        elif name == JOB_USERDATA:
            if self._metadata_after_userdata or getattr(result, "rescan_requested", 0):
                self._metadata_after_userdata = False
                self._userdata_rerun_requested = False  # se escribirá tras la lectura
                self.start_metadata()
            elif self._userdata_rerun_requested:
                self._userdata_rerun_requested = False
                self._start_write()

    def _on_job_failed(self, name: str, error: Exception) -> None:
        """Un trabajo falló con una excepción (hilo principal)."""
        self._remove_job_widget(name)
        title = JOB_TITLES.get(name, name)
        message_bar(self._window, f"Error en el trabajo: {title}", AppIcons.ERROR)
        if name == JOB_REMOVE:
            # Lo que se llegó a quitar está confirmado por lotes: la ventana muestra lo que hay
            self.removal_failed.emit()
            self._resume_after_removal()
        elif name == JOB_FILES:
            # Cada archivo se confirma por separado: la ventana muestra lo que hay
            self.files_failed.emit()
            self._resume_after_removal()
        # Las miniaturas no dependen de los metadatos: se generan igualmente (antes del cuadro
        # modal), y lo pendiente de escribir en los archivos, también
        if name == JOB_METADATA:
            self.start_thumbnails()
            self._start_write()
        elif name == JOB_USERDATA and self._metadata_after_userdata:
            self._metadata_after_userdata = False
            self.start_metadata()  # la lectura que esperaba a la escritura
        self._message_box.critical(
            f"Ha fallado el trabajo «{title}».\n\nDetalle: {error}"
        )

    def _remove_job_widget(self, name: str) -> None:
        """Quita de la barra de estado el widget de progreso de un trabajo."""
        widget = self._job_widgets.pop(name, None)
        if widget is not None:
            self._window.statusBar().removeWidget(widget)
            widget.deleteLater()

    def _clear_job_widgets(self) -> None:
        """Quita todos los widgets de progreso (al cerrar el catálogo)."""
        for name in list(self._job_widgets):
            self._remove_job_widget(name)


if __name__ == "__main__":
    # Autoprueba sin ventana: las reglas del encadenado, con un gestor de trabajos, una base
    # de datos y unos mensajes de mentira (los trabajos no hacen nada: se "terminan" a mano).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.job_coordinator
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    class FakeResult:
        """Lo que se usa del resultado de un trabajo."""

        def __init__(self, **attrs: object) -> None:
            self.has_warnings = False
            self.__dict__.update(attrs)

        def status_text(self) -> str:
            return ""

    class FakeJobs(QObject):
        """Las señales y los métodos del 'JobManager' que se usan."""

        job_started = Signal(str)
        job_progress = Signal(str, object)
        job_finished = Signal(str, object)
        job_failed = Signal(str, object)

        def __init__(self, _db: object, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self.running: set[str] = set()
            self.started: list[tuple[str, object, tuple, dict]] = []
            self.all_cancelled = False

        def is_running(self, name: str) -> bool:
            return name in self.running

        def start(self, name: str, job: object, *args: object, **kwargs: object) -> bool:
            if name in self.running:
                return False
            self.running.add(name)
            self.started.append((name, job, args, kwargs))
            self.job_started.emit(name)
            return True

        def cancel(self, name: str) -> None:
            pass

        def cancel_all(self) -> None:
            self.all_cancelled = True

        def finish(self, name: str, **attrs: object) -> None:
            assert name in self.running, (name, self.running)
            self.running.discard(name)
            self.job_finished.emit(name, FakeResult(**attrs))

        def fail(self, name: str) -> None:
            self.running.discard(name)
            self.job_failed.emit(name, RuntimeError("roto"))

        def names(self) -> list[str]:
            return [entry[0] for entry in self.started]

    class FakeDb:
        """'execute_async' que responde al momento con lo que diga cada función."""

        def __init__(self, answers: dict[object, Callable[[], object]]) -> None:
            self.answers = answers

        def execute_async(
            self, function: object, *_args: object, on_result: Any = None, **_kwargs: object
        ) -> None:
            if on_result is not None:
                on_result(self.answers[function]())

    class FakeBox:
        """Apunta las preguntas y los avisos; responde lo que diga 'answer'."""

        def __init__(self) -> None:
            self.answer = "Escribir ahora"
            self.questions: list[str] = []
            self.warnings: list[str] = []
            self.criticals: list[str] = []

        def question(self, text: str, **_kwargs: object) -> str:
            self.questions.append(text)
            return self.answer

        def warning(self, text: str, **_kwargs: object) -> None:
            self.warnings.append(text)

        def critical(self, text: str, **_kwargs: object) -> None:
            self.criticals.append(text)

    def wait(ms: int) -> None:
        """Deja correr el bucle de eventos (los temporizadores) unos milisegundos."""
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    window = QMainWindow()  # no se muestra: solo su barra de estado
    box = FakeBox()
    settings = {SETTING_WRITE_USER_DATA_TO_FILES: True}
    pending = {"count": 5, "invalidated": 3}
    db = FakeDb({
        count_pending_user_data: lambda: pending["count"],
        invalidate_thumbnails: lambda: pending["invalidated"],
    })  # fmt: skip
    created: list[FakeJobs] = []

    def make_jobs(database: object, parent: QObject | None = None) -> FakeJobs:
        created.append(FakeJobs(database, parent))
        return created[-1]

    coordinator = JobCoordinator(
        window,
        box,  # type: ignore[arg-type]
        settings,
        write_delay_ms=20,
        job_manager_factory=make_jobs,
        # Que su ventana no llegue a abrirse en la prueba
        metadata_progress=MetadataProgress(window, job_name=JOB_METADATA, show_after_ms=10**8),
    )
    events: list[tuple] = []
    coordinator.thumbnails_progressed.connect(lambda: events.append(("progressed",)))
    coordinator.thumbnails_generated.connect(lambda ids: events.append(("generated", ids)))
    coordinator.metadata_read.connect(lambda: events.append(("read",)))
    coordinator.removal_failed.connect(lambda: events.append(("remove_failed",)))

    # 0. Sin catálogo no se lanza nada
    assert not coordinator.is_attached and coordinator.busy_reason() is None
    coordinator.start_metadata()
    coordinator.regenerate_thumbnails()
    assert box.warnings == ["Primero hay que crear o abrir un catálogo."]
    print("0. Sin catálogo: nada")

    # 1. Al abrir: la lectura; la escritura pedida mientras tanto espera
    coordinator.attach(db)
    jobs = created[-1]
    coordinator.start_metadata()
    assert jobs.names() == ["metadata"]
    assert coordinator.busy_reason() == "Hay un trabajo en marcha: «Leyendo metadatos»."
    coordinator.schedule_write()
    wait(80)
    assert jobs.names() == ["metadata"]
    print("1. Lectura; la escritura espera")

    # 2. Fin de la lectura: la ventana relee la cuadrícula; miniaturas y escritura (antes
    #    se cuentan los pendientes: 5, sin pregunta)
    jobs.finish("metadata")
    assert ("read",) in events and jobs.names() == ["metadata", "thumbnails", "userdata"]
    assert box.questions == []
    print("2. Tras la lectura: miniaturas y escritura")

    # 3. Lectura pedida mientras se escribe: al terminar la escritura
    coordinator.start_metadata()
    assert jobs.names().count("metadata") == 1
    jobs.finish("userdata")
    assert jobs.names()[-1] == "metadata"
    print("3. Lectura y escritura, por turnos")

    # 4. Las miniaturas generadas se avisan; una lectura cancelada no lanza miniaturas
    jobs.finish("thumbnails", generated_ids=[7, 8])
    assert ("generated", [7, 8]) in events
    before = len(jobs.started)
    jobs.finish("metadata", cancelled=True)
    assert jobs.names()[before:] == ["userdata"]
    print("4. Lectura cancelada: sin miniaturas, con escritura")

    # 5. La escritura ve archivos cambiados fuera: se releen
    jobs.finish("userdata", rescan_requested=2)
    assert jobs.names()[-1] == "metadata"
    jobs.finish("metadata")
    jobs.finish("thumbnails")
    jobs.finish("userdata")
    print("5. Archivos cambiados fuera: se releen")

    # 6. Miniaturas pedidas con una pasada en curso: se repite al terminar
    coordinator.start_thumbnails()
    coordinator.start_thumbnails()
    jobs.finish("thumbnails")
    assert jobs.names()[-1] == "thumbnails"
    jobs.finish("thumbnails")
    print("6. Miniaturas: una pasada más si se pidió durante otra")

    # 7. Eliminar: lo demás espera; al terminar, PRIMERO la ventana y después lo que esperaba
    def fake_removal() -> None:
        """Un trabajo de quitar de mentira."""

    coordinator.start_removal(fake_removal, [1, 2], to_trash=False)
    assert jobs.started[-1] == ("remove", fake_removal, ([1, 2],), {"to_trash": False})
    assert coordinator.busy_reason() == "Hay un trabajo en marcha: «Eliminando»."
    waiting_from = len(jobs.started)
    coordinator.start_metadata()
    coordinator.start_thumbnails()
    assert len(jobs.started) == waiting_from  # nada nuevo mientras se elimina
    coordinator.removal_finished.connect(
        lambda _result: events.append(("removed", len(jobs.started)))
    )
    jobs.finish("remove")
    assert ("removed", waiting_from) in events  # la ventana, antes de relanzar nada
    assert jobs.names()[waiting_from:] == ["metadata", "thumbnails"]
    print("7. Eliminar: espera lo demás y lo relanza después")

    # 8. Eliminar falla: la ventana muestra lo que hay y se relanza lo que esperaba
    jobs.finish("metadata")  # lanza la escritura; las miniaturas ya iban: se repetirán
    jobs.finish("thumbnails")
    jobs.finish("thumbnails")  # la pasada repetida
    jobs.finish("userdata")
    assert jobs.running == set(), jobs.running
    coordinator.start_removal(fake_removal)
    coordinator.start_thumbnails()
    jobs.fail("remove")
    assert ("remove_failed",) in events and jobs.names()[-1] == "thumbnails"
    assert box.criticals[-1].startswith("Ha fallado el trabajo «Eliminando»")
    jobs.finish("thumbnails")
    print("8. Eliminar falla: la ventana, el aviso y lo que esperaba")

    # 8b. Renombrar o mover archivos: como eliminar (lo demás espera y se relanza después)
    coordinator.files_finished.connect(lambda _result: events.append(("files", len(jobs.started))))
    coordinator.files_failed.connect(lambda: events.append(("files_failed",)))
    coordinator.start_file_job(fake_removal, "plan")
    assert jobs.started[-1] == ("files", fake_removal, ("plan",), {})
    assert coordinator.busy_reason() == "Hay un trabajo en marcha: «Moviendo archivos»."
    waiting_from = len(jobs.started)
    coordinator.start_thumbnails()
    assert len(jobs.started) == waiting_from
    jobs.finish("files")
    assert ("files", waiting_from) in events and jobs.names()[-1] == "thumbnails"
    jobs.finish("thumbnails")
    coordinator.start_file_job(fake_removal, "plan")
    jobs.fail("files")
    assert ("files_failed",) in events
    assert box.criticals[-1].startswith("Ha fallado el trabajo «Moviendo archivos»")
    print("8b. Renombrar o mover: espera lo demás; al terminar o fallar, la ventana")

    # 9. La lectura falla: miniaturas y escritura igualmente, y el aviso
    coordinator.start_metadata()
    jobs.fail("metadata")
    assert jobs.names()[-2:] == ["thumbnails", "userdata"]
    assert box.criticals[-1].startswith("Ha fallado el trabajo «Leyendo metadatos»")
    print("9. Lectura fallida: miniaturas, escritura y aviso")

    # 10. Barras de la barra de estado: la lectura, ninguna (tiene su ventana); las
    #     miniaturas, sí (y piden reintentar las tarjetas vacías); una escritura corta, no
    coordinator.start_metadata()  # espera a la escritura en curso
    jobs.finish("userdata")  # ... y empieza ahora
    jobs.job_progress.emit("metadata", JobProgress(1, 100))
    jobs.job_progress.emit("thumbnails", JobProgress(5, 100))
    assert set(coordinator._job_widgets) == {"thumbnails"} and ("progressed",) in events
    jobs.finish("metadata")  # (lanza la escritura; las miniaturas siguen)
    jobs.job_progress.emit("userdata", JobProgress(1, 5))
    assert set(coordinator._job_widgets) == {"thumbnails"}
    jobs.finish("thumbnails")
    assert coordinator._job_widgets == {}
    jobs.finish("userdata")
    print("10. Barras: solo las que tocan")

    # 11. Otro catálogo con muchos pendientes: se pregunta; «Más tarde» no escribe, y
    #     activar la opción en Opciones sí (sin volver a preguntar)
    pending["count"] = 150
    box.answer = "Más tarde"
    coordinator.attach(db)
    assert created[-2].all_cancelled  # el catálogo anterior se cerró
    jobs = created[-1]
    coordinator.start_metadata()
    jobs.finish("metadata")
    assert len(box.questions) == 1 and "Hay 150 elementos" in box.questions[0]
    assert "userdata" not in jobs.names() and coordinator.pending_writer() is None
    coordinator.write_option_changed()
    assert jobs.names()[-1] == "userdata" and len(box.questions) == 1
    writer = coordinator.pending_writer()
    assert writer is not None and writer.func is write_pending_user_data
    jobs.finish("userdata")
    print("11. Muchos pendientes: pregunta; «Más tarde» y la opción")

    # 11b. La escritura lleva la etiqueta preferida de los MP3 de las Opciones, leída al
    #      lanzarla: sin elegir, ID3v2.3 sin ID3v1; después, lo elegido
    from core.audio.tag_set import DEFAULT_MP3_TAGS, TagSet
    from core.userdata.policy import UserDataDestination

    def preferred_mp3() -> TagSet:
        writer = coordinator.pending_writer()
        assert writer is not None
        return writer.keywords["writers"][UserDataDestination.AUDIO_TAGS]._preferred

    assert preferred_mp3() == DEFAULT_MP3_TAGS
    settings[SETTING_AUDIO_ID3_VERSION] = 4
    settings[SETTING_AUDIO_INCLUDE_ID3V1] = True
    assert preferred_mp3() == TagSet(id3v2=4, id3v1=True)
    del settings[SETTING_AUDIO_ID3_VERSION], settings[SETTING_AUDIO_INCLUDE_ID3V1]
    print("11b. La escritura, con la etiqueta preferida de las Opciones")

    # 12. Con la opción desactivada no se programa nada; activada, se escribe tras la espera
    settings[SETTING_WRITE_USER_DATA_TO_FILES] = False
    coordinator.schedule_write()
    wait(80)
    assert jobs.names().count("userdata") == 1 and coordinator.pending_writer() is None
    settings[SETTING_WRITE_USER_DATA_TO_FILES] = True
    coordinator.schedule_write()
    wait(80)
    assert jobs.names().count("userdata") == 2
    jobs.finish("userdata")
    print("12. La opción de escribir y la espera de la escritura")

    # 13. Regenerar: si hay miniaturas que rehacer se lanza el trabajo; si no, nada
    jobs.finish("thumbnails")
    coordinator.regenerate_thumbnails([1, 2])
    assert jobs.names()[-1] == "thumbnails"
    jobs.finish("thumbnails")
    pending["invalidated"] = 0
    count_before = len(jobs.started)
    coordinator.regenerate_failed_thumbnails()
    assert len(jobs.started) == count_before
    box.answer = "Cancelar"
    coordinator.regenerate_all_thumbnails()
    assert len(jobs.started) == count_before and "todos los archivos" in box.questions[-1]
    print("13. Regenerar miniaturas")

    # 14. Al cerrar el catálogo se cancela todo y se olvida lo pendiente
    coordinator.start_metadata()
    coordinator.schedule_write()
    coordinator.detach()
    assert jobs.all_cancelled and not coordinator.is_attached
    wait(80)  # la escritura programada no llega a lanzarse
    assert jobs.names().count("userdata") == 2
    print("14. Al cerrar: todo cancelado")

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
