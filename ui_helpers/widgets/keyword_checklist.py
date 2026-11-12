"""Árbol de palabras clave con casillas: marcar asigna, desmarcar quita (paso K4b).

    [Filtrar palabras clave        ]
    ▼ [■] Coche                  12
          [✓] Opel Astra          5
          [ ] Toyota Corolla      7
      [ ] Playa                  30

Lo usa el editor de palabras clave del inspector (módulo Imagen). Cada casilla dice si
LA SELECCIÓN tiene esa palabra:
    [✓] la tienen todos los seleccionados;
    [■] solo algunos (estado intermedio, como Lightroom);
    [ ] ninguno.
El número es el de la biblioteca (con sus hijas, como en la barra lateral).

Las palabras con alguna hija asignada a la selección llevan el NOMBRE en el color de acento
(«Familia» si la foto tiene «Ana»; más apagado si solo la tienen algunos de los
seleccionados) y el texto emergente «Contiene: Ana (3 de 5)». Su casilla no cambia: dice
solo si esa palabra está asignada (decidido con el autor el 04/11/2026; la casilla
intermedia ya significa «la tienen algunos» y pulsarla asigna la palabra).

Al pulsar una casilla:
    [ ] o [■]  ->  [✓]   se asigna a TODOS los seleccionados;
    [✓]        ->  [ ]   se quita de todos.
El widget no toca la base de datos: emite 'keyword_toggled(id, asignar)' y el editor lo
convierte en una petición al controlador. Cuando llegan los datos nuevos ('set_data'), el
árbol se rehace conservando lo desplegado.

Lo desplegado es PROPIO de este árbol (independiente de la barra izquierda) y se recupera
al volver a abrir: se lleva en 'ui_helpers/helpers/keyword_expansion.py' (estado
'INSPECTOR'), que el módulo Imagen guarda por catálogo. Con texto en el filtro, todo
desplegado (sin cambiar lo guardado).

Soltar tarjetas de la cuadrícula sobre una palabra (paso K4c-3, aquí desde el 04/11/2026:
la barra izquierda es para navegar y el inspector para editar): la fila de debajo se
resalta, una rama plegada se despliega si el ratón se queda encima ('DRAG_EXPAND_MS') y,
al soltar, se emite 'media_dropped(id, MediaDrag)': la sección asigna la palabra a ESAS
tarjetas (normalmente, las seleccionadas).

Flecha «ver sus fotos» (04/11/2026, idea del autor; como la de la «Lista de palabras
clave» de Lightroom): al pasar el ratón por una palabra con fotos aparece una flecha justo
DELANTE de su número (05/11/2026; antes, detrás); al pulsarla se emite 'show_keyword_requested(id)' y la cuadrícula
pasa a mostrar sus fotos (y las de sus hijas), eligiéndola en la barra izquierda: así se
navega desde donde se edita sin mezclar las dos cosas (lo elegido sigue estando a la
izquierda).

Sin selección (p. ej. al cambiar la cuadrícula con la flecha), el árbol se sigue viendo,
con las casillas vacías y sin poder pulsarlas (no hay a quién asignar); el menú, soltar
tarjetas y la flecha siguen funcionando.

Usa 'SidebarTreeView' (alto ajustado al contenido y número a la derecha): el que se
desplaza es el inspector entero, como en la barra lateral.

Aspecto: el general del tema (theme_qss.py); para darle uno propio en ui_theme.py, sus
nombres de objeto son 'edit_keyword_checklist_filter' y 'tree_keyword_checklist'.

OJO: al rehacer el árbol NO se bloquean las señales del MODELO (sí se ignoran con
'_building'): la vista se entera de que se borran y añaden filas por esas señales. Con
ellas bloqueadas, la vista seguía dibujando filas que ya no existían (huecos, alto de una
sola fila) y acababa cerrando el programa sin aviso (versión 1.0.0).

1.6.0 'filter_margin': el filtro, en su fila, con esos px a los lados; el árbol, a todo el
      ancho (como la «Lista de palabras clave» de la barra izquierda; pedido por el autor).
1.5.1 La flecha, delante del número; el clic se comprueba contra el sitio exacto donde se
      dibujó ('_KeywordDelegate.arrow_rects').
1.5.0 Flecha «ver sus fotos» ('show_keyword_requested') y árbol sin selección (casillas
      sin pulsar).
1.4.0 Soltar tarjetas de la cuadrícula sobre una palabra ('media_dropped').
1.3.0 Menú contextual para gestionar el árbol ('keyword_menu.py', señal
      'operation_requested'; paso K4c-2).
1.2.0 Antepasados de las palabras asignadas resaltados ('descendant_text', 'ROLE_EMPHASIS').
1.1.0 Lo desplegado se recuerda al cerrar y abrir ('KeywordExpansion', estado
      'INSPECTOR', guardado por el módulo Imagen); ya no se despliegan solos los padres
      de las palabras de la selección (se abre como se dejó).
1.0.1 Arreglado el cierre del programa y el dibujo del árbol: no se bloquean las señales
      del modelo al rehacerlo (ver arriba).

Prueba rápida de la lógica (sin Qt):
    python -m ui_helpers.widgets.keyword_checklist
"""

