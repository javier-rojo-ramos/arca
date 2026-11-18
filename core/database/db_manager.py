"""Gestor de base de datos asíncrono (QThreadPool + sqlite3) para la interfaz Qt.

Idea clave: la interfaz (hilo principal) NUNCA toca la base de datos. Cuando
necesita datos, entrega una función al gestor; el gestor la ejecuta en un hilo
secundario con su PROPIA conexión SQLite y devuelve el resultado al hilo
principal mediante señales de Qt. Así la GUI no se congela.

Regla de oro de SQLite: una 'sqlite3.Connection' no se comparte entre hilos.
Por eso cada tarea abre su conexión, la usa y la cierra.

Ejemplo de uso (desde el controlador):

    def _consulta(conn: sqlite3.Connection, tipo: str) -> list[dict]:
        # Se ejecuta en un HILO SECUNDARIO. Aquí NO se puede tocar la interfaz.
        filas = conn.execute(
            "SELECT id, title FROM media_items WHERE media_type = ?", (tipo,)
        ).fetchall()
        return rows_to_dicts(filas)

    def _on_datos(datos: list[dict]) -> None:
        # Se ejecuta en el HILO PRINCIPAL: aquí sí se puede actualizar la interfaz.
        ...

    self.db.execute_async(_consulta, "photo", on_result=self._on_datos)

Reglas para las funciones que se envían al gestor:
    - Su primer parámetro es la conexión ('conn'); el resto, los argumentos extra.
    - Deben DEVOLVER datos simples (list, dict, int...). Nunca cursores ni la conexión.
    - No deben llamar a 'conn.commit()': el gestor hace commit al terminar sin
      errores y rollback si la función lanza una excepción.
    - Los callbacks (on_result, on_error, on_finished) deben ser MÉTODOS de un
      QObject (p. ej. del controlador) o funciones normales; se ejecutan siempre
      en el hilo principal.

Medida de la cola (desde la 1.1.0): las consultas de la interfaz y los trabajos largos
('JobManager', que ocupa un hilo mientras dura cada trabajo) comparten los DB_MAX_THREADS
hilos. Para saber si la interfaz espera por falta de hilos (docs/PENDIENTE.md, GEN 15.4),
cada tarea apunta cuánto esperó en la cola antes de empezar y cuánto duró: las que esperan
QUEUE_WAIT_LOG_MS o más salen en el registro (DEBUG) con su nombre y cuántos hilos estaban
ocupados al pedirla, y al cerrar el catálogo ('shutdown') sale un resumen (INFO).

1.1.0 Medida de la espera en la cola de cada tarea, con su resumen al cerrar (GEN 15.4).
"""

__version__ = "1.1.0"
__all__ = [
    "QUEUE_WAIT_LOG_MS",
    "QUEUE_WAIT_SLOW_MS",
    "CatalogDatabaseManager",
    "QueueStats",
    "rows_to_dicts",
]

# Librerías estándar
import itertools
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

# Módulos del proyecto
from core.catalog.catalog_schema import BUSY_TIMEOUT_SECONDS, configure_connection

# Hilos máximos para la base de datos. En modo WAL varias conexiones pueden LEER
# a la vez, pero solo una puede ESCRIBIR (las demás esperan su turno).
DB_MAX_THREADS = 4

# Medida de la cola: una tarea que espera esto o más (ms) antes de empezar sale en el
# registro; el resumen cuenta también las que esperan QUEUE_WAIT_SLOW_MS o más (a partir
# de ahí, una espera ya se nota en la interfaz)
QUEUE_WAIT_LOG_MS = 100
QUEUE_WAIT_SLOW_MS = 300


