"""Progreso genérico de los trabajos largos en segundo plano.

Este módulo NO depende de Qt: es Python puro, así que los trabajos (extraer
metadatos, crear miniaturas...) se pueden escribir y probar sin interfaz.

Un "trabajo" es una función con esta forma, que se ejecuta en un hilo secundario:

    def my_job(conn, *, progress, cancel_event, **options) -> JobResult: ...

    - conn:         conexión sqlite3 propia del trabajo.
    - progress:     función a la que el trabajo avisa con un 'JobProgress'.
    - cancel_event: 'threading.Event'; si está activado, el trabajo debe parar en
                    cuanto pueda, dejando lo ya guardado en un estado coherente.

Al terminar (también si se canceló) devuelve un objeto que cumple 'JobResult'.
"""

__version__ = "1.0.0"
__all__ = ["JobProgress", "JobResult", "throttled"]

# Librerías estándar
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class JobProgress:
    """Avance de un trabajo.

    Attributes:
        done: Elementos ya tratados (bien, mal o descartados).
        total: Elementos totales del trabajo (0 si no hay nada que hacer).
        message: Texto opcional (p. ej. el archivo en curso).
    """

    done: int
    total: int
    message: str = ""

    @property
    def is_finished(self) -> bool:
        """True cuando se han tratado todos los elementos."""
        return self.done >= self.total


class JobResult(Protocol):
    """Lo que debe ofrecer el resultado de cualquier trabajo para mostrarlo en la interfaz."""

    @property
    def has_warnings(self) -> bool:
        """True si hubo errores, se canceló o algo merece la atención del usuario."""
        ...

    def status_text(self) -> str:
        """Frase corta para la barra de estado ('' si no hay nada que mostrar)."""
        ...


def throttled(
    callback: Callable[[JobProgress], None], min_interval: float = 0.1
) -> Callable[[JobProgress], None]:
    """Envuelve un callback de progreso para que no se llame más de ~10 veces por segundo.

    Un trabajo puede avisar tras CADA archivo (miles por segundo); si cada aviso
    llegara a la interfaz, la cola de eventos se saturaría. Siempre se deja pasar
    el último aviso (cuando 'done' alcanza a 'total') para que la barra termine
    en el 100 %.

    Args:
        callback: Función a la que se avisa realmente.
        min_interval: Segundos mínimos entre dos avisos.

    Returns:
        Una función con la misma firma que 'callback'.
    """
    last_call = 0.0

    def wrapper(progress: JobProgress) -> None:
        nonlocal last_call
        now = time.monotonic()
        if progress.is_finished or now - last_call >= min_interval:
            last_call = now
            callback(progress)

    return wrapper


if __name__ == "__main__":
    # Autoprueba del limitador de frecuencia
    received: list[int] = []
    fast = throttled(lambda progress: received.append(progress.done), min_interval=0.05)

    # 1000 avisos seguidos: solo pasan unos pocos, pero el último siempre llega
    for index in range(1, 1001):
        fast(JobProgress(index, 1000))
    print(f"Avisos entregados de 1000: {len(received)} (último: {received[-1]})")
    assert received[0] == 1 and received[-1] == 1000 and len(received) < 20

    # Pasado el intervalo, vuelve a dejar pasar
    time.sleep(0.06)
    received.clear()
    fast(JobProgress(5, 1000))
    assert received == [5]

    assert JobProgress(3, 3).is_finished and JobProgress(0, 0).is_finished
    assert not JobProgress(2, 3).is_finished
    print("Autoprueba finalizada correctamente.")
