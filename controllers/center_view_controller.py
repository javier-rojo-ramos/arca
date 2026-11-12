"""Vistas del centro en pantalla: página, botones de vista, deslizador y navegación.

Une piezas que no se conocen entre sí:
    - el 'ModuleHost', que sabe qué vistas ofrece el módulo activo y cuál tiene elegida
      ('active_views', 'active_view', señal 'view_changed', 'set_view');
    - los botones de vista de la barra inferior ('ViewButtons', 'widget_view_buttons');
    - la pila del centro ('stacked_widget_main': 'page_grid', 'page_single'...) y el
      deslizador del tamaño de las tarjetas, que solo se ve en la cuadrícula;
    - la cuadrícula y la vista individual, que comparten modelo y selección.

Flujo: pulsar un botón -> 'ModuleHost.set_view' (lo recuerda por módulo y por catálogo)
-> 'view_changed' -> aquí: página, botones, deslizador y foco. Lo mismo al cambiar de
módulo o al abrir y cerrar un catálogo (el host emite 'view_changed').

Teclado y ratón (sin Ctrl, Alt ni Mayús):
    cuadrícula         doble clic o Intro -> vista individual del archivo pulsado / actual
    vista individual   Esc o G -> cuadrícula, con el archivo visto seleccionado y visible
                       ← ↑ anterior, → ↓ siguiente, Inicio el primero, Fin el último
                       (en el orden de la cuadrícula); también la rueda del ratón:
                       hacia delante la anterior, hacia atrás la siguiente (la cuenta
                       la vista: 'step_requested'; a 1:1 y con Ctrl la usa el zoom)
Al elegir otra cosa en una barra (decidido por el autor el 12/11/2026, como Lightroom): el
teclado vuelve a la vista del centro (los árboles de las barras no lo cogen: 'NoFocus') y,
al terminar de cargar, en la cuadrícula queda seleccionada la PRIMERA foto que se ve (la
primera que cumple el filtro): el inspector la muestra y un atajo («3», «P»...) se le
aplica. En la vista individual ya era así. Lo avisa el 'ModuleHost' ('source_chosen'):
no al abrir el catálogo ni al cambiar de módulo.
Al entrar en la vista individual queda seleccionado SOLO el archivo que se ve (decidido
por el autor el 08/11/2026): así la barra inferior, los atajos de clasificación y el
inspector actúan sobre él sin cambios. Si se recarga la lista estando en ella: con otro
origen (barra izquierda), el primer archivo; con el mismo (otro orden, una recarga), el
que se veía, si sigue ahí.

Uso (en el controlador principal, que solo lo crea):
    CenterViewController(
        module_host, buttons=..., stack=..., pages={CenterView.GRID: page_grid, ...},
        size_slider=..., grid=list_view_grid, single=widget_single_view, parent=window,
    )

1.3.0 Al elegir otra cosa en una barra, el teclado vuelve al centro y la primera foto de la
      cuadrícula queda seleccionada ('source_chosen' del 'ModuleHost').
1.2.0 La rueda del ratón en la vista individual: foto anterior o siguiente.
1.1.0 Navegación (paso A.1, subpaso 5): doble clic / Intro, Esc / G, flechas, Inicio y
      Fin; selección de un solo archivo en la vista individual y vuelta a él al recargar.
1.0.0 Primera versión (paso A.1, subpaso 3): botones, páginas y deslizador.
"""

__version__ = "1.3.0"
__all__ = ["CenterViewController"]

# Librerías estándar
from collections.abc import Mapping
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QItemSelectionModel, QModelIndex, QObject, Qt
from qtpy.QtWidgets import QAbstractItemView, QListView, QStackedWidget, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.module_host import ModuleHost
from ui_helpers.widgets.view_buttons import ViewButtons

