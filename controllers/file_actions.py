"""Cambiar el nombre de un archivo o de una carpeta, y mover archivos a una carpeta.

Está aparte de 'main_window_controller.py' para no seguir engordándolo: el controlador solo
lo crea y lo conecta. Lo que se hace en el disco y en el catálogo está en
'core/file_ops/moves.py'; las reglas, en docs/DECISIONES.md (19/11/2026).

    GridActions.rename_requested(ids)  (menú de la tarjeta, tecla F2)
        └─► request_rename: ¿uno solo? ¿algo en marcha? → el archivo ('fetch_media_file',
                segundo plano) → ¿está en el disco? → la ventana ('rename_dialog.py')
                → el plan ('plan_rename', segundo plano) → si se omite (ya existe otro con
                ese nombre...), el motivo y otra vez la ventana con lo escrito
                → el trabajo ('execute_file_moves', «Moviendo archivos»)
    CatalogSidebar.rename_folder_requested(ubicación, carpeta, nombre)  (CAT 4.3)
        └─► request_folder_rename: ¿algo en marcha? → ¿se puede? ('plan_folder_rename' con
                el nombre que tiene: conectada, no la raíz, en el disco; cuántos archivos)
                → la ventana, en modo carpeta → el plan con el nombre nuevo → si no se
                puede, el motivo y otra vez la ventana → el trabajo ('execute_folder_rename')
    CatalogSidebar.media_dropped_on_folder(ubicación, carpeta, nombre, tarjetas)  (CAT 4.4b)
        └─► request_move: ¿del mismo catálogo? ¿algo en marcha? → el plan ('plan_move',
                segundo plano: qué se omite y por qué, y las carpetas de origen que se
                quedarían vacías) → nada que mover: por qué → la confirmación («Mover» /
                «Cancelar»: todo lo que toca el disco lleva aviso) → el trabajo
                ('execute_file_moves' con la papelera, para las carpetas que se vacían)
    JobCoordinator.files_finished / files_failed
        └─► si se renombró una carpeta, los módulos ponen al día lo que recuerdan por la
            ruta ('folder_renamed': lo desplegado y lo elegido); después, la cuadrícula y
            los contadores; aviso de lo que no se pudo (lo que esperaba a que terminara lo
            relanza después el coordinador)

Mientras la ventana está abierta, la escritura diferida no arranca (como en «Eliminar»):
se para al abrirla y se vuelve a programar si no se renombra; si se renombra, la programa
el coordinador al terminar el trabajo.

Uso (en el controlador principal, que solo lo crea y lo conecta):
    self.file_actions = FileActions(
        self, self.message_box, self.job_coordinator, get_db=lambda: self.db,
        busy_reason=self.remove_actions.busy_reason, reload_grid=self.mosaico_model.reload,
        refresh_counts=self._refresh_sidebar_counts,
        folder_renamed=lambda *args: self.module_host.folder_renamed(*args), parent=self,
    )
    self.grid_actions.rename_requested.connect(self.file_actions.request_rename)
    self.widget_catalog_sidebar.rename_folder_requested.connect(
        self.file_actions.request_folder_rename
    )
    self.widget_catalog_sidebar.media_dropped_on_folder.connect(self.file_actions.request_move)

1.2.0 Mover archivos soltados sobre una carpeta del árbol (CAT 4.4b): 'request_move', la
      confirmación ('move_confirmation_text') y, si no hay nada que mover, por qué
      ('nothing_to_move_text').
1.1.0 También el nombre de una carpeta (CAT 4.3): 'request_folder_rename' y, al terminar,
      'folder_renamed' para que los módulos pongan al día sus barras.
1.0.0 Primera versión (CAT 4.2): cambiar el nombre de un archivo.

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.file_actions
"""

__version__ = "1.2.0"
__all__ = [
    "FileActions",
    "failed_rename_text",
    "move_confirmation_text",
    "nothing_to_move_text",
    "skipped_rename_text",
]

