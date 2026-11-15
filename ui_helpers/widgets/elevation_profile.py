"""Perfil de elevación de un track: la gráfica de la altitud según la distancia.

Irá en una banda bajo el mapa del módulo Tracks (docs/MAPA.md, paso 5.3), sincronizada
con él: el círculo ámbar del mapa aparece en el perfil y al revés. Este widget solo
muestra y avisa; quién le da el perfil y a quién avisa lo decide el controlador.

Qué se ve (el dibujo está en 'ui_helpers/helpers/profile_painter.py'):
    - Arriba, los totales del track (distancia, desnivel, altitud máxima y mínima, los
      mismos números que el inspector) o, con un tramo elegido, los datos del tramo.
    - La gráfica: ejes con marcas redondas, rejilla, el área bajo la curva y la línea,
      con la pendiente por colores (en el área o en la línea, según el estilo).
    - El cursor: línea vertical, círculo ámbar sobre la curva y una etiqueta con la
      altitud, la distancia, la pendiente y la hora del punto.
    - El tramo elegido: una banda sombreada.

Ratón:
    - Al pasar por encima, el cursor sigue al ratón (salta al punto más cercano) y avisa
      con 'cursor_moved(índice)'; al salir, 'cursor_moved(-1)'.
    - Arrastrando se elige un tramo: 'range_selected(primero, último)' mientras cambia.
    - Un clic sin arrastrar quita el tramo elegido: 'selection_cleared'.

El widget no coge el teclado (como el mapa y las barras: los atajos siguen yendo a los
archivos). Quitar el tramo con Esc lo hará quien lo contenga, con 'clear_selection'.

Los métodos que se llaman desde fuera ('set_cursor', 'set_selection', 'clear_selection')
NO emiten señales: así el mapa puede mover el cursor del perfil sin que el perfil le
devuelva el aviso.

Uso:
    profile = ElevationProfile(parent)
    profile.set_profile(build_profile(read_gpx_path("ruta.gpx")))
    profile.cursor_moved.connect(...)
    profile.set_cursor(120)                          # el punto 120, desde el mapa
    profile.clear("Selecciona un track para ver su perfil")
    profile.set_style(replace(profile.profile_style(), slope_mode=SlopeMode.LINE))

1.1.0 'message()': el aviso que se ve (para quien lo contiene y sus pruebas; paso 5.3a).
1.0.1 Ventana de prueba: el modo de la pendiente elegido en el desplegable llegaba como
      texto y el perfil salía sin colores (lo arregla también 'ProfileStyle' 1.0.1).
1.0.0 Primera versión (15/11/2026; docs/MAPA.md, paso 5.2).

Prueba rápida (desde la raíz del proyecto; sin ventana):
    python -m ui_helpers.widgets.elevation_profile
Para ver y ajustar el aspecto (abre una ventana y se queda abierta; con un GPX o, sin él,
con un track inventado):
    python -m ui_helpers.widgets.elevation_profile --ventana [archivo.gpx]
"""

