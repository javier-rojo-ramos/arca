"""Una columna del panel «Metadatos» de la barra de filtros (como en Lightroom).

    ┌──────────────────────────────────────┐
    │ Ciudad ▾                          ⚙ │   cabecera: el campo y el engranaje
    ├──────────────────────────────────────┤
    │ Todo (8)                         317 │   «Todo (N)»: N valores; a la derecha, archivos
    │ Boltaña                           14 │
    │ Huesca                             4 │
    │ Desconocido                        2 │   sin el dato, al final
    └──────────────────────────────────────┘

Cabecera: a la izquierda, el CAMPO (un menú como el del editor de colecciones
inteligentes: un submenú por grupo y, dentro, los campos por secciones; solo los campos
de 'smart_fields' con 'browse=True' y los grupos de los tipos del módulo, 'set_media_types').
A la derecha, el ENGRANAJE con «Añadir columna» y «Quitar esta columna» (los activa quien
la usa: 'set_can_add' / 'set_can_remove').

Lista: la fila «Todo» (la columna no filtra) y cada valor con su recuento. Clic = solo ese
valor; Ctrl+clic añade o quita uno; Mayús+clic, un rango; clic en «Todo» vacía la columna
(y quitar lo último elegido vuelve a «Todo»). Las fechas, en árbol: año ▸ mes ▸ día. Lo
elegido que ya no aparece (recuento 0) se ve atenuado.

Solo muestra y avisa: no consulta la base de datos ni sabe qué es un filtro.
    - Lo que se ve lo ponen 'set_field' y 'set_values' (los valores y recuentos de
      'core/catalog/metadata_values.py' y lo elegido), sin emitir nada.
    - Al elegir: 'values_changed(frozenset)'; al pedir otro campo: 'field_requested(str)';
      el engranaje: 'add_requested()' y 'remove_requested()'.
Nada coge el foco: el teclado sigue en la cuadrícula.

Los textos de cada valor («Desconocido», «Sin color», «Junio», «f/2,8»...) salen de
'value_text'.

Uso (lo crea el panel de «Metadatos»):
    column = MetadataColumnWidget(parent)
    column.set_media_types(("photo", "video"))
    column.set_field("city")
    column.set_values(fetch_metadata_values(...), chosen)
    column.values_changed.connect(...)

1.0.0 Primera versión (paso A.3, «Metadatos», subpaso 2).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.metadata_column
Vista de ejemplo (abre una ventana y espera a que se cierre): tres columnas con el tema
    python -m ui_helpers.widgets.metadata_column --ventana
"""

__version__ = "1.0.0"
__all__ = [
    "ADD_COLUMN_TEXT",
    "ALL_TEXT",
    "HEADER_HEIGHT",
    "REMOVE_COLUMN_TEXT",
    "MetadataColumnWidget",
    "value_text",
]

# Librerías estándar
from collections.abc import Iterable
from datetime import date
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile, QItemSelection, QItemSelectionModel, QSize, Qt, Signal
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.grid_filter import METADATA_UNKNOWN
from core.catalog.metadata_values import MetadataValue, MetadataValues
from core.catalog.smart_fields import (
    FIELDS,
    GROUPS,
    KIND_BOOL,
    KIND_DATE,
    KIND_ENUM,
    KIND_RATING,
    browse_fields,
)
from core.catalog.smart_rules import format_value
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_theme import COLORS
from ui_helpers.inspector.formatting import (
    format_focal_length,
    format_iso,
    format_shutter,
)

