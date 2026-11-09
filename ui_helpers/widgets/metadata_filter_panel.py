"""Panel «Metadatos» de la barra de filtros: de 1 a 6 columnas, como en Lightroom.

    ┌ Fecha de captura ▾   ⚙ │ Modelo de la cámara ▾   ⚙ │ Objetivo ▾          ⚙ ┐
    │ Todo (3)           317 │ Todo (2)              317 │ Todo (4)          317 │
    │ ▸ 2024             300 │ EOS R5                 40 │ RF 24-70           38 │
    │ ...                    │ ...                       │ ...                   │
    └─────────────────────── borde inferior: se arrastra para cambiar el alto ──────┘

Las columnas ('MetadataColumnWidget') se reparten el ancho a partes iguales, separadas por
una raya fina. Cada una filtra con lo elegido en ella, y su lista cuenta sobre lo que dejan
las de su izquierda (la cascada; los recuentos los pide quien lo usa).

Solo muestra y avisa: no consulta la base de datos.
    - Lo que se ve lo pone 'set_filter' (un 'MetadataFilter' de 'core/catalog/grid_filter.py')
      y los valores de cada columna, 'set_column_values', sin emitir nada.
    - Cada cambio del usuario (elegir valores, otro campo, añadir o quitar una columna) se
      aplica en el acto y se avisa con 'metadata_filter_changed(MetadataFilter)'. Qué
      columnas hay que volver a contar lo dice 'columns_to_refresh(antes, después)'.
    - El alto se cambia arrastrando el borde inferior (como los separadores de las barras
      laterales: el cursor cambia y, con el ratón encima, una raya en el acento); al
      soltar, 'height_changed(alto)'. Se pone con 'set_panel_height'. Entre 'MIN_HEIGHT' y
      la mitad del alto de la ventana.

«Añadir columna» pone, a la derecha de la que se pulsa, el primer campo que no esté ya en
otra columna (de los que ofrece el módulo, 'set_media_types'). Con 6 columnas no se puede
añadir; con una, no se puede quitar.

Uso (lo crea el controlador principal y se lo pasa al de los filtros):
    panel = MetadataFilterPanel(parent)
    panel.set_media_types(("photo", "video"))
    panel.set_filter(MetadataFilter.from_fields(("captured_at", "camera_model", "lens_model")))
    panel.set_column_values(0, fetch_metadata_values(...))
    panel.metadata_filter_changed.connect(...)

1.0.2 Alto fijo también en su política de tamaño: sus columnas se estiran en vertical y,
      sin esto, Qt daba por «estirable» toda la franja de filtros y le repartía parte del
      sitio de la cuadrícula (hueco por encima y por debajo del panel; lo vio el autor).
1.0.1 El límite de la mitad de la ventana solo se aplica con la ventana a la vista (al
      arrancar aún no tiene su tamaño y recortaría el alto guardado); 'set_media_types'
      no rehace los menús si los tipos no cambian (se llama en cada cambio del filtro).
1.0.0 Primera versión (paso A.3, «Metadatos», subpaso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.metadata_filter_panel
Vista de ejemplo (abre una ventana y espera a que se cierre): el panel sobre un catálogo
de ejemplo en memoria, con la cascada funcionando
    python -m ui_helpers.widgets.metadata_filter_panel --ventana
"""

__version__ = "1.0.2"
__all__ = [
    "DEFAULT_HEIGHT",
    "GRIP_HEIGHT",
    "MIN_HEIGHT",
    "MetadataFilterPanel",
    "columns_to_refresh",
]

# Librerías estándar
from collections.abc import Iterable
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, Qt, Signal
from qtpy.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from qtpy.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.grid_filter import (
    MAX_METADATA_COLUMNS,
    MIN_METADATA_COLUMNS,
    MetadataFilter,
)
from core.catalog.metadata_values import MetadataValues
from core.catalog.smart_fields import GROUPS, browse_fields
from ui_helpers.helpers.ui_theme import COLORS
from ui_helpers.widgets.metadata_column import MetadataColumnWidget, column_separator

