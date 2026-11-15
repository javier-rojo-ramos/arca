"""La banda del perfil de elevación bajo el mapa (módulo Tracks): qué perfil se ve, su botón y F7.

Qué hace (docs/MAPA.md, pasos 5.3a y 5.3b; decidido con el autor el 15/11/2026):
    - Muestra el perfil del track activo: el ÚNICO track seleccionado. Sin ninguno, o con
      varios, la banda se queda (así el mapa no cambia de tamaño) con un texto en gris;
      mientras se lee el GPX, «Leyendo el recorrido…»; si no se puede leer, dice por qué,
      con los textos de la vista individual para un archivo ausente o un disco
      desconectado (el autor quiso distinguirlos de un GPX dañado).
    - El perfil lo calcula 'TrackDetailController' junto con el recorrido, en segundo plano
      ('request' y 'detail_ready'); uno visto hace poco sale de su memoria al momento. Si
      llega el mismo detalle otra vez (el mapa lo vuelve a pedir al recargarse), no se
      toca: el tramo elegido en el perfil se conserva.
    - Solo en los módulos cuyo mapa lo ofrece ('MapOptions.show_profile': Tracks) y con el
      mapa a la vista; ahí se ven la banda (si el usuario no la ha ocultado) y su botón.
    - El botón (barra inferior, a la izquierda del de la tira) y F7 la muestran u ocultan;
      si se ve y su alto se guardan en settings.json ('map_profile').
    - Botón derecho sobre el perfil: cómo se ve la pendiente («En el área», «En la línea»
      o «Sin colores»); se guarda en settings.json ('profile_slope_mode'), lo mismo que
      elige Opciones > Tracks ('apply_settings').

Sincronizada con el mapa (paso 5.3b), en los dos sentidos y sin eco (los métodos que se
llaman desde fuera no avisan):
    - El ratón sobre el track activo en el mapa ('MapView.track_hovered') pone el cursor
      del perfil en ese punto; el ratón sobre el perfil ('cursor_moved') pone el punto
      ámbar del mapa ('MapView.set_track_cursor').
    - El tramo elegido en el perfil ('range_selected') se resalta en el mapa
      ('MapView.set_track_range'); un clic en el perfil o Esc (con el teclado en la página
      del mapa: el mapa o la tira) lo quitan de los dos.
    - Solo mientras el mapa tiene el recorrido COMPLETO de ese track: los índices de sus
      puntos son entonces los del perfil (con el contorno, otros). Al volver a ponerlo
      ('TrackDetailController.detail_shown', p. ej. tras recargar el mapa), el tramo
      elegido se vuelve a resaltar.

Uso (lo crea 'MapController', que le dice cuándo se puede ver y qué hay seleccionado):
    profile = TrackProfileController(page, barra, config, track_detail, parent)
    profile.attach_map(view)         # al crearse el mapa
    profile.set_available(True)      # mapa a la vista en un módulo con perfil
    profile.show_tracks([12])        # los tracks seleccionados
    profile.reset()                  # al abrir o cerrar un catálogo
    profile.apply_settings(claves)   # tras la ventana de opciones

1.2.0 Botón derecho sobre el perfil: cómo se ve la pendiente, guardado en settings.json
      ('profile_slope_mode', también en Opciones > Tracks: 'apply_settings').
1.1.1 Textos de un GPX que no se puede leer o sin recorrido, los del autor.
1.1.0 Paso 5.3b: sincronizada con el mapa (punto ámbar en los dos sentidos, tramo
      resaltado, Esc); si no se puede leer el GPX, dice por qué ('DetailFailure').
1.0.0 Primera versión (15/11/2026; docs/MAPA.md, paso 5.3a).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.track_profile_controller
"""

__version__ = "1.2.0"
__all__ = ["TrackProfileController"]

