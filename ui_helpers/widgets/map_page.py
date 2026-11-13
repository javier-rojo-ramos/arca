"""Página del mapa en el centro de la ventana: el mapa, un aviso encima y la tira de fotos.

Es la página de la vista «Mapa» en 'stacked_widget_main' (la pone el controlador
principal). Solo muestra: qué se pinta en el mapa lo decide 'controllers/map_controller.py'.

    ┌──────────────────────────────────────────┐
    │ [+]  12 fotos sin ubicación              │   <- aviso (si hay algo que decir)
    │ [-]                                      │
    │                 mapa                     │
    ├──────────────────────────────────────────┤   <- separador: se arrastra (alto de la tira)
    │ [foto][foto][foto][foto][foto]           │   <- tira de fotos ('MapFilmstrip'), ocultable
    └──────────────────────────────────────────┘

El mapa ('MapView') NO se crea hasta que se pide ('map_view'): así el motor web solo
arranca si de verdad se abre el mapa.

Teclado: el mapa no coge el teclado (como las barras); lo coge ESTA página, para que los
atajos de clasificación («3», «P»...) y la G (volver a la cuadrícula) funcionen con el
mapa a la vista. Al hacer clic en el mapa, el foco viene aquí (la primera de sus capas
que lo acepta).

Diseño en docs/MAPA.md (§2.6).

1.1.0 La tira de fotos debajo del mapa, con un separador para su alto (paso 3.1):
      'filmstrip', 'set_filmstrip_visible', 'set_filmstrip_height', 'filmstrip_resized'.
1.0.0 Primera versión (docs/MAPA.md, paso 2.3).
"""

__version__ = "1.1.0"
__all__ = ["MapPage"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QShowEvent
from qtpy.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

# Módulos del proyecto
from ui_helpers.map.map_view import MapView
from ui_helpers.widgets.map_filmstrip import MapFilmstrip

# Dónde va el aviso: arriba a la izquierda, a la derecha de los botones de zoom del mapa
_NOTICE_X = 54
_NOTICE_Y = 10
# Alto mínimo del mapa al agrandar la tira
_MIN_MAP_HEIGHT = 150
# Alto de la tira mientras no se diga otro
_DEFAULT_FILMSTRIP_HEIGHT = 140


class MapPage(QWidget):
    """La página del mapa (ver el docstring del archivo).

    Signals:
        map_created(MapView): el mapa se acaba de crear (la primera vez que se pide).
        filmstrip_resized(int): el usuario ha cambiado el alto de la tira (px lógicos).
    """

    map_created = Signal(object)
    filmstrip_resized = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page_map")
        self._map: MapView | None = None
        self._filmstrip_height = _DEFAULT_FILMSTRIP_HEIGHT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # El mapa (arriba) y la tira (abajo), con un separador para el alto de la tira
        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setObjectName("splitter_map_page")
        self._splitter.setChildrenCollapsible(False)
        self._map_holder = QWidget(self._splitter)
        self._map_holder.setMinimumHeight(_MIN_MAP_HEIGHT)
        self._layout = QVBoxLayout(self._map_holder)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.filmstrip = MapFilmstrip(self._splitter)
        self._splitter.addWidget(self._map_holder)
        self._splitter.addWidget(self.filmstrip)
        self._splitter.setStretchFactor(0, 1)  # al agrandar la ventana, crece el mapa
        self._splitter.setStretchFactor(1, 0)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        layout.addWidget(self._splitter)
        # El teclado del mapa: los atajos de clasificación y la G (ver el docstring)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Aviso encima del mapa: no se lleva los clics (el mapa sigue moviéndose debajo)
        self._notice = QLabel(self)
        self._notice.setObjectName("lbl_map_notice")  # estilo en ui_theme.py
        self._notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._notice.hide()

    def has_map(self) -> bool:
        """True si el mapa ya está creado."""
        return self._map is not None

    def map_view(self) -> MapView:
        """El mapa; la primera vez, lo crea (y avisa con 'map_created')."""
        if self._map is None:
            self._map = MapView(self)
            self._layout.addWidget(self._map)
            self._notice.raise_()
            self.map_created.emit(self._map)
        return self._map

    def set_notice(self, text: str) -> None:
        """Pone el aviso de encima del mapa ("" = ninguno)."""
        if not text:
            self._notice.hide()
            return
        self._notice.setText(text)
        self._notice.adjustSize()
        self._notice.move(_NOTICE_X, _NOTICE_Y)
        self._notice.show()
        self._notice.raise_()

    # -------------------------------------------------------------------------
    # Tira de fotos
    # -------------------------------------------------------------------------

    def set_filmstrip_visible(self, visible: bool) -> None:
        """Muestra u oculta la tira (oculta, el mapa ocupa toda la página)."""
        self.filmstrip.setVisible(visible)
        if visible:
            self._apply_filmstrip_height()

    def filmstrip_visible(self) -> bool:
        """True si la tira se ve (o se verá, si la página aún no se ha mostrado)."""
        return not self.filmstrip.isHidden()

    def filmstrip_height(self) -> int:
        """Alto de la tira (px lógicos): el que tiene, o el que tendrá al verse."""
        return self._filmstrip_height

    def set_filmstrip_height(self, height: int) -> None:
        """Pone el alto de la tira (no emite 'filmstrip_resized')."""
        self._filmstrip_height = max(self.filmstrip.minimumHeight(), int(height))
        self._apply_filmstrip_height()

    def _apply_filmstrip_height(self) -> None:
        total = sum(self._splitter.sizes())
        if total <= 0 or self.filmstrip.isHidden():
            return  # aún sin tamaño: se pone al mostrarse ('showEvent')
        height = min(self._filmstrip_height, max(total - _MIN_MAP_HEIGHT, self.filmstrip.minimumHeight()))
        self._splitter.setSizes([total - height, height])

    def _on_splitter_moved(self, _position: int, _index: int) -> None:
        self._filmstrip_height = self._splitter.sizes()[1]
        self.filmstrip_resized.emit(self._filmstrip_height)

    def showEvent(self, event: QShowEvent) -> None:  # nombre de Qt
        super().showEvent(event)
        self._apply_filmstrip_height()

    def notice(self) -> str:
        """El aviso que se ve ("" si no hay)."""
        return self._notice.text() if self._notice.isVisibleTo(self) else ""