# --- Medidas (px lógicos) ---
DEFAULT_HEIGHT = 180  # alto de partida (cabecera y unas 7 filas)
MIN_HEIGHT = 110  # cabecera y unas 4 filas
MAX_HEIGHT_FRACTION = 0.5  # como mucho, la mitad del alto de la ventana
GRIP_HEIGHT = 5  # zona del borde inferior que se puede coger (como los separadores)

PANEL_OBJECT_NAME = "widget_metadata_panel"


def columns_to_refresh(old: MetadataFilter, new: MetadataFilter) -> range:
    """Las columnas de 'new' cuyos valores hay que volver a contar tras un cambio.

    Desde la primera que cambia: si solo cambió lo elegido en ella, las de su derecha (la
    suya no: lo que cuenta no depende de lo que elige); si cambió su campo o el número de
    columnas, también ella.
    """
    first = next(
        (i for i, (a, b) in enumerate(zip(old.columns, new.columns, strict=False)) if a != b),
        min(len(old.columns), len(new.columns)),
    )
    same_column = (
        len(old.columns) == len(new.columns)
        and first < len(new.columns)
        and old.columns[first].field == new.columns[first].field
    )
    return range(first + 1 if same_column else first, len(new.columns))


class _HeightGrip(QWidget):
    """Franja del borde inferior que se arrastra para cambiar el alto del panel."""

    def __init__(self, panel: "MetadataFilterPanel") -> None:
        super().__init__(panel)
        self._panel = panel
        self._hover = False
        self._drag_start: tuple[float, int] | None = None  # (y global, alto al empezar)
        self.setFixedHeight(GRIP_HEIGHT)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setMouseTracking(True)

    def paintEvent(self, _event: QPaintEvent) -> None:
        """Con el ratón encima (o arrastrando), una raya de 1 px en el acento, abajo."""
        if self._hover or self._drag_start is not None:
            painter = QPainter(self)
            painter.fillRect(0, self.height() - 1, self.width(), 1, QColor(COLORS.accent))
            painter.end()

    def event(self, event: QEvent) -> bool:
        """Entrar y salir con el ratón: se pinta o se borra la raya."""
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            self._hover = event.type() == QEvent.Type.Enter
            self.update()
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = (event.globalPosition().y(), self._panel.panel_height)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None:
            start_y, start_height = self._drag_start
            self._panel.set_panel_height(round(start_height + event.globalPosition().y() - start_y))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            start_height = self._drag_start[1]
            self._drag_start = None
            self.update()
            if self._panel.panel_height != start_height:
                self._panel.height_changed.emit(self._panel.panel_height)