# Librerías estándar
from collections.abc import Sequence
from dataclasses import replace
from functools import partial
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QPoint, QSize, Qt, QTimer
from qtpy.QtGui import QActionGroup, QKeySequence, QShortcut
from qtpy.QtWidgets import QBoxLayout, QMenu, QToolButton

# Módulos del proyecto
from config.app_constants import SETTING_MAP_PROFILE, SETTING_PROFILE_SLOPE_MODE, AppIcons
from controllers.track_detail_controller import DetailFailure, TrackDetail, TrackDetailController
from ui_helpers.helpers import card_glyphs
from ui_helpers.helpers.profile_style import SLOPE_MODE_LABELS, SLOPE_MODE_TITLE, SlopeMode
from ui_helpers.helpers.track_appearance import slope_mode
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.map.map_view import MapView
from ui_helpers.widgets.map_page import MapPage
from ui_helpers.widgets.single_media_view import UNAVAILABLE_TEXTS

# Textos (los del botón y «Leyendo el recorrido…», aprobados por el autor el 15/11/2026)
_PROFILE_SHOW = "Mostrar el perfil de elevación (F7)"
_PROFILE_HIDE = "Ocultar el perfil de elevación (F7)"
_NO_TRACK = "Selecciona un track para ver su perfil"
_SEVERAL_TRACKS = "Selecciona un solo track para ver su perfil"
_LOADING = "Leyendo el recorrido…"
# Por qué no se ha podido leer: ausente y sin conexión, con los textos de la vista
# individual (decididos por el autor el 08/11/2026); los otros dos, por el autor el
# 15/11/2026
_FAILURE_TEXTS = {
    DetailFailure.MISSING: UNAVAILABLE_TEXTS[card_glyphs.MISSING],
    DetailFailure.OFFLINE: UNAVAILABLE_TEXTS[card_glyphs.OFFLINE],
    DetailFailure.UNREADABLE: "No se ha podido leer el GPX: puede estar dañado",
    DetailFailure.EMPTY: "El track no tiene recorrido",
}
_UNREADABLE = "No se ha podido leer el recorrido de este track"  # cualquier otro motivo

# Medidas del botón: las del de la tira (y las de los botones de vista)
_BUTTON_SIZE = 22
_ICON_SIZE = 16
# Espera tras arrastrar el separador antes de guardar el alto
_SAVE_DELAY_MS = 600


