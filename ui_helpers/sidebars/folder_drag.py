"""Arrastrar una carpeta del árbol de «Carpetas» y ayudas al arrastrar algo sobre él (CAT 4.4c).

Lo usa 'CatalogSidebar' en su árbol de «Carpetas». Hace tres cosas:

    1. EMPEZAR A ARRASTRAR UNA CARPETA: al pulsar sobre una fila que se puede mover (lo
       decide 'can_drag', de la barra) y mover el ratón más que la distancia de arrastre
       del sistema, empieza un 'QDrag' con el formato FOLDER_MIME y la imagen de la fila.
       Al pulsar, la fila queda elegida, como con un clic (eso lo hace Qt).
    2. DESPLAZAR LA BARRA LATERAL mientras se arrastra algo (una carpeta o tarjetas) cerca
       del borde de arriba o de abajo de lo que se ve: el árbol no tiene barra de
       desplazamiento propia ('SidebarTreeView'), así que se desplaza el 'QScrollArea' que
       lo contiene. Sigue mientras el ratón esté quieto en el borde (con un temporizador:
       sin moverlo no llegan eventos).
    3. DESPLEGAR UNA CARPETA plegada al pararse encima un momento (AUTO_EXPAND_MS).

Soltar es cosa de la barra: su 'eventFilter' recibe los eventos de arrastre del árbol, le
pasa a este ayudante 'drag_moved' y 'drag_stopped', y decide dónde se puede soltar. Una
carpeta solo se suelta en la misma aplicación que la arrastra: la barra usa 'active' (lo
que se arrastra ahora en esta), no el contenido del formato, porque con dos ventanas de la
aplicación (dos catálogos) la ubicación de una no significa nada en la otra.

Uso:
    drag = FolderTreeDrag(view, can_drag=lambda index: FolderDrag(...) or None, parent=self)
    # en el 'eventFilter' de la barra, sobre el 'viewport' del árbol:
    drag.drag_moved(position)       # DragMove (también con tarjetas)
    drag.drag_stopped()             # DragLeave y Drop
    drag.active                     # la carpeta que se arrastra (None si no es una carpeta)
    drag.scrolled.connect(...)      # la barra se ha desplazado: volver a mirar el destino

1.0.0 Primera versión (CAT 4.4c).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m ui_helpers.sidebars.folder_drag
"""

__version__ = "1.0.0"
__all__ = [
    "AUTO_EXPAND_MS",
    "FOLDER_MIME",
    "FolderDrag",
    "FolderTreeDrag",
]

# Librerías estándar
import json
from collections.abc import Callable
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtCore import (
    QByteArray,
    QEvent,
    QMimeData,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    Qt,
    QTimer,
    Signal,
)
from qtpy.QtGui import QDrag
from qtpy.QtWidgets import QAbstractScrollArea, QApplication, QTreeView, QWidget

# Tipo MIME propio de una carpeta arrastrada (el prefijo 'application/x-': no estándar)
FOLDER_MIME = "application/x-arca-folder"

# Tiempo parado sobre una carpeta plegada hasta que se despliega (el de Qt, 'autoExpandDelay',
# no sirve: la barra atiende ella misma los eventos de arrastre)
AUTO_EXPAND_MS = 700
# Desplazar la barra lateral: a cuántos px del borde de lo que se ve, cuánto en cada paso y
# cada cuánto (unos 270 px por segundo)
SCROLL_MARGIN = 24
SCROLL_STEP = 8
SCROLL_INTERVAL_MS = 30


@dataclass(frozen=True, slots=True)
class FolderDrag:
    """La carpeta que se arrastra.

    Attributes:
        location_id: Su ubicación ('storage_locations.id').
        folder: Su ruta, relativa a la ubicación, con '/'.
        name: El nombre que se ve en el árbol (para los textos).
        has_subfolders: Si en el árbol tiene subcarpetas (para la confirmación).
    """

    location_id: int
    folder: str
    name: str
    has_subfolders: bool = False