class QueueStats:
    """Esperas en la cola de las tareas de un gestor (se apuntan desde los hilos)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tasks = 0  # tareas terminadas
        self.waited = 0  # las que esperaron QUEUE_WAIT_LOG_MS o más
        self.slow = 0  # las que esperaron QUEUE_WAIT_SLOW_MS o más
        self.max_wait_ms = 0.0
        self.max_wait_name = ""

    def record(self, name: str, wait_ms: float, duration_ms: float, busy: int) -> None:
        """Apunta una tarea terminada; si esperó, lo dice en el registro (DEBUG).

        Args:
            name: Nombre de la función que se ejecutó.
            wait_ms: Desde que se pidió hasta que empezó (la espera en la cola).
            duration_ms: Lo que tardó en ejecutarse.
            busy: Hilos ocupados cuando se pidió.
        """
        with self._lock:
            self.tasks += 1
            if wait_ms >= QUEUE_WAIT_LOG_MS:
                self.waited += 1
            if wait_ms >= QUEUE_WAIT_SLOW_MS:
                self.slow += 1
            if wait_ms > self.max_wait_ms:
                self.max_wait_ms, self.max_wait_name = wait_ms, name
        if wait_ms >= QUEUE_WAIT_LOG_MS:
            logger.debug(
                f"BD: «{name}» esperó {wait_ms:.0f} ms en la cola ({busy} de "
                f"{DB_MAX_THREADS} hilos ocupados al pedirla); duró {duration_ms:.0f} ms"
            )

    def summary(self) -> str:
        """El resumen para el registro (vacío si no hubo tareas)."""
        with self._lock:
            if self.tasks == 0:
                return ""
            text = (
                f"BD: {self.tasks} tareas; esperaron en la cola {QUEUE_WAIT_LOG_MS} ms o más: "
                f"{self.waited}; {QUEUE_WAIT_SLOW_MS} ms o más: {self.slow}"
            )
            if self.max_wait_name:
                text += f"; la que más, «{self.max_wait_name}», {self.max_wait_ms:.0f} ms"
            return text


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convierte filas de sqlite3.Row en diccionarios normales de Python.

    Útil como último paso de una consulta, para devolver al hilo principal datos
    simples que no dependen de la conexión (que ya estará cerrada).
    """
    return [dict(fila) for fila in rows]


class DatabaseWorkerSignals(QObject):
    """Señales con las que los hilos secundarios avisan al hilo principal.

    Hay UNA sola instancia, propiedad del gestor (que vive en el hilo principal).
    Cada señal lleva primero el 'task_id' para saber a qué petición corresponde.
    """

    # (task_id, valor devuelto por la función)
    result = Signal(int, object)
    # (task_id, excepción ocurrida)
    error = Signal(int, object)
    # (task_id) La tarea terminó, con éxito o con error
    finished = Signal(int)


class DatabaseTask(QRunnable):
    """Tarea que se ejecuta en el QThreadPool: abre conexión, ejecuta y cierra."""

    def __init__(
        self,
        task_id: int,
        db_uri: str,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        signals: DatabaseWorkerSignals,
        stats: QueueStats | None = None,
        busy: int = 0,
    ) -> None:
        """Guarda lo necesario para ejecutar la consulta más tarde, en otro hilo.

        Args:
            task_id: Identificador de la petición (para enlazar con sus callbacks).
            db_uri: URI de SQLite en modo lectura/escritura que NO crea el archivo.
            func: Función a ejecutar; recibe la conexión como primer argumento.
            args: Argumentos posicionales extra para 'func'.
            kwargs: Argumentos con nombre extra para 'func'.
            signals: Señales (del gestor) por las que se devuelve el resultado.
            stats: Dónde apuntar la espera en la cola y la duración (None = no se apunta).
            busy: Hilos ocupados cuando se pidió (para el registro).
        """
        super().__init__()
        self.task_id = task_id
        self.db_uri = db_uri
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = signals
        self.stats = stats
        self.busy = busy
        # Se crea justo antes de entregarla al pool: desde aquí cuenta la espera
        self.queued_at = time.monotonic()

    @Slot()
    def run(self) -> None:
        """Punto de entrada que Qt ejecuta en un hilo secundario."""
        started_at = time.monotonic()
        try:
            # 'closing' asegura que la conexión se cierra pase lo que pase.
            # uri=True + mode=rw: si el .db no existe da error en vez de crear
            # silenciosamente un archivo vacío.
            with closing(
                sqlite3.connect(self.db_uri, uri=True, timeout=BUSY_TIMEOUT_SECONDS)
            ) as conn:
                conn.row_factory = sqlite3.Row  # Acceso a columnas por nombre
                configure_connection(conn)  # PRAGMAs por conexión (foreign_keys...)

                try:
                    resultado = self.func(conn, *self.args, **self.kwargs)
                    conn.commit()  # Confirma los cambios si la función no falló
                except Exception:
                    conn.rollback()  # Deshace cualquier cambio a medias
                    raise

            # Se emite DESPUÉS de cerrar la conexión: así el hilo principal
            # recibe el resultado cuando el archivo ya está liberado.
            self.signals.result.emit(self.task_id, resultado)

        except Exception as exc:  # noqa: BLE001 - se reenvía al hilo principal
            logger.opt(exception=True).error("Error en consulta asíncrona a la BD.")
            self.signals.error.emit(self.task_id, exc)

        finally:
            if self.stats is not None:
                name = getattr(self.func, "__name__", type(self.func).__name__)
                self.stats.record(
                    name,
                    (started_at - self.queued_at) * 1000,
                    (time.monotonic() - started_at) * 1000,
                    self.busy,
                )
            self.signals.finished.emit(self.task_id)