class TrackProfileController(QObject):
    """La banda del perfil bajo el mapa (ver el docstring del archivo)."""

    def __init__(
        self,
        page: MapPage,
        button_bar: QBoxLayout,
        config: Any,
        track_detail: TrackDetailController,
        parent: QObject | None = None,
    ) -> None:
        """
        Args:
            page: La página del mapa (tiene la banda del perfil, 'page.profile').
            button_bar: Layout de la barra inferior donde va el botón.
            config: Configuración de la aplicación (si se ve la banda y su alto).
            track_detail: Quien lee el recorrido del track activo y calcula su perfil.
            parent: Objeto padre (el controlador del mapa).
        """
        super().__init__(parent)
        self._page = page
        self._config = config
        self._track_detail = track_detail
        # Mapa a la vista en un módulo con perfil
        self._available = False
        # Lo que eligió el usuario (botón o F7): se aplica cuando la banda está disponible
        self._wanted_visible = True
        # El track cuyo perfil se ve o se espera (None = ninguno) y el detalle que se ve
        self._track: int | None = None
        self._detail: TrackDetail | None = None
        # El mapa (se crea la primera vez que se ve: 'attach_map')
        self._view: MapView | None = None

        # El botón, oculto hasta que la banda esté disponible
        self._button = QToolButton()
        self._button.setObjectName("btn_map_profile")  # estilo en ui_theme.py
        self._button.setAutoRaise(True)
        self._button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # el teclado, en los archivos
        self._button.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
        self._button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._button.hide()
        self._button.clicked.connect(self.toggle)
        button_bar.addWidget(self._button)
        self._shortcut = QShortcut(QKeySequence(Qt.Key.Key_F7), page)
        self._shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcut.activated.connect(self.toggle)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save)

        # Esc quita el tramo elegido: solo con el teclado en la página del mapa (el mapa o la
        # tira) y solo mientras hay tramo, para no quitarle Esc a nadie más
        self._escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), page)
        self._escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._escape.setEnabled(False)
        self._escape.activated.connect(self._on_escape)

        # Botón derecho sobre el perfil: cómo se ve la pendiente
        page.profile.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        page.profile.customContextMenuRequested.connect(self._on_context_menu)

        page.profile_resized.connect(lambda _height: self._save_timer.start())
        page.profile.cursor_moved.connect(self._on_profile_cursor)
        page.profile.range_selected.connect(self._on_profile_range)
        page.profile.selection_cleared.connect(self._forget_range)
        track_detail.detail_ready.connect(self._on_detail_ready)
        track_detail.detail_failed.connect(self._on_detail_failed)
        track_detail.detail_shown.connect(self._on_detail_shown)
        self._restore()
        page.profile.clear(_NO_TRACK)

    # -------------------------------------------------------------------------
    # Lo que llama el controlador del mapa
    # -------------------------------------------------------------------------

    def attach_map(self, view: MapView) -> None:
        """El mapa, recién creado: el punto bajo el ratón en el track activo, al perfil."""
        self._view = view
        view.track_hovered.connect(self._on_map_hovered)

    def set_available(self, available: bool) -> None:
        """Si la banda se puede ver: mapa a la vista en un módulo con perfil."""
        self._available = available
        self._button.setVisible(available)
        self._page.set_profile_visible(available and self._wanted_visible)
        if not available:
            # Al volver, se decide otra vez con la selección de entonces
            self._track = None
            self._detail = None
            self._forget_range()
        self._update_button()

    def show_tracks(self, track_ids: Sequence[int]) -> None:
        """Los tracks seleccionados: con uno solo, su perfil; si no, el texto en gris."""
        if not self._available:
            return
        if len(track_ids) != 1:
            self._show_message(_NO_TRACK if not track_ids else _SEVERAL_TRACKS)
            return
        track_id = track_ids[0]
        if track_id == self._track:
            return  # ya se ve (o se está leyendo)
        self._track = track_id
        self._detail = None
        self._forget_range()
        self._page.profile.clear(_LOADING)
        self._track_detail.request(track_id)  # si está en la memoria, llega ya

    def reset(self) -> None:
        """Al abrir o cerrar un catálogo: sin perfil."""
        self._show_message(_NO_TRACK)

    def apply_settings(self, changed: set[str]) -> None:
        """Se han cambiado opciones: cómo se ve la pendiente (Opciones > Tracks)."""
        if SETTING_PROFILE_SLOPE_MODE in changed:
            self._apply_slope_mode(slope_mode(self._config))

    def toggle(self) -> None:
        """El botón o F7: muestra u oculta la banda (solo donde se puede ver)."""
        if not self._available:
            return
        self._wanted_visible = not self._wanted_visible
        self._page.set_profile_visible(self._wanted_visible)
        self._update_button()
        self._save()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _show_message(self, message: str) -> None:
        self._track = None
        self._detail = None
        self._forget_range()
        profile = self._page.profile
        if profile.profile() is not None or profile.message() != message:
            profile.clear(message)

    def _on_detail_ready(self, track_id: int, detail: TrackDetail) -> None:
        """Ha llegado el detalle de un track: si es el que se espera (y no el que ya se ve),
        su perfil."""
        if track_id != self._track or detail is self._detail:
            return
        self._detail = detail
        self._forget_range()  # el perfil nuevo empieza sin tramo
        self._page.profile.set_profile(detail.profile)

    def _on_detail_failed(self, track_id: int, reason: str) -> None:
        """No se ha podido leer el recorrido: si es el que se espera, por qué."""
        if track_id == self._track and self._detail is None:
            self._page.profile.clear(_FAILURE_TEXTS.get(reason, _UNREADABLE))

    # --- Sincronización con el mapa (paso 5.3b) ---

    def _synced_track(self) -> int | None:
        """El track del perfil, si el mapa tiene su recorrido completo (sus índices son
        entonces los del perfil); si no, None (con el contorno no se puede sincronizar)."""
        if self._view is None or self._detail is None or self._track is None:
            return None
        track = self._view.track(self._track)
        if track is None or not track.detailed:
            return None
        if track.point_count != self._detail.profile.point_count:
            return None  # otro recorrido (el archivo cambió): mejor no señalar nada
        return self._track

    def _on_map_hovered(self, track_id: int, index: int) -> None:
        """El ratón en el mapa, sobre el track activo (índice -1: se ha ido)."""
        if track_id == self._synced_track():
            self._page.profile.set_cursor(index if index >= 0 else None)

    def _on_profile_cursor(self, index: int) -> None:
        """El ratón en el perfil (-1: se ha ido): el punto ámbar del mapa, en ese punto."""
        track = self._synced_track()
        if track is not None and self._view is not None:
            self._view.set_track_cursor(track, index if index >= 0 else None)

    def _on_profile_range(self, first: int, last: int) -> None:
        """Un tramo elegido en el perfil: resaltado en el mapa; Esc lo quitará."""
        self._escape.setEnabled(True)
        track = self._synced_track()
        if track is not None and self._view is not None:
            self._view.set_track_range(track, first, last)

    def _on_escape(self) -> None:
        """Esc con un tramo elegido: fuera, del perfil y del mapa."""
        self._page.profile.clear_selection()
        self._forget_range()

    def _forget_range(self) -> None:
        """Sin tramo: se quita del mapa y Esc deja de hacer nada."""
        self._escape.setEnabled(False)
        if self._view is not None:
            self._view.clear_track_range()

    def _on_detail_shown(self, track_id: int) -> None:
        """El mapa acaba de poner el recorrido completo de un track (p. ej. tras volver a
        pintarse, cuando el tramo resaltado se pierde): si es el del perfil y hay un tramo
        elegido, se vuelve a resaltar."""
        selection = self._page.profile.selection()
        track = self._synced_track()
        if selection is not None and track == track_id and self._view is not None:
            self._view.set_track_range(track, *selection)

    # --- Cómo se ve la pendiente (botón derecho u Opciones > Tracks) ---

    def _slope_menu(self) -> QMenu:
        """El menú del botón derecho sobre el perfil: los tres modos, con el actual marcado."""
        profile = self._page.profile
        menu = QMenu(profile)
        menu.addAction(SLOPE_MODE_TITLE).setEnabled(False)  # título, no se elige
        group = QActionGroup(menu)
        group.setExclusive(True)
        current = profile.profile_style().slope_mode
        for mode, label in SLOPE_MODE_LABELS.items():
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode is current)
            group.addAction(action)
            action.triggered.connect(partial(self._choose_slope_mode, mode))
        return menu

    def _on_context_menu(self, position: QPoint) -> None:
        menu = self._slope_menu()
        menu.exec(self._page.profile.mapToGlobal(position))
        menu.deleteLater()

    def _choose_slope_mode(self, mode: SlopeMode, _checked: bool = False) -> None:
        """Un modo elegido en el menú: se aplica y se guarda (el mismo que Opciones)."""
        self._apply_slope_mode(mode)
        self._config.set(SETTING_PROFILE_SLOPE_MODE, mode.value)

    def _apply_slope_mode(self, mode: SlopeMode) -> None:
        profile = self._page.profile
        if profile.profile_style().slope_mode is not mode:
            profile.set_style(replace(profile.profile_style(), slope_mode=mode))

    def _update_button(self) -> None:
        self._button.setIcon(
            tinted_icon(AppIcons.PROFILE_HIDE if self._wanted_visible else AppIcons.PROFILE_SHOW)
        )
        self._button.setToolTip(_PROFILE_HIDE if self._wanted_visible else _PROFILE_SHOW)

    def _restore(self) -> None:
        """Si se ve y su alto, como se dejaron (settings.json)."""
        saved = self._config.get(SETTING_MAP_PROFILE)
        saved = saved if isinstance(saved, dict) else {}
        visible = saved.get("visible", True)
        self._wanted_visible = visible if isinstance(visible, bool) else True
        height = saved.get("height")
        if isinstance(height, int) and not isinstance(height, bool):
            self._page.set_profile_height(height)
        self._update_button()
        self._apply_slope_mode(slope_mode(self._config))

    def _save(self) -> None:
        self._config.set(
            SETTING_MAP_PROFILE,
            {"visible": self._wanted_visible, "height": self._page.profile_height()},
        )


