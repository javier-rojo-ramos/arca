"""Página «Tracks» de la ventana de opciones: lo básico del aspecto de los tracks.

    Colores en el mapa
        Track elegido       [■ #e5383b]
        Los demás tracks    [■ #2f6fd6]
        [Restaurar los colores de fábrica]
    Perfil de elevación
        Colores de la pendiente   [ En el área ▾ ]
        [✓] Mostrar información de puntos de interés también al recorrer el perfil...

- Cada color es un botón con su muestra; al pulsarlo, el selector de colores de Qt.
- Los de fábrica son los del tema ('track_appearance.default_track_colors').
- La pendiente es la misma opción que el menú del botón derecho sobre el perfil.
- La casilla: con el ratón sobre el perfil, el punto ámbar del mapa enseña el texto del
  waypoint por el que pasa (como con el ratón en el mapa). Activada de partida.
- Como el resto de la ventana, se guarda al pulsar «Aceptar» ('save'): settings.json,
  'map_track_colors' (solo los colores que no son los del tema), 'profile_slope_mode' y
  'profile_waypoint_tips'. El controlador del mapa los aplica al momento
  ('MapController.apply_settings').

Pedida por el autor el 15/11/2026, al cerrar la fase 5 de docs/MOD_TRACKS.md: más adelante
puede crecer con el resto del estilo del perfil ('ProfileStyle').

1.1.0 La casilla del texto de los waypoints al recorrer el perfil (el autor, 22/11/2026:
      su texto, activada de partida y sin línea de ayuda).
1.0.0 Primera versión (15/11/2026).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.dialogs.tracks_settings_page
La página se ve en la prueba de la ventana de opciones ('settings_dialog', abre una ventana).
"""

__version__ = "1.1.0"
__all__ = ["TracksSettingsPage"]

# Librerías estándar
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QSize, Signal
from qtpy.QtGui import QColor, QIcon, QPainter, QPixmap
from qtpy.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

# Módulos del proyecto
from config.app_constants import (
    SETTING_MAP_TRACK_COLORS,
    SETTING_PROFILE_SLOPE_MODE,
    SETTING_PROFILE_WAYPOINT_TIPS,
    AppIcons,
)
from ui_helpers.dialogs.settings_dialog import SettingsPage
from ui_helpers.helpers.profile_style import SLOPE_MODE_LABELS, SLOPE_MODE_TITLE, SlopeMode
from ui_helpers.helpers.track_appearance import (
    TrackColors,
    default_track_colors,
    profile_waypoint_tips,
    slope_mode,
    track_colors,
    track_colors_to_settings,
)
from ui_helpers.helpers.ui_theme import COLORS

# Textos de la página (propuestos por el asistente el 15/11/2026)
_COLORS_TITLE = "Colores en el mapa"
_ACTIVE_LABEL = "Track elegido"
_TRACK_LABEL = "Los demás tracks"
_RESET = "Restaurar los colores de fábrica"
_COLORS_HELP = (
    "El track elegido se ve con su color y por encima de los demás, que se atenúan. Los de "
    "fábrica son los del tema de la aplicación."
)
_PROFILE_TITLE = "Perfil de elevación"
_SLOPE_HELP = (
    "Cómo se ven, de verde a rojo, las pendientes del perfil, bajo el mapa del módulo "
    "Tracks. También se cambia con el botón derecho sobre el perfil."
)
# El del autor (22/11/2026), sin línea de ayuda: se entiende solo
_WAYPOINT_TIPS = (
    "Mostrar información de puntos de interés también al recorrer el perfil de elevación"
)

# Muestra del color en el botón (px)
_SWATCH = QSize(28, 14)


