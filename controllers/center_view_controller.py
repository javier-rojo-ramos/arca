"""Vistas del centro en pantalla: página, botones de vista, deslizador y navegación.

Une piezas que no se conocen entre sí:
    - el 'ModuleHost', que sabe qué vistas ofrece el módulo activo y cuál tiene elegida
      ('active_views', 'active_view', señal 'view_changed', 'set_view');
    - los botones de vista de la barra inferior ('ViewButtons', 'widget_view_buttons');
    - la pila del centro ('stacked_widget_main': 'page_grid', 'page_single'...) y el
      deslizador del tamaño de las tarjetas, que solo se ve en la cuadrícula;
    - la cuadrícula, la vista individual y el mapa, que comparten modelo y selección.

Flujo: pulsar un botón -> 'ModuleHost.set_view' (lo recuerda por módulo y por catálogo)
-> 'view_changed' -> aquí: página, botones, deslizador y foco. Lo mismo al cambiar de
módulo o al abrir y cerrar un catálogo (el host emite 'view_changed').

Teclado y ratón (sin Ctrl, Alt ni Mayús; decidido por el autor el 08/11 y el 13/11/2026):
    cuadrícula         doble clic o Intro -> vista individual del archivo pulsado / actual
                       M -> mapa (si el módulo lo ofrece)
    mapa y su tira     G -> cuadrícula. Intro, o doble clic en una foto -> vista
                       individual (el doble clic lo pide el controlador del mapa con
                       'open_single'). La tira se da con 'watch_map_widget'
    vista individual   G -> cuadrícula, con el archivo visto seleccionado y visible
                       Esc -> la vista de la que se vino (el mapa o la cuadrícula)
                       M -> mapa (si el módulo lo ofrece)
                       ← ↑ anterior, → ↓ siguiente, Inicio el primero, Fin el último
                       (en el orden de la cuadrícula); también la rueda del ratón:
                       hacia delante la anterior, hacia atrás la siguiente (la cuenta
                       la vista: 'step_requested'; a 1:1 y con Ctrl la usa el zoom)
Al elegir otra cosa en una barra (decidido por el autor el 12/11/2026, como Lightroom): el
teclado vuelve a la vista del centro (los árboles de las barras no lo cogen: 'NoFocus') y,
al terminar de cargar, en la cuadrícula queda seleccionada la PRIMERA foto que se ve (la
primera que cumple el filtro): el inspector la muestra y un atajo («3», «P»...) se le
aplica. Lo avisa el 'ModuleHost' ('source_chosen'): no al abrir el catálogo ni al cambiar
de módulo (entonces, el archivo que recuerda el módulo: ver abajo).
Al entrar en la vista individual queda seleccionado SOLO el archivo que se ve (decidido
por el autor el 08/11/2026): así la barra inferior, los atajos de clasificación y el
inspector actúan sobre él sin cambios.

Al recargar la lista, siempre queda un archivo actual si hay alguno (decidido por el autor
el 12/11/2026, como Lightroom), en la cuadrícula y en la vista individual:
    - recién elegido en una barra ('source_chosen'): el primero;
    - el mismo origen (otro orden, otro filtro, archivos quitados, metadatos leídos...): en
      la cuadrícula, lo seleccionado que siga en la lista; si no queda nada, el archivo
      actual de antes, el que recuerda el módulo o, si tampoco están, el que ocupa su
      lugar (al borrar, el siguiente: la cuadrícula no salta al principio);
    - otro origen (al volver a un módulo, al abrir el catálogo): el que recuerda el módulo
      ('ModuleHost.active_current_media', guardado por catálogo), si está en la lista;
    - si no, el primero. Este primero «de reserva» no se apunta como el del módulo: al abrir
      el catálogo, Imagen recibe antes otra lista (todo el catálogo), y lo recordado tiene
      que seguir valiendo cuando llegue la suya.
Cada vez que cambia el archivo actual (el último pulsado, o el que se ve en la vista
individual), el módulo activo lo apunta ('ModuleHost.set_current_media'). Lo recordado no
se mantiene al día: si se borra o deja de verse, se busca al cargar y no se encuentra.

Uso (en el controlador principal, que solo lo crea):
    CenterViewController(
        module_host, buttons=..., stack=..., pages={CenterView.GRID: page_grid, ...},
        size_slider=..., grid=list_view_grid, single=widget_single_view,
        map_page=pagina_del_mapa, parent=window,
    )

1.6.0 'watch_map_widget': otras piezas de la vista de mapa que cogen el teclado (la tira
      de fotos), con la G y el Intro; Intro en el mapa abre la vista individual.
1.5.0 El mapa: M lo abre desde la cuadrícula y la vista individual; G, desde el mapa, a la
      cuadrícula; Esc en la vista individual vuelve a la vista de la que se vino; el
      teclado va a la página del mapa (los atajos de clasificación, a la selección).
1.4.0 Al recargar, siempre un archivo actual: el que recuerda cada módulo (al volver a él y
      al abrir el catálogo), la selección que había (mismo origen) o el que ocupa su lugar.
1.3.0 Al elegir otra cosa en una barra, el teclado vuelve al centro y la primera foto de la
      cuadrícula queda seleccionada ('source_chosen' del 'ModuleHost').
1.2.0 La rueda del ratón en la vista individual: foto anterior o siguiente.
1.1.0 Navegación (paso A.1, subpaso 5): doble clic / Intro, Esc / G, flechas, Inicio y
      Fin; selección de un solo archivo en la vista individual y vuelta a él al recargar.
1.0.0 Primera versión (paso A.1, subpaso 3): botones, páginas y deslizador.
"""