# Textos de la interfaz
ALL_TEXT = "Todo ({count})"
ADD_COLUMN_TEXT = "Añadir columna"
REMOVE_COLUMN_TEXT = "Quitar esta columna"
_SETTINGS_TOOLTIP = "Columnas"
_FIELD_ARROW = " ▾"  # tras el nombre del campo: se puede pulsar (sin la flecha de Fusion)
_UNKNOWN_TEXT = "Desconocido"
# Los campos que tienen su propio texto para «sin el dato» (el mismo que en otros sitios:
# «Sin clasificar» es la fila de la barra izquierda, decidido por el autor el 09/11/2026)
_UNKNOWN_TEXTS: dict[str, str] = {
    "color_label": "Sin color",
    "keyword": "Sin palabras clave",
    "library": "Sin clasificar",
}
_NO_RATING_TEXT = "Sin valoración"  # la valoración 0 (no es «sin dato»: es su valor)
_BOOL_TEXTS = {1: "Sí", 0: "No"}
_MONTHS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
    "Septiembre", "Octubre", "Noviembre", "Diciembre",
)  # fmt: skip
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# Números con su formato (los demás, con el de las reglas: 'smart_rules.format_value').
# El tiempo de exposición, EXACTO: cada fila filtra por su valor, y con el nominal dos
# filas distintas se llamarían igual ('1/121 s' y '1/125 s' serían las dos '1/125 s')
_NUMBER_TEXTS = {
    "iso": format_iso,
    "f_number": lambda value: f"f/{value:g}".replace(".", ","),  # 'f/1,78', 'f/2,8'
    "focal_length": format_focal_length,
    "exposure_time": lambda value: format_shutter(value, nominal=False),
}

# --- Medidas (px lógicos) ---
HEADER_HEIGHT = 26
_SETTINGS_ICON = 14
_SETTINGS_BUTTON = 22
_INDENT = 14  # sangría de los meses y días

# --- Aspecto ---
_COUNT_COLOR = COLORS.text_dim  # recuentos, como los contadores de la barra izquierda
_EMPTY_COLOR = COLORS.text_disabled  # lo elegido que ya no aparece (recuento 0)

# Nombres de objeto (para el QSS de 'ui_theme.py')
COLUMN_OBJECT_NAME = "widget_metadata_column"
HEADER_OBJECT_NAME = "widget_metadata_header"
FIELD_OBJECT_NAME = "btn_metadata_field"
SETTINGS_OBJECT_NAME = "btn_metadata_settings"
TREE_OBJECT_NAME = "tree_metadata_values"

# Clave de la fila «Todo» en el dato de cada fila (las demás llevan su posición)
_ALL_KEY = -1
_KEY_ROLE = Qt.ItemDataRole.UserRole


def value_text(field_key: str, value: Any) -> str:
    """El texto de un valor de una columna (ver la cabecera).

    Args:
        field_key: Clave del campo (de 'smart_fields.FIELDS').
        value: El valor ('MetadataValue.value'; None = sin el dato).
    """
    spec = FIELDS[field_key]
    if value is METADATA_UNKNOWN:
        return _UNKNOWN_TEXTS.get(field_key, _UNKNOWN_TEXT)
    if spec.kind == KIND_DATE:
        return _date_text(value)
    if spec.kind == KIND_RATING:
        return "★" * value if value else _NO_RATING_TEXT
    if spec.kind == KIND_BOOL:
        return _BOOL_TEXTS.get(value, str(value))
    if spec.kind == KIND_ENUM:
        return spec.choice_label(value)
    if field_key in _NUMBER_TEXTS:
        return _NUMBER_TEXTS[field_key](value) or str(value)
    if isinstance(value, (int, float)):
        return format_value(spec, "eq", value)
    return str(value)


def _date_text(value: str) -> str:
    """'2024' (año), 'Junio' (mes) o '15 - sábado' (día)."""
    if len(value) == 7:
        return _MONTHS[int(value[5:]) - 1]
    if len(value) == 10:
        return f"{int(value[8:])} - {_WEEKDAYS[date.fromisoformat(value).weekday()]}"
    return value


def _count_text(count: int) -> str:
    """Recuento con punto de miles ('1.234'), como el resumen del inspector."""
    return f"{count:,}".replace(",", ".")