class _ColorButton(QPushButton):
    """Botón con la muestra de un color: al pulsarlo, el selector de colores de Qt.

    Signals:
        color_changed(str): se ha elegido otro color ("#rrggbb").
    """

    color_changed = Signal(str)

    def __init__(self, dialog_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dialog_title = dialog_title
        self._color = ""
        self.setIconSize(_SWATCH)
        self.clicked.connect(self._choose)

    def color(self) -> str:
        """El color que muestra ("#rrggbb")."""
        return self._color

    def set_color(self, color: str) -> None:
        """Pone un color ("#rrggbb"); avisa con 'color_changed' si cambia."""
        color = QColor(color).name()  # en minúsculas y siempre de 6 cifras
        if color == self._color:
            return
        self._color = color
        self.setText(color)
        self.setIcon(self._swatch(color))
        self.color_changed.emit(color)

    @staticmethod
    def _swatch(color: str) -> QIcon:
        """La muestra: un rectángulo del color, con un borde fino para que se vea sobre
        cualquier fondo."""
        pixmap = QPixmap(_SWATCH)
        pixmap.fill(QColor(color))
        painter = QPainter(pixmap)
        painter.setPen(QColor(COLORS.line))
        painter.drawRect(0, 0, _SWATCH.width() - 1, _SWATCH.height() - 1)
        painter.end()
        return QIcon(pixmap)

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, self._dialog_title)
        if chosen.isValid():  # «Cancelar» devuelve un color no válido
            self.set_color(chosen.name())


class TracksSettingsPage(SettingsPage):
    """Sección «Tracks»: colores de los tracks en el mapa y la pendiente del perfil."""

    title = "Tracks"
    icon = AppIcons.LIB_TRACKS

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)

        # --- Colores en el mapa ---
        self.body.addWidget(QLabel(f"<b>{_COLORS_TITLE}</b>"))
        self.button_active = _ColorButton(f"{_COLORS_TITLE}: {_ACTIVE_LABEL.lower()}")
        self.button_track = _ColorButton(f"{_COLORS_TITLE}: {_TRACK_LABEL.lower()}")
        grid = QGridLayout()
        grid.addWidget(QLabel(_ACTIVE_LABEL), 0, 0)
        grid.addWidget(self.button_active, 0, 1)
        grid.addWidget(QLabel(_TRACK_LABEL), 1, 0)
        grid.addWidget(self.button_track, 1, 1)
        grid.setColumnStretch(2, 1)
        self.body.addLayout(grid)
        self.button_reset = QPushButton(_RESET)
        self.button_reset.clicked.connect(self._reset_colors)
        reset_row = QHBoxLayout()
        reset_row.addWidget(self.button_reset)
        reset_row.addStretch(1)
        self.body.addLayout(reset_row)
        self.body.addWidget(self._help(_COLORS_HELP))

        # --- Perfil de elevación ---
        self.body.addSpacing(6)
        self.body.addWidget(QLabel(f"<b>{_PROFILE_TITLE}</b>"))
        self.combo_slope = QComboBox()
        for mode, label in SLOPE_MODE_LABELS.items():
            # El valor, como texto: así vuelve del desplegable (docs/TRAMPAS.md)
            self.combo_slope.addItem(label, mode.value)
        slope_row = QHBoxLayout()
        slope_row.addWidget(QLabel(SLOPE_MODE_TITLE))
        slope_row.addWidget(self.combo_slope)
        slope_row.addStretch(1)
        self.body.addLayout(slope_row)
        self.body.addWidget(self._help(_SLOPE_HELP))
        self.check_waypoint_tips = QCheckBox(_WAYPOINT_TIPS)
        self.body.addWidget(self.check_waypoint_tips)

    @classmethod
    def _help(cls, text: str) -> QLabel:
        label = cls.make_help_label(text)
        label.setContentsMargins(0, 0, 0, 4)  # aquí no hay casilla con la que alinearse
        return label

    def _reset_colors(self) -> None:
        default = default_track_colors()
        self.button_active.set_color(default.active)
        self.button_track.set_color(default.track)

    def _chosen_colors(self) -> TrackColors:
        return TrackColors(self.button_active.color(), self.button_track.color())

    def _chosen_mode(self) -> SlopeMode:
        return SlopeMode(self.combo_slope.currentData())

    # --- Cargar y guardar ---

    def load(self) -> None:
        colors = track_colors(self.config)
        self.button_active.set_color(colors.active)
        self.button_track.set_color(colors.track)
        self.combo_slope.setCurrentIndex(max(0, self.combo_slope.findData(slope_mode(self.config).value)))
        self.check_waypoint_tips.setChecked(profile_waypoint_tips(self.config))

    def save(self) -> set[str]:
        changed: set[str] = set()
        colors = track_colors_to_settings(self._chosen_colors())
        if colors != track_colors_to_settings(track_colors(self.config)):
            self.config.set(SETTING_MAP_TRACK_COLORS, colors)
            changed.add(SETTING_MAP_TRACK_COLORS)
        mode = self._chosen_mode()
        if mode is not slope_mode(self.config):
            self.config.set(SETTING_PROFILE_SLOPE_MODE, mode.value)
            changed.add(SETTING_PROFILE_SLOPE_MODE)
        tips = self.check_waypoint_tips.isChecked()
        if tips is not profile_waypoint_tips(self.config):
            self.config.set(SETTING_PROFILE_WAYPOINT_TIPS, tips)
            changed.add(SETTING_PROFILE_WAYPOINT_TIPS)
        return changed


