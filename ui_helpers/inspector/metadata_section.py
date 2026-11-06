"""Sección «Metadatos» del inspector: cámara, exposición, ubicación... de lo seleccionado.

Aparece cuando hay algo seleccionado y TODO es de la biblioteca Imagen (fotos y vídeos del
móvil). Con varias bibliotecas, o sin selección, el panel la oculta.

    ▼ METADATOS                                   [Por defecto ▾]   <- vista (desplegable)
         Dimensiones   5712 × 4284 (24 MP)
             Recorte
         ──────────────────────────────────
             Captura   19/10/2026 18:44:05
         ──────────────────────────────────
              Cámara   NIKON Df
            Objetivo   AF-S NIKKOR 20mm f/1.8G ED
                 ...

Qué campos hay y en qué vistas: 'metadata_fields.py' (aquí no se escribe ninguno a mano).
Las filas son SIEMPRE las de la vista elegida, con el valor común, «Varios» (en gris) o en
blanco: la sección no cambia de alto al cambiar la selección. La etiqueta muestra el nombre
completo del campo al pasar el ratón.

Los valores NO están en el resumen de la selección: la sección los pide con
'data_request' (la función 'core/catalog/selection_metadata.fetch_field_values', que el
controlador del inspector ejecuta en segundo plano) y los recibe en 'show_data'. Mientras
llegan, se ven los anteriores (sin parpadeo).

La vista elegida se guarda en 'settings.json' (SETTING_INSPECTOR_METADATA_PRESET) y se
recupera al abrir la aplicación. En el Catálogo es de solo lectura (decidido por el autor
el 02/11/2026); la edición llegará con el módulo Imagen.

1.0.1 Columna de etiquetas de ancho fijo (las de todos los campos): los valores no se
      mueven al cambiar de vista.
1.0.0 Primera versión: vistas «Por defecto», «Ubicación» y «EXIF».
"""

__version__ = "1.0.1"
__all__ = ["MetadataSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QComboBox, QSizePolicy, QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_config import config
from config.app_constants import SETTING_INSPECTOR_METADATA_PRESET
from core.catalog.libraries import Library
from core.catalog.selection_metadata import FieldValue, fetch_field_values
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.inspector.base_section import (
    InfoGrid,
    InfoRow,
    InspectorSection,
    set_secondary_text,
)
from ui_helpers.inspector.metadata_fields import (
    DEFAULT_PRESET,
    FIELDS,
    PRESETS,
    SEPARATOR,
    display_value,
    preset_rows,
    sources_for,
)

# Bibliotecas con las que aparece la sección (todo lo seleccionado debe ser de una de ellas)
_LIBRARIES = (Library.IMAGE.value,)


class MetadataSection(InspectorSection):
    """Metadatos de lo seleccionado, con varias vistas (ver el docstring del módulo)."""

    title = "Metadatos"
    key = "metadata"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._grid: InfoGrid | None = None
        self._rows: dict[str, InfoRow] = {}
        self._row_keys: tuple[str, ...] = ()

        # Vista guardada (si ya no existe, la de por defecto)
        saved = config.get(SETTING_INSPECTOR_METADATA_PRESET, DEFAULT_PRESET)
        self._preset = saved if saved in PRESETS else DEFAULT_PRESET

        # Desplegable de vistas, para la cabecera (lo coloca el panel con 'header_widget')
        self._combo = QComboBox()
        self._combo.setObjectName("combo_inspector_metadata_preset")
        self._combo.setFrame(False)  # plano, como el texto de la cabecera
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._combo.setToolTip("Qué metadatos se muestran")
        for preset in PRESETS.values():
            self._combo.addItem(preset.title, preset.key)
        self._combo.setCurrentIndex(max(0, self._combo.findData(self._preset)))
        self._combo.currentIndexChanged.connect(self._on_preset_changed)

        self._build_rows()

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def header_widget(self) -> QWidget | None:
        return self._combo

    def possible_key_labels(self) -> list[str]:
        """Las etiquetas de TODOS los campos (de cualquier vista): ancho fijo de la columna."""
        return [field.label for field in FIELDS.values()]

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Solo con selección, y si todo lo seleccionado es de la biblioteca Imagen."""
        return (
            summary.scope == "selection"
            and not summary.is_empty
            and bool(summary.libraries)
            and all(library in _LIBRARIES for library in summary.libraries)
        )

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: los valores llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Los valores comunes de los campos de la vista para los 'id' seleccionados."""
        if not ids:
            return None
        return fetch_field_values, (list(ids), sources_for(self._row_keys))

    def show_data(self, result: Any) -> None:
        """Pinta cada fila: valor común, «Varios» en gris o en blanco."""
        values: dict[str, FieldValue] = result or {}
        for key, row in self._rows.items():
            shown = display_value(key, values.get(key, FieldValue()))
            row.value.set_full_text(shown.text, shown.tooltip)
            set_secondary_text(row.value, shown.secondary)

    # -------------------------------------------------------------------------
    # Vistas
    # -------------------------------------------------------------------------

    def _build_rows(self) -> None:
        """(Re)crea las filas de la vista elegida, en blanco."""
        if self._grid is not None:
            self._layout.removeWidget(self._grid)
            self._grid.deleteLater()
        self._grid = InfoGrid(self)
        self._rows = {}
        self._row_keys = preset_rows(self._preset)
        for key in self._row_keys:
            if key == SEPARATOR:
                self._grid.add_separator()
                continue
            field = FIELDS[key]
            row = self._grid.add_row(field.label)
            row.key.setToolTip(field.long_label)  # el nombre completo, al pasar el ratón
            self._rows[key] = row
        self._layout.addWidget(self._grid)

    def _on_preset_changed(self, index: int) -> None:
        """Otra vista: se guarda, se rehacen las filas y se piden sus valores."""
        preset = self._combo.itemData(index)
        if preset not in PRESETS or preset == self._preset:
            return
        self._preset = preset
        config.set(SETTING_INSPECTOR_METADATA_PRESET, preset)
        self._build_rows()
        self.refresh_requested.emit()  # el controlador vuelve a pedir los valores
