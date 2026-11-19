"""«Cambiar nombre...» de un archivo: la ventana, el plan y el trabajo (CAT 4.2).

Está aparte de 'main_window_controller.py' para no seguir engordándolo: el controlador solo
lo crea y lo conecta. Lo que se hace en el disco y en el catálogo está en
'core/file_ops/moves.py'; las reglas, en docs/DECISIONES.md (19/11/2026).

    GridActions.rename_requested(ids)  (menú de la tarjeta, tecla F2)
        └─► request_rename: ¿uno solo? ¿algo en marcha? → el archivo ('fetch_media_file',
                segundo plano) → ¿está en el disco? → la ventana ('rename_dialog.py')
                → el plan ('plan_rename', segundo plano) → si se omite (ya existe otro con
                ese nombre...), el motivo y otra vez la ventana con lo escrito
                → el trabajo ('execute_file_moves', «Moviendo archivos»)
    JobCoordinator.files_finished / files_failed
        └─► la cuadrícula y los contadores, al día; aviso de lo que no se pudo
            (lo que esperaba a que terminara lo relanza después el coordinador)

Mientras la ventana está abierta, la escritura diferida no arranca (como en «Eliminar»):
se para al abrirla y se vuelve a programar si no se renombra; si se renombra, la programa
el coordinador al terminar el trabajo.

Uso (en el controlador principal, que solo lo crea y lo conecta):
    self.file_actions = FileActions(
        self, self.message_box, self.job_coordinator, get_db=lambda: self.db,
        busy_reason=self.remove_actions.busy_reason, reload_grid=self.mosaico_model.reload,
        refresh_counts=self._refresh_sidebar_counts, parent=self,
    )
    self.grid_actions.rename_requested.connect(self.file_actions.request_rename)

1.0.0 Primera versión (CAT 4.2): cambiar el nombre de un archivo.

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.file_actions
"""

__version__ = "1.0.0"
__all__ = ["FileActions", "failed_rename_text", "skipped_rename_text"]

# Librerías estándar
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.media_queries import AVAILABLE, OFFLINE, MediaFile, fetch_media_file
from core.file_ops.moves import SKIP_SAME, MovePlan, execute_file_moves, plan_rename
from core.file_ops.naming import rename_keeping_extension
from ui_helpers.dialogs.rename_dialog import RenameDialog
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar

# Se pregunta el nombre nuevo: (ventana, nombre actual, lo escrito antes) -> nombre o None
AskName = Callable[[QWidget, str, str | None], str | None]


def skipped_rename_text(new_name: str, reason: str) -> str:
    """Aviso cuando el nombre nuevo no se puede usar (lo dice el plan: ya existe...)."""
    return f"No se puede cambiar el nombre a «{new_name}»: {reason}."


def failed_rename_text(failed: Sequence[tuple[str, str]]) -> str:
    """Aviso cuando el sistema no dejó cambiar el nombre ((ruta, motivo)...)."""
    names = ", ".join(f"«{Path(path).name}»" for path, _reason in failed)
    return (
        f"No se pudo cambiar el nombre de {names} (quizá esté abierto en otro programa).\n\n"
        "El detalle está en el registro."
    )


