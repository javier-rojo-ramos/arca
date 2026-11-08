"""Sección «Lista de palabras clave»: el árbol con casillas, en todos los módulos (K4b).

    ▼ LISTA DE PALABRAS CLAVE
      [Filtrar palabras clave        ]
      ▼ [■] Coche                  12
            [✓] Opel Astra          5
            [ ] Toyota Corolla      7
        [ ] Playa                  30

Como la «Lista de palabras clave» de Lightroom: TODAS las palabras del catálogo, con una
casilla que dice si las tiene lo seleccionado (marcada: todos; intermedia: algunos;
vacía: ninguno). Pulsar una casilla asigna la palabra a todos o la quita de todos (ver
'ui_helpers/widgets/keyword_checklist.py'). El número es el de la biblioteca Imagen.

Aparece también SIN selección (04/11/2026): con las casillas vacías y sin poder pulsarlas,
pero con el menú, soltar tarjetas y la flecha «ver sus fotos», que pide a la barra
izquierda mostrar la palabra ('navigate_requested'). Así, tras usar la flecha (la
cuadrícula cambia y la selección se pierde), el árbol no desaparece.

Va en su propia sección, debajo de «Palabras clave» (la caja de texto), para poder
plegarla por separado: con el árbol desplegado la sección es larga (decidido por el autor
el 04/11/2026, al ver la primera versión con las dos cosas juntas).

La sección no toca la base de datos: lee con 'data_request'
('keywords.fetch_keyword_editor_data') y pide los cambios con 'edit_requested'
('keywords.apply_keyword_changes'), que atiende el controlador del inspector.

1.5.0 En todos los módulos, siempre (también sin selección: para navegar con la flecha o
      soltar tarjetas); paso A.2.
1.4.0 Flecha «ver sus fotos» ('navigate_requested') y visible también sin selección.
1.3.0 Soltar tarjetas de la cuadrícula sobre una palabra se la asigna (antes, en la barra
      izquierda: la barra es para navegar y el inspector para editar).
1.2.0 Menú contextual del árbol (crear, renombrar, mover, borrar, purgar; K4c-2).
1.1.0 Datos con 'KeywordEditorData'; los padres de las palabras asignadas, resaltados.
"""

__version__ = "1.5.0"
__all__ = ["KeywordListSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.keywords import (
    KeywordChanges,
    KeywordEditorData,
    apply_keyword_changes,
    fetch_keyword_editor_data,
)
from core.catalog.grid_source import keyword_source
from core.catalog.libraries import Library
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.inspector.base_section import InspectorSection
from ui_helpers.models.media_mime import MediaDrag
from ui_helpers.widgets.keyword_checklist import KeywordChecklist

# Biblioteca de los recuentos del árbol (la del módulo Imagen)
LIBRARY = Library.IMAGE.value


class KeywordListSection(InspectorSection):
    """Árbol de palabras con casillas para lo seleccionado (ver el docstring del módulo)."""

    title = "Lista de palabras clave"
    key = "keyword_list"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ids: tuple[int, ...] = ()           # a quién se aplican los cambios
        self._pending_ids: tuple[int, ...] = ()   # los de la última petición de datos

        layout = QVBoxLayout(self)
        # Mismos márgenes que las filas de las demás secciones ('InfoGrid')
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(0)

        self._checklist = KeywordChecklist(self)
        self._checklist.keyword_toggled.connect(self._on_keyword_toggled)
        # Menú contextual del árbol: va por el mismo camino que los demás cambios
        self._checklist.operation_requested.connect(self.edit_requested)
        # Tarjetas soltadas sobre una palabra: se les asigna (a ellas, no a la selección)
        self._checklist.media_dropped.connect(self._on_media_dropped)
        # Flecha «ver sus fotos»: la cuadrícula muestra la palabra (la elige la barra)
        self._checklist.show_keyword_requested.connect(
            lambda keyword_id: self.navigate_requested.emit(keyword_source(keyword_id, LIBRARY))
        )
        layout.addWidget(self._checklist)

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Siempre: sin selección, el árbol se ve con las casillas vacías."""
        return True

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: los datos llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Palabras de los seleccionados (ninguna sin selección) y el árbol (con los
        recuentos de Imagen)."""
        self._pending_ids = tuple(ids)
        return fetch_keyword_editor_data, (list(ids), LIBRARY)

    def show_data(self, result: Any) -> None:
        """Rehace el árbol con las casillas de la selección."""
        data = result if isinstance(result, KeywordEditorData) else KeywordEditorData()
        self._ids = self._pending_ids
        # Con los padres de las palabras asignadas resaltados (K4c)
        self._checklist.set_data(data.tree, data.selection, data.descendants)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_media_dropped(self, keyword_id: int, drag: MediaDrag) -> None:
        """Tarjetas soltadas sobre una palabra: asignársela (cuenta como «usada»)."""
        changes = KeywordChanges(add_ids=(keyword_id,))
        self.drop_edit_requested.emit(apply_keyword_changes, (list(drag.ids), changes), drag)

    def _on_keyword_toggled(self, keyword_id: int, assign: bool) -> None:
        """Casilla del árbol: asignar a todos o quitar de todos."""
        if not self._ids:
            return
        if assign:
            changes = KeywordChanges(add_ids=(keyword_id,))
        else:
            changes = KeywordChanges(remove_ids=(keyword_id,))
        self.edit_requested.emit(apply_keyword_changes, (list(self._ids), changes))
