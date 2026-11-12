"""Base de las secciones con árbol de la barra lateral de un módulo.

Cada sección (carpetas, palabras clave, fechas...) es un widget que la barra pone dentro de
una 'CollapsibleSection'. Tiene uno o más árboles ('SidebarTreeView') cuyas filas llevan un
'GridSource' (ROLE_SOURCE) y su número (ROLE_COUNT). La sección solo pinta y recuerda lo
suyo; lo común lo hace la barra que la contiene (p. ej. 'ImageSidebar'):

    - Una sola fila elegida en toda la barra: la barra conecta la selección de 'views()' y
      emite el origen elegido.
    - La fila elegida: la barra la busca con 'find_item' y la vuelve a marcar cuando la
      sección avisa con 'rebuilt' (al rehacer un árbol se pierde la selección).
    - El estado por catálogo: 'save_state' devuelve las claves de la sección, que la barra
      junta con las de las demás en un solo diccionario (por eso dos secciones no pueden
      usar la misma clave), y 'restore_state' recibe ese diccionario entero.

Una sección no sabe nada de SQL: los datos se los pone su módulo a través de la barra.

1.0.0 Primera versión: sale de 'image_sidebar.py' al dividirla en un archivo por sección
      (12/11/2026).
"""

__version__ = "1.0.0"
__all__ = ["TreeSection", "make_item"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Signal
from qtpy.QtGui import QStandardItem
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from core.catalog.grid_source import GridSource
from ui_helpers.widgets.sidebar_tree_view import ROLE_COUNT, ROLE_SOURCE, SidebarTreeView


def make_item(text: str, source: GridSource | None, count: int | None = None) -> QStandardItem:
    """Una fila (sin añadirla a ningún sitio): texto, origen y número (None = sin número)."""
    item = QStandardItem(text)
    item.setEditable(False)
    item.setData(source, ROLE_SOURCE)
    item.setData(count, ROLE_COUNT)
    return item


class TreeSection(QWidget):
    """Contenido de una sección con árbol (ver el docstring del módulo).

    Por defecto no hace nada: cada sección implementa lo que necesite.

    Signals:
        rebuilt(): un árbol de la sección se ha rehecho (la barra vuelve a marcar la fila
            elegida, si es de la sección).
    """

    rebuilt = Signal()

    def views(self) -> tuple[SidebarTreeView, ...]:
        """Sus árboles (la barra conecta su selección)."""
        return ()

    def find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de un origen, o None si no es de la sección o ahora no está en el árbol."""
        return None

    def owns(self, source: GridSource) -> bool:
        """Si un origen es de la sección aunque su fila aún no esté (p. ej. el guardado,
        antes de que llegue el árbol, que se lee en segundo plano)."""
        return False

    def reveal(self, source: GridSource) -> None:
        """Prepara el árbol para que se vea la fila de un origen pedido desde fuera
        (desplegar sus padres, vaciar un filtro que la oculte...)."""

    def save_state(self) -> dict:
        """Lo que la sección guarda por catálogo (claves propias; ver el docstring)."""
        return {}

    def restore_state(self, state: dict) -> None:
        """Recupera lo suyo del estado de la barra (lo que no se entienda se ignora)."""

    def reset(self) -> None:
        """Sin catálogo: la sección, vacía."""