if __name__ == "__main__":
    # Autoprueba sin ventana: la página de verdad (sin crear el mapa), una configuración en
    # memoria y un lector de detalles de mentira que responde cuando se le dice.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.track_profile_controller
    import sys
    from array import array

    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import QApplication, QHBoxLayout, QWidget

    from controllers.track_detail_controller import path_segments
    from core.tracks.gpx_document import PathSegment, TrackPath
    from core.tracks.profile import build_profile
    from ui_helpers.map.map_types import MapTrack

    app = QApplication.instance() or QApplication(sys.argv[:1])

    class _Config:
        def __init__(self, data: dict | None = None) -> None:
            self.data = dict(data or {})

        def get(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self.data[key] = value

    class _Detail(QObject):
        """Como 'TrackDetailController': 'request' apunta lo pedido; lo que tenga en su
        «memoria» lo entrega al momento."""

        detail_ready = Signal(int, object)
        detail_failed = Signal(int, str)
        detail_shown = Signal(int)

        def __init__(self) -> None:
            super().__init__()
            self.requests: list[int] = []
            self.cache: dict[int, TrackDetail] = {}

        def request(self, track_id: int) -> None:
            self.requests.append(track_id)
            if track_id in self.cache:
                self.detail_ready.emit(track_id, self.cache[track_id])

    class _View(QObject):
        """Como 'MapView': sus tracks (con la geometría de ahora) y lo que se le pide."""

        track_hovered = Signal(int, int)

        def __init__(self) -> None:
            super().__init__()
            self.tracks: dict[int, MapTrack] = {}
            self.calls: list[tuple] = []

        def track(self, track_id: int) -> MapTrack | None:
            return self.tracks.get(track_id)

        def set_track_cursor(self, track_id: int, index: int | None) -> None:
            self.calls.append(("cursor", track_id, index))

        def set_track_range(self, track_id: int, first: int, last: int) -> None:
            self.calls.append(("range", track_id, first, last))

        def clear_track_range(self) -> None:
            self.calls.append(("clear",))

        def take(self) -> list[tuple]:
            calls, self.calls = self.calls, []
            return calls

    def _detail(count: int) -> TrackDetail:
        lats = array("d", [42.6 + k * 0.0001 for k in range(count)])
        path = TrackPath((PathSegment(lats, array("d", [0.0] * count),
                                      array("d", [1000.0 + k for k in range(count)]),
                                      array("d", [float(k) for k in range(count)])),))  # fmt: skip
        return TrackDetail(path, build_profile(path))

    holder = QWidget()
    bar = QHBoxLayout(holder)
    page = MapPage()
    config = _Config()
    source = _Detail()
    controller = TrackProfileController(page, bar, config, source)  # type: ignore[arg-type]
    profile = page.profile

    # --- Al empezar: sin perfil, la banda y el botón ocultos (ningún módulo con perfil)
    assert profile.message() == _NO_TRACK and profile.profile() is None
    assert not page.profile_visible() and controller._button.isHidden()
    controller.show_tracks([5])  # no disponible: no hace nada
    assert source.requests == []

    # --- Disponible (Tracks con el mapa a la vista): banda y botón
    controller.set_available(True)
    assert page.profile_visible() and not controller._button.isHidden()
    assert controller._button.toolTip() == _PROFILE_HIDE

    # --- Ninguno, varios, uno
    controller.show_tracks([])
    assert profile.message() == _NO_TRACK
    controller.show_tracks([1, 2])
    assert profile.message() == _SEVERAL_TRACKS
    controller.show_tracks([5])
    assert profile.message() == _LOADING and source.requests == [5]
    controller.show_tracks([5])  # el mismo: no se pide otra vez
    assert source.requests == [5]
    five = _detail(30)
    source.detail_ready.emit(6, _detail(10))  # otro track: no es el que se espera
    assert profile.profile() is None
    source.detail_ready.emit(5, five)
    assert profile.profile() is five.profile and profile.message() == ""
    # El mismo detalle otra vez (el mapa se recarga): no se toca (el tramo se conserva)
    profile.set_selection(2, 20)
    source.detail_ready.emit(5, five)
    assert profile.selection() == (2, 20)

    # --- Uno que no se puede leer: dice por qué
    controller.show_tracks([7])
    assert profile.message() == _LOADING
    source.detail_failed.emit(8, "offline")  # otro
    assert profile.message() == _LOADING
    source.detail_failed.emit(7, "offline")
    assert profile.message() == "Sin conexión (disco desconectado)", profile.message()
    for number, reason, text in (
        (71, "missing", "Ausente (archivo no encontrado)"),
        (72, "unreadable", _FAILURE_TEXTS[DetailFailure.UNREADABLE]),
        (73, "empty", "El track no tiene recorrido"),
        (74, "error", _UNREADABLE),  # cualquier otro motivo
    ):
        controller.show_tracks([number])
        source.detail_failed.emit(number, reason)
        assert profile.message() == text, (reason, profile.message())

    # --- En la memoria: llega al momento, sin pasar por «Leyendo…» a la vista
    source.cache[9] = _detail(12)
    controller.show_tracks([9])
    assert profile.profile() is source.cache[9].profile

    # --- El botón (o F7): oculta y muestra, y se guarda
    controller.toggle()
    assert not page.profile_visible() and controller._button.toolTip() == _PROFILE_SHOW
    assert config.data[SETTING_MAP_PROFILE]["visible"] is False
    controller.toggle()
    assert page.profile_visible() and config.data[SETTING_MAP_PROFILE]["visible"] is True

    # --- Otro módulo (o el mapa oculto): banda y botón fuera; el botón no hace nada
    controller.set_available(False)
    assert not page.profile_visible() and controller._button.isHidden()
    controller.toggle()
    assert config.data[SETTING_MAP_PROFILE]["visible"] is True
    # Al volver, se decide otra vez con la selección (el 9, de la memoria)
    controller.set_available(True)
    requests = len(source.requests)
    controller.show_tracks([9])
    assert len(source.requests) == requests + 1 and profile.profile() is source.cache[9].profile

    # --- El alto: al arrastrar el separador se guarda (tras una espera)
    page.profile_resized.emit(210)
    assert controller._save_timer.isActive()
    page.set_profile_height(210)
    controller._save()
    assert config.data[SETTING_MAP_PROFILE] == {"visible": True, "height": 210}

    # --- Sincronización con el mapa (paso 5.3b); el perfil es el del 9
    view = _View()
    controller.attach_map(view)  # type: ignore[arg-type]
    nine = source.cache[9]
    # Con el contorno en el mapa no se sincroniza (sus índices son otros)
    view.tracks[9] = MapTrack(9, "Nueve", (((42.6, 0.0), (42.7, 0.0)),))
    view.track_hovered.emit(9, 1)
    profile.cursor_moved.emit(3)  # como si el ratón pasara por el perfil
    assert profile.cursor_index() is None and view.take() == []
    # Con el recorrido completo, sí: del mapa al perfil (sin eco) y del perfil al mapa
    view.tracks[9] = MapTrack(9, "Nueve", path_segments(nine.path), detailed=True)
    view.track_hovered.emit(9, 5)
    assert profile.cursor_index() == 5 and view.take() == []
    view.track_hovered.emit(9, -1)
    assert profile.cursor_index() is None
    view.track_hovered.emit(8, 2)  # otro track
    assert profile.cursor_index() is None
    profile.cursor_moved.emit(4)
    profile.cursor_moved.emit(-1)
    assert view.take() == [("cursor", 9, 4), ("cursor", 9, None)]
    # El tramo elegido en el perfil, resaltado en el mapa; Esc, ahora sí, lo quitará
    assert not controller._escape.isEnabled()
    profile.set_selection(2, 8)
    profile.range_selected.emit(2, 8)
    assert view.take() == [("range", 9, 2, 8)] and controller._escape.isEnabled()
    # El mapa se vuelve a pintar (pierde el tramo) y pone otra vez el recorrido: de nuevo
    source.detail_shown.emit(9)
    assert view.take() == [("range", 9, 2, 8)]
    source.detail_shown.emit(4)  # otro track
    assert view.take() == []
    # Esc: fuera de los dos
    controller._escape.activated.emit()
    assert profile.selection() is None and view.take() == [("clear",)]
    assert not controller._escape.isEnabled()
    # Un clic en el perfil sin arrastrar ('selection_cleared'), también
    profile.set_selection(1, 3)
    profile.range_selected.emit(1, 3)
    view.take()
    profile.selection_cleared.emit()
    assert view.take() == [("clear",)]
    # Otro track: su tramo, fuera del mapa
    profile.set_selection(1, 3)
    profile.range_selected.emit(1, 3)
    view.take()
    controller.show_tracks([5])
    assert view.take() == [("clear",)] and profile.message() == _LOADING

    # --- Cómo se ve la pendiente: el menú del botón derecho y Opciones
    menu = controller._slope_menu()
    actions = menu.actions()
    assert [a.text() for a in actions] == [SLOPE_MODE_TITLE, *SLOPE_MODE_LABELS.values()]
    assert not actions[0].isEnabled() and actions[1].isChecked()  # en el área, de partida
    actions[3].trigger()  # «Sin colores»
    assert profile.profile_style().slope_mode is SlopeMode.OFF
    assert config.data[SETTING_PROFILE_SLOPE_MODE] == "off"
    menu.deleteLater()
    menu = controller._slope_menu()
    assert [a.isChecked() for a in menu.actions()[1:]] == [False, False, True]
    menu.deleteLater()
    config.data[SETTING_PROFILE_SLOPE_MODE] = "line"  # lo que guarda Opciones > Tracks
    controller.apply_settings({"otra_clave"})
    assert profile.profile_style().slope_mode is SlopeMode.OFF  # no era la suya
    controller.apply_settings({SETTING_PROFILE_SLOPE_MODE})
    assert profile.profile_style().slope_mode is SlopeMode.LINE

    # --- Cerrar el catálogo
    controller.reset()
    assert profile.message() == _NO_TRACK and profile.profile() is None

    # --- Lo guardado, al crear otro: oculta y con su alto
    other_page, other_holder = MapPage(), QWidget()
    other = TrackProfileController(
        other_page, QHBoxLayout(other_holder),
        _Config({SETTING_MAP_PROFILE: {"visible": False, "height": 230},
                 SETTING_PROFILE_SLOPE_MODE: "off"}),
        source,  # type: ignore[arg-type]
    )  # fmt: skip
    assert other_page.profile_height() == 230 and other._button.toolTip() == _PROFILE_SHOW
    assert other_page.profile.profile_style().slope_mode is SlopeMode.OFF
    other.set_available(True)
    assert not other_page.profile_visible() and not other._button.isHidden()
    print("Autoprueba finalizada correctamente.")
