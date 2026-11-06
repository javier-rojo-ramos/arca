"""Gestor de trabajos largos en segundo plano (metadatos, miniaturas...).

Un "trabajo" es una función de 'core/jobs/progress.py' (recibe una conexión, avisa
del progreso y obedece a un evento de cancelación). Este gestor se encarga de
todo lo demás para que los trabajos no sepan nada de Qt:

    - Los ejecuta en un hilo secundario, apoyándose en 'CatalogDatabaseManager'
      (que ya abre una conexión propia por tarea y entrega los resultados al
      hilo principal con señales).
    - Crea el evento de cancelación de cada trabajo y lo activa en 'cancel()'.
    - Limita la frecuencia de los avisos de progreso (~10 por segundo) para no
      saturar la interfaz, y los convierte en señales de Qt.
    - Impide que un mismo trabajo se lance dos veces a la vez.

Cada trabajo se identifica por un nombre ("metadata", "thumbnails"...). Los
trabajos distintos pueden ejecutarse a la vez.

Uso (desde el controlador, en el hilo principal):

    self.jobs = JobManager(self.db, parent=self)
    self.jobs.job_progress.connect(self._on_job_progress)    # (nombre, JobProgress)
    self.jobs.job_finished.connect(self._on_job_finished)    # (nombre, resultado)
    self.jobs.job_failed.connect(self._on_job_failed)        # (nombre, excepción)
    self.jobs.start("metadata", process_pending_metadata)
    ...
    self.jobs.cancel("metadata")                             # botón "Cancelar"

Nota: usa el pool de hilos del gestor de la base de datos (4 hilos). Cada trabajo
ocupa uno mientras dura. Si algún día se acumularan trabajos largos y las
consultas de la interfaz tuvieran que esperar, se puede dar a los trabajos un
pool propio sin cambiar nada de lo que hay aquí arriba.
"""

__version__ = "1.0.0"
__all__ = ["JobManager"]

# Librerías estándar
import threading
from collections.abc import Callable
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal

# Módulos del proyecto
from core.database.db_manager import CatalogDatabaseManager
from core.jobs.progress import throttled


class JobManager(QObject):
    """Lanza, cancela y sigue trabajos largos en segundo plano.

    Debe crearse y usarse desde el hilo principal.

    Signals:
        job_started(str): Un trabajo ha empezado (nombre).
        job_progress(str, object): Avance de un trabajo (nombre, JobProgress).
        job_finished(str, object): Un trabajo terminó, también si se canceló
            (nombre, resultado del trabajo).
        job_failed(str, object): Un trabajo falló con una excepción (nombre, error).
    """

    job_started = Signal(str)
    job_progress = Signal(str, object)
    job_finished = Signal(str, object)
    job_failed = Signal(str, object)

    def __init__(self, db: CatalogDatabaseManager, parent: QObject | None = None) -> None:
        """Crea el gestor.

        Args:
            db: Gestor asíncrono de la base de datos del catálogo activo.
            parent: QObject padre (normalmente la ventana principal).
        """
        super().__init__(parent)
        self._db = db
        # Trabajos en curso: nombre -> evento que los cancela
        self._cancel_events: dict[str, threading.Event] = {}

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def is_running(self, name: str) -> bool:
        """Indica si un trabajo con ese nombre está en curso."""
        return name in self._cancel_events

    def start(self, name: str, job: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Lanza un trabajo en un hilo secundario.

        Args:
            name: Nombre del trabajo ("metadata", "thumbnails"...).
            job: Función del trabajo. Se llama como
                'job(conn, *args, progress=..., cancel_event=..., **kwargs)'.
            *args: Argumentos posicionales extra para el trabajo.
            **kwargs: Argumentos con nombre extra para el trabajo.

        Returns:
            True si se lanzó; False si ya había un trabajo con ese nombre en curso.
        """
        if name in self._cancel_events:
            logger.debug(f"El trabajo '{name}' ya está en curso: no se lanza otra vez.")
            return False

        cancel_event = threading.Event()
        self._cancel_events[name] = cancel_event

        # Esta función se llama desde el hilo secundario: emitir una señal de Qt es
        # seguro, y Qt la entrega en el hilo principal.
        progress = throttled(lambda value: self.job_progress.emit(name, value))

        logger.info(f"Trabajo '{name}' iniciado")
        self.job_started.emit(name)
        self._db.execute_async(
            job,
            *args,
            cancel_event=cancel_event,
            progress=progress,
            on_result=lambda result: self._on_result(name, result),
            on_error=lambda error: self._on_error(name, error),
            **kwargs,
        )
        return True

    def cancel(self, name: str) -> None:
        """Pide la cancelación de un trabajo. Se detiene en cuanto puede."""
        event = self._cancel_events.get(name)
        if event is not None:
            logger.info(f"Cancelando el trabajo '{name}'...")
            event.set()

    def cancel_all(self) -> None:
        """Pide la cancelación de todos los trabajos en curso."""
        for name in list(self._cancel_events):
            self.cancel(name)

    # -------------------------------------------------------------------------
    # Callbacks del gestor de la base de datos (siempre en el hilo principal)
    # -------------------------------------------------------------------------

    def _on_result(self, name: str, result: Any) -> None:
        """El trabajo terminó (con éxito o cancelado)."""
        # Se libera el nombre ANTES de avisar: así quien reciba la señal puede
        # volver a lanzar el trabajo desde su propio manejador.
        self._cancel_events.pop(name, None)
        logger.info(f"Trabajo '{name}' terminado")
        self.job_finished.emit(name, result)

    def _on_error(self, name: str, error: Exception) -> None:
        """El trabajo falló con una excepción."""
        self._cancel_events.pop(name, None)
        logger.error(f"Trabajo '{name}' fallido: {error}")
        self.job_failed.emit(name, error)
