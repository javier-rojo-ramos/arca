"""Página del mapa en el centro de la ventana: el mapa y un aviso encima.

Es la página de la vista «Mapa» en 'stacked_widget_main' (la pone el controlador
principal). Solo muestra: qué se pinta en el mapa lo decide 'controllers/map_controller.py'.

    ┌──────────────────────────────────────────┐
    │ [+]  12 fotos sin ubicación              │   <- aviso (si hay algo que decir)
    │ [-]                                      │
    │                 mapa                     │
    └──────────────────────────────────────────┘

El mapa ('MapView') NO se crea hasta que se pide ('map_view'): así el motor web solo
arranca si de verdad se abre el mapa.

Teclado: el mapa no coge el teclado (como las barras); lo coge ESTA página, para que los
atajos de clasificación («3», «P»...) y la G (volver a la cuadrícula) funcionen con el
mapa a la vista. Al hacer clic en el mapa, el foco viene aquí (la primera de sus capas
que lo acepta).

Diseño en docs/MAPA.md (§2.6).

1.0.0 Primera versión (docs/MAPA.md, paso 2.3).
"""

__version__ = "1.0.0"
__all__ = ["MapPage"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

# Módulos del proyecto
from ui_helpers.map.map_view import MapView

# Dónde va el aviso: arriba a la izquierda, a la derecha de los botones de zoom del mapa
_NOTICE_X = 54
_NOTICE_Y = 10


class MapPage(QWidget):
    """La página del mapa (ver el docstring del archivo).

    Signals:
        map_created(MapView): el mapa se acaba de crear (la primera vez que se pide).
    """

    map_created = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page_map")
        self._map: MapView | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
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

    def notice(self) -> str:
        """El aviso que se ve ("" si no hay)."""
        return self._notice.text() if self._notice.isVisibleTo(self) else ""
