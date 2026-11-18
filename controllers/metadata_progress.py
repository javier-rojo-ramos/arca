"""Abre y cierra la ventana «Leyendo metadatos» mientras dura la lectura de metadatos.

Decidido por el autor el 18/11/2026 (docs/PENDIENTE.md, GEN 20.2): mientras se leen los
metadatos no se puede modificar nada; una ventana modal con el avance bloquea la ventana
principal entera ('ui_helpers/dialogs/metadata_progress_dialog.py'), en lugar de vigilar
cada acción. Lo que protege los archivos de verdad está en los datos (GEN 20.1:
'core/userdata/LEEME.md'); esto es para que el usuario no edite lo que aún no ha visto.

Cuándo se ve:
    - Solo si la lectura dura más de SHOW_AFTER_MS (al abrir el catálogo con tres
      archivos cambiados fuera, la lectura acaba antes y no aparece nada).
    - Si en ese momento hay otra ventana modal abierta (el resumen «Carpeta añadida», que
      sale mientras la lectura ya ha empezado; Opciones...), espera a que se cierre.
    - Se cierra al terminar la lectura, al fallar o al cancelarla con su botón (el
      trabajo termina el lote en curso y entonces avisa). También si desaparece el
      gestor de trabajos (al cerrar el catálogo).
    - Lo demás no bloquea: el recorrido de «Añadir carpeta» (los archivos nuevos aún no
      se ven), las miniaturas (no tocan los datos del usuario) ni la escritura.

Uso (en el controlador principal, que solo lo crea y le pasa cada gestor de trabajos):
    self.metadata_progress = MetadataProgress(self, job_name=JOB_METADATA, parent=self)
    ...
    self.job_manager = JobManager(self.db, parent=self)
    self.metadata_progress.attach(self.job_manager)   # antes de conectar lo demás

Se conecta ANTES que el resto de las señales del gestor para que, al terminar o fallar
la lectura, la ventana se cierre antes de que salga cualquier otro aviso.

1.0.0 Primera versión (GEN 20.2).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.metadata_progress
"""

__version__ = "1.0.0"
__all__ = ["RETRY_MS", "SHOW_AFTER_MS", "MetadataProgress"]

# Librerías estándar
from collections.abc import Callable
from typing import Any, Protocol

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QTimer
from qtpy.QtWidgets import QApplication, QWidget

# Módulos del proyecto
from core.jobs.progress import JobProgress
from ui_helpers.dialogs.metadata_progress_dialog import MetadataProgressDialog

# La ventana solo sale si la lectura dura más que esto (ms): «un par de segundos»
SHOW_AFTER_MS = 2000

# Si hay otra ventana modal abierta, cada cuánto se vuelve a mirar (ms)
RETRY_MS = 300


class _ProgressWindow(Protocol):
    """Lo que se usa de la ventana (la de verdad, o una de mentira en la autoprueba)."""

    def set_progress(self, done: int, total: int) -> None: ...
    def show(self) -> None: ...
    def finish(self) -> None: ...
    def deleteLater(self) -> None: ...  # nombre de Qt