__version__ = "1.1.0"
__all__ = ["ElevationProfile"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QRectF, QSize, Qt, Signal
from qtpy.QtGui import (
    QFont,
    QFontMetricsF,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
)
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from core.tracks.gpx_document import PathSegment, TrackPath
from core.tracks.profile import ElevationProfileData, drawing_runs, index_at_distance, range_stats
from ui_helpers.helpers.profile_format import range_text, totals_text
from ui_helpers.helpers.profile_painter import (
    ProfileLayout,
    build_layout,
    paint_overlay,
    render_static,
)
from ui_helpers.helpers.profile_style import ProfileStyle, slope_bands
from ui_helpers.helpers.ui_theme import PROFILE_COLORS

# Aviso de un track sin altitud (la línea de arriba sigue diciendo su distancia)
_NO_ELEVATION = "Este track no tiene datos de altitud"

# Píxeles que hay que mover el ratón con el botón pulsado para que cuente como arrastre
_DRAG_THRESHOLD_PX = 3


class ElevationProfile(QWidget):
    """El perfil de elevación (ver el docstring del archivo).

    Signals:
        cursor_moved(int): punto bajo el ratón (índice del recorrido); -1 al salir.
        range_selected(int, int): tramo elegido arrastrando (primero, último), cada vez
            que cambia.
        selection_cleared(): el usuario ha quitado el tramo (clic sin arrastrar).
    """

    cursor_moved = Signal(int)
    range_selected = Signal(int, int)
    selection_cleared = Signal()

    def __init__(self, parent: QWidget | None = None, style: ProfileStyle | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("elevation_profile")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Se pinta entero (el fondo también): Qt no tiene que borrarlo antes
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumHeight(60)
        self._style = style if style is not None else ProfileStyle(PROFILE_COLORS)
        self._data: ElevationProfileData | None = None
        self._message = ""
        self._cursor: int | None = None
        self._selection: tuple[int, int] | None = None
        self._header = ""
        # Arrastre: dónde se pulsó (x) y en qué punto; si ya cuenta como arrastre
        self._press_x: float | None = None
        self._anchor: int | None = None
        self._dragging = False
        # Lo que se calcula al cambiar el tamaño, el perfil o el estilo (las franjas de la
        # pendiente, solo al cambiar el perfil o el estilo: None = por calcular)
        self._layout: ProfileLayout | None = None
        self._runs: list[list[int]] = []
        self._bands: list[int] | None = None
        self._static: QPixmap | None = None

    # -------------------------------------------------------------------------
    # Lo que se llama desde fuera
    # -------------------------------------------------------------------------

    def set_profile(self, data: ElevationProfileData | None, message: str = "") -> None:
        """Muestra un perfil (None, ninguno: se ve 'message' en el centro). Quita el cursor
        y el tramo elegido."""
        self._data = data if data is not None and data.point_count else None
        self._message = message if self._data is None else ""
        if self._data is not None and not self._data.has_elevation:
            self._message = _NO_ELEVATION
        self._cursor = None
        self._selection = None
        self._end_drag()
        self._update_header()
        self._bands = None
        self._invalidate()

    def clear(self, message: str = "") -> None:
        """Sin perfil; 'message' en el centro (p. ej., que no hay ningún track elegido)."""
        self.set_profile(None, message)

    def profile(self) -> ElevationProfileData | None:
        """El perfil que se ve (None, ninguno)."""
        return self._data

    def message(self) -> str:
        """El aviso del centro ("" si no hay: se ve un perfil con altitud)."""
        return self._message

    def set_style(self, style: ProfileStyle) -> None:
        """Cambia el aspecto (colores, grosores, cómo se ve la pendiente...)."""
        self._style = style
        self._bands = None
        self._invalidate()

    def profile_style(self) -> ProfileStyle:
        """El estilo con el que se dibuja ('style()' es de Qt: otra cosa)."""
        return self._style

    def set_cursor(self, index: int | None) -> None:
        """Pone el cursor en un punto (None, lo quita), p. ej. porque el ratón pasa por el
        mapa. No emite 'cursor_moved'."""
        if index is not None and (self._data is None or not 0 <= index < self._data.point_count):
            index = None
        if index != self._cursor:
            self._cursor = index
            self.update()

    def cursor_index(self) -> int | None:
        """El punto del cursor (None, sin cursor)."""
        return self._cursor

    def set_selection(self, first: int, last: int) -> None:
        """Elige un tramo (da igual el orden de los dos puntos). No emite señales."""
        count = self._data.point_count if self._data is not None else 0
        if not (0 <= first < count and 0 <= last < count):
            return
        self._set_selection((min(first, last), max(first, last)))

    def clear_selection(self) -> None:
        """Quita el tramo elegido. No emite señales."""
        self._set_selection(None)

    def selection(self) -> tuple[int, int] | None:
        """El tramo elegido (primero, último), o None."""
        return self._selection

    # -------------------------------------------------------------------------
    # Qt
    # -------------------------------------------------------------------------

    def sizeHint(self) -> QSize:  # nombre de Qt
        return QSize(640, 160)

    def resizeEvent(self, event: QResizeEvent) -> None:  # nombre de Qt
        super().resizeEvent(event)
        self._invalidate()

    def changeEvent(self, event: QEvent) -> None:  # nombre de Qt
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._invalidate()

    def paintEvent(self, _event: QPaintEvent) -> None:  # nombre de Qt
        self._ensure_layout()
        painter = QPainter(self)
        if self._static is not None:
            painter.drawPixmap(0, 0, self._static)
        paint_overlay(
            painter, QRectF(self.rect()), self._font(), self._style, self._data, self._layout,
            header=self._header, message=self._message, cursor=self._cursor,
            selection=self._selection,
        )  # fmt: skip
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # nombre de Qt
        index = self._index_at(event.position().x())
        if index is None:
            return
        if self._press_x is not None and not self._dragging:
            self._dragging = abs(event.position().x() - self._press_x) >= _DRAG_THRESHOLD_PX
        if self._dragging and self._anchor is not None:
            chosen = (min(self._anchor, index), max(self._anchor, index))
            if chosen != self._selection and chosen[0] != chosen[1]:
                self._set_selection(chosen)
                self.range_selected.emit(*chosen)
        if index != self._cursor:
            self._cursor = index
            self.update()
            self.cursor_moved.emit(index)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # nombre de Qt
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        index = self._index_at(event.position().x())
        if index is not None:
            self._press_x = event.position().x()
            self._anchor = index
            self._dragging = False
        return None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # nombre de Qt
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        clicked = self._press_x is not None and not self._dragging
        self._end_drag()
        if clicked and self._selection is not None:
            self._set_selection(None)
            self.selection_cleared.emit()
        if not self.rect().contains(event.position().toPoint()):
            self._leave()  # se soltó fuera: el ratón ya no está encima
        return None

    def leaveEvent(self, event: QEvent) -> None:  # nombre de Qt
        super().leaveEvent(event)
        if not self._dragging:
            self._leave()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _font(self) -> QFont:
        font = QFont(self.font())
        if self._style.font_point_size is not None:
            font.setPointSizeF(self._style.font_point_size)
        return font

    def _invalidate(self) -> None:
        """Lo calculado ya no vale (tamaño, perfil o estilo nuevos): se rehace al pintar."""
        self._layout = None
        self._static = None
        self.update()

    def _ensure_layout(self) -> None:
        if self._static is not None:
            return
        font = self._font()
        rect, metrics = QRectF(self.rect()), QFontMetricsF(font)
        self._layout = build_layout(rect, metrics, self._style, self._data)
        self._runs = []
        if self._layout is not None and self._data is not None:
            self._runs = drawing_runs(self._data, max(1, int(self._layout.plot.width())))
            if self._bands is None:
                style = self._style
                self._bands = slope_bands(
                    self._data.slopes, self._data.segment_starts, style.slope_thresholds_pct,
                    style.slope_hysteresis_pct,
                )  # fmt: skip
        self._static = render_static(
            self.size(), self.devicePixelRatioF(), font, self._style, self._data, self._layout,
            self._runs, self._bands or [],
        )  # fmt: skip

    def _index_at(self, x: float) -> int | None:
        """El punto del recorrido bajo una posición horizontal (None si no hay curva)."""
        self._ensure_layout()
        if self._data is None or self._layout is None:
            return None
        return index_at_distance(self._data, self._layout.distance_at(x))

    def _set_selection(self, selection: tuple[int, int] | None) -> None:
        if selection != self._selection:
            self._selection = selection
            self._update_header()
            self.update()

    def _update_header(self) -> None:
        """La línea de arriba: el tramo elegido o, sin él, los totales."""
        if self._data is None:
            self._header = ""
        elif self._selection is not None:
            self._header = range_text(range_stats(self._data, *self._selection))
        else:
            self._header = totals_text(self._data.totals)

    def _end_drag(self) -> None:
        self._press_x = None
        self._anchor = None
        self._dragging = False

    def _leave(self) -> None:
        """El ratón ha salido: sin cursor (y se avisa)."""
        if self._cursor is not None:
            self._cursor = None
            self.update()
            self.cursor_moved.emit(-1)


# -----------------------------------------------------------------------------
# Pruebas
# -----------------------------------------------------------------------------


def _synthetic_path() -> TrackPath:
    """Un track inventado de unos 6,3 km: sube con pendientes de todo tipo, llanea y baja;
    con una pausa del GPS (dos segmentos), un hueco sin altitud, ruido de ±1,5 m y hora."""
    import math
    from array import array

    pieces = [(1000, 3), (800, 8), (600, 13), (400, 18), (300, 26), (500, 0),  # (m, %)
              (900, -12), (1500, -6), (300, -22)]  # fmt: skip
    step_m, metres_per_degree = 6.0, 111_195.0
    segments, current = [], None
    latitude, elevation, moment, k = 42.6, 1300.0, 1_714_550_400.0, 0
    for number, (length, slope) in enumerate(pieces):
        if number in (0, 6):  # la pausa del GPS: otro segmento, 200 m más allá
            if number:
                latitude += 200 / metres_per_degree
            current = PathSegment(array("d"), array("d"), array("d"), array("d"))
            segments.append(current)
        for _ in range(int(length / step_m)):
            latitude += step_m / metres_per_degree
            elevation += slope / 100 * step_m
            noise = ((k * 7919) % 7 - 3) * 0.5
            current.latitudes.append(latitude)
            current.longitudes.append(0.0)
            current.elevations.append(math.nan if 300 <= k < 312 else elevation + noise)
            current.times.append(moment)
            moment += step_m / 1.1  # a 4 km/h
            k += 1
    return TrackPath(tuple(segments))


def _self_test() -> None:
    """Autoprueba sin ventana: se dibuja en memoria y se le mandan eventos del ratón."""
    import math
    import sys
    from array import array
    from dataclasses import replace

    from qtpy.QtCore import QPointF
    from qtpy.QtGui import QColor, QImage
    from qtpy.QtWidgets import QApplication

    from core.tracks.profile import build_profile
    from ui_helpers.helpers.profile_style import SlopeMode, slope_band

    app = QApplication.instance() or QApplication(sys.argv[:1])
    assert app is not None
    data = build_profile(_synthetic_path())
    assert len(data.segment_starts) == 2 and data.has_elevation

    profile = ElevationProfile()
    profile.resize(900, 220)
    seen: list[tuple] = []
    profile.cursor_moved.connect(lambda i: seen.append(("cursor", i)))
    profile.range_selected.connect(lambda a, b: seen.append(("range", a, b)))
    profile.selection_cleared.connect(lambda: seen.append(("cleared",)))

    def mouse(kind: QEvent.Type, x: float, buttons: Qt.MouseButton = Qt.MouseButton.NoButton) -> None:
        button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
        point = QPointF(x, 110)
        event = QMouseEvent(kind, point, point, button, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(profile, event)

    def pixel(image: QImage, x: float, y: float) -> QColor:
        return image.pixelColor(int(x), int(y))

    def close(color: QColor, expected: QColor, tolerance: int = 6) -> bool:
        return all(abs(a - b) <= tolerance for a, b in zip(color.getRgb()[:3], expected.getRgb()[:3], strict=True))

    # --- Sin perfil: el aviso, y el ratón no hace nada
    profile.clear("Selecciona un track para ver su perfil")
    image = profile.grab().toImage()
    background = QColor(PROFILE_COLORS.background)
    assert close(pixel(image, 5, 5), background)
    mouse(QEvent.Type.MouseMove, 300)
    assert seen == [] and profile.cursor_index() is None

    # --- Con perfil (pendiente en el área, el estilo de partida)
    profile.set_profile(data)
    image = profile.grab().toImage()
    layout = profile._layout  # (la prueba mira dentro)
    assert layout is not None and layout.x_ticks[0] == 0 and layout.y_ticks
    assert layout.altitude_low <= data.totals.elevation_min_m <= data.totals.elevation_max_m <= layout.altitude_high
    # Un poco por debajo de la curva, el color de la franja de su pendiente (con su
    # opacidad sobre el fondo), en un punto de cada franja
    style = profile.profile_style()
    targets = (500, 1300, 2100, 2600, 2950)  # metros: 3, 8, 13, 18 y 26 %
    for expected_band, target in enumerate(targets):
        index = index_at_distance(data, target)
        band = profile._bands[index] if profile._bands else -2
        assert band == expected_band == slope_band(data.slopes[index], style.slope_thresholds_pct)
        x, y = layout.x(data.distances[index]), layout.y(data.smoothed[index])
        expected = QColor(style.colors.slope[band])
        alpha = style.slope_area_opacity
        blend = QColor.fromRgbF(*(alpha * c + (1 - alpha) * b for c, b in
                                  zip(expected.getRgbF()[:3], background.getRgbF()[:3], strict=True)))  # fmt: skip
        found = pixel(image, x, min(layout.plot.bottom() - 2, y + 12))
        assert close(found, blend), (target, band, found.name(), blend.name())
    # Encima de la curva, el fondo
    index = index_at_distance(data, 1300)
    assert close(pixel(image, layout.x(data.distances[index]), layout.plot.top() + 3), background)

    # --- El ratón: el cursor sigue al punto más cercano y avisa al cambiar
    x = layout.x(data.distances[400])
    mouse(QEvent.Type.MouseMove, x)
    assert seen[-1] == ("cursor", profile.cursor_index()) and abs(profile.cursor_index() - 400) <= 1
    count = len(seen)
    mouse(QEvent.Type.MouseMove, x)  # el mismo punto: sin aviso
    assert len(seen) == count
    image = profile.grab().toImage()
    line_x = int(layout.x(data.distances[profile.cursor_index()]))
    assert close(pixel(image, line_x, layout.plot.top() + 2), QColor(PROFILE_COLORS.cursor), 30)
    QApplication.sendEvent(profile, QEvent(QEvent.Type.Leave))
    assert seen[-1] == ("cursor", -1) and profile.cursor_index() is None

    # --- Desde fuera (el mapa): sin avisos
    seen.clear()
    profile.set_cursor(250)
    assert profile.cursor_index() == 250 and seen == []
    profile.set_cursor(10**6)  # no existe: sin cursor
    assert profile.cursor_index() is None
    profile.set_selection(900, 100)
    assert profile.selection() == (100, 900) and seen == []
    assert profile._header.startswith("Tramo ")
    profile.clear_selection()
    assert profile.selection() is None and profile._header.startswith("Distancia ")

    # --- Arrastrar elige un tramo; un clic lo quita
    left, right = layout.x(data.distances[200]), layout.x(data.distances[600])
    mouse(QEvent.Type.MouseButtonPress, left, Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseMove, left + 1, Qt.MouseButton.LeftButton)  # aún no es arrastre
    assert profile.selection() is None
    mouse(QEvent.Type.MouseMove, right, Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseButtonRelease, right)
    first, last = profile.selection()
    assert abs(first - 200) <= 1 and abs(last - 600) <= 1 and ("range", first, last) in seen
    image = profile.grab().toImage()  # la banda del tramo, sin errores
    seen.clear()
    mouse(QEvent.Type.MouseButtonPress, right, Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseButtonRelease, right)
    assert profile.selection() is None and seen == [("cleared",)]
    mouse(QEvent.Type.MouseButtonPress, right, Qt.MouseButton.LeftButton)  # sin tramo: nada
    mouse(QEvent.Type.MouseButtonRelease, right)
    assert seen == [("cleared",)]

    # --- Los otros modos de la pendiente y otro estilo: bajo la curva, el área en su color
    for mode in (SlopeMode.LINE, SlopeMode.OFF):
        profile.set_style(replace(style, slope_mode=mode, grid_pattern="dash", font_point_size=8))
        image = profile.grab().toImage()
        new_layout = profile._layout
        assert new_layout is not None
        index = index_at_distance(data, 2950)
        x, y = new_layout.x(data.distances[index]), new_layout.y(data.smoothed[index])
        assert close(pixel(image, x, min(new_layout.plot.bottom() - 2, y + 12)), QColor(style.colors.area))
    profile.set_style(style)

    # --- Un track sin altitud: el aviso; el ratón no hace nada
    segment = _synthetic_path().segments[0]
    nothing = array("d", [math.nan]) * len(segment)
    flat = build_profile(TrackPath((PathSegment(segment.latitudes, segment.longitudes, nothing, nothing),)))
    profile.set_profile(flat)
    assert profile._message == _NO_ELEVATION and profile._header.startswith("Distancia ")
    seen.clear()
    mouse(QEvent.Type.MouseMove, 300)
    assert seen == [] and profile.grab().toImage().width() == 900

    # --- Tamaños pequeños o raros, sin errores
    profile.set_profile(data)
    for width, height in ((120, 60), (2000, 400), (300, 61)):
        profile.resize(width, height)
        profile.grab()
    print("Autoprueba finalizada correctamente.")


def _window(gpx: str | None) -> None:
    """Ventana para ver y ajustar el aspecto, con un GPX o con el track inventado."""
    import sys
    from dataclasses import replace

    from qtpy.QtGui import QKeySequence, QShortcut
    from qtpy.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QHBoxLayout,
        QLabel,
        QSlider,
        QVBoxLayout,
    )

    from core.tracks.gpx_document import read_gpx_path
    from core.tracks.profile import build_profile
    from ui_helpers.helpers.profile_style import SlopeMode
    from ui_helpers.helpers.ui_theme import apply_theme

    app = QApplication(sys.argv[:1])
    apply_theme()
    data = build_profile(read_gpx_path(gpx) if gpx else _synthetic_path())

    window = QWidget()
    window.setWindowTitle(f"ElevationProfile (prueba) — {gpx or 'track inventado'}")
    window.resize(1300, 320)
    layout = QVBoxLayout(window)
    bar = QHBoxLayout()
    layout.addLayout(bar)
    profile = ElevationProfile(window)
    layout.addWidget(profile, 1)

    modes = QComboBox(window)
    for text, mode in (("En el área", SlopeMode.AREA), ("En la línea", SlopeMode.LINE),
                       ("Sin colores", SlopeMode.OFF)):  # fmt: skip
        modes.addItem(text, mode)
    # (el desplegable devuelve el modo como texto: 'SlopeMode(...)' lo vuelve a convertir)
    modes.currentIndexChanged.connect(
        lambda _i: profile.set_style(
            replace(profile.profile_style(), slope_mode=SlopeMode(modes.currentData()))
        )
    )
    bar.addWidget(QLabel("Pendiente:", window))
    bar.addWidget(modes)
    # El mapa simulado: mueve el cursor del perfil desde fuera, como hará el mapa
    slider = QSlider(Qt.Orientation.Horizontal, window)
    slider.setRange(-1, data.point_count - 1)
    slider.setValue(-1)
    slider.valueChanged.connect(lambda value: profile.set_cursor(value if value >= 0 else None))
    bar.addWidget(QLabel("Mapa simulado:", window))
    bar.addWidget(slider, 1)
    empty = QCheckBox("Sin track", window)
    empty.toggled.connect(lambda on: profile.clear("Selecciona un track para ver su perfil") if on
                          else profile.set_profile(data))  # fmt: skip
    bar.addWidget(empty)
    log = QLabel("", window)
    log.setMinimumWidth(260)
    bar.addWidget(log)
    profile.cursor_moved.connect(lambda i: log.setText(f"cursor_moved({i})"))
    profile.range_selected.connect(lambda a, b: log.setText(f"range_selected({a}, {b})"))
    profile.selection_cleared.connect(lambda: log.setText("selection_cleared()"))
    escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), window)
    escape.activated.connect(profile.clear_selection)

    profile.set_profile(data)
    window.show()
    app.exec()


if __name__ == "__main__":
    # Ejecutar desde la raíz del proyecto:
    #   python -m ui_helpers.widgets.elevation_profile [--ventana [archivo.gpx]]
    import sys

    if "--ventana" in sys.argv:
        arguments = sys.argv[sys.argv.index("--ventana") + 1 :]
        _window(arguments[0] if arguments else None)
    else:
        _self_test()
