"""Árbol de las barras laterales: alto ajustado al contenido y contador a la derecha.

Lo usan las secciones de la barra lateral del catálogo (Catálogo, Carpetas, Colecciones)
y lo usarán las de los demás modos (Imagen, Vídeo...). Aporta dos cosas a 'QTreeView':

    1. ALTO AJUSTADO AL CONTENIDO: no tiene barra de desplazamiento propia. Mide lo que
       ocupan sus filas visibles y crece o encoge al desplegar una carpeta. La barra de
       desplazamiento es la de la barra lateral entera (como en Lightroom, donde el panel
       completo se desplaza y no cada sección por separado). La rueda del ratón sobre el
       árbol desplaza la barra lateral.

    2. CONTADOR A LA DERECHA de cada fila ('CountDelegate'), atenuado, como los números
       de Lightroom. El nombre se recorta con "…" si no cabe, pero el número siempre se ve.

Cada fila lleva, en roles propios:
    ROLE_SOURCE  el 'GridSource' que se muestra al pulsarla (None = fila que no filtra,
                 p. ej. un conjunto de colecciones).
    ROLE_COUNT   el número de elementos (None = aún sin contar: no se pinta nada).
    ROLE_EMPHASIS  opcional: nombre en el color de acento (EMPHASIS_FULL) o en el acento
                 atenuado (EMPHASIS_PARTIAL). Lo usa el árbol con casillas del inspector
                 para las palabras con hijas asignadas («Familia» si la foto tiene «Ana»).

1.3.0 El hueco para la subclase pasa a estar ANTES del contador ('badge_width',
      'paint_badge'; antes, 'trailing_width' / 'paint_trailing', a su derecha): la flecha
      «ver sus fotos» va delante del número (lo prefirió el autor).
1.2.0 'CountDelegate.trailing_width' y 'paint_trailing': hueco a la derecha del contador
      para dibujar algo más (la flecha «ver sus fotos» del árbol de palabras del inspector).
1.1.0 Rol 'ROLE_EMPHASIS': nombre resaltado con el color de acento (paso K4c).
1.0.1 El árbol pide un ancho mínimo pequeño: al estrechar la barra lateral el contador
      seguía oculto por la derecha (el árbol pedía ~256 px y se salía del área visible).
"""

__version__ = "1.3.0"
__all__ = [
    "EMPHASIS_FULL",
    "EMPHASIS_PARTIAL",
    "ROLE_COUNT",
    "ROLE_EMPHASIS",
    "ROLE_SOURCE",
    "CountDelegate",
    "SidebarTreeView",
]

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, QRect, QSize, Qt
from qtpy.QtGui import QColor, QPainter, QPalette, QWheelEvent
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

# Roles propios de las filas de las barras laterales
ROLE_SOURCE = Qt.ItemDataRole.UserRole + 1
ROLE_COUNT = Qt.ItemDataRole.UserRole + 2
ROLE_EMPHASIS = Qt.ItemDataRole.UserRole + 3

# Valores de ROLE_EMPHASIS (sin valor o 0 = nombre normal)
EMPHASIS_PARTIAL = 1
EMPHASIS_FULL = 2
# Opacidad del acento en EMPHASIS_PARTIAL (0-255): más apagado, sobre el fondo del panel
_PARTIAL_ALPHA = 140

# Alto mínimo de cada fila (píxeles lógicos): como en Lightroom, filas algo holgadas
_MIN_ROW_HEIGHT = 22

# Ancho mínimo que pide el árbol (píxeles lógicos). Pequeño a propósito: el ancho real lo
# decide la barra lateral (ver 'SidebarTreeView.sizeHint')
_MIN_WIDTH = 60

# Separación entre el nombre y el número, y margen derecho del número
_COUNT_GAP = 8
_COUNT_RIGHT_MARGIN = 6
# Separación entre lo que una subclase dibuja delante del contador y el contador
_BADGE_GAP = 4


