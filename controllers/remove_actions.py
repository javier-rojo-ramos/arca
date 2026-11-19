"""«Eliminar...»: quitar archivos del catálogo o enviarlos también a la papelera.

Sacado de 'main_window_controller.py' (docs/PENDIENTE.md, GEN 15.3) SIN CAMBIAR lo que
hace: el código se movió tal cual. El trabajo lo lanza el coordinador de los trabajos
('job_coordinator.py', con el nombre «remove»), que avisa al terminar.

    GridActions.remove_requested(ids)  (menú de las tarjetas, tecla Supr)
        └─► request_remove: ¿algo en marcha? → qué puede ir a la papelera (segundo plano)
                → la ventana «Eliminar» ('remove_dialog.py') → el trabajo
                ('remove_media_items'; con «del catálogo», antes escribe lo pendiente)
    JobCoordinator.removal_finished / removal_failed
        └─► la cuadrícula y los contadores, al día; aviso de lo que no fue a la papelera
            (lo que esperaba a que terminara lo relanza después el coordinador)

También lo usa «Quitar del catálogo...» de una carpeta ('folder_actions.py'): le pide
'busy_reason' y 'start_removal_job', para que vaya por el mismo camino.

Uso (en el controlador principal, que solo lo crea y lo conecta):
    self.remove_actions = RemoveActions(
        self, self.message_box, self.job_coordinator, get_db=lambda: self.db,
        is_adding_folder=lambda: self.folder_import.is_running,
        reload_grid=self.mosaico_model.reload, refresh_counts=self._refresh_sidebar_counts,
        parent=self,
    )
    self.grid_actions.remove_requested.connect(self.remove_actions.request_remove)

1.2.0 «Eliminar del disco» pasa al trabajo las carpetas que se quedan vacías, las que
      anunció la ventana ('RemovalPlan.empty_folders', CAT 3.3).
1.1.0 'start_removal_job' pasa al trabajo los argumentos con nombre (las carpetas vacías
      y la papelera de «Quitar del catálogo…», CAT 3.2).
1.0.0 Primera versión (GEN 15.3): el código de 'main_window_controller.py', movido.

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.remove_actions
"""

__version__ = "1.2.0"
__all__ = ["REMOVE_FAILED_LIST_MAX", "RemoveActions", "failed_trash_text"]

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
from core.catalog.media_removal import RemovalPlan, plan_removal, remove_media_items
from ui_helpers.dialogs.remove_dialog import RemoveDialog
from ui_helpers.helpers.ui_file_manager import move_to_trash
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar

# Archivos que, como mucho, se enumeran en el aviso de los que no se pudieron eliminar
REMOVE_FAILED_LIST_MAX = 10


def failed_trash_text(failed: Sequence[tuple[str, str]]) -> str:
    """Aviso de los archivos que no se pudieron enviar a la papelera ((ruta, motivo)...).

    Está fuera de la clase para poder probarlo sin ventanas.
    """
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
    return f"{head}\n\n{shown}\n\nEl detalle está en el registro."


