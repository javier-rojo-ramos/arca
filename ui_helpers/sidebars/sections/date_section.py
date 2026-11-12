"""Sección «Fechas» de la barra de un módulo: la línea de tiempo (año ▸ mes ▸ día).

    ▼ FECHAS
    ▾ 2024                     412
      ▾ 01 Enero                 35
          10 Miércoles            2
          19 Viernes              1
      ▸ 02 Febrero               12
    ▸ 2023                     380
      Sin fecha                   3

    - Los años, del más reciente al más antiguo; dentro, los meses y los días con archivos,
      en el orden del calendario; «Sin fecha», al final (decidido por el autor el
      12/11/2026: ver DECISIONES.md).
    - Cada fila lleva el origen de 'timeline.date_source': al elegirla, la cuadrícula
      muestra exactamente los archivos que cuenta (lo comprueba la autoprueba de
      'core/catalog/timeline.py').
    - Sin iconos, como las palabras clave: los nombres, en la columna de las flechas de las
      subcarpetas ('TEXT_NAME_INDENT').
    - Lo desplegado (años y meses) se guarda por catálogo en 'expanded_dates'. La primera
      vez, todo plegado: solo se ven los años.

Uso (lo hace la barra, p. ej. 'ImageSidebar'; ver 'tree_section.py'):
    dates = DateSection("image", parent)
    dates.set_tree(fetch_timeline(conn, "image").values)   # lo lee el módulo

1.0.0 Primera versión (paso A.4, sección «Fechas» del módulo Imagen).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.sidebars.sections.date_section
"""

__version__ = "1.0.0"
__all__ = ["DateSection", "date_label", "date_tooltip"]

# Librerías estándar
from datetime import date

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, Qt
from qtpy.QtGui import QStandardItem, QStandardItemModel
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.grid_source import GridSource
from core.catalog.metadata_values import MetadataValue
from core.catalog.timeline import NO_DATE, date_source, is_date_source
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.inspector.formatting import MONTH_NAMES, WEEKDAY_NAMES
from ui_helpers.sidebars.sections.tree_section import TEXT_NAME_INDENT, TreeSection, make_item
from ui_helpers.widgets.sidebar_tree_view import ROLE_SOURCE, SidebarTreeView

# Textos de la interfaz
NO_DATE_TEXT = "Sin fecha"
NO_DATE_TOOLTIP = (
    "Sin fecha de captura: archivos cuyos metadatos aún no se han leído\n"
    "o en los que no se ha podido leer ninguna fecha."
)

# Rol propio: valor de la fila ('AAAA', 'AAAA-MM'...), para recordar lo desplegado
_ROLE_DATE = Qt.ItemDataRole.UserRole + 45


def date_label(value: str | None) -> str:
    """El texto de una fila: '2024', '01 Enero', '01 Martes' o «Sin fecha»."""
    if value is NO_DATE:
        return NO_DATE_TEXT
    if len(value) == 7:
        return f"{value[5:]} {MONTH_NAMES[int(value[5:]) - 1]}"
    if len(value) == 10:
        return f"{value[8:]} {WEEKDAY_NAMES[date.fromisoformat(value).weekday()]}"
    return value


def date_tooltip(value: str | None) -> str:
    """El texto emergente: la fecha completa ('Martes, 1 de enero de 2024'), el mes con su
    año ('Enero de 2024'), el año o qué es «Sin fecha»."""
    if value is NO_DATE:
        return NO_DATE_TOOLTIP
    if len(value) == 7:
        return f"{MONTH_NAMES[int(value[5:]) - 1]} de {value[:4]}"
    if len(value) == 10:
        day = date.fromisoformat(value)
        month = MONTH_NAMES[day.month - 1].lower()
        return f"{WEEKDAY_NAMES[day.weekday()]}, {day.day} de {month} de {day.year}"
    return value