class MetadataFilterPanel(QWidget):
    """Las columnas de «Metadatos» y el borde para cambiar el alto (ver el docstring del
    archivo).

    Signals:
        metadata_filter_changed(object): el usuario ha cambiado algo (un 'MetadataFilter').
        height_changed(int): se ha terminado de arrastrar el borde (el alto nuevo).
    """

    metadata_filter_changed = Signal(object)
    height_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(PANEL_OBJECT_NAME)
        # Alto FIJO (lo pone 'set_panel_height'). Las columnas piden estirarse en vertical y
        # Qt pasa esa petición hacia arriba aunque el alto esté fijado: sin 'Fixed', la
        # franja de filtros entera se estiraría y se llevaría parte del sitio de la cuadrícula
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._filter = MetadataFilter()
        self._media_types: tuple[str, ...] = ()
        self._columns: list[MetadataColumnWidget] = []
        self._separators: list[QFrame] = []
        self._values: list[MetadataValues | None] = []  # lo último que se mostró en cada una

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        layout.addLayout(self._row, 1)
        self._grip = _HeightGrip(self)
        layout.addWidget(self._grip)
        self.setFixedHeight(DEFAULT_HEIGHT)

    # --- Lo que se ve (sin emitir nada) -------------------------------------------------

    @property
    def metadata_filter(self) -> MetadataFilter:
        """Las columnas y lo elegido en ellas, tal como se ven."""
        return self._filter

    @property
    def panel_height(self) -> int:
        """Alto del panel (px lógicos)."""
        return self.height() if self.minimumHeight() != self.maximumHeight() else self.minimumHeight()

    def set_media_types(self, media_types: Iterable[str]) -> None:
        """Tipos del módulo: qué grupos de campos ofrece cada columna."""
        media_types = tuple(media_types)
        if media_types == self._media_types:
            return
        self._media_types = media_types
        for column in self._columns:
            column.set_media_types(self._media_types)

    def set_filter(self, metadata_filter: MetadataFilter) -> None:
        """Muestra unas columnas. Con los mismos campos solo cambia lo elegido (se conservan
        los valores que ya se veían); con otros, las columnas se vuelven a crear."""
        if metadata_filter == self._filter:
            return
        same_fields = [c.field for c in metadata_filter.columns] == [c.field for c in self._filter.columns]
        self._filter = metadata_filter
        if not same_fields:
            self._rebuild()
            return
        for index, values in enumerate(self._values):
            if values is not None:
                self._columns[index].set_values(values, metadata_filter.columns[index].values)

    def set_column_values(self, index: int, values: MetadataValues) -> None:
        """Pone los valores y recuentos de una columna (si es de otro campo, una respuesta
        que llega tarde, la columna no hace nada)."""
        if not 0 <= index < len(self._columns) or values.field != self._filter.columns[index].field:
            return
        self._values[index] = values
        self._columns[index].set_values(values, self._filter.columns[index].values)

    def set_panel_height(self, height: int) -> None:
        """Pone el alto, dentro de los límites (ver el docstring del archivo)."""
        self.setFixedHeight(max(MIN_HEIGHT, min(height, self._max_height())))

    def _max_height(self) -> int:
        """La mitad del alto de la ventana (sin ventana a la vista, sin límite: al
        arrancar aún no tiene su tamaño y recortaría el alto guardado)."""
        window = self.window()
        if window is self or not window.isVisible():
            return 10_000
        return max(MIN_HEIGHT, int(window.height() * MAX_HEIGHT_FRACTION))

    # --- Columnas -------------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Vuelve a crear las columnas del filtro (sin valores hasta 'set_column_values')."""
        for column in self._columns:
            column.deleteLater()
        self._columns = [self._new_column(c.field) for c in self._filter.columns]
        self._values = [None] * len(self._columns)
        self._relayout()

    def _new_column(self, field_key: str) -> MetadataColumnWidget:
        column = MetadataColumnWidget(self)
        column.set_media_types(self._media_types)
        column.set_field(field_key)
        column.values_changed.connect(lambda chosen, c=column: self._on_values_changed(c, chosen))
        column.field_requested.connect(lambda key, c=column: self._on_field_requested(c, key))
        column.add_requested.connect(lambda c=column: self._on_add_requested(c))
        column.remove_requested.connect(lambda c=column: self._on_remove_requested(c))
        return column

    def _relayout(self) -> None:
        """Pone las columnas en su orden, con una raya entre cada dos, y activa «Añadir» y
        «Quitar» según cuántas hay."""
        while self._row.count():
            self._row.takeAt(0)
        for separator in self._separators:
            separator.deleteLater()
        self._separators = []
        for index, column in enumerate(self._columns):
            if index:
                separator = column_separator(self)
                self._separators.append(separator)
                self._row.addWidget(separator)
            self._row.addWidget(column, 1)
            column.set_can_add(len(self._columns) < MAX_METADATA_COLUMNS)
            column.set_can_remove(len(self._columns) > MIN_METADATA_COLUMNS)

    def _offered_fields(self) -> list[str]:
        """Campos que ofrecen las columnas en este módulo, en el orden del menú."""
        groups = [g.key for g in GROUPS if not g.media_types or set(g.media_types) & set(self._media_types)]
        return [spec.key for group in groups for spec in browse_fields(group)]

    def _emit(self, metadata_filter: MetadataFilter) -> None:
        self._filter = metadata_filter
        self.metadata_filter_changed.emit(metadata_filter)

    def _on_values_changed(self, column: MetadataColumnWidget, chosen: Any) -> None:
        """Lo elegido en una columna (la columna ya lo muestra)."""
        self._emit(self._filter.with_values(self._columns.index(column), chosen))

    def _on_field_requested(self, column: MetadataColumnWidget, field_key: str) -> None:
        """Otro campo en una columna: se vacía hasta que lleguen sus valores."""
        index = self._columns.index(column)
        column.set_field(field_key)
        self._values[index] = None
        self._emit(self._filter.with_field(index, field_key))

    def _on_add_requested(self, column: MetadataColumnWidget) -> None:
        """Una columna nueva a la derecha, con el primer campo que no esté ya en otra."""
        if len(self._columns) >= MAX_METADATA_COLUMNS:
            return
        index = self._columns.index(column)
        used = {c.field for c in self._filter.columns}
        offered = self._offered_fields()
        field_key = next((key for key in offered if key not in used), offered[0])
        self._columns.insert(index + 1, self._new_column(field_key))
        self._values.insert(index + 1, None)
        self._relayout()
        self._emit(self._filter.with_column_added(index, field_key))

    def _on_remove_requested(self, column: MetadataColumnWidget) -> None:
        """Quita una columna (y lo elegido en ella)."""
        if len(self._columns) <= MIN_METADATA_COLUMNS:
            return
        index = self._columns.index(column)
        self._columns.pop(index).deleteLater()
        self._values.pop(index)
        self._relayout()
        self._emit(self._filter.with_column_removed(index))