# Librerías estándar
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.media_queries import AVAILABLE, OFFLINE, MediaFile, fetch_media_file
from core.file_ops.moves import (
    SKIP_SAME,
    FolderRenamePlan,
    MovePlan,
    execute_file_moves,
    execute_folder_rename,
    plan_folder_rename,
    plan_move,
    plan_rename,
)
from core.file_ops.naming import rename_keeping_extension
from ui_helpers.dialogs.rename_dialog import RenameDialog
from ui_helpers.helpers.ui_file_manager import move_to_trash
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar

# Se pregunta el nombre nuevo: (ventana, nombre actual, lo escrito antes[, folder_files=N])
# -> nombre o None ('RenameDialog.ask'; con 'folder_files', en modo carpeta)
AskName = Callable[..., str | None]


def skipped_rename_text(new_name: str, reason: str, *, folder: bool = False) -> str:
    """Aviso cuando el nombre nuevo no se puede usar (lo dice el plan: ya existe...)."""
    what = "de la carpeta " if folder else ""
    return f"No se puede cambiar el nombre {what}a «{new_name}»: {reason}."


def failed_rename_text(failed: Sequence[tuple[str, str]], *, folder: bool = False) -> str:
    """Aviso cuando el sistema no dejó cambiar el nombre ((ruta, motivo)...)."""
    names = ", ".join(f"«{Path(path).name}»" for path, _reason in failed)
    why = (
        "quizá haya un archivo suyo abierto en otro programa"
        if folder
        else "quizá esté abierto en otro programa"
    )
    what = "de la carpeta " if folder else "de "
    return (
        f"No se pudo cambiar el nombre {what}{names} ({why}).\n\n"
        "El detalle está en el registro."
    )


# Al mover, el motivo de que un archivo ya esté donde se suelta se dice de otra forma
_MOVE_REASONS = {SKIP_SAME: "ya está en esa carpeta"}

MOVE_BUTTON_TEXT = "Mover"
CANCEL_BUTTON_TEXT = "Cancelar"


def _files(count: int) -> str:
    return "1 archivo" if count == 1 else f"{count} archivos"


def _reasons_text(skipped: Sequence[tuple[str, str]]) -> str:
    """'1 porque ya está en esa carpeta, 2 porque ya existe un archivo con ese nombre'."""
    counts: dict[str, int] = {}
    for _path, reason in skipped:
        reason = _MOVE_REASONS.get(reason, reason)
        counts[reason] = counts.get(reason, 0) + 1
    return ", ".join(f"{count} porque {reason}" for reason, count in counts.items())


def nothing_to_move_text(folder_name: str, plan: MovePlan) -> str:
    """Aviso cuando no se puede mover nada de lo soltado (ya estaba allí, otro disco...)."""
    if plan.skipped and all(reason == SKIP_SAME for _path, reason in plan.skipped):
        verb = "Ya está" if len(plan.skipped) == 1 else "Ya están"
        return f"{verb} en «{folder_name}»."
    return f"No se puede mover nada a «{folder_name}»: {_reasons_text(plan.skipped)}."