class MetadataProgress(QObject):
    """Sigue el trabajo de lectura de metadatos y muestra su ventana mientras dura."""

    def __init__(
        self,
        window: QWidget,
        *,
        job_name: str = "metadata",
        show_after_ms: int = SHOW_AFTER_MS,
        dialog_factory: Callable[[QWidget], Any] = MetadataProgressDialog,
        active_modal: Callable[[], QWidget | None] = QApplication.activeModalWidget,
        parent: QObject | None = None,
    ) -> None:
        """Prepara el seguimiento (aún sin gestor de trabajos: ver 'attach').

        Args:
            window: Ventana principal: la que se bloquea (padre de la ventana de avance).
            job_name: Nombre del trabajo de lectura de metadatos en el 'JobManager'.
            show_after_ms: Cuánto debe durar la lectura para que salga la ventana.
            dialog_factory: Crea la ventana (para las pruebas, una de mentira).
            active_modal: La ventana modal abierta, si la hay (para las pruebas).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._window = window
        self._job_name = job_name
        self._show_after_ms = show_after_ms
        self._dialog_factory = dialog_factory
        self._active_modal = active_modal
        self._jobs: Any = None  # el 'JobManager' del catálogo abierto
        self._dialog: _ProgressWindow | None = None
        self._progress: JobProgress | None = None  # el último avance (para abrir con él)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._try_show)

    # -------------------------------------------------------------------------
    # Gestor de trabajos (uno por catálogo)
    # -------------------------------------------------------------------------

    def attach(self, jobs: Any) -> None:
        """Empieza a seguir los trabajos de un 'JobManager' (deja el anterior)."""
        self.detach()
        self._jobs = jobs
        jobs.job_started.connect(self._on_started)
        jobs.job_progress.connect(self._on_progress)
        jobs.job_finished.connect(self._on_ended)
        jobs.job_failed.connect(self._on_ended)
        jobs.destroyed.connect(self._on_jobs_destroyed)

    def detach(self) -> None:
        """Deja de seguir el gestor actual y cierra la ventana, si se veía."""
        jobs, self._jobs = self._jobs, None
        if jobs is not None:
            for signal, slot in (
                (jobs.job_started, self._on_started),
                (jobs.job_progress, self._on_progress),
                (jobs.job_finished, self._on_ended),
                (jobs.job_failed, self._on_ended),
                (jobs.destroyed, self._on_jobs_destroyed),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass  # ya desconectada, o el gestor ya no existe
        self._stop()

    # -------------------------------------------------------------------------
    # Señales del gestor
    # -------------------------------------------------------------------------

    def _on_started(self, name: str) -> None:
        if name != self._job_name:
            return
        self._progress = None
        self._timer.start(self._show_after_ms)

    def _on_progress(self, name: str, progress: JobProgress) -> None:
        if name != self._job_name:
            return
        self._progress = progress
        if self._dialog is not None:
            self._dialog.set_progress(progress.done, progress.total)

    def _on_ended(self, name: str, _result: object) -> None:
        """La lectura terminó, se canceló o falló: la ventana se cierra."""
        if name == self._job_name:
            self._stop()

    def _on_jobs_destroyed(self, *_args: object) -> None:
        """El gestor desapareció (catálogo cerrado) sin avisar del final: se cierra todo."""
        self._jobs = None
        self._stop()

    # -------------------------------------------------------------------------
    # La ventana
    # -------------------------------------------------------------------------

    def _try_show(self) -> None:
        """Pasado el tiempo: abre la ventana si la lectura sigue y no hay otra modal."""
        if self._dialog is not None or self._jobs is None:
            return
        if not self._jobs.is_running(self._job_name):
            return
        if self._active_modal() is not None:
            # Otra ventana modal (el resumen de «Añadir carpeta»...): ya bloquea; al
            # cerrarla, sale esta
            self._timer.start(RETRY_MS)
            return
        dialog = self._dialog_factory(self._window)
        dialog.cancel_requested.connect(self._on_cancel_requested)
        if self._progress is not None:
            dialog.set_progress(self._progress.done, self._progress.total)
        self._dialog = dialog
        dialog.show()

    def _on_cancel_requested(self) -> None:
        """«Cancelar» en la ventana: se pide parar la lectura (se cierra al terminar)."""
        if self._jobs is not None:
            self._jobs.cancel(self._job_name)

    def _stop(self) -> None:
        """Para la espera y cierra la ventana, si se veía."""
        self._timer.stop()
        self._progress = None
        dialog, self._dialog = self._dialog, None
        if dialog is not None:
            dialog.finish()
            dialog.deleteLater()


if __name__ == "__main__":
    # Autoprueba sin ventana: un gestor de trabajos y una ventana de mentira.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.metadata_progress
    import sys
    import time
    from typing import ClassVar

    from qtpy.QtCore import QCoreApplication, QEvent, Signal

    app = QApplication.instance() or QApplication(sys.argv)

    class FakeJobs(QObject):
        """Las señales y los métodos del 'JobManager' que se usan."""

        job_started = Signal(str)
        job_progress = Signal(str, object)
        job_finished = Signal(str, object)
        job_failed = Signal(str, object)

        def __init__(self) -> None:
            super().__init__()
            self.running: set[str] = set()
            self.cancelled: list[str] = []

        def is_running(self, name: str) -> bool:
            return name in self.running

        def cancel(self, name: str) -> None:
            self.cancelled.append(name)

        def begin(self, name: str = "metadata") -> None:
            self.running.add(name)
            self.job_started.emit(name)

        def end(self, name: str = "metadata", *, failed: bool = False) -> None:
            self.running.discard(name)
            (self.job_failed if failed else self.job_finished).emit(name, None)

    class FakeDialog(QObject):
        """Apunta lo que le hacen, sin abrir nada."""

        cancel_requested = Signal()
        opened: ClassVar[list["FakeDialog"]] = []  # todas las que se han abierto

        def __init__(self, parent: QWidget) -> None:
            super().__init__()
            self.parent_window = parent
            self.progress: tuple[int, int] | None = None
            self.shown = self.finished = False
            FakeDialog.opened.append(self)

        def set_progress(self, done: int, total: int) -> None:
            self.progress = (done, total)

        def show(self) -> None:
            self.shown = True

        def finish(self) -> None:
            self.finished = True

    modal = {"widget": None}
    window = QWidget()
    follower = MetadataProgress(
        window,
        show_after_ms=30,
        dialog_factory=FakeDialog,
        active_modal=lambda: modal["widget"],
    )
    jobs = FakeJobs()
    follower.attach(jobs)

    def wait(ms: int) -> None:
        """Deja correr el bucle de eventos (los temporizadores) unos milisegundos."""
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    # 1. Una lectura corta no abre nada; otro trabajo, tampoco
    jobs.begin()
    jobs.job_progress.emit("metadata", JobProgress(1, 3))
    jobs.end()
    jobs.begin("thumbnails")
    jobs.job_progress.emit("thumbnails", JobProgress(10, 500))
    wait(80)
    jobs.end("thumbnails")
    assert FakeDialog.opened == []
    print("1. Lectura corta y otros trabajos: sin ventana")

    # 2. Una lectura larga la abre pasado el tiempo, con el último avance; con otra modal
    #    abierta, espera a que se cierre
    modal["widget"] = QWidget()
    jobs.begin()
    jobs.job_progress.emit("metadata", JobProgress(120, 22012))
    wait(80)
    assert FakeDialog.opened == []  # el resumen «Carpeta añadida» sigue abierto
    modal["widget"] = None
    wait(RETRY_MS + 100)
    (dialog,) = FakeDialog.opened
    assert dialog.shown and dialog.parent_window is window and dialog.progress == (120, 22012)
    jobs.job_progress.emit("metadata", JobProgress(500, 22012))
    jobs.job_progress.emit("thumbnails", JobProgress(1, 2))  # no es suyo
    assert dialog.progress == (500, 22012)
    print("2. Lectura larga: ventana al rato (tras la otra modal), con el avance")

    # 3. «Cancelar» pide parar la lectura; la ventana se cierra cuando el trabajo termina
    dialog.cancel_requested.emit()
    assert jobs.cancelled == ["metadata"] and not dialog.finished
    jobs.end()
    assert dialog.finished
    wait(80)
    assert len(FakeDialog.opened) == 1  # un temporizador rezagado no la reabre
    print("3. Cancelar: se pide al trabajo; se cierra al terminar")

    # 4. Si la lectura falla, también se cierra
    jobs.begin()
    wait(80)
    failed_dialog = FakeDialog.opened[-1]
    jobs.end(failed=True)
    assert len(FakeDialog.opened) == 2 and failed_dialog.finished
    print("4. Lectura fallida: se cierra")

    # 5. Otro catálogo (otro gestor): el anterior deja de contar; y si el gestor
    #    desaparece con la ventana abierta, se cierra
    other = FakeJobs()
    follower.attach(other)
    jobs.begin()
    wait(80)
    assert len(FakeDialog.opened) == 2  # el gestor anterior ya no abre nada
    other.begin()
    wait(80)
    orphan = FakeDialog.opened[-1]
    assert len(FakeDialog.opened) == 3 and orphan.shown
    other.deleteLater()
    # 'processEvents' no ejecuta los 'deleteLater' pendientes (el bucle normal, sí)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert orphan.finished
    print("5. Cambio de gestor y gestor destruido: correcto")

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
