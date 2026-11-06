"""Sección «Palabras clave» del inspector: las palabras asignadas a lo seleccionado.

    ▼ PALABRAS CLAVE
         Coche, Toyota Corolla*, Playa

Como el panel «Etiquetas de palabras clave» de Lightroom: las palabras van separadas por
comas, por orden alfabético, y las que NO tienen todos los seleccionados llevan un
asterisco. Al pasar el ratón se ven sus rutas completas («Coche > Toyota Corolla») y en
cuántos de los seleccionados está cada una.

Aparece con cualquier selección, sea de la biblioteca que sea: las palabras clave son
comunes a todos los tipos de archivo (decidido el 03/11/2026). Es de solo lectura: en el
módulo Imagen la sustituye el editor ('keyword_editor_section.py', paso K4b).

1.1.0 No aparece en el módulo Imagen ('hidden_in'): allí está el editor.

Las palabras NO están en el resumen de la selección: la sección las pide con
'data_request' ('core/catalog/keywords.fetch_selection_keywords', en segundo plano) y las
recibe en 'show_data'.

Prueba rápida del texto (sin Qt):
    python -m ui_helpers.inspector.keywords_section
"""

__version__ = "1.1.0"
__all__ = ["KeywordsSection", "keywords_text"]

# Librerías estándar
from collections import Counter
from collections.abc import Callable, Sequence
from html import escape
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.keywords import SelectionKeywords, fetch_selection_keywords
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.inspector.base_section import InspectorSection, set_secondary_text

# Texto cuando lo seleccionado no tiene ninguna palabra
EMPTY_TEXT = "Sin palabras clave"
# Marca de las palabras que no tienen todos los seleccionados (como Lightroom)
PARTIAL_MARK = "*"
# Palabras como máximo en el texto (con Ctrl+A en un catálogo grande podrían ser cientos)
MAX_SHOWN = 150


def keywords_text(selection: SelectionKeywords) -> tuple[str, str]:
    """Texto y texto emergente de la sección.

    Se muestra el nombre de cada palabra; si dos palabras distintas se llaman igual (dos
    «Ana» en sitios distintos del árbol), su ruta completa, para distinguirlas.

    Returns:
        (texto, tooltip). Sin palabras: (EMPTY_TEXT, "").
    """
    if not selection.items:
        return EMPTY_TEXT, ""
    repeated = Counter(path[-1].casefold() for path, _count in selection.items)
    shown: list[str] = []
    details: list[str] = []
    for path, count in selection.items:
        name = " > ".join(path) if repeated[path[-1].casefold()] > 1 else path[-1]
        partial = count < selection.total
        shown.append(f"{name}{PARTIAL_MARK}" if partial else name)
        where = f" ({count} de {selection.total})" if partial else ""
        details.append(f"{' > '.join(path)}{where}")
    extra = len(shown) - MAX_SHOWN
    text = ", ".join(shown[:MAX_SHOWN]) + (f" y {extra} más" if extra > 0 else "")
    tooltip_lines = details[:MAX_SHOWN] + ([f"… y {extra} más"] if extra > 0 else [])
    if any(count < selection.total for _path, count in selection.items):
        tooltip_lines.append(f"{PARTIAL_MARK} No la tienen todos los seleccionados.")
    return text, "\n".join(tooltip_lines)


class KeywordsSection(InspectorSection):
    """Palabras clave de lo seleccionado (ver el docstring del módulo)."""

    title = "Palabras clave"
    key = "keywords"
    # En Imagen se editan: allí la sustituye 'KeywordEditorSection'
    hidden_in = ("image",)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        # Mismos márgenes que las filas de las demás secciones ('InfoGrid')
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(0)

        # Texto con saltos de línea automáticos; seleccionable para copiar una palabra
        self._label = QLabel(EMPTY_TEXT, self)
        self._label.setObjectName("lbl_inspector_keywords")
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # Al menos dos líneas de alto: con una o dos palabras la sección no cambia de alto
        self._label.setMinimumHeight(self._label.fontMetrics().lineSpacing() * 2)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        set_secondary_text(self._label)
        layout.addWidget(self._label)

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Con cualquier selección (de cualquier biblioteca); sin selección, no."""
        return summary.scope == "selection" and not summary.is_empty

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: las palabras llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Las palabras de los 'id' seleccionados."""
        if not ids:
            return None
        return fetch_selection_keywords, (list(ids),)

    def show_data(self, result: Any) -> None:
        """Pinta las palabras (o «Sin palabras clave», en gris)."""
        selection = result if isinstance(result, SelectionKeywords) else SelectionKeywords()
        text, tooltip = keywords_text(selection)
        self._label.setText(text)
        self._label.setToolTip(escape(tooltip).replace("\n", "<br>") if tooltip else "")
        set_secondary_text(self._label, not selection.items)


if __name__ == "__main__":
    # Autoprueba del texto (no necesita Qt real). Ejecutar desde la raíz del proyecto:
    #     python -m ui_helpers.inspector.keywords_section
    assert keywords_text(SelectionKeywords(total=3)) == (EMPTY_TEXT, "")
    one = SelectionKeywords(total=1, items=((("Coche",), 1), (("Coche", "Toyota Corolla"), 1)))
    assert keywords_text(one) == ("Coche, Toyota Corolla", "Coche\nCoche > Toyota Corolla")
    # Varias fotos: la que no tienen todas, con asterisco y su recuento en el tooltip
    many = SelectionKeywords(total=3, items=((("Coche", "Toyota Corolla"), 1), (("Playa",), 3)))
    text, tooltip = keywords_text(many)
    assert text == "Toyota Corolla*, Playa", text
    assert tooltip.splitlines()[0] == "Coche > Toyota Corolla (1 de 3)", tooltip
    assert tooltip.endswith("No la tienen todos los seleccionados.")
    # Dos palabras con el mismo nombre: con su ruta
    twins = SelectionKeywords(total=1, items=((("Amigos", "Ana"), 1), (("Familia", "Ana"), 1)))
    assert keywords_text(twins)[0] == "Amigos > Ana, Familia > Ana"
    # Muchas: se corta el texto
    lots = SelectionKeywords(total=1, items=tuple(((f"P{n:03}",), 1) for n in range(MAX_SHOWN + 5)))
    assert keywords_text(lots)[0].endswith(" y 5 más")
    print("Autoprueba finalizada correctamente.")
