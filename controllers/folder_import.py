"""Añadir y sincronizar carpetas del catálogo, con su resumen y «Quitar archivos ausentes».

Sacado de 'main_window_controller.py' (docs/PENDIENTE.md, GEN 15.2) SIN CAMBIAR lo que
hace: el código se movió tal cual; lo que necesita de la ventana (la base de datos, lanzar
la lectura de metadatos, recargar la cuadrícula) se le pasa con funciones, como a
'folder_actions.py'.

    «Añadir carpeta» (menú, botón «+» de la sección Carpetas)
        └─► request_add: elegir la carpeta → qué contiene según el catálogo (segundo plano)
                → «¿Qué contiene esta carpeta?» → start
    «Sincronizar carpeta» (menú de una carpeta)  └─► request_sync → start(sync=True)
    start: 'add_folder' en segundo plano (una sola importación a la vez: la acción queda
        desactivada), con su avance en la barra de estado → al terminar, la lectura de
        metadatos, la cuadrícula y el resumen. Al sincronizar, si el recorrido fue fiable y
        faltan archivos, el resumen ofrece quitarlos del catálogo (como Lightroom).
    «Quitar archivos ausentes del catálogo...» (menú de una carpeta)
        └─► request_remove_missing: cuenta → pregunta → los quita (con las carpetas que ya
            no están en el disco: 'count_missing' y 'remove_missing_items'; CAT 6.2c)

Uso (en el controlador principal, que solo lo crea y lo conecta):
    self.folder_import = FolderImport(
        self, self.message_box, self.config, action=self.action_add_folder,
        get_db=lambda: self.db, get_catalog_dir=lambda: self.catalog_dir,
        start_metadata=self.job_coordinator.start_metadata,
        reload_grid=self.mosaico_model.reload, parent=self,
    )
    self.action_add_folder.triggered.connect(self.folder_import.request_add)
    ...
    self.folder_import.cancel()   # al cerrar el catálogo (lo ya guardado se conserva)
    self.folder_import.finish()   # después de cerrar la base de datos

1.1.0 «Quitar archivos ausentes» también quita las carpetas que ya no están en el disco:
      la pregunta y el mensaje final las nombran, y una carpeta sin archivos ausentes que ya
      no está ya no da «no hay archivos ausentes» (CAT 6.2c).
1.0.0 Primera versión (GEN 15.2): el código de 'main_window_controller.py', movido.

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.folder_import
"""

__version__ = "1.1.0"
__all__ = ["FolderImport"]

# Librerías estándar
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal
from qtpy.QtGui import QAction
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from config.app_constants import SETTING_LAST_ADD_FOLDER_PARENT, AppIcons
from core.catalog.folder_importer import AddFolderProgress, AddFolderResult, add_folder
from core.catalog.folder_scanner import ScanError
from core.catalog.libraries import FOLDER_AUTO, folder_content_for
from core.catalog.missing_items import (
    MissingCount,
    RemovedItems,
    count_missing,
    count_missing_items,
    remove_missing_items,
)
from core.catalog.storage_locations import StorageLocationError
from ui_helpers.dialogs.folder_content_dialog import FolderContentDialog
from ui_helpers.helpers.ui_file_dialogs import select_folder
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar


class FolderImport(QObject):
    """Añade o sincroniza una carpeta del catálogo y quita sus archivos ausentes.

    Signals:
        scan_progress(object): avance de 'add_folder' ('AddFolderProgress'). Se emite desde
            el hilo secundario (por eso es una señal): Qt la entrega en el hilo principal,
            donde sí se puede tocar la interfaz.
    """

    scan_progress = Signal(object)

    def __init__(
        self,
        window: QWidget,
        message_box: MessageBoxHelper,
        config: Any,
        *,
        action: QAction,
        get_db: Callable[[], Any],
        get_catalog_dir: Callable[[], Path | None],
        start_metadata: Callable[[], None],
        reload_grid: Callable[[], None],
        choose_folder: Callable[..., str | None] = select_folder,
        ask_content: Callable[..., str | None] = FolderContentDialog.ask,
        parent: QObject | None = None,
    ) -> None:
        """Prepara las operaciones de carpeta.

        Args:
            window: Ventana principal (padre de los diálogos y su barra de estado).
            message_box: Ayudante de mensajes de la ventana.
            config: La configuración (dónde se abre «Añadir carpeta»).
            action: «Añadir carpeta al catálogo»: desactivada mientras se añade una.
            get_db: Devuelve el gestor de la base de datos del catálogo abierto, o None.
            get_catalog_dir: Devuelve la carpeta del catálogo abierto, o None.
            start_metadata: Lanza la lectura de metadatos de lo pendiente.
            reload_grid: Vuelve a leer la cuadrícula.
            choose_folder: El selector de carpetas ('select_folder'; para las pruebas, otro).
            ask_content: «¿Qué contiene esta carpeta?» ('FolderContentDialog.ask').
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._window = window
        self._message_box = message_box
        self._config = config
        self._action = action
        self._get_db = get_db
        self._get_catalog_dir = get_catalog_dir
        self._start_metadata = start_metadata
        self._reload_grid = reload_grid
        self._choose_folder = choose_folder
        self._ask_content = ask_content
        # Distinto de None mientras se está añadiendo una carpeta: es el evento que
        # cancela el proceso (add_folder lo consulta desde su hilo)
        self._add_folder_cancel: threading.Event | None = None
        # True si lo que está en marcha es "Sincronizar carpeta" (solo cambian los textos)
        self._add_folder_is_sync = False
        self.scan_progress.connect(self._on_add_folder_progress)

    # -------------------------------------------------------------------------
    # Estado (lo consulta la ventana)
    # -------------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True mientras se añade o sincroniza una carpeta."""
        return self._add_folder_cancel is not None

    def cancel(self) -> None:
        """Pide parar lo que se esté añadiendo (al cerrar el catálogo; lo guardado se conserva)."""
        if self._add_folder_cancel is not None:
            # add_folder se detiene en cuanto puede: lo ya guardado se conserva
            self._add_folder_cancel.set()

    def finish(self) -> None:
        """Restablece el estado tras añadir una carpeta (con éxito, error o cancelación).

        Lo llama el propio 'add_folder' al terminar y, al cerrar el catálogo, la ventana
        (sus avisos ya no llegarán).
        """
        self._add_folder_cancel = None
        self._action.setEnabled(True)

    # -------------------------------------------------------------------------
    # Añadir una carpeta al catálogo
    # -------------------------------------------------------------------------

    def request_add(self) -> None:
        """Pide una carpeta y qué contiene, y la añade al catálogo activo en segundo plano.

        Pasos: elegir la carpeta -> mirar en segundo plano qué contiene según el catálogo
        (si está dentro de una carpeta ya declarada, hereda lo suyo) -> preguntar "¿Qué
        contiene esta carpeta?" con eso ya elegido -> añadirla (ver '_ask_folder_content').
        """
        db = self._get_db()
        if db is None:
            self._message_box.warning(
                "Primero hay que crear o abrir un catálogo.\n\n"
                "Usa «Nuevo catálogo» del menú Archivo."
            )
            return

        # Se abre donde estaba la última carpeta añadida (si ya no existe, 'select_folder'
        # abre la carpeta personal)
        folder = self._choose_folder(
            parent=self._window,
            title="Seleccionar la carpeta que se añadirá al catálogo",
            initial_path=self._config.get(SETTING_LAST_ADD_FOLDER_PARENT, "") or None,
            force_dialog=True,
        )
        if not folder:
            return
        # 'folder_content_for(conn, carpeta)' solo lee: es rápido, pero toca la BD, así que
        # va en segundo plano. Si falla, se pregunta igual con "Detectar automáticamente"
        db.execute_async(
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
        if self._get_db() is None:
            return  # el catálogo se cerró mientras se consultaba
        if self._add_folder_cancel is not None:
            self._message_box.info(
                "Ya se está añadiendo o sincronizando una carpeta.\n\n"
                "Espera a que termine antes de añadir otra."
            )
            return
        content = self._ask_content(self._window, folder, current=current)
        if content is None:
            return  # cancelado
        # La próxima vez, «Añadir carpeta» se abre en la carpeta que contiene esta
        self._config.set(SETTING_LAST_ADD_FOLDER_PARENT, Path(folder).parent.as_posix())
        self.start(folder, sync=False, content=content)

    def request_sync(self, folder: str) -> None:
        """Menú de una carpeta > "Sincronizar carpeta": la vuelve a recorrer.

        Es la misma operación que añadirla (ver 'add_folder'): incorpora los archivos
        nuevos, relee los cambiados y marca los que han desaparecido. Como "Sincronizar
        carpeta" de Lightroom.
        """
        if self._get_db() is None:
            return
        if self._add_folder_cancel is not None:
            self._message_box.info(
                "Ya se está añadiendo o sincronizando una carpeta.\n\n"
                "Espera a que termine antes de sincronizar otra."
            )
            return
        self.start(folder, sync=True)

    def start(self, folder: str | Path, *, sync: bool, content: str | None = None) -> None:
        """Añade (o sincroniza) una carpeta del catálogo en un hilo secundario.

        Args:
            folder: Carpeta a añadir o sincronizar.
            sync: True si viene de "Sincronizar carpeta" (solo cambian los textos).
            content: Qué contiene la carpeta ('auto' o una biblioteca), elegido en
                "¿Qué contiene esta carpeta?". None = no cambiar lo declarado (al
                sincronizar).
        """
        db = self._get_db()
        if db is None:
            return

        # Mientras dure, la acción queda desactivada: solo una importación a la vez
        self._add_folder_cancel = threading.Event()
        self._add_folder_is_sync = sync
        self._action.setEnabled(False)
        verb = "Sincronizando carpeta" if sync else "Añadiendo carpeta al catálogo"
        message_bar(self._window, f"{verb}...", duracion=0)

        # 'add_folder' recibe la conexión como primer parámetro (la pone el gestor)
        db.execute_async(
            add_folder,
            folder,
            content=content,
            cancel_event=self._add_folder_cancel,
            progress=self.scan_progress.emit,
            on_result=self._on_add_folder_result,
            on_error=self._on_add_folder_error,
            on_finished=self.finish,
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
            self._window,
            f"{verb}... {progress.saved_items} archivos procesados",
            duracion=0,
        )

    def _on_add_folder_result(self, result: AddFolderResult) -> None:
        """Muestra el resultado de añadir la carpeta (hilo principal)."""
        logger.info(f"Carpeta añadida al catálogo:\n{result.summary()}")

        # Lo recién añadido queda pendiente de leer: se empieza ya, mientras el usuario
        # lee el resumen (el cuadro de aviso no detiene el trabajo en segundo plano)
        if not result.cancelled:
            self._start_metadata()

        # Los archivos nuevos ya están en el catálogo: aparecen en la cuadrícula
        self._reload_grid()

        sync = self._add_folder_is_sync
        title = "Carpeta sincronizada" if sync else "Carpeta añadida"

        # Al SINCRONIZAR, si el recorrido fue completo y fiable, se mira cuántos archivos
        # de la carpeta están ausentes (los de ahora y los que ya lo estaban) para ofrecer
        # quitarlos del catálogo, como Lightroom
        reliable = not result.cancelled and result.missing_check_skipped is None
        db = self._get_db()
        if sync and reliable and db is not None:
            db.execute_async(
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
            message_bar(self._window, f"{title}, con avisos.", AppIcons.WARNING)
        else:
            message_bar(
                self._window,
                f"{title}: {result.new_items} archivos nuevos.",
                AppIcons.CHECK_CIRCLE,
            )

        if missing_to_remove > 0:
            answer = self._message_box.question(
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
            self._message_box.warning(result.summary(), title=title)
        else:
            self._message_box.info(result.summary(), title=title)

    def _on_add_folder_error(self, error: Exception) -> None:
        """Informa de que no se pudo añadir la carpeta (hilo principal)."""
        message_bar(self._window, "No se pudo añadir la carpeta.", AppIcons.ERROR)

        if isinstance(error, (StorageLocationError, ScanError)):
            # Carpeta no válida, solapada con otra del catálogo...: el mensaje ya
            # está redactado para el usuario
            self._message_box.warning(str(error))
        else:
            self._message_box.critical(
                f"No se pudo añadir la carpeta al catálogo.\n\nDetalle: {error}"
            )

    # -------------------------------------------------------------------------
    # Quitar del catálogo los archivos ausentes
    # -------------------------------------------------------------------------

    def request_remove_missing(self, location_id: int, folder: str) -> None:
        """Menú de una carpeta > "Quitar archivos ausentes del catálogo...": cuenta y pregunta."""
        db = self._get_db()
        if db is None:
            return
        if self._add_folder_cancel is not None:
            self._message_box.info(
                "Se está añadiendo o sincronizando una carpeta.\n\n"
                "Espera a que termine antes de quitar archivos del catálogo."
            )
            return
        db.execute_async(
            count_missing,
            location_id,
            folder,
            on_result=lambda count: self._confirm_remove_missing(location_id, folder, count),
            on_error=lambda error: self._message_box.critical(
                f"No se pudieron contar los archivos ausentes.\n\nDetalle: {error}"
            ),
        )

    def _confirm_remove_missing(self, location_id: int, folder: str, count: MissingCount) -> None:
        """Pregunta antes de quitar del catálogo los ausentes de una carpeta (y las carpetas
        que ya no están en el disco)."""
        if count.items == 0 and count.folders == 0:
            self._message_box.info("En esta carpeta no hay archivos ausentes.")
            return
        lines = []
        if count.items:
            lines.append(f"Hay {count.items} archivos de esta carpeta que ya no están en el disco.")
        if count.folder_missing:
            lines.append(
                "La carpeta tampoco está: se quitará también del árbol."
                if count.items
                else "Esta carpeta ya no está en el disco."
            )
        elif count.folders == 1:
            lines.append("Una subcarpeta ya no está en el disco: se quitará también del árbol.")
        elif count.folders:
            lines.append(
                f"{count.folders} subcarpetas ya no están en el disco: se quitarán también "
                "del árbol."
            )
        if count.items:
            question = (
                "¿Quitarlos del catálogo? Los archivos del disco no se tocan. Si alguno solo se "
                "ha movido o renombrado, se perderán su valoración y sus datos en el catálogo "
                "(salvo lo que ya esté escrito en el propio archivo)."
            )
        else:
            question = (
                f"¿{'Quitarla' if count.folders == 1 else 'Quitarlas'} del catálogo? En el disco "
                "no se toca nada."
            )
        answer = self._message_box.question(
            " ".join(lines) + "\n\n" + question,
            buttons=["Quitar del catálogo", "Cancelar"],
        )
        if answer == "Quitar del catálogo":
            self._remove_missing(location_id, folder)

    def _remove_missing(self, location_id: int, folder: str) -> None:
        """Quita del catálogo (en segundo plano) los ausentes de una carpeta."""
        db = self._get_db()
        if db is None:
            return
        db.execute_async(
            remove_missing_items,
            location_id,
            folder,
            catalog_dir=self._get_catalog_dir(),
            on_result=self._on_missing_removed,
            on_error=lambda error: self._message_box.critical(
                f"No se pudieron quitar los archivos ausentes.\n\nDetalle: {error}"
            ),
        )

    def _on_missing_removed(self, result: RemovedItems) -> None:
        """Los ausentes ya no están en el catálogo: se recargan la cuadrícula y la barra lateral."""
        parts = []
        if result.count:
            parts.append(f"{result.count} archivos ausentes")
        if result.folders:
            parts.append("1 carpeta" if result.folders == 1 else f"{result.folders} carpetas")
        message_bar(
            self._window,
            f"Quitados del catálogo: {' y '.join(parts) or '0 archivos ausentes'}.",
            AppIcons.CHECK_CIRCLE,
        )
        # Al recargar, la barra lateral actualiza sola sus contadores y su árbol
        self._reload_grid()


if __name__ == "__main__":
    # Autoprueba sin ventana: la base de datos, los mensajes, el selector de carpetas y
    # «¿Qué contiene esta carpeta?» son de mentira (responden al momento).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.folder_import
    import sys
    from types import SimpleNamespace

    from qtpy.QtWidgets import QApplication, QMainWindow

    app = QApplication.instance() or QApplication(sys.argv)

    class FakeDb:
        """'execute_async' que responde al momento (o se queda «trabajando» con 'hold')."""

        def __init__(self) -> None:
            self.answers: dict[object, Callable[..., object]] = {}
            self.calls: list[tuple[object, tuple, dict]] = []
            self.hold = False  # True: la tarea no termina (para probar «ya se está añadiendo»)

        def execute_async(
            self,
            function: object,
            *args: object,
            on_result: Any = None,
            on_error: Any = None,
            on_finished: Any = None,
            **kwargs: object,
        ) -> None:
            self.calls.append((function, args, kwargs))
            if self.hold:
                return
            try:
                result = self.answers[function](*args, **kwargs)
            except Exception as error:  # noqa: BLE001 - como el gestor: va a 'on_error'
                if on_error is not None:
                    on_error(error)
            else:
                if on_result is not None:
                    on_result(result)
            if on_finished is not None:
                on_finished()

        def called(self, function: object) -> list[tuple[tuple, dict]]:
            return [(args, kwargs) for f, args, kwargs in self.calls if f is function]

    class FakeBox:
        """Apunta los mensajes; responde lo que diga 'answer'."""

        def __init__(self) -> None:
            self.answer = ""
            self.log: list[tuple[str, str]] = []

        def info(self, text: str, **_kwargs: object) -> None:
            self.log.append(("info", text))

        def warning(self, text: str, **_kwargs: object) -> None:
            self.log.append(("warning", text))

        def critical(self, text: str, **_kwargs: object) -> None:
            self.log.append(("critical", text))

        def question(self, text: str, **_kwargs: object) -> str:
            self.log.append(("question", text))
            return self.answer

    class FakeConfig(dict):
        def set(self, key: str, value: object) -> None:
            self[key] = value

    def make_result(*, cancelled: bool = False, issues: int = 0) -> SimpleNamespace:
        """Un 'AddFolderResult' de mentira."""
        return SimpleNamespace(
            summary=lambda: "Resumen de la carpeta",
            cancelled=cancelled,
            stats=SimpleNamespace(issues=issues),
            missing_check_skipped=None,
            new_items=12,
            location=SimpleNamespace(id=7),
            relative_folder="Viajes",
        )

    window = QMainWindow()  # no se muestra: su barra de estado
    action = QAction("Añadir carpeta", window)
    db_state: dict[str, Any] = {"db": None}
    box, config = FakeBox(), FakeConfig()
    events: list[str] = []
    picked = {"folder": "C:/Fotos/Viajes", "content": "image"}
    seen_while_running: list[tuple[bool, bool]] = []

    importer = FolderImport(
        window,
        box,  # type: ignore[arg-type]
        config,
        action=action,
        get_db=lambda: db_state["db"],
        get_catalog_dir=lambda: Path("C:/Catalogo"),
        start_metadata=lambda: events.append("metadata"),
        reload_grid=lambda: events.append("reload"),
        choose_folder=lambda **_kwargs: picked["folder"],
        ask_content=lambda _window, _folder, current: (
            events.append(f"ask:{current}") or picked["content"]
        ),
    )

    # 0. Sin catálogo: aviso y nada más
    importer.request_add()
    assert box.log == [("warning", box.log[0][1])] and "Primero hay que crear" in box.log[0][1]
    print("0. Sin catálogo: aviso")

    # 1. Añadir: carpeta -> lo que contiene según el catálogo -> la ventana -> 'add_folder';
    #    mientras dura, la acción desactivada; después, lectura, cuadrícula y resumen
    db = FakeDb()
    db_state["db"] = db

    def fake_add_folder(folder: str, **kwargs: object) -> SimpleNamespace:
        seen_while_running.append((importer.is_running, action.isEnabled()))
        assert isinstance(kwargs["cancel_event"], threading.Event)
        kwargs["progress"](SimpleNamespace(saved_items=5))  # el avance, desde el «hilo»
        return make_result()

    db.answers = {folder_content_for: lambda folder: "auto", add_folder: fake_add_folder}
    box.log.clear()
    importer.request_add()
    ((args, kwargs),) = db.called(add_folder)
    assert args == ("C:/Fotos/Viajes",) and kwargs["content"] == "image"
    assert events == ["ask:auto", "metadata", "reload"], events
    assert config[SETTING_LAST_ADD_FOLDER_PARENT] == "C:/Fotos"
    assert seen_while_running == [(True, False)]
    assert not importer.is_running and action.isEnabled()
    assert box.log == [("info", "Resumen de la carpeta")]
    print("1. Añadir: elegir, preguntar, añadir, leer, recargar y resumen")

    # 2. Elegir «Cancelar» en el selector o en la ventana: no se añade nada
    picked["folder"] = None
    importer.request_add()
    picked["folder"], picked["content"] = "C:/Fotos/Otra", None
    importer.request_add()
    assert len(db.called(add_folder)) == 1
    print("2. Cancelar al elegir: nada")

    # 3. Sincronizar con 3 ausentes: el resumen pregunta; «Quitar del catálogo» los quita
    db.answers[count_missing_items] = lambda location, folder: 3
    db.answers[remove_missing_items] = lambda location, folder, catalog_dir: SimpleNamespace(
        count=3, folders=0
    )
    events.clear()
    box.log.clear()
    box.answer = "Quitar del catálogo"
    importer.request_sync("C:/Fotos/Viajes")
    assert db.called(add_folder)[-1][1]["content"] is None  # al sincronizar no se cambia
    assert box.log[0][0] == "question" and "Hay 3 archivos" in box.log[0][1]
    ((args, kwargs),) = db.called(remove_missing_items)
    assert args == (7, "Viajes") and kwargs["catalog_dir"] == Path("C:/Catalogo")
    assert events == ["metadata", "reload", "reload"], events  # al añadir y al quitar
    print("3. Sincronizar con ausentes: pregunta y los quita")

    # 4. «Mantener como ausentes»: no se quita nada
    box.answer = "Mantener como ausentes"
    importer.request_sync("C:/Fotos/Viajes")
    assert len(db.called(remove_missing_items)) == 1
    print("4. Mantener los ausentes")

    # 5. Mientras se añade una, no se puede añadir, sincronizar ni quitar ausentes
    db.hold = True
    importer.start("C:/Fotos/Lenta", sync=False, content="auto")
    db.hold = False
    box.log.clear()
    importer.request_sync("C:/Fotos/Viajes")
    importer.request_remove_missing(7, "Viajes")
    picked["content"] = "image"
    importer.request_add()  # pide la carpeta, pero no la ventana
    assert [kind for kind, _ in box.log] == ["info", "info", "info"], box.log
    assert importer.is_running and not action.isEnabled()
    slow_cancel = db.called(add_folder)[-1][1]["cancel_event"]  # la de «Lenta»
    assert not slow_cancel.is_set()
    importer.cancel()
    assert slow_cancel.is_set()  # 'add_folder' para en cuanto puede
    importer.finish()  # (al cerrar el catálogo)
    assert not importer.is_running and action.isEnabled()
    print("5. Una importación a la vez; cancelar y terminar")

    # 6. Errores: carpeta no válida (aviso redactado) u otro (error con el detalle)
    def invalid(folder: str, **_kwargs: object) -> None:
        raise StorageLocationError("La carpeta se solapa con otra del catálogo.")

    db.answers[add_folder] = invalid
    box.log.clear()
    importer.start("C:/Fotos/Mala", sync=False)
    db.answers[add_folder] = lambda folder, **_kwargs: 1 / 0
    importer.start("C:/Fotos/Rota", sync=False)
    assert box.log[0] == ("warning", "La carpeta se solapa con otra del catálogo.")
    assert box.log[1][0] == "critical" and "No se pudo añadir la carpeta" in box.log[1][1]
    assert not importer.is_running and action.isEnabled()
    print("6. Errores al añadir")

    # 7. Recorrido cancelado: sin lectura de metadatos y con el resumen como aviso
    db.answers[add_folder] = lambda folder, **_kwargs: make_result(cancelled=True)
    events.clear()
    box.log.clear()
    importer.start("C:/Fotos/Viajes", sync=True)
    assert events == ["reload"] and box.log == [("warning", "Resumen de la carpeta")]
    print("7. Recorrido cancelado: sin lectura")

    # 8. «Quitar archivos ausentes» del menú: sin ausentes, aviso; con ausentes, pregunta
    db.answers[count_missing] = lambda location, folder: MissingCount()
    box.log.clear()
    importer.request_remove_missing(7, "Viajes")
    assert box.log == [("info", "En esta carpeta no hay archivos ausentes.")]
    db.answers[count_missing] = lambda location, folder: MissingCount(items=2)
    box.answer = "Quitar del catálogo"
    importer.request_remove_missing(7, "Viajes")
    assert len(db.called(remove_missing_items)) == 2
    assert box.log[-1][1].startswith("Hay 2 archivos de esta carpeta") and "subcarpeta" not in box.log[-1][1]
    # Con carpetas que ya no están (CAT 6.2c): la pregunta las nombra; sin archivos, también
    db.answers[count_missing] = lambda location, folder: MissingCount(2, 1, True)
    importer.request_remove_missing(7, "Viajes")
    assert "La carpeta tampoco está: se quitará también del árbol." in box.log[-1][1]
    db.answers[count_missing] = lambda location, folder: MissingCount(0, 1, True)
    importer.request_remove_missing(7, "Viajes")
    assert box.log[-1][1].startswith("Esta carpeta ya no está en el disco.\n\n¿Quitarla del")
    db.answers[count_missing] = lambda location, folder: MissingCount(0, 3, False)
    importer.request_remove_missing(7, "Viajes")
    assert box.log[-1][1].startswith("3 subcarpetas ya no están en el disco")
    assert "¿Quitarlas del catálogo? En el disco no se toca nada." in box.log[-1][1]
    assert len(db.called(remove_missing_items)) == 5
    print("8. Quitar archivos ausentes desde el menú (también las carpetas que ya no están)")

    # 9. Un aviso de avance rezagado (ya terminado) no hace nada
    importer.scan_progress.emit(SimpleNamespace(saved_items=99))
    app.processEvents()
    print("9. Avance rezagado: ignorado")

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