def _demo_catalog() -> Any:
    """Catálogo de ejemplo en memoria para '--ventana' (fotos de un viaje inventado)."""
    import sqlite3

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")
    photos = (
        ("España", "Huesca", "Torla", "2024-06-15", "EOS R5", "RF 24-70", 3),
        ("España", "Huesca", "Torla", "2024-06-15", "EOS R5", "RF 100-400", 4),
        ("España", "Huesca", "Broto", "2024-06-16", "EOS R5", "RF 24-70", 0),
        ("España", "Huesca", "Boltaña", "2024-06-17", "iPhone 15", None, 5),
        ("España", "Zaragoza", "Zaragoza", "2024-06-20", "iPhone 15", None, 0),
        ("Francia", "Pirineos Atlánticos", "Pau", "2023-08-02", "EOS R5", "RF 24-70", 2),
        ("Francia", "Pirineos Atlánticos", "Gavarnie", "2023-08-03", "EOS R5", "RF 100-400", 0),
        ("Francia", "Altos Pirineos", "Lourdes", "2023-08-04", "iPhone 15", None, 1),
        (None, None, None, None, "EOS R5", "RF 24-70", 0),
    )
    for n, (country, region, city, day, model, lens, rating) in enumerate(photos):
        cursor = db.execute(
            "INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type, "
            "mime_type, file_size, file_mtime_ns, title, country, region, city, "
            "content_created_at, rating, file_extension) VALUES (1, ?, ?, 'photo', 'image/jpeg', "
            "1, 0, ?, ?, ?, ?, ?, ?, ?)",
            (f"{n}.jpg", f"{n}.jpg", f"{n}.jpg", country, region, city,
             f"{day} 10:00:00" if day else None, rating, "heic" if model == "iPhone 15" else "jpg"),
        )
        db.execute(
            "INSERT INTO photo_details(media_id, camera_model, lens_model) VALUES (?, ?, ?)",
            (cursor.lastrowid, model, lens),
        )
    return db