__version__ = "1.6.0"
__all__ = ["KeywordChecklist", "check_states", "descendant_text", "emphasis_level"]

# Librerías estándar
from collections.abc import Iterable

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QModelIndex, QObject, QPoint, QPointF, QRect, Qt, QTimer, Signal
from qtpy.QtGui import QBrush, QColor, QPainter, QPalette, QPen, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.keywords import KeywordTreeNode, SelectionKeywords, filter_keyword_tree
from ui_helpers.helpers.keyword_expansion import INSPECTOR, KeywordExpansion, keyword_expansion
from ui_helpers.helpers.keyword_menu import ask_keyword_operation
from ui_helpers.models.media_mime import MEDIA_IDS_MIME, decode_media_ids
from ui_helpers.widgets.sidebar_tree_view import (
    EMPHASIS_FULL,
    EMPHASIS_PARTIAL,
    ROLE_COUNT,
    ROLE_EMPHASIS,
    CountDelegate,
    SidebarTreeView,
)

# Rol propio: id de la palabra de la fila
_ROLE_KEYWORD_ID = Qt.ItemDataRole.UserRole + 41

# Estados de las casillas (los mismos valores que 'Qt.CheckState')
UNCHECKED = 0
PARTIAL = 1
CHECKED = 2


def check_states(selection: SelectionKeywords) -> dict[int, int]:
    """Estado de cada palabra de la selección: CHECKED (todos) o PARTIAL (algunos).

    Las que no aparecen están sin marcar (UNCHECKED).
    """
    return {
        keyword_id: CHECKED if count >= selection.total else PARTIAL
        for (_path, count), keyword_id in zip(selection.items, selection.keyword_ids, strict=False)
    }


# Espera (ms) con el ratón encima de una rama plegada, al arrastrar, para desplegarla
DRAG_EXPAND_MS = 700

# Nombres de hijas como mucho en el texto emergente de un padre resaltado
_MAX_DESCENDANT_NAMES = 6

# {id: (en cuántos seleccionados hay hijas, rutas de las hijas)}: 'fetch_descendant_marks'
DescendantMarks = dict[int, tuple[int, tuple[tuple[str, ...], ...]]]


def emphasis_level(count: int, total: int) -> int:
    """Resaltado de un padre: completo si TODOS los seleccionados tienen alguna hija."""
    if count <= 0:
        return 0
    return EMPHASIS_FULL if count >= total else EMPHASIS_PARTIAL


def descendant_text(count: int, total: int, paths: tuple[tuple[str, ...], ...]) -> str:
    """«Contiene: Ana, Javi (3 de 5)»: las hijas asignadas (por su nombre) y en cuántos."""
    names = [path[-1] for path in paths]
    shown = ", ".join(names[:_MAX_DESCENDANT_NAMES])
    if len(names) > _MAX_DESCENDANT_NAMES:
        shown += f" y {len(names) - _MAX_DESCENDANT_NAMES} más"
    where = f" ({count} de {total})" if total > 1 else ""
    return f"Contiene: {shown}{where}"


