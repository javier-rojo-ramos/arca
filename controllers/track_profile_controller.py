"""La banda del perfil de elevación bajo el mapa (módulo Tracks): qué perfil se ve, su botón y F7.

Qué hace (docs/MAPA.md, paso 5.3a; decidido con el autor el 15/11/2026):
    - Muestra el perfil del track activo: el ÚNICO track seleccionado. Sin ninguno, o con
      varios, la banda se queda (así el mapa no cambia de tamaño) con un texto en gris;
      mientras se lee el GPX, «Leyendo el recorrido…»; si no se puede leer (archivo
      ausente, disco desconectado, GPX dañado), lo dice.
    - El perfil lo calcula 'TrackDetailController' junto con el recorrido, en segundo plano
      ('request' y 'detail_ready'); uno visto hace poco sale de su memoria al momento. Si
      llega el mismo detalle otra vez (el mapa lo vuelve a pedir al recargarse), no se
      toca: el tramo elegido en el perfil se conserva.
    - Solo en los módulos cuyo mapa lo ofrece ('MapOptions.show_profile': Tracks) y con el
      mapa a la vista; ahí se ven la banda (si el usuario no la ha ocultado) y su botón.
    - El botón (barra inferior, a la izquierda del de la tira) y F7 la muestran u ocultan;
      si se ve y su alto se guardan en settings.json ('map_profile').

Lo que TODAVÍA NO hace (paso 5.3b): el punto ámbar del mapa en el perfil y al revés, el
tramo elegido resaltado en el mapa y quitarlo con Esc.

Uso (lo crea 'MapController', que le dice cuándo se puede ver y qué hay seleccionado):
    profile = TrackProfileController(page, barra, config, track_detail, parent)
    profile.set_available(True)      # mapa a la vista en un módulo con perfil
    profile.show_tracks([12])        # los tracks seleccionados
    profile.reset()                  # al abrir o cerrar un catálogo

1.0.0 Primera versión (15/11/2026; docs/MAPA.md, paso 5.3a).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m controllers.track_profile_controller
"""

__version__ = "1.0.0"
__all__ = ["TrackProfileController"]

# Librerías estándar
from collections.abc import Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QSize, Qt, QTimer
from qtpy.QtGui import QKeySequence, QShortcut
from qtpy.QtWidgets import QBoxLayout, QToolButton

# Módulos del proyecto
from config.app_constants import SETTING_MAP_PROFILE, AppIcons
from controllers.track_detail_controller import TrackDetail, TrackDetailController
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.widgets.map_page import MapPage

# Textos (los del botón y «Leyendo el recorrido…», aprobados por el autor el 15/11/2026)
_PROFILE_SHOW = "Mostrar el perfil de elevación (F7)"
_PROFILE_HIDE = "Ocultar el perfil de elevación (F7)"
_NO_TRACK = "Selecciona un track para ver su perfil"
_SEVERAL_TRACKS = "Selecciona un solo track para ver su perfil"
_LOADING = "Leyendo el recorrido…"
_UNREADABLE = "No se ha podido leer el recorrido de este track"

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

        page.profile_resized.connect(lambda _height: self._save_timer.start())
        track_detail.detail_ready.connect(self._on_detail_ready)
        track_detail.detail_failed.connect(self._on_detail_failed)
        self._restore()
        page.profile.clear(_NO_TRACK)

    # -------------------------------------------------------------------------
    # Lo que llama el controlador del mapa
    # -------------------------------------------------------------------------

    def set_available(self, available: bool) -> None:
        """Si la banda se puede ver: mapa a la vista en un módulo con perfil."""
        self._available = available
        self._button.setVisible(available)
        self._page.set_profile_visible(available and self._wanted_visible)
        if not available:
            # Al volver, se decide otra vez con la selección de entonces
            self._track = None
            self._detail = None
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
        self._page.profile.clear(_LOADING)
        self._track_detail.request(track_id)  # si está en la memoria, llega ya

    def reset(self) -> None:
        """Al abrir o cerrar un catálogo: sin perfil."""
        self._show_message(_NO_TRACK)

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
        profile = self._page.profile
        if profile.profile() is not None or profile.message() != message:
            profile.clear(message)

    def _on_detail_ready(self, track_id: int, detail: TrackDetail) -> None:
        """Ha llegado el detalle de un track: si es el que se espera (y no el que ya se ve),
        su perfil."""
        if track_id != self._track or detail is self._detail:
            return
        self._detail = detail
        self._page.profile.set_profile(detail.profile)

    def _on_detail_failed(self, track_id: int) -> None:
        if track_id == self._track and self._detail is None:
            self._page.profile.clear(_UNREADABLE)

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

    from core.tracks.gpx_document import PathSegment, TrackPath
    from core.tracks.profile import build_profile

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
        detail_failed = Signal(int)

        def __init__(self) -> None:
            super().__init__()
            self.requests: list[int] = []
            self.cache: dict[int, TrackDetail] = {}

        def request(self, track_id: int) -> None:
            self.requests.append(track_id)
            if track_id in self.cache:
                self.detail_ready.emit(track_id, self.cache[track_id])

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

    # --- Uno que no se puede leer
    controller.show_tracks([7])
    assert profile.message() == _LOADING
    source.detail_failed.emit(8)  # otro
    assert profile.message() == _LOADING
    source.detail_failed.emit(7)
    assert profile.message() == _UNREADABLE

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

    # --- Cerrar el catálogo
    controller.reset()
    assert profile.message() == _NO_TRACK and profile.profile() is None

    # --- Lo guardado, al crear otro: oculta y con su alto
    other_page, other_holder = MapPage(), QWidget()
    other = TrackProfileController(
        other_page, QHBoxLayout(other_holder),
        _Config({SETTING_MAP_PROFILE: {"visible": False, "height": 230}}),
        source,  # type: ignore[arg-type]
    )  # fmt: skip
    assert other_page.profile_height() == 230 and other._button.toolTip() == _PROFILE_SHOW
    other.set_available(True)
    assert not other_page.profile_visible() and not other._button.isHidden()
    print("Autoprueba finalizada correctamente.")