class DateSection(TreeSection):
    """Años, meses y días con archivos de una biblioteca (ver el docstring del módulo)."""

    def __init__(self, library: str, parent: QWidget | None = None) -> None:
        """Crea la sección vacía.

        Args:
            library: Biblioteca del módulo ('image'...).
            parent: Widget padre.
        """
        super().__init__(parent)
        self._library = library
        self._tree: tuple[MetadataValue, ...] = ()
        self._expanded: set[str] = set()  # años y meses desplegados ('2024', '2024-01')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._model = QStandardItemModel(self)
        self._view = SidebarTreeView(self, name_indent=TEXT_NAME_INDENT)
        self._view.setModel(self._model)
        self._view.expanded.connect(lambda index: self._on_expanded(index, True))
        self._view.collapsed.connect(lambda index: self._on_expanded(index, False))
        layout.addWidget(self._view)

    # -------------------------------------------------------------------------
    # Datos (los pone la barra)
    # -------------------------------------------------------------------------

    def set_tree(self, values: tuple[MetadataValue, ...]) -> None:
        """Pone los años con sus meses y días ('fetch_timeline(...).values'); no hace nada
        si no han cambiado."""
        values = tuple(values)
        if values == self._tree and self._model.rowCount() > 0:
            return
        self._tree = values
        self._rebuild()

    # -------------------------------------------------------------------------
    # 'TreeSection'
    # -------------------------------------------------------------------------

    def views(self) -> tuple[SidebarTreeView, ...]:
        return (self._view,)

    def find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de un año, un mes, un día o «Sin fecha» (por su origen)."""
        if not is_date_source(source, self._library):
            return None

        def search(parent: QStandardItem) -> QStandardItem | None:
            for row in range(parent.rowCount()):
                child = parent.child(row)
                if child.data(ROLE_SOURCE) == source:
                    return child
                found = search(child)
                if found is not None:
                    return found
            return None

        return search(self._model.invisibleRootItem())

    def owns(self, source: GridSource) -> bool:
        return is_date_source(source, self._library)

    def save_state(self) -> dict:
        return {"expanded_dates": sorted(self._expanded)}

    def restore_state(self, state: dict) -> None:
        expanded = state.get("expanded_dates")
        if isinstance(expanded, list):
            self._expanded = {value for value in expanded if isinstance(value, str)}
            self._apply_expanded()

    def reset(self) -> None:
        self._tree = ()
        self._expanded.clear()
        self._rebuild()

    # -------------------------------------------------------------------------
    # Árbol
    # -------------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Rehace el árbol conservando lo desplegado; después, 'rebuilt' (la barra vuelve a
        marcar la fila elegida).

        No se bloquean las señales del MODELO (ver TRAMPAS.md): solo las de la vista (lo
        desplegado por código no se anota) y las de su selección.
        """
        view, model = self._view, self._model
        with _blocked(view.selectionModel(), view):
            model.clear()
            self._append(model.invisibleRootItem(), self._tree)
            self._apply_expanded()
        view.updateGeometry()
        self.rebuilt.emit()

    def _append(self, parent: QStandardItem, values: tuple[MetadataValue, ...]) -> None:
        """Añade las filas (y, dentro, sus meses o sus días) bajo 'parent'."""
        for value in values:
            item = make_item(
                date_label(value.value), date_source(self._library, value.value), value.count
            )
            item.setData(value.value, _ROLE_DATE)
            item.setToolTip(date_tooltip(value.value))
            parent.appendRow(item)
            self._append(item, value.children)

    def _apply_expanded(self) -> None:
        """Despliega los años y meses de '_expanded' y pliega los demás."""
        with _blocked(self._view):

            def visit(parent: QStandardItem) -> None:
                for row in range(parent.rowCount()):
                    child = parent.child(row)
                    if child.hasChildren():
                        expanded = child.data(_ROLE_DATE) in self._expanded
                        self._view.setExpanded(child.index(), expanded)
                        visit(child)

            visit(self._model.invisibleRootItem())
        self._view.updateGeometry()

    def _on_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo que despliega o pliega el usuario."""
        value = index.data(_ROLE_DATE)
        if isinstance(value, str):
            (self._expanded.add if expanded else self._expanded.discard)(value)


if __name__ == "__main__":
    # Autoprueba (sin ventana). Ejecutar desde la raíz:
    #   python -m ui_helpers.sidebars.sections.date_section
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Textos (el 1 de enero de 2024 fue lunes)
    assert date_label("2024") == "2024" and date_label(NO_DATE) == "Sin fecha"
    assert date_label("2024-01") == "01 Enero" and date_label("2024-11") == "11 Noviembre"
    assert date_label("2024-01-01") == "01 Lunes" and date_label("2024-01-10") == "10 Miércoles"
    assert date_tooltip("2024-01-10") == "Miércoles, 10 de enero de 2024"
    assert date_tooltip("2024-02") == "Febrero de 2024" and date_tooltip("2024") == "2024"

    # 2. El árbol: filas, números y orígenes
    tree = (
        MetadataValue("2024", 4, (
            MetadataValue("2024-01", 3, (
                MetadataValue("2024-01-10", 2), MetadataValue("2024-01-19", 1))),
            MetadataValue("2024-02", 1, (MetadataValue("2024-02-11", 1),)),
        )),
        MetadataValue("2023", 1, (MetadataValue("2023-12", 1, (MetadataValue("2023-12-31", 1),)),)),
        MetadataValue(NO_DATE, 2),
    )  # fmt: skip
    section = DateSection("image")
    rebuilt: list[bool] = []
    section.rebuilt.connect(lambda: rebuilt.append(True))
    section.set_tree(tree)
    model = section._model
    assert [model.item(r).text() for r in range(model.rowCount())] == ["2024", "2023", "Sin fecha"]
    january = model.item(0).child(0)
    assert january.text() == "01 Enero" and january.child(1).text() == "19 Viernes"
    day_source = date_source("image", "2024-01-19")
    assert section.find_item(day_source) is january.child(1) and section.owns(day_source)
    assert section.find_item(date_source("image", NO_DATE)) is model.item(2)
    assert section.find_item(date_source("video", "2024")) is None  # de otra biblioteca
    assert not section.owns(date_source("video", "2024"))
    assert rebuilt == [True]
    section.set_tree(tree)  # lo mismo: no se rehace
    assert rebuilt == [True]

    # 3. Lo desplegado: al principio, nada; se guarda, se recupera y sobrevive al rehacer
    view = section._view
    assert not view.isExpanded(model.item(0).index())
    view.setExpanded(model.item(0).index(), True)  # como el usuario
    view.setExpanded(january.index(), True)
    assert section.save_state() == {"expanded_dates": ["2024", "2024-01"]}
    section.set_tree(tree[1:])  # otro árbol (sin 2024): lo desplegado se conserva
    section.set_tree(tree)
    assert view.isExpanded(model.item(0).index()) and view.isExpanded(model.item(0).child(0).index())
    section.restore_state({"expanded_dates": ["2023", 5]})  # lo que no es texto se ignora
    assert not view.isExpanded(model.item(0).index()) and view.isExpanded(model.item(1).index())
    section.reset()
    assert model.rowCount() == 0 and section.save_state() == {"expanded_dates": []}
    print("Autoprueba finalizada correctamente.")
