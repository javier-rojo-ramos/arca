"""Bloquear las señales de varios objetos Qt mientras se rehace algo por código.

    with blocked_signals(view.selectionModel(), view):
        model.clear()          # no avisa de cambios de selección ni de despliegues
        ...

Al salir, cada objeto vuelve a como estaba (si ya tenía las señales bloqueadas, sigue
así). Se usa en lugar de 'QSignalBlocker' para bloquear varios a la vez y para no
depender de cómo lo exponga cada versión de PySide.

Lo usan la barra lateral del módulo Imagen y el árbol con casillas del inspector.
"""

__version__ = "1.0.0"
__all__ = ["blocked_signals"]

# Librerías estándar
from collections.abc import Iterator
from contextlib import contextmanager

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject


@contextmanager
def blocked_signals(*objects: QObject | None) -> Iterator[None]:
    """Bloquea las señales de 'objects' durante el bloque 'with' (los None se ignoran)."""
    targets = [obj for obj in objects if obj is not None]
    previous = [obj.blockSignals(True) for obj in targets]
    try:
        yield
    finally:
        for obj, was_blocked in zip(targets, previous, strict=True):
            obj.blockSignals(was_blocked)
