"""Qué palabras clave están desplegadas en cada árbol, para recuperarlo al volver a abrir.

En el módulo Imagen hay dos árboles de palabras clave: el de la barra izquierda
(«LISTA DE PALABRAS CLAVE», para navegar) y el del inspector («LISTA DE PALABRAS CLAVE»,
con casillas). Cada uno tiene SU PROPIO estado de ramas desplegadas (decidido por el
autor el 04/11/2026: no se sincronizan), y los dos deben abrirse como se dejaron al
cerrar el programa.

Este módulo guarda esos estados con un nombre ('SIDEBAR', 'INSPECTOR'): el árbol lo
consulta y lo actualiza, y el módulo Imagen lo guarda y recupera por catálogo con el
resto de su estado ('ImageModule.save_state' / 'restore_state'), porque los 'id' de las
palabras son de cada catálogo. Así el árbol del inspector no necesita saber qué catálogo
está abierto.

Cómo se usa:
    expansion = keyword_expansion(INSPECTOR)
    expansion.set_expanded(keyword_id, True)    # el usuario ha desplegado una rama
    expansion.ids()                             # para desplegar al rehacer el árbol
    expansion.replace(guardado)                 # al abrir un catálogo
    expansion.changed.connect(...)              # cambió (p. ej. al abrir un catálogo)

1.1.0 Un estado por árbol (con nombre), no uno compartido: los dos árboles se pliegan y
      despliegan por separado, cada uno recordado al cerrar.
"""

__version__ = "1.1.0"
__all__ = ["INSPECTOR", "SIDEBAR", "KeywordExpansion", "keyword_expansion"]

# Librerías estándar
from collections.abc import Iterable

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal

# Nombres de los estados: el árbol de la barra izquierda y el del inspector
SIDEBAR = "sidebar"
INSPECTOR = "inspector"


class KeywordExpansion(QObject):
    """Conjunto de 'keywords.id' desplegados, con aviso al cambiar.

    Signals:
        changed(): ha cambiado lo desplegado (el árbol se pone igual).
    """

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ids: set[int] = set()

    def ids(self) -> frozenset[int]:
        """Las palabras desplegadas."""
        return frozenset(self._ids)

    def is_expanded(self, keyword_id: int) -> bool:
        return keyword_id in self._ids

    def set_expanded(self, keyword_id: int, expanded: bool) -> None:
        """Despliega o pliega una palabra (avisa solo si cambia algo)."""
        if expanded == (keyword_id in self._ids):
            return
        (self._ids.add if expanded else self._ids.discard)(keyword_id)
        self.changed.emit()

    def replace(self, ids: Iterable[int]) -> None:
        """Sustituye todo lo desplegado (al abrir o cerrar un catálogo); lo que no sea un
        número entero se ignora (p. ej. un settings.json tocado a mano)."""
        new = {value for value in ids if isinstance(value, int) and not isinstance(value, bool)}
        if new != self._ids:
            self._ids = new
            self.changed.emit()


_states: dict[str, KeywordExpansion] = {}


def keyword_expansion(name: str) -> KeywordExpansion:
    """El estado del árbol 'name' ('SIDEBAR' o 'INSPECTOR'; se crea la primera vez)."""
    if name not in _states:
        _states[name] = KeywordExpansion()
    return _states[name]