__version__ = "1.6.0"
__all__ = ["CenterViewController"]

# Librerías estándar
from collections.abc import Mapping
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QItemSelection, QItemSelectionModel, QModelIndex, QObject, Qt
from qtpy.QtWidgets import QAbstractItemView, QListView, QStackedWidget, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.module_host import ModuleHost
from ui_helpers.widgets.view_buttons import ViewButtons

_KEY = Qt.Key
# Teclas de la cuadrícula que abren la vista individual
_OPEN_KEYS = {_KEY.Key_Return, _KEY.Key_Enter}
# Teclas de las vistas (como Lightroom: G, la cuadrícula; M, el mapa)
_GRID_KEY = _KEY.Key_G
_MAP_KEY = _KEY.Key_M
# En la vista individual: volver a la vista de la que se vino
_BACK_KEY = _KEY.Key_Escape
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
        map_page: QWidget | None = None,
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
            map_page: La página del mapa (recibe el teclado en el mapa), o None.
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
        self._map_page = map_page
        # Otras piezas de la vista de mapa con teclado propio (la tira: 'watch_map_widget')
        self._map_widgets: list[QWidget] = []
        # Adónde vuelve Esc desde la vista individual: la vista de la que se vino
        self._single_back = CenterView.GRID
        self._model: Any = grid.model()
        self._shown: CenterView | None = None  # vista que está en pantalla
        # Para volver a lo que se veía tras recargar la lista (el mismo origen): el 'id' del
        # archivo actual, los 'id' seleccionados y la primera fila seleccionada (o la actual)
        self._id_before_reset: int | None = None
        self._ids_selected_before_reset: list[int] = []
        self._row_before_reset: int | None = None
        # El usuario ha elegido otra cosa en una barra: al recargar, la primera, seleccionada
        self._select_first = False
        self._last_source: object = getattr(self._model, "source", None)
        # True mientras se elige el primero «de reserva»: el módulo no lo apunta
        self._choosing_fallback = False

        buttons.view_requested.connect(self._on_view_requested)
        host.view_changed.connect(self._show)
        source_chosen = getattr(host, "source_chosen", None)
        if source_chosen is not None:
            source_chosen.connect(self._on_source_chosen)
        grid.doubleClicked.connect(lambda index: self.open_single(index.row()))
        grid.installEventFilter(self)
        single.installEventFilter(self)
        if map_page is not None:
            map_page.installEventFilter(self)
        # La rueda en la vista individual (si la vista la ofrece): anterior o siguiente
        step_requested = getattr(single, "step_requested", None)
        if step_requested is not None:
            step_requested.connect(self._on_step_requested)
        self._model.modelAboutToBeReset.connect(self._remember_shown)
        self._model.modelReset.connect(self._on_rows_reset)
        # El archivo actual, apuntado en el módulo activo (al recargar, el modelo de
        # selección se vacía SIN avisar: lo apuntado sigue siendo el de antes)
        grid.selectionModel().currentChanged.connect(self._on_current_changed)
        self._show()  # el módulo inicial ya se activó al crear el host

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def current_view(self) -> CenterView:
        """Vista que se está viendo (la del módulo activo)."""
        return self._host.active_view

    def watch_map_widget(self, widget: QWidget) -> None:
        """Atiende también las teclas de otra pieza de la vista de mapa que coge el
        teclado (la tira de fotos): G, a la cuadrícula; Intro, la vista individual."""
        if widget not in self._map_widgets:
            self._map_widgets.append(widget)
            widget.installEventFilter(self)

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
                # Esc volverá a la vista de la que se viene (el mapa o la cuadrícula)
                self._single_back = previous if previous == CenterView.MAP else CenterView.GRID
                # Al entrar (también con el botón): solo el archivo que se ve, seleccionado
                row = self._current_row()
                if row >= 0:
                    self._select_only(row)
            self._single.setFocus()
        elif view == CenterView.MAP and self._map_page is not None:
            # El mapa no coge el teclado: lo coge su página, para los atajos y la G
            self._map_page.setFocus()
        elif view == CenterView.GRID and previous in (CenterView.SINGLE, CenterView.MAP):
            self._grid.setFocus()
            self._grid.scrollTo(self._grid.currentIndex(), QAbstractItemView.ScrollHint.EnsureVisible)

    # -------------------------------------------------------------------------
    # Navegación
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress or event.modifiers() not in _NO_MODIFIER:
            return False
        key = event.key()
        if watched is self._grid:
            if key in _OPEN_KEYS:
                self.open_single()
                return True
            return key == _MAP_KEY and self._show_view(CenterView.MAP)
        if (watched is self._map_page and self._map_page is not None) or watched in self._map_widgets:
            if self._shown != CenterView.MAP:
                return False
            if key in _OPEN_KEYS:
                self.open_single()
                return True
            return key == _GRID_KEY and self._show_view(CenterView.GRID)
        if watched is not self._single or self._shown != CenterView.SINGLE:
            return False
        if key == _GRID_KEY:
            self._host.set_view(CenterView.GRID)
        elif key == _BACK_KEY:
            self._show_view(self._single_back) or self._host.set_view(CenterView.GRID)
        elif key == _MAP_KEY:
            return self._show_view(CenterView.MAP)
        elif key in _STEP_KEYS:
            self._move_to(self._current_row() + _STEP_KEYS[key])
        elif key == _KEY.Key_Home:
            self._move_to(0)
        elif key == _KEY.Key_End:
            self._move_to(self._model.rowCount() - 1)
        else:
            return False  # el resto (atajos de clasificación...) sigue su camino
        return True

    def _show_view(self, view: CenterView) -> bool:
        """Pasa a esa vista si el módulo la ofrece. False (y nada cambia) si no."""
        if view not in self._host.active_views():
            return False
        self._host.set_view(view)
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

    def _select_rows(self, rows: list[int], current: int) -> None:
        """Deja seleccionadas esas filas (por tramos seguidos), con 'current' como actual."""
        ordered = sorted(rows)
        selection = QItemSelection()
        start = end = ordered[0]
        for row in ordered[1:]:
            if row != end + 1:  # fin de un tramo
                selection.select(self._model.index(start, 0), self._model.index(end, 0))
                start = row
            end = row
        selection.select(self._model.index(start, 0), self._model.index(end, 0))
        selection_model = self._grid.selectionModel()
        selection_model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        index = self._model.index(current, 0)
        selection_model.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._grid.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def _select_fallback(self) -> None:
        """El primero, porque no se encontró lo que tocaba: sin que el módulo lo apunte."""
        self._choosing_fallback = True
        try:
            self._select_only(0)
        finally:
            self._choosing_fallback = False

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Otro archivo actual: el módulo activo lo apunta (salvo el primero «de reserva»)."""
        if current.isValid() and not self._choosing_fallback:
            self._host.set_current_media(self._media_id(current.row()))

    def _remember_shown(self) -> None:
        """Antes de recargar la lista: el archivo actual y lo seleccionado."""
        current = self._grid.currentIndex()
        # Por tramos: 'selectedIndexes' pregunta al modelo por cada fila (con un Ctrl+A de
        # 20 000, unas 20 veces más lento)
        spans = self._grid.selectionModel().selection()
        selected = sorted({row for span in spans for row in range(span.top(), span.bottom() + 1)})
        self._id_before_reset = self._media_id(current.row()) if current.isValid() else None
        self._ids_selected_before_reset = self._media_ids(selected)
        if selected:
            self._row_before_reset = selected[0]
        else:
            self._row_before_reset = current.row() if current.isValid() else None

    def _on_source_chosen(self) -> None:
        """El usuario ha elegido otra cosa en una barra: el teclado, a la vista del centro
        (los atajos, a las fotos) y, al recargar, la primera foto seleccionada."""
        self._select_first = True
        if self._shown == CenterView.SINGLE:
            self._single.setFocus()
        elif self._shown == CenterView.MAP and self._map_page is not None:
            self._map_page.setFocus()
        else:
            self._grid.setFocus()

    def _on_rows_reset(self) -> None:
        """Lista recargada: qué queda seleccionado (las reglas, en el docstring del archivo)."""
        source = getattr(self._model, "source", None)
        same_source, self._last_source = source == self._last_source, source
        select_first, self._select_first = self._select_first, False
        before, self._id_before_reset = self._id_before_reset, None
        selected, self._ids_selected_before_reset = self._ids_selected_before_reset, []
        row_before, self._row_before_reset = self._row_before_reset, None
        count = self._model.rowCount()
        if count == 0:
            return  # nada que seleccionar (la vista dirá «No hay archivos»)
        if select_first:
            self._select_only(0)  # recién elegido en una barra (el módulo lo apunta)
            return
        if same_source and self._shown != CenterView.SINGLE:
            rows = [row for row in map(self._row_of_id, selected) if row is not None]
            if rows:
                current = self._row_of_id(before)
                self._select_rows(rows, current if current is not None else min(rows))
                return
        remembered = self._host.active_current_media
        candidates = (before, remembered) if same_source else (remembered,)
        row = next((r for r in map(self._row_of_id, candidates) if r is not None), None)
        if row is None and same_source and row_before is not None:
            row = min(row_before, count - 1)  # ya no está: el que ocupa su lugar
        if row is not None:
            self._select_only(row)
        else:
            self._select_fallback()

    def _media_id(self, row: int) -> int | None:
        if hasattr(self._model, "media_ids"):
            ids = self._model.media_ids([row])
            return ids[0] if ids else None
        return row  # modelos de prueba sin 'media_ids'

    def _media_ids(self, rows: list[int]) -> list[int]:
        if hasattr(self._model, "media_ids"):
            return list(self._model.media_ids(rows))
        return list(rows)  # modelos de prueba sin 'media_ids'

    def _row_of_id(self, media_id: int | None) -> int | None:
        """Fila de ese 'id' en la lista recién cargada (None si no está o si es None)."""
        if media_id is None:
            return None
        if hasattr(self._model, "row_of_id"):
            return self._model.row_of_id(media_id)
        return media_id if 0 <= media_id < self._model.rowCount() else None


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
            self.current_media: int | None = None  # el archivo que recuerda el módulo

        @property
        def active_view(self) -> CenterView:
            return self.view

        @property
        def active_current_media(self) -> int | None:
            return self.current_media

        def set_current_media(self, media_id: int | None) -> None:
            self.current_media = media_id

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

    # El módulo apunta el archivo actual cada vez que cambia
    assert host.current_media == 30
    # Recarga con el mismo origen (otro orden): sigue en el mismo archivo (id 30)
    model.fill([40, 30, 20, 10])
    assert selected_rows() == [1] and model.media_ids([grid.currentIndex().row()]) == [30]
    # Otro origen (al volver a un módulo, al abrir el catálogo): el que recuerda el módulo
    host.current_media = 60
    model.source = "carpeta B"
    model.fill([50, 30, 60])
    assert selected_rows() == [2] and host.current_media == 60
    # Otro origen sin lo recordado: el primero, «de reserva», que el módulo no apunta...
    model.source = "carpeta D"
    model.fill([70, 80])
    assert selected_rows() == [0] and host.current_media == 60
    # ...para que valga cuando llegue su lista (Imagen, al abrir el catálogo)
    model.source = "carpeta B"
    model.fill([50, 30, 60])
    assert selected_rows() == [2]
    # Mismo origen, el archivo visto borrado: el que ocupa su lugar (no el primero)
    model.fill([50, 30])
    assert selected_rows() == [1] and host.current_media == 30
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

    # En la cuadrícula, una recarga con el mismo origen conserva TODA la selección que siga
    # en la lista, con la misma actual (otro orden)
    def selected_ids() -> list[int]:
        return sorted(model.media_ids(selected_rows()))

    def current_id() -> int:
        return model.media_ids([grid.currentIndex().row()])[0]

    selection = grid.selectionModel()
    model.fill([10, 20, 30, 40, 50])
    for row in (0, 1, 3):
        selection.select(model.index(row, 0), QItemSelectionModel.SelectionFlag.Select)
    selection.setCurrentIndex(model.index(3, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
    assert selected_ids() == [10, 20, 40] and host.current_media == 40
    model.fill([50, 40, 30, 20, 10])
    assert selected_ids() == [10, 20, 40] and current_id() == 40
    # Un filtro deja fuera parte (también la actual): lo que queda, y la actual, la primera
    model.fill([30, 20, 10])
    assert selected_ids() == [10, 20] and current_id() == 20 and host.current_media == 20
    # Se borran las seleccionadas: el siguiente, en su lugar (el módulo lo apunta)
    model.fill([10, 20, 30, 40, 50])
    selection.clearSelection()
    for row in (1, 2):
        selection.select(model.index(row, 0), QItemSelectionModel.SelectionFlag.Select)
    selection.setCurrentIndex(model.index(2, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
    model.fill([10, 40, 50])
    assert selected_ids() == [40] and host.current_media == 40
    # Lista vacía antes (al abrir el catálogo con el mismo origen): el que recuerda el módulo
    model.fill([])
    host.current_media = 50
    model.fill([40, 50])
    assert selected_ids() == [50]
    # Sin nada antes ni recordado: el primero, sin apuntarlo
    model.fill([])
    host.current_media = None
    model.fill([7, 8])
    assert selected_ids() == [7] and host.current_media is None
    # Si se acaba de elegir otra cosa en una barra ('source_chosen'): la primera, apuntada
    host.current_media = 8
    host.source_chosen.emit()
    model.fill([80, 90, 8])
    assert selected_rows() == [0] and grid.currentIndex().row() == 0 and host.current_media == 80
    model.fill([81, 91])  # la siguiente recarga, ya normal: la 80 no está, la que ocupa su lugar
    assert selected_rows() == [0] and host.current_media == 81
    host.source_chosen.emit()
    model.fill([])  # lo elegido no tiene nada: nada que seleccionar
    assert selected_rows() == []

    # El mapa (13/11/2026): M lo abre, G vuelve a la cuadrícula; desde el mapa, la vista
    # individual vuelve al mapa con Esc y con M, y a la cuadrícula con G
    page_map = QWidget(stack)
    stack.addWidget(page_map)
    map_controller = CenterViewController(
        host, buttons=ViewButtons(window), stack=stack,  # type: ignore[arg-type]
        pages={CenterView.GRID: page_grid, CenterView.SINGLE: page_single, CenterView.MAP: page_map},
        size_slider=slider, grid=grid, single=single, map_page=page_map, parent=window,
    )  # fmt: skip
    controller.deleteLater()  # el de antes ya no atiende nada
    controller.setParent(None)
    grid.removeEventFilter(controller)
    single.removeEventFilter(controller)
    host.view_changed.disconnect(controller._show)
    host.views = (CenterView.GRID, CenterView.SINGLE)
    host.set_view(CenterView.GRID)
    press(grid, _KEY.Key_M)  # el módulo no ofrece el mapa: no pasa nada
    assert host.view is CenterView.GRID
    host.views = (CenterView.GRID, CenterView.SINGLE, CenterView.MAP)
    model.fill([10, 20, 30, 40])
    selection.setCurrentIndex(model.index(1, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    press(grid, _KEY.Key_M)
    assert host.view is CenterView.MAP and stack.currentWidget() is page_map and slider.isHidden()
    press(page_map, _KEY.Key_G)
    assert host.view is CenterView.GRID and stack.currentWidget() is page_grid
    # Desde el mapa, doble clic en una foto (lo pide el controlador del mapa) y Esc: al mapa
    host.set_view(CenterView.MAP)
    map_controller.open_single(2)
    assert host.view is CenterView.SINGLE and selected_rows() == [2]
    press(single, _KEY.Key_Escape)
    assert host.view is CenterView.MAP and selected_rows() == [2]
    map_controller.open_single(3)
    press(single, _KEY.Key_M)
    assert host.view is CenterView.MAP
    map_controller.open_single(3)
    press(single, _KEY.Key_G)
    assert host.view is CenterView.GRID
    # Desde la cuadrícula, Esc sigue volviendo a la cuadrícula; M, al mapa
    press(grid, _KEY.Key_Return)
    press(single, _KEY.Key_Escape)
    assert host.view is CenterView.GRID
    press(grid, _KEY.Key_Return)
    press(single, _KEY.Key_M)
    assert host.view is CenterView.MAP
    # En el mapa, Esc y las demás teclas no son de este controlador (los atajos, a la selección)
    for key in (_KEY.Key_Escape, _KEY.Key_3, _KEY.Key_M):
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        assert map_controller.eventFilter(page_map, event) is False, key
    # La tira de fotos del mapa: G a la cuadrícula; Intro, la vista individual y Esc, de vuelta
    strip = QWidget(page_map)
    map_controller.watch_map_widget(strip)
    selection.setCurrentIndex(model.index(2, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    press(strip, _KEY.Key_Return)
    assert host.view is CenterView.SINGLE and selected_rows() == [2]
    press(single, _KEY.Key_Escape)
    assert host.view is CenterView.MAP
    press(strip, _KEY.Key_G)
    assert host.view is CenterView.GRID
    press(strip, _KEY.Key_G)  # fuera del mapa, la tira no hace nada
    assert host.view is CenterView.GRID

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