# Ancho (px lógicos) del hueco de la flecha «ver sus fotos», delante del número
ARROW_WIDTH = 14


class _KeywordDelegate(CountDelegate):
    """Como 'CountDelegate', con la flecha «ver sus fotos» delante del número: solo en la
    fila bajo el ratón (las palabras sin fotos no tienen número, así que tampoco flecha).
    El hueco se reserva en todas las filas con número, así el nombre no se mueve.

    Guarda dónde dibujó la flecha de cada palabra ('arrow_rects', por su id, en
    coordenadas de la vista): el clic se comprueba contra ese mismo rectángulo (su
    posición depende del ancho del número).
    """

    badge_width = ARROW_WIDTH

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.arrow_rects: dict[int, QRect] = {}

    def paint_badge(self, painter: QPainter, rect: QRect, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        keyword_id = index.data(_ROLE_KEYWORD_ID)
        if isinstance(keyword_id, int):
            self.arrow_rects[keyword_id] = QRect(rect)
        if not (option.state & QStyle.StateFlag.State_MouseOver):
            return
        # Una flecha «→» fina, en el color de acento, centrada en su hueco
        color = option.palette.color(QPalette.ColorRole.Highlight)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        center = rect.center()
        x0, x1 = center.x() - 4.5, center.x() + 4.5
        y = center.y() + 0.5
        painter.drawLine(QPointF(x0, y), QPointF(x1, y))
        painter.drawLine(QPointF(x1 - 3.5, y - 3.5), QPointF(x1, y))
        painter.drawLine(QPointF(x1 - 3.5, y + 3.5), QPointF(x1, y))
        painter.restore()


class KeywordChecklist(QWidget):
    """Filtro + árbol de palabras con casillas (ver el docstring del módulo).

    Signals:
        keyword_toggled(int, bool): el usuario ha pulsado la casilla de una palabra
            ('keywords.id'); True = asignarla a todos, False = quitarla de todos.
        operation_requested(object, object): desde el menú contextual, (función,
            argumentos) de 'keywords' para cambiar el árbol (crear, renombrar...).
        media_dropped(int, object): se han soltado tarjetas de la cuadrícula sobre una
            palabra (su id y el 'MediaDrag').
        show_keyword_requested(int): se ha pulsado la flecha «ver sus fotos» de una palabra.
    """

    show_keyword_requested = Signal(int)

    keyword_toggled = Signal(int, bool)
    operation_requested = Signal(object, object)
    media_dropped = Signal(int, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        expansion: KeywordExpansion | None = None,
        *,
        filter_margin: int = 0,
    ) -> None:
        """Crea el filtro y el árbol (vacío hasta 'set_data').

        Args:
            parent: Widget padre.
            expansion: Lo desplegado (por defecto, el estado 'INSPECTOR').
            filter_margin: px a cada lado del filtro (el árbol ocupa siempre todo el ancho).
        """
        super().__init__(parent)
        self._tree: tuple[KeywordTreeNode, ...] = ()
        self._states: dict[int, int] = {}
        self._descendants: DescendantMarks = {}
        self._total = 0  # cuántos hay seleccionados
        # Lo desplegado de este árbol (lo guarda el módulo Imagen por catálogo)
        self._expansion = expansion if expansion is not None else keyword_expansion(INSPECTOR)
        self._expansion.changed.connect(self._apply_expansion)
        self._building = False  # rehaciendo las filas: los avisos no son del usuario
        # Arrastrar tarjetas: la fila resaltada y la rama que se desplegará si se espera
        self._drop_target: QStandardItem | None = None
        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.setInterval(DRAG_EXPAND_MS)
        self._expand_timer.timeout.connect(self._expand_drop_target)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # El filtro, en su fila (con sus márgenes a los lados)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(filter_margin, 0, filter_margin, 0)
        self._filter = QLineEdit(self)
        self._filter.setObjectName("edit_keyword_checklist_filter")
        self._filter.setPlaceholderText("Filtrar palabras clave")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._rebuild)
        filter_row.addWidget(self._filter)
        layout.addLayout(filter_row)

        self._model = QStandardItemModel(self)
        self._model.itemChanged.connect(self._on_item_changed)
        self._view = SidebarTreeView(self)
        self._view.setObjectName("tree_keyword_checklist")
        self._view.setModel(self._model)
        # Aquí no se elige ninguna fila: solo se marcan casillas
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # Número y flecha «ver sus fotos» (la flecha, en la fila bajo el ratón)
        self._delegate = _KeywordDelegate(self._view)
        self._view.setItemDelegate(self._delegate)
        self._view.setMouseTracking(True)
        self._view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._view.expanded.connect(lambda index: self._on_expanded(index, True))
        self._view.collapsed.connect(lambda index: self._on_expanded(index, False))
        # Menú contextual: crear, renombrar, mover, borrar, purgar ('keyword_menu.py')
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_menu)
        # Soltar tarjetas de la cuadrícula sobre una palabra (ver 'eventFilter')
        self._view.setAcceptDrops(True)
        self._view.viewport().setAcceptDrops(True)
        self._view.viewport().installEventFilter(self)
        layout.addWidget(self._view)

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def set_data(
        self,
        tree: tuple[KeywordTreeNode, ...],
        selection: SelectionKeywords,
        descendants: DescendantMarks | None = None,
    ) -> None:
        """Árbol de la biblioteca, palabras de la selección y padres con hijas asignadas
        ('keywords.fetch_descendant_marks'): rehace las filas."""
        self._tree = tuple(tree)
        self._states = check_states(selection)
        self._descendants = dict(descendants or {})
        self._total = selection.total
        self._rebuild()

    def clear_filter(self) -> None:
        """Vacía el filtro (el árbol vuelve a como estaba)."""
        self._filter.clear()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Rehace las filas con el filtro actual y lo desplegado."""
        filtering = bool(self._filter.text().strip())
        shown = filter_keyword_tree(self._tree, self._filter.text())
        self._clear_drop_target()  # la fila resaltada va a desaparecer
        self._delegate.arrow_rects.clear()  # se vuelven a anotar al dibujar
        # Sin bloquear señales (ver el docstring del módulo): '_building' hace que los
        # avisos de las casillas y de lo desplegado se ignoren mientras tanto
        self._building = True
        try:
            self._model.clear()
            self._append_nodes(self._model.invisibleRootItem(), shown)
            if filtering:
                self._view.expandAll()
            else:
                self._apply_expansion()
        finally:
            self._building = False
        self._view.updateGeometry()

    def _append_nodes(self, parent: QStandardItem, nodes: Iterable[KeywordTreeNode]) -> None:
        """Añade las palabras (y sus hijas) bajo 'parent', con su casilla."""
        for node in nodes:
            item = QStandardItem(node.name)
            item.setEditable(False)
            # Casilla que el usuario puede pulsar; el estado intermedio solo lo pone el
            # programa (al pulsarla en ese estado, pasa a marcada: asignar a todos)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState(self._states.get(node.id, UNCHECKED)))
            if not self._total:
                # Sin selección: la casilla se ve (vacía) pero no se puede pulsar
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(node.id, _ROLE_KEYWORD_ID)
            item.setData(node.count or None, ROLE_COUNT)
            tooltip = f"{node.name}\n{node.count} en la biblioteca con esta palabra o sus hijas"
            if node.count:
                tooltip += " (la flecha de la derecha las muestra)"
            if self._states.get(node.id) == PARTIAL:
                tooltip += "\nLa tienen solo algunos de los seleccionados: marcar la asigna a todos."
            if node.id in self._descendants:
                count, paths = self._descendants[node.id]
                item.setData(emphasis_level(count, self._total), ROLE_EMPHASIS)
                tooltip += "\n" + descendant_text(count, self._total, paths)
            item.setToolTip(tooltip)
            parent.appendRow(item)
            self._append_nodes(item, node.children)

    def _apply_expansion(self) -> None:
        """Despliega y pliega las ramas como dice su estado (sin filtro)."""
        if self._filter.text().strip():
            return

        def visit(parent: QStandardItem) -> None:
            for row in range(parent.rowCount()):
                child = parent.child(row)
                if child.hasChildren():
                    expanded = self._expansion.is_expanded(child.data(_ROLE_KEYWORD_ID))
                    self._view.setExpanded(child.index(), expanded)
                    visit(child)

        visit(self._model.invisibleRootItem())

    def _on_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo que despliega o pliega el usuario (no lo que despliega el filtro)."""
        if self._building or self._filter.text().strip():
            return
        keyword_id = index.data(_ROLE_KEYWORD_ID)
        if isinstance(keyword_id, int):
            self._expansion.set_expanded(keyword_id, expanded)

    # --- Soltar tarjetas de la cuadrícula sobre una palabra ---

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # nombre de Qt
        """Arrastrar y soltar sobre el árbol (su 'viewport'): solo tarjetas de la
        cuadrícula (MEDIA_IDS_MIME), sobre cualquier palabra. Como el árbol de colecciones
        del Catálogo ('catalog_sidebar.py')."""
        if watched is not self._view.viewport():
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            # La flecha «ver sus fotos»: se atiende al soltar el botón; la pulsación y el
            # doble clic sobre ella no llegan al árbol (no despliegan ni marcan nada)
            keyword_id = self._arrow_hit(event.position().toPoint()) if event.button() == Qt.MouseButton.LeftButton else None
            if keyword_id is not None:
                if kind == QEvent.Type.MouseButtonRelease:
                    self.show_keyword_requested.emit(keyword_id)
                return True
            return super().eventFilter(watched, event)
        if kind == QEvent.Type.DragEnter:
            if event.mimeData().hasFormat(MEDIA_IDS_MIME):
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            else:
                event.ignore()
            return True
        if kind == QEvent.Type.DragMove:
            item = self._drop_item_at(event.position().toPoint())
            self._set_drop_target(item)
            if item is not None:
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            else:
                event.ignore()
            return True
        if kind == QEvent.Type.DragLeave:
            self._clear_drop_target()
            return True
        if kind == QEvent.Type.Drop:
            item = self._drop_item_at(event.position().toPoint())
            self._clear_drop_target()
            drag = decode_media_ids(event.mimeData())
            keyword_id = item.data(_ROLE_KEYWORD_ID) if item is not None else None
            if not isinstance(keyword_id, int) or drag is None:
                event.ignore()
                return True
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.media_dropped.emit(keyword_id, drag)
            return True
        return super().eventFilter(watched, event)

    def _arrow_hit(self, position: QPoint) -> int | None:
        """Id de la palabra cuya flecha está en 'position' (solo las que tienen fotos).

        Se compara con el rectángulo donde el delegado la dibujó (un poco más ancho, para
        que sea fácil de pulsar)."""
        index = self._view.indexAt(position)
        if not index.isValid() or not index.data(ROLE_COUNT):
            return None
        keyword_id = index.data(_ROLE_KEYWORD_ID)
        arrow = self._delegate.arrow_rects.get(keyword_id) if isinstance(keyword_id, int) else None
        if arrow is None:
            return None
        return keyword_id if arrow.adjusted(-2, 0, 2, 0).contains(position) else None

    def _drop_item_at(self, position: QPoint) -> QStandardItem | None:
        """La palabra bajo el ratón, o None."""
        index = self._view.indexAt(position)
        if not index.isValid() or not isinstance(index.data(_ROLE_KEYWORD_ID), int):
            return None
        return self._model.itemFromIndex(index)

    def _set_drop_target(self, item: QStandardItem | None) -> None:
        """Resalta la palabra sobre la que se soltaría; si tiene hijas plegadas, se
        desplegará al esperar un momento encima."""
        if item is self._drop_target:
            return
        self._clear_drop_target()
        if item is not None:
            highlight = QColor(self.palette().color(QPalette.ColorRole.Highlight))
            highlight.setAlpha(110)
            item.setData(QBrush(highlight), Qt.ItemDataRole.BackgroundRole)
            self._drop_target = item
            if item.hasChildren() and not self._view.isExpanded(item.index()):
                self._expand_timer.start()

    def _clear_drop_target(self) -> None:
        """Quita el resaltado (si lo había) y cancela el despliegue pendiente."""
        self._expand_timer.stop()
        if self._drop_target is not None:
            try:
                self._drop_target.setData(None, Qt.ItemDataRole.BackgroundRole)
            except RuntimeError:
                pass  # la fila ya no existe (se reconstruyó el árbol)
            self._drop_target = None

    def _expand_drop_target(self) -> None:
        """El ratón sigue encima de una rama plegada: se despliega (y se recuerda)."""
        if self._drop_target is not None:
            try:
                self._view.expand(self._drop_target.index())
            except RuntimeError:
                self._drop_target = None

    # --- Menú contextual ---

    def _show_menu(self, position: QPoint) -> None:
        """Clic derecho: el menú de la palabra pulsada (o el de un hueco)."""
        keyword_id = self._view.indexAt(position).data(_ROLE_KEYWORD_ID)
        operation = ask_keyword_operation(
            self,
            self._tree,
            keyword_id if isinstance(keyword_id, int) else None,
            self._view.viewport().mapToGlobal(position),
        )
        if operation is not None:
            self.operation_requested.emit(*operation)

    def _on_item_changed(self, item: QStandardItem) -> None:
        """El usuario ha pulsado una casilla: se pide asignar o quitar (para todos)."""
        if self._building:
            return
        keyword_id = item.data(_ROLE_KEYWORD_ID)
        if not isinstance(keyword_id, int):
            return
        state = item.checkState()
        # 'itemChanged' avisa de CUALQUIER cambio de la fila (p. ej. el resaltado al
        # arrastrar encima): solo cuenta si la casilla es distinta de la que se puso
        if int(state.value if hasattr(state, "value") else state) == self._states.get(keyword_id, UNCHECKED):
            return
        assign = state == Qt.CheckState.Checked
        # Hasta que lleguen los datos nuevos, el estado es el que se ha pedido
        self._states[keyword_id] = CHECKED if assign else UNCHECKED
        if not assign:
            self._states.pop(keyword_id, None)
        self.keyword_toggled.emit(keyword_id, assign)


