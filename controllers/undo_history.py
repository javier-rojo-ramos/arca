"""Deshacer (Ctrl+Z) en toda la aplicación: un solo historial de cambios.

Acordado con el autor el 13/11/2026 (docs/PENDIENTE.md, B; docs/MAPA.md, paso 3.4): cada
cambio que se puede deshacer deja aquí un PASO con su descripción y la forma de deshacerlo;
Ctrl+Z, en cualquier sitio de la ventana, deshace el último. Las cajas de texto conservan
su propio Ctrl+Z mientras se escribe en ellas (Qt les da preferencia).

Hoy solo lo llena el mapa (ubicar, mover y quitar la ubicación de fotos). Después, en
pasos aparte: la valoración, la marca y el color; los metadatos del inspector; las palabras
clave. Nunca lo que no tiene vuelta atrás («Eliminar del disco», «Purgar»).

Un paso no deshace por sí mismo: su función 'undo' lo pide (p. ej. por la cola de cambios
del inspector, que lo guarda en el catálogo, lo escribe en los archivos y avisa). Los
cambios ya escritos en los archivos se deshacen con otro cambio, que se vuelve a escribir.

El historial es del catálogo abierto: al cerrarlo se vacía ('clear'). Sin rehacer, de
momento.

Uso (en el controlador principal, que solo lo crea y lo conecta):
    historial = UndoHistory(ventana)                      # Ctrl+Z en la ventana
    historial.undone.connect(...)                         # «Deshecho: ubicar 3 fotos»
    historial.push(UndoStep("ubicar 3 fotos", funcion))   # quien hace un cambio

1.0.0 Primera versión (docs/MAPA.md, paso 3.4).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.undo_history
"""

__version__ = "1.0.0"
__all__ = ["MAX_STEPS", "UndoHistory", "UndoStep"]

# Librerías estándar
from collections.abc import Callable
from dataclasses import dataclass

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Qt, Signal
from qtpy.QtGui import QKeySequence, QShortcut
from qtpy.QtWidgets import QWidget

# Pasos que se recuerdan como mucho (los más antiguos se olvidan)
MAX_STEPS = 100


@dataclass(frozen=True, slots=True)
class UndoStep:
    """Un cambio que se puede deshacer.

    Attributes:
        description: Qué se hizo, en minúscula, para «Deshecho: …» («ubicar 3 fotos»).
        undo: Pide deshacerlo (no espera a que termine).
    """

    description: str
    undo: Callable[[], None]


class UndoHistory(QObject):
    """El historial de cambios que se pueden deshacer (ver el docstring del archivo).

    Signals:
        undone(str): se ha pedido deshacer un paso (su descripción).
        nothing_to_undo(): Ctrl+Z sin nada que deshacer.
    """

    undone = Signal(str)
    nothing_to_undo = Signal()

    def __init__(self, window: QWidget | None = None, parent: QObject | None = None) -> None:
        """
        Args:
            window: Ventana en la que Ctrl+Z deshace (None = sin atajo: solo 'undo').
            parent: Objeto padre (por defecto, la ventana).
        """
        super().__init__(parent if parent is not None else window)
        self._steps: list[UndoStep] = []
        if window is not None:
            self._shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), window)
            self._shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            self._shortcut.activated.connect(self.undo)

    def push(self, step: UndoStep) -> None:
        """Apunta un cambio que se puede deshacer."""
        self._steps.append(step)
        del self._steps[:-MAX_STEPS]

    def can_undo(self) -> bool:
        """True si hay algo que deshacer."""
        return bool(self._steps)

    def last_description(self) -> str | None:
        """Lo que deshará Ctrl+Z (None si nada)."""
        return self._steps[-1].description if self._steps else None

    def undo(self) -> UndoStep | None:
        """Deshace el último cambio (None si no había ninguno)."""
        if not self._steps:
            self.nothing_to_undo.emit()
            return None
        step = self._steps.pop()
        logger.info(f"Deshacer: {step.description}")
        step.undo()
        self.undone.emit(step.description)
        return step

    def clear(self) -> None:
        """Olvida todo (al cerrar el catálogo: sus cambios no valen para otro)."""
        self._steps.clear()


if __name__ == "__main__":
    # Autoprueba (sin ventana).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.undo_history
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    history = UndoHistory()
    done: list[str] = []
    events: list[str] = []
    history.undone.connect(lambda text: events.append(f"deshecho: {text}"))
    history.nothing_to_undo.connect(lambda: events.append("nada"))

    # 1. Vacío: nada que deshacer
    assert not history.can_undo() and history.undo() is None and events == ["nada"]

    # 2. Se deshace en orden inverso, y cada paso una sola vez
    for name in ("ubicar 1 foto", "mover 1 foto", "quitar la ubicación de 3 fotos"):
        history.push(UndoStep(name, lambda name=name: done.append(name)))
    assert history.last_description() == "quitar la ubicación de 3 fotos"
    history.undo()
    history.undo()
    assert done == ["quitar la ubicación de 3 fotos", "mover 1 foto"]
    assert events[-1] == "deshecho: mover 1 foto" and history.last_description() == "ubicar 1 foto"

    # 3. Tope: se olvidan los más antiguos
    history.clear()
    for number in range(MAX_STEPS + 20):
        history.push(UndoStep(str(number), lambda: None))
    assert history.last_description() == str(MAX_STEPS + 19)
    count = 0
    while history.undo() is not None:
        count += 1
    assert count == MAX_STEPS

    # 4. Con una ventana: el atajo Ctrl+Z existe en ella
    window = QWidget()
    with_window = UndoHistory(window)
    assert with_window.parent() is window and with_window._shortcut.key().matches(QKeySequence("Ctrl+Z"))
    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