class CountDelegate(QStyledItemDelegate):
    """Pinta cada fila con el nombre a la izquierda y el contador (atenuado) a la derecha.

    Una subclase puede reservar 'badge_width' px justo DELANTE del contador (en las filas
    que tienen número) y dibujar ahí lo que quiera con 'paint_badge' (p. ej. una flecha).
    El nombre se recorta contando siempre con ese hueco, así no se mueve al aparecer.
    """

    # Ancho (px lógicos) que se reserva delante del contador (0 = nada)
    badge_width = 0

    def paint_badge(self, painter: QPainter, rect: QRect, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Dibuja lo de delante del contador en 'rect' (coordenadas de la vista; por
        defecto, nada)."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()

        # Zona del texto calculada CON el texto puesto (después se borra para que Qt pinte
        # solo el fondo, la selección y el icono, y el texto lo pintemos nosotros)
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        name = opt.text
        opt.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        count = index.data(ROLE_COUNT)
        count_text = "" if count is None else str(count)

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        enabled = bool(opt.state & QStyle.StateFlag.State_Enabled)
        group = QPalette.ColorGroup.Normal if enabled else QPalette.ColorGroup.Disabled
        name_role = (
            QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        )

        painter.save()
        painter.setFont(opt.font)
        metrics = opt.fontMetrics

        # 1. Contador, alineado a la derecha
        count_width = metrics.horizontalAdvance(count_text) if count_text else 0
        if count_text:
            # Atenuado salvo en la fila seleccionada (ahí se lee mejor con el color del texto)
            count_role = name_role if selected else QPalette.ColorRole.PlaceholderText
            painter.setPen(opt.palette.color(group, count_role))
            painter.drawText(
                text_rect.adjusted(0, 0, -_COUNT_RIGHT_MARGIN, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                count_text,
            )

        # 1b. Lo de delante del contador (si la subclase lo pide y hay número)
        badge = self.badge_width + _BADGE_GAP if (self.badge_width and count_text) else 0
        if badge:
            right = text_rect.right() - _COUNT_RIGHT_MARGIN - count_width - _BADGE_GAP
            rect = QRect(right - self.badge_width + 1, text_rect.top(), self.badge_width, text_rect.height())
            self.paint_badge(painter, rect, opt, index)

        # 2. Nombre, recortado con "…" para no pisar el contador. Resaltado con el color
        #    de acento ('Highlight' de la paleta del tema) si la fila lo pide
        reserved = count_width + badge + _COUNT_GAP + _COUNT_RIGHT_MARGIN if count_text else 0
        name_rect = text_rect.adjusted(2, 0, -reserved, 0)
        elided = metrics.elidedText(name, Qt.TextElideMode.ElideRight, max(0, name_rect.width()))
        name_color = opt.palette.color(group, name_role)
        emphasis = index.data(ROLE_EMPHASIS)
        if emphasis in (EMPHASIS_PARTIAL, EMPHASIS_FULL) and not selected:
            name_color = QColor(opt.palette.color(group, QPalette.ColorRole.Highlight))
            if emphasis == EMPHASIS_PARTIAL:
                name_color.setAlpha(_PARTIAL_ALPHA)
        painter.setPen(name_color)
        painter.drawText(
            name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Alto mínimo de fila (el ancho no importa: la columna ocupa todo el árbol)."""
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), _MIN_ROW_HEIGHT))


class SidebarTreeView(QTreeView):
    """'QTreeView' sin barra de desplazamiento propia, con el alto de sus filas visibles.

    Configuración para la barra lateral: sin cabecera ni marco, selección de una sola
    fila, sin edición, y el delegado del contador. Las filas se pueden desplegar (el
    árbol de carpetas) o no ('setRootIsDecorated(False)' para listas planas).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setUniformRowHeights(True)  # todas las filas miden lo mismo: más rápido
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setIndentation(14)
        self.setItemDelegate(CountDelegate(self))

        # Sin barras propias: el alto se ajusta al contenido (sizeHint) y el ancho, al de
        # la barra lateral (los nombres largos se recortan con "…")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # Al desplegar o plegar una rama cambia el número de filas visibles
        self.expanded.connect(self._update_height)
        self.collapsed.connect(self._update_height)

    # -------------------------------------------------------------------------
    # Alto ajustado al contenido
    # -------------------------------------------------------------------------

    def setModel(self, model) -> None:  # nombre de Qt
        """Asigna el modelo y vigila sus cambios (filas nuevas o borradas cambian el alto)."""
        super().setModel(model)
        if model is not None:
            model.rowsInserted.connect(self._update_height)
            model.rowsRemoved.connect(self._update_height)
            model.modelReset.connect(self._update_height)
            model.layoutChanged.connect(self._update_height)
        self._update_height()

    def _visible_row_count(self) -> int:
        """Número de filas que se ven (las de ramas plegadas no cuentan)."""
        model = self.model()
        if model is None or model.rowCount() == 0:
            return 0
        count = 0
        index = model.index(0, 0)
        while index.isValid():
            count += 1
            index = self.indexBelow(index)  # recorre solo lo desplegado
        return count

    def _content_height(self) -> int:
        """Alto de las filas visibles (+ el marco, que normalmente es 0)."""
        rows = self._visible_row_count()
        row_height = self.sizeHintForRow(0) if rows else 0
        return rows * max(row_height, _MIN_ROW_HEIGHT) + 2 * self.frameWidth()

    def sizeHint(self) -> QSize:  # nombre de Qt
        """Alto = el de las filas visibles; ancho = el mínimo (lo pone la barra lateral).

        El ancho NO puede ser el que propone 'QTreeView' (unos 256 px): la barra lateral
        está dentro de un 'QScrollArea' que no deja el contenido más estrecho que lo que
        piden sus hijos, así que al estrechar la barra el árbol se salía por la derecha y
        el contador quedaba oculto. Con un ancho mínimo pequeño, el árbol siempre ocupa
        exactamente el ancho visible y el nombre se recorta con "…".
        """
        return QSize(_MIN_WIDTH, self._content_height())

    def minimumSizeHint(self) -> QSize:  # nombre de Qt
        return QSize(_MIN_WIDTH, self._content_height())

    def _update_height(self, *_args) -> None:
        """Pide al layout que vuelva a preguntar el tamaño (ver 'sizeHint')."""
        self.updateGeometry()

    # -------------------------------------------------------------------------
    # Rueda del ratón
    # -------------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # nombre de Qt
        """La rueda no desplaza el árbol (no tiene barra): se deja pasar a la barra lateral."""
        event.ignore()