class MetadataColumnWidget(QWidget):
    """Una columna de «Metadatos» (ver el docstring del archivo).

    Signals:
        field_requested(str): se ha elegido otro campo en el menú de la cabecera.
        values_changed(object): ha cambiado lo elegido (un frozenset; vacío = «Todo»).
        add_requested(): «Añadir columna».
        remove_requested(): «Quitar esta columna».
    """

    field_requested = Signal(str)
    values_changed = Signal(object)
    add_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(COLUMN_OBJECT_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Las columnas del panel se reparten el ancho a partes iguales, sea cual sea su texto
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self._field = ""
        self._media_types: tuple[str, ...] = ()
        self._chosen: frozenset[Any] = frozenset()
        self._row_values: list[Any] = []  # valor de cada fila (su clave es la posición)
        self._expanded: set[str] = set()  # años y meses desplegados (se mantienen al recargar)
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cabecera: el campo (con su menú) y el engranaje
        header = QWidget(self)
        header.setObjectName(HEADER_OBJECT_NAME)
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setFixedHeight(HEADER_HEIGHT)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 2, 0)
        header_layout.setSpacing(2)
        self._field_button = QToolButton(header)
        self._field_button.setObjectName(FIELD_OBJECT_NAME)
        self._field_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._field_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._field_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._field_menu = QMenu(self._field_button)
        self._field_button.setMenu(self._field_menu)
        header_layout.addWidget(self._field_button)  # a la izquierda, con su ancho
        header_layout.addStretch(1)

        self._settings_button = QToolButton(header)
        self._settings_button.setObjectName(SETTINGS_OBJECT_NAME)
        self._settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._settings_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.setToolTip(_SETTINGS_TOOLTIP)
        self._settings_button.setFixedSize(_SETTINGS_BUTTON, _SETTINGS_BUTTON)
        self._settings_button.setIconSize(QSize(_SETTINGS_ICON, _SETTINGS_ICON))
        if QFile.exists(AppIcons.SETTINGS):
            self._settings_button.setIcon(tinted_icon(AppIcons.SETTINGS, COLORS.text_dim,
                                                      hover_color=COLORS.accent))
        else:
            self._settings_button.setText("⚙")
        settings_menu = QMenu(self._settings_button)
        self._add_action = settings_menu.addAction(ADD_COLUMN_TEXT)
        self._remove_action = settings_menu.addAction(REMOVE_COLUMN_TEXT)
        self._add_action.triggered.connect(self.add_requested)
        self._remove_action.triggered.connect(self.remove_requested)
        self._settings_button.setMenu(settings_menu)
        header_layout.addWidget(self._settings_button)
        layout.addWidget(header)

        # Lista de valores: texto a la izquierda y recuento a la derecha
        self._tree = QTreeWidget(self)
        self._tree.setObjectName(TREE_OBJECT_NAME)
        self._tree.setColumnCount(2)
        self._tree.setHeaderHidden(True)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setIndentation(_INDENT)
        self._tree.setRootIsDecorated(False)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._tree.itemExpanded.connect(lambda item: self._remember_expanded(item, True))
        self._tree.itemCollapsed.connect(lambda item: self._remember_expanded(item, False))
        layout.addWidget(self._tree, 1)

        self._rebuild_field_menu()

    # --- Lo que se ve (sin emitir nada) -------------------------------------------------

    @property
    def field(self) -> str:
        """Campo que muestra ('' si aún no tiene)."""
        return self._field

    @property
    def chosen(self) -> frozenset[Any]:
        """Lo elegido (vacío = «Todo»)."""
        return self._chosen

    def set_media_types(self, media_types: Iterable[str]) -> None:
        """Tipos del módulo: el menú de campos ofrece solo sus grupos (Estándar, siempre)."""
        self._media_types = tuple(media_types)
        self._rebuild_field_menu()

    def set_field(self, field_key: str) -> None:
        """Pone el campo de la columna y vacía la lista (hasta que llegue 'set_values').

        Raises:
            ValueError: Si el campo no se ofrece como columna.
        """
        spec = FIELDS.get(field_key)
        if spec is None or not spec.browse:
            raise ValueError(f"Campo no disponible en «Metadatos»: {field_key!r}")
        if field_key != self._field:
            self._expanded.clear()
        self._field = field_key
        group = next(g.label for g in GROUPS if g.key == spec.group)
        self._field_button.setText(spec.label + _FIELD_ARROW)
        self._field_button.setToolTip(f"{group} › {spec.section} › {spec.label}")
        self._tree.setRootIsDecorated(spec.kind == KIND_DATE)
        self._chosen = frozenset()
        self._fill(None)
        self._check_current_field()

    def set_values(self, values: MetadataValues, chosen: Iterable[Any] = ()) -> None:
        """Pone los valores y recuentos y marca lo elegido. Si son de otro campo (una
        respuesta que llega tarde), no hace nada."""
        if values.field != self._field:
            return
        self._chosen = frozenset(chosen)
        self._fill(values)

    def set_can_add(self, can: bool) -> None:
        """Activa «Añadir columna» (no, con el máximo de columnas)."""
        self._add_action.setEnabled(can)

    def set_can_remove(self, can: bool) -> None:
        """Activa «Quitar esta columna» (no, si es la única)."""
        self._remove_action.setEnabled(can)

    # --- Menú de campos -------------------------------------------------------------------

    def _rebuild_field_menu(self) -> None:
        """Un submenú por grupo con campos de columna y, dentro, los campos por secciones
        (como el editor de colecciones inteligentes). Solo los grupos del módulo."""
        self._field_menu.clear()
        for group in GROUPS:
            if group.media_types and not set(group.media_types) & set(self._media_types):
                continue
            specs = browse_fields(group.key)
            if not specs:
                continue
            submenu = self._field_menu.addMenu(group.label)
            section = None
            for spec in specs:
                if spec.section != section:
                    # Título de la sección (en negrita y sin poder pulsarse)
                    if section is not None:
                        submenu.addSeparator()
                    title = submenu.addAction(spec.section)
                    title.setEnabled(False)
                    font = QFont(title.font())
                    font.setBold(True)
                    title.setFont(font)
                    section = spec.section
                action = submenu.addAction(f"    {spec.label}")
                action.setCheckable(True)
                action.setData(spec.key)
                action.triggered.connect(lambda _checked=False, key=spec.key: self._on_field_chosen(key))
        self._check_current_field()

    def _check_current_field(self) -> None:
        """Marca en el menú el campo de la columna."""
        for submenu_action in self._field_menu.actions():
            submenu = submenu_action.menu()
            for action in submenu.actions() if submenu else ():
                if action.isCheckable():
                    action.setChecked(action.data() == self._field)

    def _on_field_chosen(self, key: str) -> None:
        self._check_current_field()  # lo que se ve lo confirma 'set_field'
        if key != self._field:
            self.field_requested.emit(key)

    # --- La lista ---------------------------------------------------------------------------

    def _fill(self, values: MetadataValues | None) -> None:
        """Rellena la lista ('None' = vacía) y marca lo elegido, sin emitir nada."""
        self._updating = True
        try:
            self._tree.clear()
            self._row_values = []
            if values is None:
                return
            all_item = QTreeWidgetItem(self._tree, [ALL_TEXT.format(count=values.value_count),
                                                    _count_text(values.total)])
            self._style_item(all_item, _ALL_KEY, values.total)
            for value in values.values:
                self._add_item(self._tree.invisibleRootItem(), value)
            self._select_chosen()
        finally:
            self._updating = False

    def _add_item(self, parent: QTreeWidgetItem, value: MetadataValue) -> None:
        """Una fila (y, en las fechas, las de sus meses o días)."""
        item = QTreeWidgetItem(parent, [value_text(self._field, value.value), _count_text(value.count)])
        self._style_item(item, len(self._row_values), value.count)
        self._row_values.append(value.value)
        for child in value.children:
            self._add_item(item, child)
        if isinstance(value.value, str) and value.value in self._expanded:
            item.setExpanded(True)

    @staticmethod
    def _style_item(item: QTreeWidgetItem, key: int, count: int) -> None:
        """Su clave, el recuento a la derecha y, si no tiene archivos, atenuada."""
        item.setData(0, _KEY_ROLE, key)
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setForeground(1, QBrush(QColor(_COUNT_COLOR)))
        item.setToolTip(0, item.text(0))
        if count == 0 and key != _ALL_KEY:
            for column in (0, 1):
                item.setForeground(column, QBrush(QColor(_EMPTY_COLOR)))

    def _items(self) -> list[QTreeWidgetItem]:
        """Todas las filas, también las de dentro (meses y días)."""
        found: list[QTreeWidgetItem] = []
        pending = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while pending:
            item = pending.pop(0)
            found.append(item)
            pending[:0] = [item.child(i) for i in range(item.childCount())]
        return found

    def _select_chosen(self) -> None:
        """Marca lo elegido (o «Todo», si no hay nada) y despliega lo que lo contiene."""
        selection = self._tree.selectionModel()
        selection.clearSelection()
        targets = [
            item for item in self._items()
            if (key := item.data(0, _KEY_ROLE)) != _ALL_KEY and self._row_values[key] in self._chosen
        ] or [self._tree.topLevelItem(0)]
        for item in targets:
            self._tree.setCurrentItem(item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
            item.setSelected(True)
            parent = item.parent()
            while parent is not None:  # un día o un mes elegido, a la vista
                parent.setExpanded(True)
                parent = parent.parent()

    def _remember_expanded(self, item: QTreeWidgetItem, expanded: bool) -> None:
        """Recuerda los años y meses desplegados (para la siguiente recarga)."""
        key = item.data(0, _KEY_ROLE)
        if key is None or key == _ALL_KEY:
            return
        value = self._row_values[key]
        if isinstance(value, str):
            (self._expanded.add if expanded else self._expanded.discard)(value)

    def _on_selection_changed(self, selected: QItemSelection, _deselected: QItemSelection) -> None:
        """Clic en «Todo»: solo «Todo»; en un valor: quita «Todo»; sin nada: vuelve a «Todo».
        Si lo elegido cambia, lo avisa."""
        if self._updating:
            return
        all_item = self._tree.topLevelItem(0)
        if all_item is None:
            return
        all_index = self._tree.indexFromItem(all_item, 0)
        self._updating = True
        try:
            if any(index.row() == all_index.row() and not index.parent().isValid()
                   for index in selected.indexes()):
                self._tree.clearSelection()
                all_item.setSelected(True)
            else:
                chosen_items = [i for i in self._tree.selectedItems() if i is not all_item]
                all_item.setSelected(not chosen_items)
        finally:
            self._updating = False
        chosen = frozenset(
            self._row_values[key]
            for item in self._tree.selectedItems()
            if (key := item.data(0, _KEY_ROLE)) != _ALL_KEY
        )
        if chosen != self._chosen:
            self._chosen = chosen
            self.values_changed.emit(chosen)


if __name__ == "__main__":
    # Autoprueba (sin ventana). Ejecutar desde la raíz:  python -m ui_helpers.widgets.metadata_column
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Textos de los valores
    assert value_text("city", "Huesca") == "Huesca" and value_text("city", None) == "Desconocido"
    assert value_text("library", None) == "Sin clasificar"
    assert value_text("color_label", None) == "Sin color" and value_text("color_label", "red") == "Rojo"
    assert value_text("keyword", None) == "Sin palabras clave"
    assert value_text("rating", 0) == "Sin valoración" and value_text("rating", 3) == "★★★"
    assert value_text("flag", 0) == "Sin marca" and value_text("flag", -1) == "Rechazada"
    assert value_text("has_gps", 1) == "Sí" and value_text("is_missing", 0) == "No"
    assert value_text("media_type", "video") == "Vídeo"
    assert value_text("iso", 100) == "ISO 100" and value_text("f_number", 1.78) == "f/1,78"
    assert value_text("f_number", 2.8) == "f/2,8" and value_text("focal_length", 26.0) == "26 mm"
    assert value_text("exposure_time", 1 / 121) == "1/121 s"
    assert value_text("captured_at", "2024") == "2024" and value_text("captured_at", "2024-06") == "Junio"
    assert value_text("captured_at", "2024-06-15") == "15 - sábado"

    emitted: list[Any] = []
    requests: list[str] = []
    column = MetadataColumnWidget()
    column.values_changed.connect(emitted.append)
    column.field_requested.connect(requests.append)
    column.add_requested.connect(lambda: requests.append("add"))
    column.remove_requested.connect(lambda: requests.append("remove"))

    # 2. Campo y valores: «Todo (N)» con el total; lo elegido que no aparece, atenuado
    column.set_field("city")
    assert column._field_button.text() == "Ciudad ▾" and column._tree.topLevelItemCount() == 0
    city = MetadataValues("city", 317, (
        MetadataValue("Boltaña", 14), MetadataValue("Huesca", 4), MetadataValue("Pau", 0),
        MetadataValue(None, 2),
    ))  # fmt: skip
    column.set_values(city, {"Pau"})
    texts = [(column._tree.topLevelItem(i).text(0), column._tree.topLevelItem(i).text(1))
             for i in range(column._tree.topLevelItemCount())]
    assert texts == [("Todo (2)", "317"), ("Boltaña", "14"), ("Huesca", "4"), ("Pau", "0"),
                     ("Desconocido", "2")], texts
    assert [i.text(0) for i in column._tree.selectedItems()] == ["Pau"] and not emitted
    dim = column._tree.topLevelItem(3).foreground(0).color().name()
    assert dim == QColor(_EMPTY_COLOR).name()
    assert not column._tree.rootIsDecorated()

    # 3. Elegir: uno, otro más (Ctrl), «Todo» (vacía), quitar el último (vuelve a «Todo»)
    def item(text: str) -> QTreeWidgetItem:
        return next(i for i in column._items() if i.text(0) == text)

    flags = QItemSelectionModel.SelectionFlag
    model = column._tree.selectionModel()
    model.select(column._tree.indexFromItem(item("Huesca")), flags.ClearAndSelect | flags.Rows)
    assert emitted[-1] == {"Huesca"}
    model.select(column._tree.indexFromItem(item("Desconocido")), flags.Select | flags.Rows)
    assert emitted[-1] == {"Huesca", None}
    model.select(column._tree.indexFromItem(item("Todo (2)")), flags.Select | flags.Rows)
    assert emitted[-1] == frozenset() and [i.text(0) for i in column._tree.selectedItems()] == ["Todo (2)"]
    model.select(column._tree.indexFromItem(item("Boltaña")), flags.ClearAndSelect | flags.Rows)
    model.select(column._tree.indexFromItem(item("Boltaña")), flags.Deselect | flags.Rows)
    assert emitted[-2:] == [{"Boltaña"}, frozenset()] and item("Todo (2)").isSelected()
    count = len(emitted)
    model.select(column._tree.indexFromItem(item("Todo (2)")), flags.ClearAndSelect | flags.Rows)
    assert len(emitted) == count  # ya estaba en «Todo»: no avisa
    # Una respuesta de otro campo (llega tarde): no cambia nada
    column.set_values(MetadataValues("country", 1, (MetadataValue("España", 1),)))
    assert item("Boltaña") is not None

    # 4. Fechas: árbol; lo elegido, a la vista; lo desplegado se mantiene al recargar
    column.set_field("captured_at")
    assert column._tree.rootIsDecorated() and column.chosen == frozenset()
    june = MetadataValue("2024-06", 2, (MetadataValue("2024-06-15", 1), MetadataValue("2024-06-20", 1)))
    dates = MetadataValues("captured_at", 5, (
        MetadataValue("2024", 2, (june,)),
        MetadataValue("2023", 1, (MetadataValue("2023-01", 1, (MetadataValue("2023-01-02", 1),)),)),
        MetadataValue(None, 2),
    ))  # fmt: skip
    column.set_values(dates, {"2024-06-20"})
    assert item("2024").isExpanded() and item("Junio").isExpanded() and not item("2023").isExpanded()
    assert [i.text(0) for i in column._tree.selectedItems()] == ["20 - jueves"]
    item("2023").setExpanded(True)
    column.set_values(dates, {"2024-06-20"})
    assert item("2023").isExpanded()

    # 5. Menú de campos: solo los grupos del módulo; elegir uno lo pide
    column.set_media_types(("photo", "video"))
    groups = [a.text() for a in column._field_menu.actions()]
    assert groups == ["Estándar", "Imagen"], groups
    column.set_media_types(("photo", "video", "audio", "track"))
    assert [a.text() for a in column._field_menu.actions()][-1] == "Tracks GPS"
    image = next(a.menu() for a in column._field_menu.actions() if a.text() == "Imagen")
    lens = next(a for a in image.actions() if a.data() == "lens_model")
    lens.trigger()
    assert requests == ["lens_model"] and column.field == "captured_at"
    standard = column._field_menu.actions()[0].menu()
    assert next(a for a in standard.actions() if a.data() == "captured_at").isChecked()
    try:
        column.set_field("file_name")
        raise AssertionError("debía rechazar un campo que no es columna")
    except ValueError:
        pass

    # 6. Engranaje: añadir y quitar (los activa quien la usa)
    column.set_can_remove(False)
    assert not column._remove_action.isEnabled() and column._add_action.isEnabled()
    column._add_action.trigger()
    column.set_can_remove(True)
    column._remove_action.trigger()
    assert requests[-2:] == ["add", "remove"]

    # 7. Nada coge el foco
    assert column._tree.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert column._field_button.focusPolicy() == Qt.FocusPolicy.NoFocus
    column.deleteLater()
    print("Autoprueba finalizada correctamente.")

    if "--ventana" in sys.argv:
        # Vista de ejemplo: tres columnas con el tema; lo que se pide sale por la consola
        import resources.recursos_rc  # noqa: F401 - los iconos (:/img/...)
        from ui_helpers.helpers.ui_theme import GRID_BG, apply_theme

        apply_theme()
        window = QWidget()
        window.setWindowTitle("Columnas de «Metadatos» (ejemplo)")
        window.setObjectName("demo_metadata_columns")
        window.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        window.setStyleSheet(f"QWidget#demo_metadata_columns {{ background-color: {GRID_BG}; }}")
        row = QHBoxLayout(window)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)
        rating = MetadataValues("rating", 317, (
            MetadataValue(3, 20), MetadataValue(5, 4), MetadataValue(0, 293),
        ))  # fmt: skip
        for key, values, chosen in (("captured_at", dates, {"2024-06-20"}),
                                    ("city", city, {"Pau"}), ("rating", rating, set())):
            demo = MetadataColumnWidget(window)
            demo.set_media_types(("photo", "video"))
            demo.set_field(key)
            demo.set_values(values, chosen)
            demo.values_changed.connect(lambda v, k=key: print(k, "->", sorted(map(str, v))))
            demo.field_requested.connect(lambda k: print("Otro campo:", k))
            demo.add_requested.connect(lambda: print("Añadir columna"))
            demo.remove_requested.connect(lambda: print("Quitar esta columna"))
            row.addWidget(demo, 1)
        window.resize(900, 260)
        window.show()
        app.exec()