class RemoveActions(QObject):
    """Atiende «Eliminar...» y lo que se hace al terminar cualquier trabajo de quitar."""

    def __init__(
        self,
        window: QWidget,
        message_box: MessageBoxHelper,
        jobs: Any,
        *,
        get_db: Callable[[], Any],
        is_adding_folder: Callable[[], bool],
        reload_grid: Callable[[], None],
        refresh_counts: Callable[[], None],
        ask_remove: Callable[[QWidget, RemovalPlan], bool | None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Conecta los avisos del coordinador de los trabajos.

        Args:
            window: Ventana principal (padre de la ventana «Eliminar»; su barra de estado).
            message_box: Ayudante de mensajes de la ventana.
            jobs: El coordinador de los trabajos ('JobCoordinator').
            get_db: Devuelve el gestor de la base de datos del catálogo abierto, o None.
            is_adding_folder: True mientras se añade o sincroniza una carpeta.
            reload_grid: Vuelve a leer la cuadrícula.
            refresh_counts: Pone al día los contadores de la barra lateral.
            ask_remove: La ventana «Eliminar» (None = 'RemoveDialog.ask'; se busca al crear
                el objeto: así una prueba puede sustituir 'RemoveDialog' en este módulo).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._window = window
        self._message_box = message_box
        self._jobs = jobs
        self._get_db = get_db
        self._is_adding_folder = is_adding_folder
        self._reload_grid = reload_grid
        self._refresh_counts = refresh_counts
        self._ask_remove = ask_remove or RemoveDialog.ask
        jobs.removal_finished.connect(self._on_removal_finished)
        jobs.removal_failed.connect(self._on_removal_failed)

    def busy_reason(self) -> str | None:
        """Por qué ahora no se puede eliminar (algo en marcha), o None si se puede.

        Eliminar mientras se añade una carpeta o corre un trabajo podría dejar miniaturas
        de elementos ya quitados o escribir en un archivo que va a la papelera.
        """
        if self._is_adding_folder():
            return "Se está añadiendo una carpeta al catálogo."
        return self._jobs.busy_reason()

    def request_remove(self, media_ids: list[int]) -> None:
        """«Eliminar...» de la cuadrícula: primero se calcula qué puede ir a la papelera."""
        db = self._get_db()
        if db is None or not self._jobs.is_attached or not media_ids:
            return
        busy = self.busy_reason()
        if busy:
            self._message_box.info(f"{busy}\n\nEspera a que termine para eliminar archivos.")
            return
        ids = list(media_ids)
        db.execute_async(
            plan_removal,
            ids,
            on_result=lambda plan: self._on_removal_planned(ids, plan),
            on_error=lambda error: (
                logger.error(f"No se pudo preparar la eliminación: {error}"),
                message_bar(self._window, "No se pudo preparar la eliminación.", AppIcons.ERROR),
            ),
        )

    def _on_removal_planned(self, media_ids: list[int], plan: RemovalPlan) -> None:
        """Pregunta qué hacer (quitar del catálogo o papelera) y lanza el trabajo."""
        if self._get_db() is None or not self._jobs.is_attached or plan.total == 0:
            return  # el catálogo se cerró mientras tanto, o ya no existen
        # Mientras la ventana está abierta no debe arrancar la escritura diferida (su
        # temporizador sigue corriendo durante un diálogo modal): se para y, si no se
        # elimina, se vuelve a programar
        self._jobs.stop_scheduled_write()
        to_trash = self._ask_remove(self._window, plan)
        busy = self.busy_reason() if to_trash is not None else None
        if to_trash is None or busy or not self._jobs.is_attached:
            if busy:
                self._message_box.info(f"{busy}\n\nNo se ha eliminado nada; inténtalo al terminar.")
            self._jobs.schedule_write()
            return

        # Con la papelera no se escribe antes lo pendiente: el archivo se va; y se borran las
        # carpetas que se quedan vacías, las que anunció la ventana (CAT 3.3)
        self._jobs.start_removal(
            remove_media_items,
            media_ids,
            to_trash=to_trash,
            trash=move_to_trash if to_trash else None,
            write_pending=None if to_trash else self._jobs.pending_writer(),
            empty_folders=plan.empty_folders if to_trash else (),
        )

    def start_removal_job(
        self, job: Callable[..., object], *args: object, **kwargs: object
    ) -> None:
        """Lanza un trabajo de quitar del catálogo (p. ej. una carpeta) como "Eliminar".

        Con el mismo nombre que «Eliminar»: misma barra de progreso y, al terminar, lo mismo
        que tras eliminar ('_on_removal_finished'). Se vuelve a comprobar que no haya nada
        en marcha: puede haber empezado algo mientras se preguntaba al usuario. Los
        argumentos con nombre pasan al trabajo (p. ej. las carpetas vacías y la papelera).
        """
        if not self._jobs.is_attached:
            return
        busy = self.busy_reason()
        if busy:
            self._message_box.info(f"{busy}\n\nNo se ha quitado nada; inténtalo al terminar.")
            return
        self._jobs.start_removal(
            job, *args, write_pending=self._jobs.pending_writer(), **kwargs
        )

    def _on_removal_finished(self, result: object) -> None:
        """Terminó de eliminar: cuadrícula, contadores y aviso de fallos.

        Lo que esperaba a que terminara lo lanza después 'JobCoordinator'.
        """
        # Lo quitado desaparece de la cuadrícula (queda seleccionado el que ocupa su lugar:
        # 'CenterViewController')
        self._reload_grid()
        self._refresh_counts()

        failed = list(getattr(result, "failed", ()))
        if failed:
            self._message_box.warning(failed_trash_text(failed))

    def _on_removal_failed(self) -> None:
        """Eliminar falló: lo que se llegó a quitar está confirmado por lotes; se muestra."""
        self._reload_grid()
        self._refresh_counts()


if __name__ == "__main__":
    # Autoprueba sin ventana: el coordinador, la base de datos, los mensajes y la ventana
    # «Eliminar» son de mentira (responden al momento).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.remove_actions
    import sys
    from types import SimpleNamespace

    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import QApplication, QMainWindow

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. El aviso de lo que no fue a la papelera (1, varios y más de los que se enumeran)
    one = failed_trash_text([("C:/Fotos/a.jpg", "abierto")])
    assert one.startswith("No se pudo enviar a la papelera 1 archivo") and "\na.jpg\n" in one
    many = failed_trash_text([(f"C:/Fotos/{n}.jpg", "x") for n in range(12)])
    assert many.startswith("No se pudieron enviar a la papelera 12 archivos")
    assert "9.jpg\n... y 2 más" in many and "10.jpg" not in many
    print("1. Aviso de la papelera")

    class FakeJobs(QObject):
        """Lo que se usa del 'JobCoordinator'."""

        removal_finished = Signal(object)
        removal_failed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.is_attached = True
            self.busy: str | None = None
            self.log: list[tuple] = []

        def busy_reason(self) -> str | None:
            return self.busy

        def stop_scheduled_write(self) -> None:
            self.log.append(("stop_write",))

        def schedule_write(self) -> None:
            self.log.append(("schedule_write",))

        def pending_writer(self) -> object:
            return "escribir-pendiente"

        def start_removal(self, job: object, *args: object, **kwargs: object) -> None:
            self.log.append(("start", job, args, kwargs))

    class FakeDb:
        def __init__(self, plan: RemovalPlan) -> None:
            self.plan = plan

        def execute_async(self, _function: object, *_args: object, on_result: Any = None, **_k: object) -> None:
            on_result(self.plan)

    class FakeBox:
        def __init__(self) -> None:
            self.log: list[tuple[str, str]] = []

        def info(self, text: str, **_kwargs: object) -> None:
            self.log.append(("info", text))

        def warning(self, text: str, **_kwargs: object) -> None:
            self.log.append(("warning", text))

    window = QMainWindow()
    jobs, box = FakeJobs(), FakeBox()
    state: dict[str, Any] = {"db": FakeDb(RemovalPlan(total=2, trashable=2)), "adding": False}
    answers: list[bool | None] = []
    events: list[str] = []
    actions = RemoveActions(
        window,
        box,  # type: ignore[arg-type]
        jobs,
        get_db=lambda: state["db"],
        is_adding_folder=lambda: state["adding"],
        reload_grid=lambda: events.append("reload"),
        refresh_counts=lambda: events.append("counts"),
        ask_remove=lambda _window, _plan: answers.pop(0),
    )

    # 2. «Eliminar del catálogo»: para la escritura diferida mientras pregunta, y lanza el
    #    trabajo escribiendo antes lo pendiente
    answers.append(False)
    actions.request_remove([3, 4])
    assert jobs.log[0] == ("stop_write",)
    (_, job, args, kwargs) = jobs.log[1]
    assert job is remove_media_items and args == ([3, 4],)
    assert kwargs == {
        "to_trash": False, "trash": None, "write_pending": "escribir-pendiente",
        "empty_folders": (),
    }  # fmt: skip
    print("2. Eliminar del catálogo")

    # 3. «Eliminar del disco»: con la papelera y sin escribir antes (el archivo se va)
    jobs.log.clear()
    answers.append(True)
    actions.request_remove([5])
    kwargs = jobs.log[1][3]
    assert kwargs["to_trash"] is True and kwargs["trash"] is move_to_trash
    assert kwargs["write_pending"] is None and kwargs["empty_folders"] == ()  # el plan, tal cual
    print("3. Eliminar del disco")

    # 4. «Cancelar» en la ventana: no se elimina y la escritura vuelve a programarse
    jobs.log.clear()
    answers.append(None)
    actions.request_remove([6])
    assert jobs.log == [("stop_write",), ("schedule_write",)]
    print("4. Cancelar")

    # 5. Algo en marcha (antes de preguntar, o si empieza mientras se pregunta): no se elimina
    jobs.log.clear()
    jobs.busy = "Hay un trabajo en marcha: «Generando miniaturas»."
    actions.request_remove([7])
    assert jobs.log == [] and box.log[-1][1].startswith("Hay un trabajo en marcha")
    jobs.busy = None
    state["adding"] = True
    assert actions.busy_reason() == "Se está añadiendo una carpeta al catálogo."
    state["adding"] = False

    def start_job_while_asking(_window: QWidget, _plan: RemovalPlan) -> bool:
        jobs.busy = "Hay un trabajo en marcha: «Leyendo metadatos»."
        return False

    actions._ask_remove = start_job_while_asking
    actions.request_remove([8])
    assert [entry[0] for entry in jobs.log] == ["stop_write", "schedule_write"]
    assert "No se ha eliminado nada" in box.log[-1][1]
    jobs.busy = None
    print("5. Con algo en marcha, no se elimina")

    # 6. Quitar una carpeta ('folder_actions'): el mismo camino, escribiendo antes lo pendiente
    jobs.log.clear()

    def remove_folder(*_args: object) -> None:
        """Un trabajo de quitar de mentira."""

    actions.start_removal_job(remove_folder, 7, "Viajes")
    assert jobs.log == [("start", remove_folder, (7, "Viajes"), {"write_pending": "escribir-pendiente"})]
    jobs.log.clear()
    actions.start_removal_job(remove_folder, 7, "Viajes", trash="papelera")  # con más argumentos
    assert jobs.log[0][3] == {"write_pending": "escribir-pendiente", "trash": "papelera"}
    print("6. Quitar una carpeta (con argumentos para el trabajo)")

    # 7. Al terminar: cuadrícula, contadores y el aviso si algo no fue a la papelera
    box.log.clear()
    jobs.removal_finished.emit(SimpleNamespace(failed=[("C:/Fotos/a.jpg", "abierto")]))
    jobs.removal_failed.emit()
    assert events == ["reload", "counts", "reload", "counts"]
    assert box.log[0][0] == "warning" and "a.jpg" in box.log[0][1]
    print("7. Al terminar o fallar: la cuadrícula al día")

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