if __name__ == "__main__":
    # Autoprueba de la lógica (no necesita Qt real). Desde la raíz del proyecto:
    #     python -m ui_helpers.widgets.keyword_checklist
    sel = SelectionKeywords(
        total=3, items=((("Coche", "Opel Astra"), 3), (("Playa",), 1)), keyword_ids=(11, 20)
    )
    assert check_states(sel) == {11: CHECKED, 20: PARTIAL}
    # Padres resaltados: completo si todos tienen alguna hija; texto emergente
    assert emphasis_level(3, 3) == EMPHASIS_FULL and emphasis_level(1, 3) == EMPHASIS_PARTIAL
    assert emphasis_level(0, 3) == 0
    assert descendant_text(3, 5, (("Familia", "Ana"), ("Familia", "Javi"))) == "Contiene: Ana, Javi (3 de 5)"
    assert descendant_text(1, 1, (("Familia", "Ana"),)) == "Contiene: Ana"
    many = tuple(("P", f"H{n}") for n in range(8))
    assert descendant_text(1, 1, many).endswith(" y 2 más")
    # Estado de lo desplegado: avisa solo si cambia algo; uno por árbol
    from ui_helpers.helpers.keyword_expansion import SIDEBAR
    assert keyword_expansion(INSPECTOR) is keyword_expansion(INSPECTOR)
    assert keyword_expansion(INSPECTOR) is not keyword_expansion(SIDEBAR)
    expansion = KeywordExpansion()
    calls = []
    expansion.changed.connect(lambda: calls.append(1))
    expansion.set_expanded(10, True)
    expansion.set_expanded(10, True)
    expansion.replace([10, True, "x"])  # lo raro se ignora: queda igual, sin aviso
    assert expansion.ids() == {10}, expansion.ids()
    print("Autoprueba finalizada correctamente.")