if __name__ == "__main__":
    # Autoprueba (sin ventana). Ejecutar desde la raíz:
    #   python -m ui_helpers.widgets.metadata_filter_panel
    import sys

    from qtpy.QtCore import QCoreApplication, QPointF
    from qtpy.QtWidgets import QApplication

    from core.catalog.metadata_values import MetadataValue

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Qué columnas hay que volver a contar
    three = MetadataFilter.from_fields(("country", "city", "lens_model"))
    assert columns_to_refresh(three, three) == range(3, 3)
    assert columns_to_refresh(three, three.with_values(0, ["España"])) == range(1, 3)
    assert columns_to_refresh(three, three.with_field(1, "region")) == range(1, 3)
    assert columns_to_refresh(three, three.with_column_added(0, "iso")) == range(1, 4)
    assert columns_to_refresh(three, three.with_column_removed(0)) == range(2)
    assert columns_to_refresh(three, three.with_column_removed(2)) == range(2, 2)

    holder = QWidget()
    holder.resize(900, 800)
    panel = MetadataFilterPanel(holder)
    changes: list[MetadataFilter] = []
    heights: list[int] = []
    panel.metadata_filter_changed.connect(changes.append)
    panel.height_changed.connect(heights.append)

    def fields() -> list[str]:
        return [column.field for column in panel._columns]

    def flush() -> None:
        """Borra de verdad lo que se pidió borrar con 'deleteLater'."""
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    # 2. Columnas: las del filtro, con una raya entre cada dos
    panel.set_media_types(("photo", "video"))
    start = MetadataFilter.from_fields(("captured_at", "camera_model", "lens_model"))
    panel.set_filter(start)
    assert fields() == ["captured_at", "camera_model", "lens_model"] and len(panel._separators) == 2
    assert panel._row.count() == 5 and not changes
    assert not panel.sizePolicy().expandingDirections() & Qt.Orientation.Vertical
    first_columns = list(panel._columns)
    panel.set_filter(start)  # el mismo filtro: no se vuelven a crear
    assert panel._columns == first_columns

    # 3. Valores: solo si son del campo de la columna
    models = MetadataValues("camera_model", 9, (MetadataValue("EOS R5", 6), MetadataValue("iPhone 15", 3)))
    panel.set_column_values(1, models)
    panel.set_column_values(2, models)  # de otro campo: no se pone
    panel.set_column_values(7, models)  # una columna que no existe: nada
    assert panel._values == [None, models, None]
    assert panel._columns[1]._tree.topLevelItemCount() == 3

    # 4. Lo que hace el usuario se aplica y se avisa
    panel._columns[1].values_changed.emit(frozenset({"EOS R5"}))
    assert changes[-1] == start.with_values(1, ["EOS R5"]) == panel.metadata_filter
    panel._columns[0].field_requested.emit("city")
    assert fields()[0] == "city" and changes[-1].columns[0].field == "city"
    panel._columns[0].add_requested.emit()  # el primer campo que no está: «Extensión»
    assert fields() == ["city", "file_extension", "camera_model", "lens_model"]
    assert len(panel._separators) == 3 and panel._values == [None, None, models, None]
    assert changes[-1].columns[2].values == {"EOS R5"}  # lo elegido sigue en su columna
    while len(panel._columns) < MAX_METADATA_COLUMNS:
        panel._columns[-1].add_requested.emit()
    assert all(not c._add_action.isEnabled() for c in panel._columns)
    panel._columns[0].add_requested.emit()  # con 6, no hace nada
    assert len(panel._columns) == MAX_METADATA_COLUMNS
    while len(panel._columns) > MIN_METADATA_COLUMNS:
        panel._columns[0].remove_requested.emit()
    assert fields() == [changes[-1].columns[0].field] and not panel._separators
    assert not panel._columns[0]._remove_action.isEnabled()
    panel._columns[0].remove_requested.emit()  # la única: no se quita
    assert len(panel._columns) == 1
    flush()
    assert len(panel.findChildren(MetadataColumnWidget)) == 1  # las quitadas, borradas
    assert len(panel.findChildren(QFrame, "line_metadata_separator")) == 0

    # 5. 'set_filter' con los mismos campos: solo cambia lo elegido (y no avisa)
    count = len(changes)
    panel.set_filter(start)
    panel.set_column_values(1, models)
    same = list(panel._columns)
    panel.set_filter(start.with_values(1, ["iPhone 15"]))
    assert panel._columns == same and panel._columns[1].chosen == {"iPhone 15"}
    assert len(changes) == count

    # 6. Alto: dentro de los límites; arrastrar el borde lo cambia y lo avisa al soltar
    assert panel.panel_height == DEFAULT_HEIGHT
    panel.set_panel_height(20)
    assert panel.panel_height == MIN_HEIGHT
    panel.set_panel_height(5000)
    assert panel.panel_height == 5000  # sin la ventana a la vista, sin límite
    holder.isVisible = lambda: True  # como si se viera (sin abrir ninguna ventana)
    panel.set_panel_height(5000)
    assert panel.panel_height == 400  # la mitad de la ventana (800)
    panel.set_panel_height(DEFAULT_HEIGHT)

    def mouse(kind: QEvent.Type, y: float) -> None:
        buttons = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
        event = QMouseEvent(kind, QPointF(5, 2), QPointF(5, y), Qt.MouseButton.LeftButton,
                            buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(panel._grip, event)

    mouse(QEvent.Type.MouseButtonPress, 100)
    mouse(QEvent.Type.MouseMove, 160)
    assert panel.panel_height == DEFAULT_HEIGHT + 60 and not heights
    mouse(QEvent.Type.MouseButtonRelease, 160)
    assert heights == [DEFAULT_HEIGHT + 60]
    mouse(QEvent.Type.MouseButtonPress, 100)
    mouse(QEvent.Type.MouseButtonRelease, 100)  # sin moverse: no avisa
    assert heights == [DEFAULT_HEIGHT + 60]
    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")

    if "--ventana" in sys.argv:
        # Vista de ejemplo: el panel sobre un catálogo inventado, con la cascada (aquí se
        # cuenta en el hilo principal; la aplicación lo hará en segundo plano)
        import resources.recursos_rc  # noqa: F401 - los iconos (:/img/...)
        from core.catalog.grid_filter import FILTER_METADATA, GridFilter
        from core.catalog.grid_source import ALL_ITEMS
        from core.catalog.media_queries import source_condition
        from core.catalog.metadata_values import fetch_metadata_values
        from ui_helpers.helpers.ui_theme import GRID_BG, apply_theme

        apply_theme()
        db = _demo_catalog()
        window = QWidget()
        window.setWindowTitle("Panel «Metadatos» (ejemplo)")
        window.setObjectName("demo_metadata_panel")
        window.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        window.setStyleSheet(f"QWidget#demo_metadata_panel {{ background-color: {GRID_BG}; }}")
        demo_layout = QVBoxLayout(window)
        demo_layout.setContentsMargins(0, 0, 0, 0)
        demo = MetadataFilterPanel(window)
        demo_layout.addWidget(demo)
        demo_layout.addStretch(1)

        def refresh(new: MetadataFilter, old: MetadataFilter | None = None) -> None:
            grid = GridFilter(active=frozenset({FILTER_METADATA}), metadata=new)
            rows = range(len(new.columns)) if old is None else columns_to_refresh(old, new)
            for i in rows:
                column = new.columns[i]
                demo.set_column_values(i, fetch_metadata_values(
                    db, ALL_ITEMS, column.field, grid.metadata_column_filters(i), column.values))
            where, params = source_condition(ALL_ITEMS, grid.rule_sets())
            (shown,) = db.execute(f"SELECT COUNT(*) FROM media_items AS m WHERE {where}", params).fetchone()
            print(f"La cuadrícula mostraría {shown} de 9 fotos; recontadas: {list(rows)}")

        previous = [MetadataFilter.from_fields(("country", "region", "city"))]

        def on_changed(new: MetadataFilter) -> None:
            refresh(new, previous[0])
            previous[0] = new

        demo.set_media_types(("photo", "video"))
        demo.set_filter(previous[0])
        refresh(previous[0])
        demo.metadata_filter_changed.connect(on_changed)
        demo.height_changed.connect(lambda h: print("Alto nuevo:", h))
        window.resize(1000, 520)
        window.show()
        app.exec()
