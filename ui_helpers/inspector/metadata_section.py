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
recupera al abrir la aplicación.

Edición (paso C.5; decisiones del autor del 10/11/2026 en docs/DECISIONES.md): los campos
de 'EDITABLE_KEYS' (título, pie, creador, copyright) son cajas ('editable_row.py'). Lo
escrito se aplica a los seleccionados PARA LOS QUE SE MOSTRARON los valores (como la caja
de palabras clave) con 'edit_requested' ('media_queries.update_metadata_fields'), que
atiende el controlador del inspector: queda pendiente de escribir en los archivos, como la
valoración. Si la caja mostraba «Varios», antes se pregunta («Edición múltiple», con «No
volver a mostrar»: SETTING_CONFIRM_MULTI_EDIT). Al refrescar, lo que el usuario está
escribiendo no se pisa.

El GPS, la altitud y la dirección (12/11/2026) también son cajas: muestran lo mismo que la
fila y lo escrito se interpreta antes de guardarlo ('value_parsing.py'; la caja «GPS»
cambia la latitud y la longitud). Si no vale, la caja vuelve a su valor y avisa junto a
ella ('EditableValue.reject'), sin preguntar ni guardar nada.

1.3.0 GPS, altitud y dirección editables: lo escrito se interpreta ('value_parsing.py');
      lo que no vale, aviso junto a la caja.
1.2.1 El desplegable de vistas, 2 px más a la izquierda (alineado con el resto del
      inspector; pedido por el autor).
1.2.0 Título, pie, creador y copyright editables (cajas de 'editable_row.py'), con el
      aviso «Edición múltiple» si tenían valores distintos. Autoprueba (sin ventana).
1.1.0 Es de la biblioteca Imagen ('libraries'): aparece cuando todo lo seleccionado es de
      ella, en cualquier módulo (paso A.2). Sin cambio visible.
1.0.1 Columna de etiquetas de ancho fijo (las de todos los campos): los valores no se
      mueven al cambiar de vista.
1.0.0 Primera versión: vistas «Por defecto», «Ubicación» y «EXIF».

Prueba rápida (sin ventana; necesita PySide6):
    python -m ui_helpers.inspector.metadata_section