_KEY = Qt.Key
# Teclas de la cuadrícula que abren la vista individual
_OPEN_KEYS = {_KEY.Key_Return, _KEY.Key_Enter}
# Teclas de la vista individual que vuelven a la cuadrícula
_BACK_KEYS = {_KEY.Key_Escape, _KEY.Key_G}
# Pasos de las flechas en la vista individual
_STEP_KEYS = {_KEY.Key_Left: -1, _KEY.Key_Up: -1, _KEY.Key_Right: 1, _KEY.Key_Down: 1}
# Modificadores que no impiden los atajos (el del teclado numérico)
_NO_MODIFIER = (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)


class CenterViewController(QObject):
    """Pone en pantalla la vista del centro del módulo activo y la navegación entre
    archivos (ver el docstring del archivo)."""

    def __init__(
        self,
        host: ModuleHost,
        *,
        buttons: ViewButtons,
        stack: QStackedWidget,
        pages: Mapping[CenterView, QWidget],
        size_slider: QWidget,
        grid: QListView,
        single: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Conecta las piezas y muestra ya la vista del módulo activo.

        Args:
            host: Coordinador de los módulos.
            buttons: Botones de vista de la barra inferior.
            stack: Pila del centro ('stacked_widget_main').
            pages: Página de cada vista (las que no estén usan la de la cuadrícula).
            size_slider: Deslizador del tamaño de las tarjetas (solo en la cuadrícula).
            grid: La cuadrícula (su modelo y su selección son los de la vista individual).
            single: La vista individual (recibe aquí sus teclas de navegación).
            parent: Objeto padre (la ventana principal).
        """
        super().__init__(parent)
        self._host = host
        self._buttons = buttons
        self._stack = stack
        self._pages = dict(pages)
        self._slider = size_slider
        self._grid = grid
        self._single = single
        self._model: Any = grid.model()
        self._shown: CenterView | None = None  # vista que está en pantalla
        # Para volver al archivo visto tras recargar la lista: su 'id' y el origen de antes
        self._id_before_reset: int | None = None
        # El usuario ha elegido otra cosa en una barra: al recargar, la primera, seleccionada
        self._select_first = False
        self._last_source: object = getattr(self._model, "source", None)

        buttons.view_requested.connect(self._on_view_requested)
        host.view_changed.connect(self._show)
        source_chosen = getattr(host, "source_chosen", None)
        if source_chosen is not None:
            source_chosen.connect(self._on_source_chosen)
        grid.doubleClicked.connect(lambda index: self.open_single(index.row()))
        grid.installEventFilter(self)
        single.installEventFilter(self)
        # La rueda en la vista individual (si la vista la ofrece): anterior o siguiente
        step_requested = getattr(single, "step_requested", None)
        if step_requested is not None:
            step_requested.connect(self._on_step_requested)
        self._model.modelAboutToBeReset.connect(self._remember_shown)
        self._model.modelReset.connect(self._on_rows_reset)
        self._show()  # el módulo inicial ya se activó al crear el host

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def current_view(self) -> CenterView:
        """Vista que se está viendo (la del módulo activo)."""
        return self._host.active_view

    def open_single(self, row: int | None = None) -> None:
        """Abre la vista individual con el archivo de esa fila (o el actual)."""
        if CenterView.SINGLE not in self._host.active_views():
            return
        target = self._current_row() if row is None else row
        if target >= 0:
            self._select_only(target)
        self._host.set_view(CenterView.SINGLE)

    # -------------------------------------------------------------------------
    # Vista en pantalla
    # -------------------------------------------------------------------------

    def _on_view_requested(self, key: str) -> None:
        """Un botón de vista: se pide al host (que la recuerda y avisa con 'view_changed')."""
        view = CenterView.from_key(key)
        if view is not None:
            self._host.set_view(view)

    def _show(self, _view: object = None) -> None:
        """Página, botones, deslizador y foco según la vista del módulo activo."""
        view = self._host.active_view
        self._buttons.set_views(
            [(v.value, v.tooltip, getattr(AppIcons, v.icon_name, "") if v.icon_name else "")
             for v in self._host.active_views()],
            view.value,
        )  # fmt: skip
        page = self._pages.get(view)
        if page is None:
            logger.warning(f"La vista {view.value!r} todavía no tiene página: se ve la cuadrícula.")
            page = self._pages[CenterView.GRID]
        self._stack.setCurrentWidget(page)
        # El tamaño de las tarjetas solo tiene sentido en la cuadrícula. Se oculta solo el
        # deslizador (no su zona), para que la barra de clasificación siga centrada
        self._slider.setVisible(view == CenterView.GRID)

        previous, self._shown = self._shown, view
        if view == CenterView.SINGLE:
            if previous != CenterView.SINGLE:
                # Al entrar (también con el botón): solo el archivo que se ve, seleccionado
                row = self._current_row()
                if row >= 0:
                    self._select_only(row)
            self._single.setFocus()
        elif view == CenterView.GRID and previous == CenterView.SINGLE:
            self._grid.setFocus()
            self._grid.scrollTo(self._grid.currentIndex(), QAbstractItemView.ScrollHint.EnsureVisible)

    # -------------------------------------------------------------------------
    # Navegación
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress or event.modifiers() not in _NO_MODIFIER:
            return False
        key = event.key()
        if watched is self._grid and key in _OPEN_KEYS:
            self.open_single()
            return True
        if watched is not self._single or self._shown != CenterView.SINGLE:
            return False
        if key in _BACK_KEYS:
            self._host.set_view(CenterView.GRID)
        elif key in _STEP_KEYS:
            self._move_to(self._current_row() + _STEP_KEYS[key])
        elif key == _KEY.Key_Home:
            self._move_to(0)
        elif key == _KEY.Key_End:
            self._move_to(self._model.rowCount() - 1)
        else:
            return False  # el resto (atajos de clasificación...) sigue su camino
        return True

    def _current_row(self) -> int:
        """Fila actual: la de la cuadrícula; si no hay, la primera seleccionada o la primera
        de todas (la misma regla que la vista individual). -1 si no hay filas."""
        if self._model.rowCount() == 0:
            return -1
        current = self._grid.currentIndex()
        if current.isValid():
            return current.row()
        selected = self._grid.selectionModel().selectedIndexes()
        return min(index.row() for index in selected) if selected else 0

    def _on_step_requested(self, step: int) -> None:
        """La rueda en la vista individual: tantos archivos atrás o adelante."""
        if self._shown == CenterView.SINGLE:
            self._move_to(self._current_row() + step)

    def _move_to(self, row: int) -> None:
        """Pasa a otro archivo en la vista individual (se queda en los extremos)."""
        count = self._model.rowCount()
        if count:
            self._select_only(max(0, min(row, count - 1)))

    def _select_only(self, row: int) -> None:
        """Deja seleccionada solo esa fila, como actual, y visible en la cuadrícula."""
        index: QModelIndex = self._model.index(row, 0)
        if not index.isValid():
            return
        self._grid.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self._grid.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def _remember_shown(self) -> None:
        """Antes de recargar la lista: qué archivo se estaba viendo."""
        row = self._current_row()
        self._id_before_reset = self._media_id(row) if row >= 0 else None

    def _on_source_chosen(self) -> None:
        """El usuario ha elegido otra cosa en una barra: el teclado, a la vista del centro
        (los atajos, a las fotos) y, al recargar, la primera foto seleccionada."""
        self._select_first = True
        if self._shown == CenterView.SINGLE:
            self._single.setFocus()
        else:
            self._grid.setFocus()

    def _on_rows_reset(self) -> None:
        """Lista recargada: en la vista individual, otro origen -> el primer archivo; el
        mismo origen -> el que se veía (si sigue). En la cuadrícula, si se acaba de elegir
        otra cosa en una barra, el primero (si no, nada: se queda sin selección)."""
        source = getattr(self._model, "source", None)
        same_source, self._last_source = source == self._last_source, source
        select_first, self._select_first = self._select_first, False
        if self._shown != CenterView.SINGLE:
            if select_first and self._model.rowCount():
                self._select_only(0)
            return
        if self._model.rowCount() == 0:
            return
        row = 0
        if same_source and self._id_before_reset is not None and hasattr(self._model, "row_of_id"):
            found = self._model.row_of_id(self._id_before_reset)
            row = found if found is not None else 0
        self._select_only(row)

    def _media_id(self, row: int) -> int | None:
        if hasattr(self._model, "media_ids"):
            ids = self._model.media_ids([row])
            return ids[0] if ids else None
        return row  # modelos de prueba sin 'media_ids'


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'), con un host de mentira.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.center_view_controller
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import Signal
    from qtpy.QtGui import QKeyEvent, QStandardItem, QStandardItemModel
    from qtpy.QtWidgets import QApplication, QSlider

    app = QApplication([])

    class _FakeHost(QObject):
        view_changed = Signal(object)
        source_chosen = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.views = (CenterView.GRID, CenterView.SINGLE)
            self.view = CenterView.GRID

        @property
        def active_view(self) -> CenterView:
            return self.view

        def active_views(self) -> tuple[CenterView, ...]:
            return self.views

        def set_view(self, view: CenterView) -> None:
            if view in self.views and view != self.view:
                self.view = view
                self.view_changed.emit(view)

    class _Model(QStandardItemModel):
        """Con 'source', 'row_of_id' y 'media_ids', como el modelo de la cuadrícula."""

        source = "carpeta A"

        def fill(self, ids: list[int]) -> None:
            self.beginResetModel()
            self.removeRows(0, self.rowCount())
            for media_id in ids:
                item = QStandardItem(str(media_id))
                item.setData(media_id, Qt.ItemDataRole.UserRole)
                self.appendRow(item)
            self.endResetModel()

        def media_ids(self, rows: list[int]) -> list[int]:
            return [self.item(r).data(Qt.ItemDataRole.UserRole) for r in rows if 0 <= r < self.rowCount()]

        def row_of_id(self, media_id: int) -> int | None:
            return next((r for r in range(self.rowCount()) if self.media_ids([r]) == [media_id]), None)

    def press(widget: QWidget, key: Qt.Key) -> None:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    window = QWidget()  # nunca se muestra
    model = _Model(window)
    model.fill([10, 20, 30, 40])
    grid = QListView(window)
    grid.setModel(model)
    grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    class _Single(QWidget):
        """Lo que el controlador usa de la vista individual: la señal de la rueda."""

        step_requested = Signal(int)

    single = _Single(window)
    stack = QStackedWidget(window)
    page_grid, page_single = QWidget(stack), QWidget(stack)
    stack.addWidget(page_grid)
    stack.addWidget(page_single)
    slider = QSlider(window)
    buttons = ViewButtons(window)
    host = _FakeHost()
    controller = CenterViewController(
        host, buttons=buttons, stack=stack,  # type: ignore[arg-type]
        pages={CenterView.GRID: page_grid, CenterView.SINGLE: page_single},
        size_slider=slider, grid=grid, single=single, parent=window,
    )  # fmt: skip

    def selected_rows() -> list[int]:
        return sorted(index.row() for index in grid.selectionModel().selectedIndexes())

    # Al empezar: la cuadrícula, con su botón marcado y el deslizador visible
    assert stack.currentWidget() is page_grid and buttons.current == "grid" and not slider.isHidden()

    # Varias seleccionadas, la actual la 2; Intro en la cuadrícula -> individual, solo la 2
    grid.selectionModel().select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    grid.selectionModel().setCurrentIndex(model.index(2, 0), QItemSelectionModel.SelectionFlag.Select)
    assert selected_rows() == [0, 2]
    press(grid, _KEY.Key_Return)
    assert host.view is CenterView.SINGLE and stack.currentWidget() is page_single
    assert selected_rows() == [2] and grid.currentIndex().row() == 2 and slider.isHidden()

    # Flechas, Inicio y Fin (se queda en los extremos)
    press(single, _KEY.Key_Right)
    assert selected_rows() == [3]
    press(single, _KEY.Key_Down)
    assert selected_rows() == [3]  # ya era la última
    press(single, _KEY.Key_Home)
    assert selected_rows() == [0]
    press(single, _KEY.Key_Up)
    assert selected_rows() == [0]
    press(single, _KEY.Key_End)
    assert selected_rows() == [3]
    press(single, _KEY.Key_Left)
    assert selected_rows() == [2]
    # La rueda (la cuenta la vista y pide pasos): adelante y atrás, en los extremos se queda
    single.step_requested.emit(1)
    assert selected_rows() == [3]
    single.step_requested.emit(5)
    assert selected_rows() == [3]
    single.step_requested.emit(-1)
    assert selected_rows() == [2]
    # Una tecla que no es suya (un atajo de clasificación) no se consume
    event = QKeyEvent(QEvent.Type.KeyPress, _KEY.Key_3, Qt.KeyboardModifier.NoModifier)
    assert controller.eventFilter(single, event) is False

    # Recarga con el mismo origen (otro orden): sigue en el mismo archivo (id 30)
    model.fill([40, 30, 20, 10])
    assert selected_rows() == [1] and model.media_ids([grid.currentIndex().row()]) == [30]
    # Otro origen: el primer archivo
    model.source = "carpeta B"
    model.fill([50, 30, 60])
    assert selected_rows() == [0]
    # Origen vacío: nada seleccionado (la vista dirá «No hay archivos»)
    model.source = "carpeta C"
    model.fill([])
    assert selected_rows() == [] and host.view is CenterView.SINGLE

    # Esc -> cuadrícula, con el archivo visto seleccionado
    model.source = "carpeta A"
    model.fill([10, 20, 30, 40])
    press(single, _KEY.Key_End)
    press(single, _KEY.Key_Escape)
    assert host.view is CenterView.GRID and stack.currentWidget() is page_grid
    assert selected_rows() == [3] and not slider.isHidden()
    # En la cuadrícula, las flechas no son de este controlador; G tampoco
    assert controller.eventFilter(grid, QKeyEvent(QEvent.Type.KeyPress, _KEY.Key_Right,
                                                  Qt.KeyboardModifier.NoModifier)) is False  # fmt: skip

    # Botón de la vista individual con varias seleccionadas: también queda solo la actual
    grid.selectionModel().select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    assert selected_rows() == [0, 3]
    buttons._buttons["single"].click()
    assert selected_rows() == [3]
    press(single, _KEY.Key_G)
    assert host.view is CenterView.GRID

    # Doble clic en una tarjeta: la vista individual con esa
    grid.doubleClicked.emit(model.index(1, 0))
    assert host.view is CenterView.SINGLE and selected_rows() == [1]

    # Un módulo sin vista individual: Intro no hace nada
    host.set_view(CenterView.GRID)
    host.views = (CenterView.GRID,)
    host.view_changed.emit(CenterView.GRID)
    press(grid, _KEY.Key_Return)
    assert host.view is CenterView.GRID and buttons.isHidden()

    # En la cuadrícula: una recarga normal deja la lista sin selección; si se acaba de elegir
    # otra cosa en una barra ('source_chosen'), queda seleccionada la primera
    grid.selectionModel().clearSelection()
    model.fill([50, 60, 70])
    assert selected_rows() == []
    host.source_chosen.emit()
    model.fill([80, 90])
    assert selected_rows() == [0] and grid.currentIndex().row() == 0
    model.fill([81, 91])  # la siguiente recarga, ya normal: sin selección
    assert selected_rows() == []
    host.source_chosen.emit()
    model.fill([])  # lo elegido no tiene nada: nada que seleccionar
    assert selected_rows() == []

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