if __name__ == "__main__":
    # Autoprueba sin ventana: la página con una configuración en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.tracks_settings_page
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])

    class _Config(dict):
        def set(self, key: str, value: Any) -> None:
            self[key] = value

    default = default_track_colors()

    # --- Sin nada guardado: los del tema y la pendiente en el área; guardar, nada cambia
    config = _Config()
    page = TracksSettingsPage(config, {})
    page.load()
    assert page.button_active.color() == default.active.lower()
    assert page.button_track.color() == default.track.lower()
    assert page.button_active.text() == default.active.lower()
    assert page._chosen_mode() is SlopeMode.AREA
    assert page.check_waypoint_tips.isChecked()  # activada de partida
    assert page.save() == set() and config == {}

    # --- Otros colores y otro modo: se guarda solo lo que no es del tema
    seen: list[str] = []
    page.button_track.color_changed.connect(seen.append)
    page.button_track.set_color("#00AA55")
    page.button_track.set_color("#00aa55")  # el mismo: sin aviso
    assert seen == ["#00aa55"]
    page.combo_slope.setCurrentIndex(page.combo_slope.findData("line"))
    assert page.save() == {SETTING_MAP_TRACK_COLORS, SETTING_PROFILE_SLOPE_MODE}
    assert config[SETTING_MAP_TRACK_COLORS] == {"track": "#00aa55"}
    assert config[SETTING_PROFILE_SLOPE_MODE] == "line"
    assert page.save() == set()  # otra vez, sin cambios

    # --- Abrir de nuevo: lo guardado
    page = TracksSettingsPage(config, {})
    page.load()
    assert page.button_track.color() == "#00aa55" and page._chosen_mode() is SlopeMode.LINE

    # --- La casilla de los waypoints: desmarcada se guarda (un no); marcada otra vez, un sí
    page.check_waypoint_tips.setChecked(False)
    assert page.save() == {SETTING_PROFILE_WAYPOINT_TIPS}
    assert config[SETTING_PROFILE_WAYPOINT_TIPS] is False
    page = TracksSettingsPage(config, {})
    page.load()
    assert not page.check_waypoint_tips.isChecked()
    page.check_waypoint_tips.setChecked(True)
    assert page.save() == {SETTING_PROFILE_WAYPOINT_TIPS}
    assert config[SETTING_PROFILE_WAYPOINT_TIPS] is True

    # --- Restaurar los de fábrica
    page.button_reset.click()
    assert page.button_active.color() == default.active.lower()
    assert page.button_track.color() == default.track.lower()
    assert page.save() == {SETTING_MAP_TRACK_COLORS} and config[SETTING_MAP_TRACK_COLORS] == {}

    # --- Algo raro guardado: los de partida, sin errores
    page = TracksSettingsPage(
        _Config({SETTING_MAP_TRACK_COLORS: "x", SETTING_PROFILE_SLOPE_MODE: 3,
                 SETTING_PROFILE_WAYPOINT_TIPS: "no"}),
        {},
    )  # fmt: skip
    page.load()
    assert page.button_active.color() == default.active.lower() and page._chosen_mode() is SlopeMode.AREA
    assert page.check_waypoint_tips.isChecked()
    print("Autoprueba finalizada correctamente.")