"""

__version__ = "1.3.0"
__all__ = ["MetadataSection", "multi_edit_question"]

# Librerías estándar
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QComboBox, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_config import config
from config.app_constants import (
    SETTING_CONFIRM_MULTI_EDIT,
    SETTING_INSPECTOR_METADATA_PRESET,
)
from core.catalog.libraries import Library
from core.catalog.media_queries import update_metadata_fields
from core.catalog.selection_metadata import FieldValue, fetch_field_values
from core.catalog.selection_summary import SelectionSummary
from core.userdata.editable_fields import field_for
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.inspector.base_section import (
    InfoGrid,
    InfoRow,
    InspectorSection,
    set_secondary_text,
)
from ui_helpers.inspector.editable_row import EditableValue
from ui_helpers.inspector.metadata_fields import (
    DEFAULT_PRESET,
    EDITABLE_KEYS,
    FIELDS,
    PRESETS,
    SEPARATOR,
    display_value,
    editor_value,
    preset_rows,
    sources_for,
)
from ui_helpers.inspector.value_parsing import NUMERIC_COLUMNS, parse_numeric

# Aviso «Edición múltiple» (textos decididos por el autor el 10/11/2026)
MULTI_EDIT_TITLE = "Edición múltiple"
MULTI_EDIT_ACCEPT = "Cambiar todos"
MULTI_EDIT_CANCEL = "Cancelar"
MULTI_EDIT_DONT_ASK = "No volver a mostrar"
# Largo máximo del valor citado en el aviso (un pie largo se corta con «…»)
_QUOTED_MAX = 60

# Cuánto se aparta el desplegable de vistas del borde derecho de la cabecera (px lógicos),
# para alinearlo con el resto del inspector (pedido por el autor el 10/11/2026). El margen
# de la cabecera es común a todas las secciones plegables (también las de la barra
# izquierda) y un QSS con márgenes haría que Qt dibujara el desplegable de otra forma: por
# eso va en un contenedor propio
_COMBO_RIGHT_INSET = 2


def multi_edit_question(label: str, count: int, value: str | None) -> str:
    """Texto del aviso «Edición múltiple».

    Args:
        label: Nombre del campo («Título», «Pie de ilustración»...).
        count: Archivos seleccionados.
        value: Lo que se va a poner (None = vaciar).
    """
    if value is None:
        question = f"¿Dejar «{label}» vacío en los {count}?"
    else:
        first_line = value.strip().split("\n")[0]
        if len(first_line) > _QUOTED_MAX or "\n" in value.strip():
            first_line = first_line[:_QUOTED_MAX].rstrip() + "…"
        question = f"¿Poner a todos «{first_line}»?"
    return (
        f"Los {count} archivos seleccionados tienen valores distintos en «{label}». {question}"
    )


class MetadataSection(InspectorSection):
    """Metadatos de lo seleccionado, con varias vistas (ver el docstring del módulo)."""

    title = "Metadatos"
    key = "metadata"
    libraries = (Library.IMAGE.value,)  # solo si todo lo seleccionado es de Imagen

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._grid: InfoGrid | None = None
        self._rows: dict[str, InfoRow] = {}  # filas de solo lectura
        self._editors: dict[str, EditableValue] = {}  # cajas de los campos editables
        self._row_keys: tuple[str, ...] = ()
        self._ids: tuple[int, ...] = ()  # a quién se aplica lo escrito (lo mostrado)
        self._pending_ids: tuple[int, ...] = ()  # los de la última petición de datos
        # Pregunta antes de cambiar un campo con «Varios»: (campo, archivos, valor) -> sí/no.
        # Se puede sustituir (p. ej. en las pruebas)
        self.confirm_multi_edit: Callable[[str, int, str | None], bool] = self._ask_multi_edit

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
        # En su contenedor, con el margen derecho (ver '_COMBO_RIGHT_INSET')
        self._header = QWidget()
        self._header.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, _COMBO_RIGHT_INSET, 0)
        header_layout.setSpacing(0)
        header_layout.addWidget(self._combo)

        self._build_rows()

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def header_widget(self) -> QWidget | None:
        return self._header

    def possible_key_labels(self) -> list[str]:
        """Las etiquetas de TODOS los campos (de cualquier vista): ancho fijo de la columna."""
        return [field.label for field in FIELDS.values()]

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Solo con selección (que todo sea de Imagen lo comprueba 'fits')."""
        return summary.scope == "selection" and not summary.is_empty

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: los valores llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Los valores comunes de los campos de la vista para los 'id' seleccionados."""
        if not ids:
            return None
        self._pending_ids = tuple(ids)
        return fetch_field_values, (list(ids), sources_for(self._row_keys))

    def show_data(self, result: Any) -> None:
        """Pinta cada fila: valor común, «Varios» en gris o en blanco.

        Una caja en la que el usuario está escribiendo para ESTOS mismos seleccionados no
        se toca (p. ej. un refresco por otra causa).
        """
        values: dict[str, FieldValue] = result or {}
        same = self._pending_ids == self._ids
        self._ids = self._pending_ids
        for key, row in self._rows.items():
            shown = display_value(key, values.get(key, FieldValue()))
            row.value.set_full_text(shown.text, shown.tooltip)
            set_secondary_text(row.value, shown.secondary)
        for key, editor in self._editors.items():
            if same and editor.is_editing():
                continue
            text, mixed = editor_value(key, values.get(key, FieldValue()))
            editor.set_value(text, mixed=mixed)

    # -------------------------------------------------------------------------
    # Edición
    # -------------------------------------------------------------------------

    def _on_committed(self, key: str, editor: EditableValue, value: str | None) -> None:
        """El usuario ha aplicado un texto en una caja: se guarda para los mostrados.

        En las cajas numéricas (el GPS), lo escrito se interpreta antes: si no vale, la caja
        vuelve a su valor y avisa junto a ella. Si la caja mostraba «Varios», antes se
        pregunta; con «Cancelar», vuelve a «Varios».
        """
        ids = self._ids
        if not ids:
            editor.revert()
            return
        if key in NUMERIC_COLUMNS:
            try:
                values = parse_numeric(key, value or "")
            except ValueError as error:
                editor.reject(str(error))
                return
        else:
            values = {key: value}
        if editor.mixed and not self.confirm_multi_edit(FIELDS[key].long_label, len(ids), value):
            editor.revert()
            return
        editor.mark_applied()
        self.edit_requested.emit(update_metadata_fields, (list(ids), values))

    def _ask_multi_edit(self, label: str, count: int, value: str | None) -> bool:
        """Aviso «Edición múltiple» (salvo que se pidiera no volver a mostrarlo)."""
        if config.get(SETTING_CONFIRM_MULTI_EDIT, True) is False:
            return True
        clicked, dont_ask = MessageBoxHelper(self).question_with_checkbox(
            multi_edit_question(label, count, value),
            MULTI_EDIT_DONT_ASK,
            title=MULTI_EDIT_TITLE,
            buttons=[MULTI_EDIT_ACCEPT, MULTI_EDIT_CANCEL],
        )
        accepted = clicked == MULTI_EDIT_ACCEPT
        # «No volver a mostrar» solo cuenta si se aceptó (con «Cancelar» no se guarda)
        if accepted and dont_ask:
            config.set(SETTING_CONFIRM_MULTI_EDIT, False)
        return accepted

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
        self._editors = {}
        self._row_keys = preset_rows(self._preset)
        for key in self._row_keys:
            if key == SEPARATOR:
                self._grid.add_separator()
                continue
            field = FIELDS[key]
            if key in EDITABLE_KEYS:
                multiline = key not in NUMERIC_COLUMNS and field_for(key).multiline
                editor = EditableValue(multiline=multiline)
                label = self._grid.add_editor_row(field.label, editor, align_top=multiline)
                label.setToolTip(field.long_label)
                editor.committed.connect(partial(self._on_committed, key, editor))
                self._editors[key] = editor
                continue
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


if __name__ == "__main__":
    # Autoprueba sin ventana (no se muestra nada ni se toca settings.json): las cajas
    # editables, lo que piden al catálogo y el aviso de «Varios».
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.inspector.metadata_section
    import sys

    from qtpy.QtWidgets import QApplication

    from core.catalog.selection_metadata import MIXED, VALUE
    from ui_helpers.inspector.metadata_fields import MIXED_TEXT

    app = QApplication.instance() or QApplication(sys.argv)
    section = MetadataSection()
    section._preset = DEFAULT_PRESET  # la vista por defecto, sin guardarla
    section._build_rows()
    assert set(section._editors) == set(EDITABLE_KEYS), section._editors
    assert not set(section._rows) & set(EDITABLE_KEYS)  # o caja o texto, no las dos
    # El desplegable de vistas va en la cabecera dentro de su contenedor, apartado del borde
    header = section.header_widget()
    assert header is not None and section._combo.parentWidget() is header
    assert header.layout().contentsMargins().right() == _COMBO_RIGHT_INSET

    edits: list[tuple[Any, Any]] = []
    section.edit_requested.connect(lambda function, arguments: edits.append((function, arguments)))
    asked: list[tuple[str, int, str | None]] = []
    answer = [False]

    def confirm(label: str, count: int, value: str | None) -> bool:
        asked.append((label, count, value))
        return answer[0]

    section.confirm_multi_edit = confirm

    # 1. Los valores de dos fotos: el título común, el creador distinto, el resto vacío
    section.data_request(None, [1, 2])  # type: ignore[arg-type]  # el resumen no se usa
    section.show_data({
        "title": FieldValue(VALUE, ("Atardecer",)),
        "description": FieldValue(VALUE, ("Primera\nSegunda",)),
        "creator": FieldValue(MIXED),
    })  # fmt: skip
    title, creator = section._editors["title"], section._editors["creator"]
    assert title.text() == "Atardecer" and creator.text() == MIXED_TEXT
    assert section._editors["description"].text() == "Primera\nSegunda"
    assert section._editors["copyright"].text() == ""

    # 2. Sin «Varios»: se aplica sin preguntar, a los dos mostrados
    title.editor().setText("Nuevo título")
    title.editor().commit_requested.emit()
    assert edits == [(update_metadata_fields, ([1, 2], {"title": "Nuevo título"}))], edits
    assert asked == []

    # 3. Con «Varios»: se pregunta; «Cancelar» vuelve a «Varios» sin cambiar nada
    creator.editor().setText("Javier Rojo")
    creator.editor().commit_requested.emit()
    assert asked == [("Creador", 2, "Javier Rojo")] and len(edits) == 1
    assert creator.text() == MIXED_TEXT
    # «Cambiar todos» al borrar «Varios»: se vacía en los dos
    answer[0] = True
    creator.editor().setText("")
    creator.editor().commit_requested.emit()
    assert edits[-1] == (update_metadata_fields, ([1, 2], {"creator": None})), edits
    print("1-3. Cajas: aplicar, «Varios» con aviso, «Cancelar» y vaciar en todos")

    # 4. Otra selección: los valores nuevos y lo escrito va a los nuevos
    section.data_request(None, [7])  # type: ignore[arg-type]
    section.show_data({"title": FieldValue(VALUE, ("Otra",))})
    assert title.text() == "Otra" and creator.text() == ""
    title.editor().setText("Última")
    title.editor().commit_requested.emit()
    assert edits[-1][1] == ([7], {"title": "Última"})
    print("4. Otra selección: lo escrito va a los que se muestran")

    # 4b. GPS, altitud y dirección: la caja muestra lo de la fila; lo escrito se interpreta
    section.data_request(None, [3, 4])  # type: ignore[arg-type]
    section.show_data({
        "gps": FieldValue(VALUE, (42.682089, 0.069991)),
        "altitude": FieldValue(VALUE, (1418.1,)),
        "direction": FieldValue(MIXED),
    })  # fmt: skip
    gps, altitude = section._editors["gps"], section._editors["altitude"]
    direction = section._editors["direction"]
    assert gps.text() == "42°40'55,5204\" N 0°4'11,9676\" E" and altitude.text() == "1.418,1 m"
    assert direction.text() == MIXED_TEXT
    before = len(edits)
    gps.editor().setText("41.3874, 2.1686")
    gps.editor().commit_requested.emit()
    assert edits[-1] == (update_metadata_fields, ([3, 4], {"latitude": 41.3874, "longitude": 2.1686}))
    altitude.editor().setText("−12,5 m")
    altitude.editor().commit_requested.emit()
    assert edits[-1][1] == ([3, 4], {"altitude": -12.5})
    # Vaciar el GPS: las dos columnas
    gps.editor().setText("")
    gps.editor().commit_requested.emit()
    assert edits[-1][1] == ([3, 4], {"latitude": None, "longitude": None})
    # Lo que no vale: la caja vuelve a su valor, no se pregunta ni se guarda nada
    asked.clear()
    count = len(edits)
    for editor, bad in ((altitude, "mucho"), (gps, "0, 0"), (direction, "Nortee")):
        shown = editor.text()
        editor.editor().setText(bad)
        editor.editor().commit_requested.emit()
        assert editor.text() == shown and len(edits) == count and asked == [], bad
    # La dirección con «Varios»: se pregunta, con lo escrito
    direction.editor().setText("Sur")
    direction.editor().commit_requested.emit()
    assert asked == [("Dirección de la cámara", 2, "Sur")]
    assert edits[-1][1] == ([3, 4], {"gps_direction": 180.0}) and len(edits) == before + 4
    print("4b. GPS, altitud y dirección: interpretados; lo que no vale, de vuelta y sin guardar")

    # 5. Textos del aviso
    assert multi_edit_question("Título", 37, "Atardecer en León") == (
        "Los 37 archivos seleccionados tienen valores distintos en «Título». "
        "¿Poner a todos «Atardecer en León»?"
    )
    assert multi_edit_question("Título", 37, None).endswith("¿Dejar «Título» vacío en los 37?")
    assert multi_edit_question("Pie de ilustración", 2, "Una\nDos").endswith("«Una…»?")
    assert "«" + "x" * 60 + "…»" in multi_edit_question("Pie de ilustración", 2, "x" * 80)
    print("5. Textos del aviso «Edición múltiple»")

    section.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