class FileActions(QObject):
    """Atiende «Cambiar nombre...» y lo que se hace al terminar de renombrar."""

    def __init__(
        self,
        window: QWidget,
        message_box: MessageBoxHelper,
        jobs: Any,
        *,
        get_db: Callable[[], Any],
        busy_reason: Callable[[], str | None],
        reload_grid: Callable[[], None],
        refresh_counts: Callable[[], None],
        ask_name: AskName | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Conecta los avisos del coordinador de los trabajos.

        Args:
            window: Ventana principal (padre de la ventana; su barra de estado).
            message_box: Ayudante de mensajes de la ventana.
            jobs: El coordinador de los trabajos ('JobCoordinator').
            get_db: Devuelve el gestor de la base de datos del catálogo abierto, o None.
            busy_reason: Por qué ahora no se puede (algo en marcha), o None
                ('RemoveActions.busy_reason': añadir carpeta o cualquier trabajo).
            reload_grid: Vuelve a leer la cuadrícula.
            refresh_counts: Pone al día los contadores de la barra lateral.
            ask_name: La ventana (None = 'RenameDialog.ask'; para las pruebas).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._window = window
        self._message_box = message_box
        self._jobs = jobs
        self._get_db = get_db
        self._busy_reason = busy_reason
        self._reload_grid = reload_grid
        self._refresh_counts = refresh_counts
        self._ask_name: AskName = ask_name or RenameDialog.ask
        jobs.files_finished.connect(self._on_files_finished)
        jobs.files_failed.connect(self._on_files_failed)

    def _ready(self) -> bool:
        """True si hay catálogo abierto y nada en marcha (si hay algo, lo dice)."""
        if self._get_db() is None or not self._jobs.is_attached:
            return False
        busy = self._busy_reason()
        if busy:
            self._message_box.info(f"{busy}\n\nEspera a que termine para cambiar el nombre.")
            return False
        return True

    def request_rename(self, media_ids: list[int]) -> None:
        """«Cambiar nombre...» o F2: primero se mira el archivo (segundo plano)."""
        if not media_ids or self._get_db() is None:
            return
        if len(media_ids) > 1:
            message_bar(
                self._window, "Para cambiar el nombre, elige un solo archivo.", AppIcons.WARNING
            )
            return
        if not self._ready():
            return
        media_id = media_ids[0]
        self._get_db().execute_async(
            fetch_media_file,
            media_id,
            on_result=lambda media_file: self._on_file(media_id, media_file),
            on_error=lambda error: logger.error(f"No se pudo leer el archivo {media_id}: {error}"),
        )

    def _on_file(self, media_id: int, media_file: MediaFile | None) -> None:
        """Con el archivo a la vista: si está en el disco, la ventana."""
        if self._get_db() is None or media_file is None:
            return  # el catálogo se cerró mientras tanto, o el archivo ya no está
        name = media_file.path.name
        if media_file.availability != AVAILABLE:
            reason = (
                "su disco no está conectado"
                if media_file.availability == OFFLINE
                else "no está en el disco"
            )
            self._message_box.info(f"No se puede cambiar el nombre de «{name}»: {reason}.")
            return
        self._ask(media_id, name, None)

    def _ask(self, media_id: int, file_name: str, initial_stem: str | None) -> None:
        """La ventana; con el nombre escrito, el plan (segundo plano)."""
        # Mientras la ventana está abierta no debe arrancar la escritura diferida (su
        # temporizador sigue corriendo durante un diálogo modal)
        self._jobs.stop_scheduled_write()
        stem = self._ask_name(self._window, file_name, initial_stem)
        if stem is None or not self._ready():
            self._jobs.schedule_write()
            return
        self._get_db().execute_async(
            plan_rename,
            media_id,
            stem,
            on_result=lambda plan: self._on_planned(media_id, file_name, stem, plan),
            on_error=lambda error: (
                logger.error(f"No se pudo preparar el cambio de nombre: {error}"),
                self._jobs.schedule_write(),
            ),
        )

    def _on_planned(self, media_id: int, file_name: str, stem: str, plan: MovePlan) -> None:
        """Si el nombre se puede usar, el trabajo; si no, el motivo y otra vez la ventana."""
        if self._get_db() is None:
            return
        if not plan.moves:
            reason = plan.skipped[0][1] if plan.skipped else ""
            if reason == SKIP_SAME or not reason:
                self._jobs.schedule_write()
                return
            new_name = rename_keeping_extension(file_name, stem)
            self._message_box.warning(skipped_rename_text(new_name, reason))
            self._ask(media_id, file_name, stem)  # para corregirlo, con lo que se escribió
            return
        if not self._ready():
            self._jobs.schedule_write()
            return
        self._jobs.start_file_job(execute_file_moves, plan)

    def _on_files_finished(self, result: object) -> None:
        """Terminó de renombrar: cuadrícula, contadores y aviso de lo que falló.

        Lo que esperaba a que terminara lo lanza después 'JobCoordinator'.
        """
        self._reload_grid()
        self._refresh_counts()
        failed = list(getattr(result, "failed", ()))
        if failed:
            self._message_box.warning(failed_rename_text(failed))

    def _on_files_failed(self) -> None:
        """Renombrar falló: cada archivo se confirma por separado; se muestra lo que hay."""
        self._reload_grid()
        self._refresh_counts()


if __name__ == "__main__":
    # Autoprueba sin ventana: el coordinador, la base de datos, los mensajes y la ventana
    # «Cambiar nombre» son de mentira (responden al momento).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.file_actions
    import sys
    from types import SimpleNamespace

    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import QApplication, QMainWindow

    from core.catalog.media_queries import MISSING
    from core.file_ops.moves import SKIP_EXISTS, PlannedMove

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Los avisos
    assert skipped_rename_text("Boda.CR3", SKIP_EXISTS) == (
        "No se puede cambiar el nombre a «Boda.CR3»: ya existe un archivo con ese nombre."
    )
    assert failed_rename_text([("C:/Fotos/a.jpg", "x")]).startswith(
        "No se pudo cambiar el nombre de «a.jpg» (quizá"
    )
    print("1. Avisos")

    class FakeJobs(QObject):
        """Lo que se usa del 'JobCoordinator'."""

        files_finished = Signal(object)
        files_failed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.is_attached = True
            self.log: list[tuple] = []

        def stop_scheduled_write(self) -> None:
            self.log.append(("stop_write",))

        def schedule_write(self) -> None:
            self.log.append(("schedule_write",))

        def start_file_job(self, job: object, *args: object, **kwargs: object) -> None:
            self.log.append(("start", job, args))

    class FakeDb:
        """'execute_async' que responde al momento: el archivo o el plan."""

        def __init__(self) -> None:
            self.media_file: MediaFile | None = None
            self.plans: list[MovePlan] = []

        def execute_async(self, function: object, *_args: object, on_result: Any = None,
                          **_kwargs: object) -> None:  # fmt: skip
            on_result(self.media_file if function is fetch_media_file else self.plans.pop(0))

    class FakeBox:
        def __init__(self) -> None:
            self.log: list[tuple[str, str]] = []

        def info(self, text: str, **_kwargs: object) -> None:
            self.log.append(("info", text))

        def warning(self, text: str, **_kwargs: object) -> None:
            self.log.append(("warning", text))

    window = QMainWindow()
    jobs, box, db = FakeJobs(), FakeBox(), FakeDb()
    state: dict[str, Any] = {"busy": None}
    answers: list[str | None] = []
    asked: list[tuple[str, str | None]] = []
    events: list[str] = []

    def fake_ask(_window: QWidget, file_name: str, initial: str | None) -> str | None:
        asked.append((file_name, initial))
        return answers.pop(0)

    actions = FileActions(
        window,
        box,  # type: ignore[arg-type]
        jobs,
        get_db=lambda: db,
        busy_reason=lambda: state["busy"],
        reload_grid=lambda: events.append("reload"),
        refresh_counts=lambda: events.append("counts"),
        ask_name=fake_ask,
    )
    db.media_file = MediaFile(7, Path("C:/Fotos/IMG_1.CR3"), None, AVAILABLE)
    move = PlannedMove(7, 1, Path("C:/Fotos"), "IMG_1.CR3", 1, Path("C:/Fotos"), "Boda.CR3")

    # 2. Cambiar el nombre: la ventana, el plan y el trabajo
    answers.append("Boda")
    db.plans.append(MovePlan(moves=(move,)))
    actions.request_rename([7])
    assert asked == [("IMG_1.CR3", None)]
    assert jobs.log == [("stop_write",), ("start", execute_file_moves, (MovePlan(moves=(move,)),))]
    print("2. Cambiar el nombre: ventana, plan y trabajo")

    # 3. El nombre ya existe: el motivo y otra vez la ventana con lo escrito; cancelar
    jobs.log.clear()
    asked.clear()
    answers.extend(["Ocupado", None])
    db.plans.append(MovePlan(skipped=(("IMG_1.CR3", SKIP_EXISTS),)))
    actions.request_rename([7])
    assert asked == [("IMG_1.CR3", None), ("IMG_1.CR3", "Ocupado")]
    assert box.log[-1] == ("warning", skipped_rename_text("Ocupado.CR3", SKIP_EXISTS))
    assert jobs.log[-1] == ("schedule_write",) and all(entry[0] != "start" for entry in jobs.log)
    print("3. Nombre ocupado: el motivo y la ventana otra vez; cancelar")

    # 4. Varios archivos, algo en marcha, un archivo ausente: no se abre la ventana
    asked.clear()
    actions.request_rename([7, 8])
    state["busy"] = "Hay un trabajo en marcha: «Leyendo metadatos»."
    actions.request_rename([7])
    assert box.log[-1][1].startswith("Hay un trabajo en marcha")
    state["busy"] = None
    db.media_file = MediaFile(7, Path("C:/Fotos/IMG_1.CR3"), None, MISSING)
    actions.request_rename([7])
    assert box.log[-1] == ("info", "No se puede cambiar el nombre de «IMG_1.CR3»: no está en el disco.")
    assert asked == []
    print("4. Varios, algo en marcha o ausente: sin ventana")

    # 5. Al terminar: cuadrícula, contadores y el aviso si algo falló
    box.log.clear()
    jobs.files_finished.emit(SimpleNamespace(failed=[("C:/Fotos/IMG_1.CR3", "abierto")]))
    jobs.files_failed.emit()
    assert events == ["reload", "counts", "reload", "counts"]
    assert box.log[0][0] == "warning" and "«IMG_1.CR3»" in box.log[0][1]
    print("5. Al terminar o fallar: la cuadrícula al día")

    window.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