class FolderTreeDrag(QObject):
    """Empieza el arrastre de una carpeta y desplaza o despliega mientras se arrastra.

    Signals:
        scrolled(QPoint): la barra lateral se ha desplazado sola; lleva dónde está ahora el
            ratón en el 'viewport' del árbol (lo que hay debajo ha cambiado).
    """

    scrolled = Signal(QPoint)

    def __init__(
        self,
        view: QTreeView,
        *,
        can_drag: Callable[[QModelIndex], FolderDrag | None],
        parent: QObject | None = None,
    ) -> None:
        """Vigila el ratón sobre el árbol.

        Args:
            view: El árbol de carpetas.
            can_drag: Dice si una fila se puede arrastrar y, si sí, qué carpeta es.
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._view = view
        self._can_drag = can_drag
        self.active: FolderDrag | None = None
        # Al pulsar sobre una fila que se puede arrastrar: dónde, cuál y qué carpeta
        self._pressed: tuple[QPoint, QPersistentModelIndex, FolderDrag] | None = None
        # Mientras se arrastra: la fila de debajo (para desplegarla) y el ratón, en el
        # 'viewport' de la barra lateral (ahí no se mueve al desplazarla)
        self._hover = QPersistentModelIndex()
        self._cursor: QPoint | None = None
        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.setInterval(AUTO_EXPAND_MS)
        self._expand_timer.timeout.connect(self._expand_hovered)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(SCROLL_INTERVAL_MS)
        self._scroll_timer.timeout.connect(self._scroll_step)
        # Se guarda el 'viewport': al cerrar la ventana le llegan eventos cuando el árbol ya
        # se ha destruido, y preguntarle al árbol por él daría error (ver 'eventFilter')
        self._viewport = view.viewport()
        self._viewport.installEventFilter(self)

    # -------------------------------------------------------------------------
    # Empezar a arrastrar
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # nombre de Qt
        """Pulsar sobre una carpeta que se puede mover y mover el ratón: arrastrarla."""
        if watched is not self._viewport:  # sin tocar el árbol (puede estar destruyéndose)
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            self._pressed = None
            if event.button() == Qt.MouseButton.LeftButton:
                position = event.position().toPoint()
                index = self._view.indexAt(position)
                drag = self._can_drag(index) if index.isValid() else None
                if drag is not None:
                    self._pressed = (position, QPersistentModelIndex(index), drag)
        elif kind == QEvent.Type.MouseMove and self._pressed is not None:
            start, index, drag = self._pressed
            if not event.buttons() & Qt.MouseButton.LeftButton or not index.isValid():
                self._pressed = None  # soltado fuera, o el árbol se ha reconstruido
            elif (
                event.position().toPoint() - start
            ).manhattanLength() >= QApplication.startDragDistance():
                self._pressed = None
                self._start(self._view.model().index(index.row(), 0, index.parent()), start, drag)
                return True  # el movimiento ya no elige otras filas
        elif kind == QEvent.Type.MouseButtonRelease:
            self._pressed = None
        return super().eventFilter(watched, event)

    def _start(self, index: QModelIndex, start: QPoint, drag: FolderDrag) -> None:
        """Arrastra la carpeta (con la imagen de su fila). Vuelve cuando se suelta."""
        mime = QMimeData()
        payload = json.dumps({"location_id": drag.location_id, "folder": drag.folder})
        mime.setData(FOLDER_MIME, QByteArray(payload.encode("utf-8")))
        qdrag = QDrag(self._view)
        qdrag.setMimeData(mime)
        rect = self._view.visualRect(index)
        if rect.isValid():
            qdrag.setPixmap(self._view.viewport().grab(rect))
            qdrag.setHotSpot(start - rect.topLeft())
        self.active = drag
        try:
            qdrag.exec(Qt.DropAction.MoveAction)
        finally:
            self.active = None
            self.drag_stopped()

    # -------------------------------------------------------------------------
    # Mientras se arrastra algo sobre el árbol
    # -------------------------------------------------------------------------

    def drag_moved(self, position: QPoint) -> None:
        """El ratón se ha movido sobre el árbol arrastrando algo (en su 'viewport')."""
        index = self._view.indexAt(position)
        if QPersistentModelIndex(index) != self._hover:
            self._hover = QPersistentModelIndex(index)
            self._expand_timer.stop()
            model = self._view.model()
            if index.isValid() and model.hasChildren(index) and not self._view.isExpanded(index):
                self._expand_timer.start()
        scroll = self._scroll_area()
        if scroll is None:
            return
        self._cursor = self._view.viewport().mapTo(scroll.viewport(), position)
        if self._scroll_direction(scroll) and not self._scroll_timer.isActive():
            self._scroll_timer.start()

    def drag_stopped(self) -> None:
        """Se ha soltado, o el arrastre ha salido del árbol: nada más que hacer."""
        self._expand_timer.stop()
        self._scroll_timer.stop()
        self._hover = QPersistentModelIndex()
        self._cursor = None

    def _expand_hovered(self) -> None:
        """Lleva un rato sobre una carpeta plegada: se despliega."""
        if self._hover.isValid():
            hover = self._hover
            self._view.expand(self._view.model().index(hover.row(), 0, hover.parent()))

    def _scroll_area(self) -> QAbstractScrollArea | None:
        """El área con desplazamiento que contiene al árbol (la de la barra lateral)."""
        widget: QWidget | None = self._view.parentWidget()
        while widget is not None and not isinstance(widget, QAbstractScrollArea):
            widget = widget.parentWidget()
        return widget

    def _scroll_direction(self, scroll: QAbstractScrollArea) -> int:
        """-1 si el ratón está en el borde de arriba de lo que se ve, 1 abajo, 0 si no."""
        if self._cursor is None:
            return 0
        y, height = self._cursor.y(), scroll.viewport().height()
        if y < SCROLL_MARGIN:
            return -1
        if y > height - SCROLL_MARGIN:
            return 1
        return 0

    def _scroll_step(self) -> None:
        """Un paso de desplazamiento; se para al llegar al final o al salir del borde."""
        scroll = self._scroll_area()
        direction = self._scroll_direction(scroll) if scroll is not None else 0
        if not direction or scroll is None or self._cursor is None:
            self._scroll_timer.stop()
            return
        bar = scroll.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + direction * SCROLL_STEP)
        if bar.value() == before:
            self._scroll_timer.stop()  # ya está arriba (o abajo) del todo
            return
        # Lo que hay bajo el ratón ha cambiado: la barra vuelve a mirar el destino
        self.scrolled.emit(self._view.viewport().mapFrom(scroll.viewport(), self._cursor))


if __name__ == "__main__":
    # Autoprueba sin ventana (plataforma 'offscreen'): un árbol alto dentro de un área con
    # desplazamiento. Ejecutar desde la raíz del proyecto:
    #   python -m ui_helpers.sidebars.folder_drag
    import os
    import sys
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import QPointF
    from qtpy.QtGui import QMouseEvent, QStandardItem, QStandardItemModel
    from qtpy.QtWidgets import QScrollArea, QVBoxLayout

    from ui_helpers.widgets.sidebar_tree_view import SidebarTreeView

    app = QApplication.instance() or QApplication(sys.argv)

    def wait(milliseconds: int) -> None:
        end = time.monotonic() + milliseconds / 1000
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget(scroll)
    layout = QVBoxLayout(content)
    view = SidebarTreeView(content)
    model = QStandardItemModel(view)
    for number in range(40):
        row = QStandardItem(f"Carpeta {number}")
        row.appendRow(QStandardItem(f"Dentro de {number}"))
        model.appendRow(row)
    view.setModel(model)
    layout.addWidget(view)
    scroll.setWidget(content)
    scroll.resize(240, 200)
    scroll.show()
    app.processEvents()

    asked: list[int] = []

    def can_drag(index: QModelIndex) -> FolderDrag | None:
        asked.append(index.row())
        return None if index.row() == 0 else FolderDrag(1, f"C{index.row()}", "x")

    helper = FolderTreeDrag(view, can_drag=can_drag, parent=view)

    # 1. Pulsar: solo una fila que se puede arrastrar queda «a punto»
    def press(row: int) -> None:
        center = QPointF(view.visualRect(model.index(row, 0)).center())
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress, center, center, Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )  # fmt: skip
        QApplication.sendEvent(view.viewport(), event)

    press(0)
    assert helper._pressed is None and asked == [0]
    press(2)
    assert helper._pressed is not None and helper._pressed[2].folder == "C2"
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    QApplication.sendEvent(view.viewport(), release)
    assert helper._pressed is None
    print("1. Pulsar: solo las filas que se pueden arrastrar")

    # 2. Parado sobre una carpeta plegada: se despliega
    helper._expand_timer.setInterval(50)
    first = model.index(1, 0)
    helper.drag_moved(view.visualRect(first).center())
    assert not view.isExpanded(first)
    wait(150)
    assert view.isExpanded(first)
    helper.drag_stopped()
    print("2. Parado sobre una carpeta plegada: se despliega")

    # 3. En el borde de abajo de lo que se ve: la barra se desplaza (y avisa); fuera, no
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == 0
    moves: list[QPoint] = []
    helper.scrolled.connect(moves.append)
    bottom = scroll.viewport().mapTo(view.viewport(), QPoint(10, scroll.viewport().height() - 5))
    helper.drag_moved(bottom)
    wait(200)
    assert bar.value() > 0 and moves, (bar.value(), moves)
    stopped_at = bar.value()
    helper.drag_moved(view.viewport().mapFrom(scroll.viewport(), QPoint(10, 100)))  # al centro
    wait(100)
    assert bar.value() == stopped_at and not helper._scroll_timer.isActive()
    helper.drag_moved(view.viewport().mapFrom(scroll.viewport(), QPoint(10, 3)))  # arriba
    wait(200)
    assert bar.value() < stopped_at
    helper.drag_stopped()
    assert not helper._scroll_timer.isActive()
    print("3. En el borde: la barra se desplaza; en el centro o al parar, no")

    scroll.close()
    scroll.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