class _PendingCall:
    """Callbacks de una petición en curso (se guardan hasta que la tarea termina)."""

    __slots__ = ("on_error", "on_finished", "on_result")

    def __init__(
        self,
        on_result: Callable[[Any], None] | None,
        on_error: Callable[[Exception], None] | None,
        on_finished: Callable[[], None] | None,
    ) -> None:
        self.on_result = on_result
        self.on_error = on_error
        self.on_finished = on_finished


class CatalogDatabaseManager(QObject):
    """Envía consultas a la base de datos del catálogo sin bloquear la interfaz.

    Debe crearse y usarse desde el hilo principal.
    """

    def __init__(self, db_path: str | Path, parent: QObject | None = None) -> None:
        """Prepara el gestor para un catálogo concreto.

        Args:
            db_path: Ruta al archivo 'catalogo.db' (debe existir).
            parent: QObject padre (normalmente la ventana principal).

        Raises:
            FileNotFoundError: Si el archivo de base de datos no existe.
        """
        super().__init__(parent)
        self.db_path = Path(db_path).resolve()
        if not self.db_path.is_file():
            raise FileNotFoundError(f"No existe la base de datos: {self.db_path}")

        # URI de SQLite: 'mode=rw' = lectura/escritura pero SIN crear el archivo
        self._db_uri = f"{self.db_path.as_uri()}?mode=rw"

        # Pool PROPIO para la BD (no el global ni el de miniaturas), así una
        # ráfaga de miniaturas no retrasa las consultas ni al revés.
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(DB_MAX_THREADS)

        # Señales únicas del gestor: viven en el hilo principal. Al ser slots de
        # un QObject y usar QueuedConnection, se ejecutan SIEMPRE en el hilo
        # principal aunque se emitan desde un hilo secundario.
        self._signals = DatabaseWorkerSignals(self)
        queued = Qt.ConnectionType.QueuedConnection
        self._signals.result.connect(self._on_task_result, queued)
        self._signals.error.connect(self._on_task_error, queued)
        self._signals.finished.connect(self._on_task_finished, queued)

        # Peticiones en curso: task_id -> callbacks. Contador para generar ids.
        self._pending: dict[int, _PendingCall] = {}
        self._id_counter = itertools.count(1)
        self._is_shutting_down = False
        # Esperas en la cola de las tareas de este catálogo (ver la cabecera)
        self.queue_stats = QueueStats()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def execute_async(
        self,
        db_func: Callable[..., Any],
        *args: Any,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Encola una función de base de datos para ejecutarla en un hilo secundario.

        Args:
            db_func: Función cuyo primer parámetro es la conexión sqlite3.
            *args: Argumentos extra para 'db_func'.
            on_result: Se llama (en el hilo principal) con lo que devuelva 'db_func'.
            on_error: Se llama (en el hilo principal) con la excepción si falla.
            on_finished: Se llama (en el hilo principal) al terminar, con o sin error.
            **kwargs: Argumentos con nombre extra para 'db_func'.
        """
        if self._is_shutting_down:
            logger.warning("Consulta ignorada: el gestor de BD se está cerrando.")
            return

        task_id = next(self._id_counter)
        self._pending[task_id] = _PendingCall(on_result, on_error, on_finished)

        task = DatabaseTask(
            task_id,
            self._db_uri,
            db_func,
            args,
            kwargs,
            self._signals,
            stats=self.queue_stats,
            busy=self._pool.activeThreadCount(),
        )
        self._pool.start(task)

    def shutdown(self) -> None:
        """Cancela lo pendiente y espera a las tareas en curso.

        Llamar al cerrar la ventana o al cambiar de catálogo, ANTES de soltar el
        gestor, para que no quede ningún hilo usando el archivo .db.
        """
        self._is_shutting_down = True
        self._pool.clear()  # Descarta las tareas que aún no han empezado
        self._pool.waitForDone()  # Espera a las que ya están ejecutándose
        self._pending.clear()  # Ya nadie esperará sus callbacks
        summary = self.queue_stats.summary()
        if summary:
            logger.info(summary)

    # -------------------------------------------------------------------------
    # Slots internos (siempre se ejecutan en el hilo principal)
    # -------------------------------------------------------------------------

    @Slot(int, object)
    def _on_task_result(self, task_id: int, value: Any) -> None:
        """Entrega el resultado al callback 'on_result' de la petición."""
        pendiente = self._pending.get(task_id)
        if pendiente and pendiente.on_result:
            self._call_safely(pendiente.on_result, value)

    @Slot(int, object)
    def _on_task_error(self, task_id: int, exc: Exception) -> None:
        """Entrega el error al callback 'on_error' de la petición."""
        pendiente = self._pending.get(task_id)
        if pendiente and pendiente.on_error:
            self._call_safely(pendiente.on_error, exc)

    @Slot(int)
    def _on_task_finished(self, task_id: int) -> None:
        """Avisa de que la tarea terminó y libera sus callbacks."""
        pendiente = self._pending.pop(task_id, None)
        if pendiente and pendiente.on_finished:
            self._call_safely(pendiente.on_finished)

    @staticmethod
    def _call_safely(callback: Callable[..., None], *args: Any) -> None:
        """Ejecuta un callback del usuario; si falla, lo registra sin romper el gestor."""
        try:
            callback(*args)
        except Exception:  # noqa: BLE001
            logger.exception("Error en un callback de la base de datos.")


if __name__ == "__main__":
    # Autoprueba: crea un catálogo temporal, inserta y lee datos en hilos
    # secundarios y comprueba que los callbacks llegan al hilo principal.
    # Ejecutar desde la raíz del proyecto:  python -m core.database.db_manager
    import sys
    import tempfile

    from qtpy.QtCore import QCoreApplication, QThread, QTimer

    from core.catalog.catalog_builder import CatalogBuilder

    app = QCoreApplication(sys.argv)
    hilo_principal = QThread.currentThread()

    with tempfile.TemporaryDirectory() as tmp:
        ruta_db = CatalogBuilder(Path(tmp) / "PruebaCatálogo").build()
        gestor = CatalogDatabaseManager(ruta_db)

        def insertar(conn: sqlite3.Connection) -> int:
            """Se ejecuta en un hilo secundario."""
            conn.execute(
                "INSERT INTO storage_locations(name, absolute_path) VALUES (?, ?)",
                ("Prueba", "/tmp/prueba"),
            )
            return conn.execute("SELECT COUNT(*) FROM storage_locations").fetchone()[0]

        def leer(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            """Se ejecuta en un hilo secundario."""
            return rows_to_dicts(conn.execute("SELECT id, name FROM storage_locations"))

        def fallar(conn: sqlite3.Connection) -> None:
            """Provoca un error a propósito (la tabla no existe)."""
            conn.execute("SELECT * FROM tabla_inexistente")

        def al_leer(datos: list[dict[str, Any]]) -> None:
            en_principal = QThread.currentThread() == hilo_principal
            print(f"Lectura: {datos} | callback en hilo principal: {en_principal}")

        def al_insertar(total: int) -> None:
            print(f"Inserción OK, filas en storage_locations: {total}")
            # Encadenamos la lectura cuando la inserción ya terminó
            gestor.execute_async(leer, on_result=al_leer)

        def al_fallar(exc: Exception) -> None:
            print(f"Error capturado correctamente: {type(exc).__name__}: {exc}")

        gestor.execute_async(insertar, on_result=al_insertar)
        gestor.execute_async(fallar, on_error=al_fallar)

        # Dejamos 1,5 s para que todo termine y cerramos limpiamente
        def terminar() -> None:
            gestor.shutdown()
            app.quit()

        QTimer.singleShot(1500, terminar)
        app.exec()

        # Medida de la cola: 6 tareas de 0,25 s con 4 hilos -> las 2 últimas esperan unos
        # 250 ms antes de empezar; las primeras, nada
        cola = CatalogDatabaseManager(ruta_db)
        terminadas: list[int] = []

        def dormir(conn: sqlite3.Connection, segundos: float) -> None:
            """Una tarea lenta (no toca la base de datos)."""
            time.sleep(segundos)

        for _ in range(6):
            cola.execute_async(dormir, 0.25, on_finished=lambda: terminadas.append(1))
        limite = time.monotonic() + 5
        while len(terminadas) < 6 and time.monotonic() < limite:
            app.processEvents()
            time.sleep(0.01)
        stats = cola.queue_stats
        assert len(terminadas) == 6 and stats.tasks == 6, (len(terminadas), stats.tasks)
        assert stats.waited == 2 and stats.max_wait_name == "dormir", stats.__dict__
        assert 150 <= stats.max_wait_ms < 1000, stats.max_wait_ms
        assert stats.summary().startswith("BD: 6 tareas; esperaron en la cola 100 ms o más: 2")
        cola.shutdown()
        # Una espera corta no cuenta como espera
        sueltas = QueueStats()
        sueltas.record("rapida", 20, 5, 1)
        assert (sueltas.tasks, sueltas.waited, sueltas.slow) == (1, 0, 0)
        assert QueueStats().summary() == ""
        print(f"Cola: {stats.summary()}")
        print("Autoprueba finalizada correctamente.")