def move_confirmation_text(folder_name: str, plan: MovePlan) -> str:
    """La confirmación antes de mover: cuántos, lo que se omite y las carpetas que se vacían."""
    count = len(plan.moves)
    if count == 1:
        head = (
            f"Se va a mover 1 archivo a «{folder_name}», también en el disco (con su .xmp, si "
            "es un RAW). Conserva la valoración, las palabras clave y las colecciones."
        )
    else:
        head = (
            f"Se van a mover {count} archivos a «{folder_name}», también en el disco (con su "
            ".xmp, si son RAW). Conservan la valoración, las palabras clave y las colecciones."
        )
    paragraphs = [head]
    if plan.skipped:
        verb = "no se moverá" if len(plan.skipped) == 1 else "no se moverán"
        paragraphs.append(
            f"{_files(len(plan.skipped))} {verb}: {_reasons_text(plan.skipped)}."
        )
    names = sorted(
        (PurePosixPath(top).name for empty in plan.empty_folders for top in empty.top_folders),
        key=str.casefold,
    )
    if len(names) == 1:
        paragraphs.append(
            f"La carpeta «{names[0]}» se quedará vacía y también se eliminará del disco."
        )
    elif names:
        listed = ", ".join(f"«{name}»" for name in names[:-1]) + f" y «{names[-1]}»"
        paragraphs.append(
            f"{len(names)} carpetas se quedarán vacías y también se eliminarán del disco: "
            f"{listed}."
        )
    items = sum(empty.folder_file_items for empty in plan.empty_folders)
    if items:
        paragraphs.append(
            f"Su archivo .arca.json, con los datos de {_files(items)} que ya no "
            f"{'está' if items == 1 else 'están'} en el disco, irá a la Papelera."
        )
    return "\n\n".join(paragraphs)


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
        folder_renamed: Callable[[int, str, str], None] | None = None,
        get_catalog_key: Callable[[], str] | None = None,
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
            folder_renamed: Se llama tras renombrar una carpeta (ubicación, ruta vieja,
                ruta nueva): los módulos ponen al día sus barras ('ModuleHost').
            get_catalog_key: La carpeta del catálogo abierto, en texto: las tarjetas
                soltadas de otro catálogo (otra ventana) no se mueven. None = no se mira.
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
        self._folder_renamed = folder_renamed
        self._get_catalog_key = get_catalog_key
        # Qué hace el trabajo en marcha, para el aviso si algo falla: 'rename' (un archivo),
        # 'folder' (una carpeta) o 'move' (mover a una carpeta)
        self._job_kind = "rename"
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
        self._job_kind = "rename"
        self._jobs.start_file_job(execute_file_moves, plan)

    # -------------------------------------------------------------------------
    # Carpetas (CAT 4.3)
    # -------------------------------------------------------------------------

    def request_folder_rename(self, location_id: int, folder: str, name: str) -> None:
        """«Cambiar nombre...» de una carpeta: primero, si se puede (segundo plano)."""
        if not self._ready():
            return
        self._get_db().execute_async(
            plan_folder_rename,
            location_id,
            folder,
            name,  # con el nombre que tiene: dice si se puede y cuántos archivos tiene
            on_result=lambda plan: self._on_folder_checked(name, plan),
            on_error=lambda error: logger.error(f"No se pudo mirar la carpeta {folder}: {error}"),
        )

    def _on_folder_checked(self, name: str, plan: FolderRenamePlan) -> None:
        """Si la carpeta se puede renombrar, la ventana; si no, por qué."""
        if self._get_db() is None:
            return
        if plan.problem not in (None, SKIP_SAME):
            self._message_box.info(
                f"No se puede cambiar el nombre de la carpeta «{name}»: {plan.problem}."
            )
            return
        self._ask_folder(plan, name, None)

    def _ask_folder(self, plan: FolderRenamePlan, name: str, initial: str | None) -> None:
        """La ventana en modo carpeta; con el nombre escrito, el plan (segundo plano)."""
        self._jobs.stop_scheduled_write()
        new_name = self._ask_name(self._window, name, initial, folder_files=plan.count)
        if new_name is None or not self._ready():
            self._jobs.schedule_write()
            return
        self._get_db().execute_async(
            plan_folder_rename,
            plan.location_id,
            plan.source_path,
            new_name,
            on_result=lambda new_plan: self._on_folder_planned(plan, name, new_name, new_plan),
            on_error=lambda error: (
                logger.error(f"No se pudo preparar el cambio de nombre: {error}"),
                self._jobs.schedule_write(),
            ),
        )

    def _on_folder_planned(
        self, checked: FolderRenamePlan, name: str, new_name: str, plan: FolderRenamePlan
    ) -> None:
        """Si el nombre se puede usar, el trabajo; si no, el motivo y otra vez la ventana."""
        if self._get_db() is None:
            return
        if plan.problem is not None:
            if plan.problem == SKIP_SAME:
                self._jobs.schedule_write()
                return
            self._message_box.warning(skipped_rename_text(new_name, plan.problem, folder=True))
            self._ask_folder(checked, name, new_name)
            return
        if not self._ready():
            self._jobs.schedule_write()
            return
        self._job_kind = "folder"
        self._jobs.start_file_job(execute_folder_rename, plan)

    # -------------------------------------------------------------------------
    # Mover a una carpeta (CAT 4.4b)
    # -------------------------------------------------------------------------

    def request_move(self, location_id: int, folder: str, name: str, drag: Any) -> None:
        """Tarjetas soltadas sobre una carpeta del árbol: primero el plan (segundo plano)."""
        if self._get_db() is None:
            return
        if self._get_catalog_key is not None and getattr(drag, "catalog", None) != (
            self._get_catalog_key()
        ):
            self._message_box.warning("Esos archivos son de otro catálogo: no se pueden mover.")
            return
        if not self._ready():
            return
        self._get_db().execute_async(
            plan_move,
            list(drag.ids),
            location_id,
            folder,
            on_result=lambda plan: self._on_move_planned(name, plan),
            on_error=lambda error: logger.error(f"No se pudo preparar el traslado: {error}"),
        )

    def _on_move_planned(self, name: str, plan: MovePlan) -> None:
        """La confirmación y el trabajo; si no hay nada que mover, por qué."""
        if self._get_db() is None:
            return
        if not plan.moves:
            self._message_box.info(nothing_to_move_text(name, plan))
            return
        self._jobs.stop_scheduled_write()
        answer = self._message_box.question(
            move_confirmation_text(name, plan),
            title=MOVE_BUTTON_TEXT,
            buttons=[MOVE_BUTTON_TEXT, CANCEL_BUTTON_TEXT],
        )
        if answer != MOVE_BUTTON_TEXT or not self._ready():
            self._jobs.schedule_write()
            return
        self._job_kind = "move"
        self._jobs.start_file_job(execute_file_moves, plan, trash=move_to_trash)

    def _on_files_finished(self, result: object) -> None:
        """Terminó de renombrar: cuadrícula, contadores y aviso de lo que falló.

        Lo que esperaba a que terminara lo lanza después 'JobCoordinator'. Si se renombró
        una carpeta, ANTES los módulos ponen al día lo que recuerdan por la ruta: así la
        carpeta elegida sigue elegida con su nombre nuevo.
        """
        folder = getattr(result, "folder", None)
        if folder is not None and self._folder_renamed is not None:
            self._folder_renamed(*folder)
        self._reload_grid()
        self._refresh_counts()
        failed = list(getattr(result, "failed", ()))
        if failed:
            if self._job_kind == "move":
                text = failed_rename_text(failed).replace(
                    "No se pudo cambiar el nombre de", "No se pudo mover"
                )
            else:
                text = failed_rename_text(failed, folder=self._job_kind == "folder")
            self._message_box.warning(text)

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

    def fake_ask(
        _window: QWidget, file_name: str, initial: str | None, **kwargs: object
    ) -> str | None:
        asked.append((file_name, initial, *kwargs.values()))
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
        folder_renamed=lambda *args: events.append(("folder", *args)),
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
    assert box.log[-1] == (
        "info", "No se puede cambiar el nombre de «IMG_1.CR3»: no está en el disco."
    )
    assert asked == []
    print("4. Varios, algo en marcha o ausente: sin ventana")

    # 5. Al terminar: cuadrícula, contadores y el aviso si algo falló
    box.log.clear()
    jobs.files_finished.emit(SimpleNamespace(failed=[("C:/Fotos/IMG_1.CR3", "abierto")]))
    jobs.files_failed.emit()
    assert events == ["reload", "counts", "reload", "counts"]
    assert box.log[0][0] == "warning" and "«IMG_1.CR3»" in box.log[0][1]
    print("5. Al terminar o fallar: la cuadrícula al día")

    # 6. Una carpeta: se mira si se puede, la ventana (modo carpeta), el plan y el trabajo;
    #    al terminar, primero los módulos (lo elegido) y después la cuadrícula
    asked.clear()
    events.clear()
    jobs.log.clear()
    checked = FolderRenamePlan(1, "2024/Viaje", "2024/Viaje", Path("C:/F"), 12, SKIP_SAME)
    ready = FolderRenamePlan(1, "2024/Viaje", "2024/Ordesa", Path("C:/F"), 12, None)
    db.plans.extend([checked, ready])
    answers.append("Ordesa")
    actions.request_folder_rename(1, "2024/Viaje", "Viaje")
    assert asked == [("Viaje", None, 12)], asked
    assert jobs.log[-1] == ("start", execute_folder_rename, (ready,))
    jobs.files_finished.emit(SimpleNamespace(folder=(1, "2024/Viaje", "2024/Ordesa"), failed=[]))
    assert events == [("folder", 1, "2024/Viaje", "2024/Ordesa"), "reload", "counts"], events
    # Una carpeta de un disco desconectado: el motivo, sin ventana
    asked.clear()
    db.plans.append(FolderRenamePlan(1, "X", "X", None, 0, "su disco no está conectado"))
    actions.request_folder_rename(1, "X", "X")
    assert asked == [] and box.log[-1][1].endswith("su disco no está conectado.")
    assert "carpeta" in failed_rename_text([("C:/F/Viaje", "x")], folder=True)
    print("6. Una carpeta: se mira, ventana, plan y trabajo; al terminar, los módulos primero")

    # 7. Mover a una carpeta: los textos, la confirmación y el trabajo con la papelera
    from core.catalog.empty_folders import EmptyFolder, EmptyFolderPlan
    from ui_helpers.models.media_mime import MediaDrag

    two = MovePlan(
        moves=(move, move),
        skipped=(("x.jpg", SKIP_SAME), ("y.jpg", SKIP_EXISTS)),
        empty_folders=(EmptyFolderPlan(Path("C:/F"), (EmptyFolder("2024/Viaje"),)),),
    )
    text = move_confirmation_text("Ordesa", two)
    assert text.startswith("Se van a mover 2 archivos a «Ordesa», también en el disco"), text
    assert "2 archivos no se moverán: 1 porque ya está en esa carpeta, 1 porque ya existe" in text
    assert "La carpeta «Viaje» se quedará vacía y también se eliminará del disco." in text
    assert nothing_to_move_text("Ordesa", MovePlan(skipped=(("x", SKIP_SAME),))) == (
        "Ya está en «Ordesa»."
    )
    music = MovePlan(skipped=(("x", "la carpeta de destino es de «Música»"),))
    assert nothing_to_move_text("M", music) == (
        "No se puede mover nada a «M»: 1 porque la carpeta de destino es de «Música»."
    )
    jobs.log.clear()
    box.question = lambda text, **_k: (box.log.append(("question", text)), "Mover")[1]
    db.plans.append(MovePlan(moves=(move,)))
    actions._get_catalog_key = lambda: "C:/Catalogo"
    actions.request_move(1, "Ordesa", "Ordesa", MediaDrag("C:/Catalogo", (7,)))
    assert jobs.log[-1] == ("start", execute_file_moves, (MovePlan(moves=(move,)),))
    assert box.log[-1][0] == "question" and "a «Ordesa»" in box.log[-1][1]
    actions.request_move(1, "Ordesa", "Ordesa", MediaDrag("C:/Otro", (7,)))
    assert box.log[-1] == ("warning", "Esos archivos son de otro catálogo: no se pueden mover.")
    print("7. Mover a una carpeta: textos, confirmación y trabajo; otro catálogo, no")

    window.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
