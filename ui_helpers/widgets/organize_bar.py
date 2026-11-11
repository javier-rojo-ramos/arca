"""Barra para clasificar lo seleccionado: marca, valoración, etiqueta de color y selección rápida.

Va centrada en la barra inferior de la ventana ('frame_main_bottom'), como la barra de la
Biblioteca de Lightroom, y es común a todos los módulos:

    [□] [✕]   ★★★★★   ■ ■ ■ ■ ■   ●
     │   │      │         │        └─ selección rápida (B)
     │   │      │         └─ etiqueta roja, amarilla, verde, azul (6-9) y púrpura
     │   │      └─ valoración (0-5)
     │   └─ rechazar (X)
     └─ marcar (P)

Todo se dibuja con 'ui_helpers/helpers/card_marks.py', las mismas funciones que la tarjeta
de la cuadrícula: el recuadro de marcada, la X, las estrellas y el círculo son idénticos.

Comportamiento (el mismo que los atajos de teclado):
    - Actúa sobre la SELECCIÓN de la cuadrícula. Sin selección, se ve atenuada y no responde.
    - Muestra el estado de lo seleccionado: si todo tiene el mismo valor, se ve activo (las
      estrellas rellenas, el recuadro blanco, el color con un anillo, el círculo blanco);
      si hay valores distintos, no se marca nada.
    - Al pulsar un elemento, se aplica a toda la selección; si TODA ya lo tenía, se quita
      (sin estrellas, sin marca, sin color, fuera de la selección rápida).
    - Escribe a través del modelo ('MediaGridModel.set_field'), como la tarjeta y el
      teclado: el controlador lo guarda en el catálogo y en los archivos igual.
    - Se mantiene al día sola: escucha los cambios de la selección y de los datos del
      modelo (también los que se hacen con el teclado o en la tarjeta).
    - No coge el foco: tras pulsarla, los atajos de la cuadrícula siguen funcionando.

Uso (en el .ui es un widget promocionado, 'widget_organize_bar'):
    self.widget_organize_bar.attach(self.list_view_grid, self.mosaico_model)

1.1.0 El fondo bajo el ratón y el anillo del color activo, los mismos que la fila
      «Atributos» de la barra de filtros (del tema: 'bg_hover' y 'text'; antes, blanco
      translúcido y blanco, que en un tema claro no se verían). Decidido por el autor el
      09/11/2026.
1.0.0 Primera versión (barra inferior, paso 2).
"""

__version__ = "1.1.0"
__all__ = ["MIXED", "OrganizeBar", "common_value", "toggled_value"]

# Librerías estándar
from collections.abc import Iterable
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer
from qtpy.QtGui import QColor, QFont, QPainter, QPen
from qtpy.QtWidgets import QListView, QSizePolicy, QToolTip, QWidget

# Módulos del proyecto
from core.catalog.color_labels import COLOR_LABELS
from ui_helpers.helpers import card_marks
from ui_helpers.helpers.ui_color_labels import LABEL_TEXTS, label_color
from ui_helpers.helpers.ui_theme import COLORS, GRID_BG
from ui_helpers.models.media_grid_model import QUICK_SELECTION_FIELD, MediaGridModel
from ui_helpers.models.media_roles import (
    ROLE_COLOR_LABEL,
    ROLE_FLAG,
    ROLE_QUICK_SELECTION,
    ROLE_RATING,
)

# Valor "hay valores distintos en la selección" (no es ningún valor válido)
MIXED = object()

# --- Medidas (px lógicos) ---
_HEIGHT = 26  # alto de la barra
_FLAG_W, _FLAG_H = 10, 14  # recuadro de la marca (en la tarjeta, 8 × 11)
_STAR_W = 16  # ancho de cada estrella (en la tarjeta, 12)
_SWATCH = 12  # lado del cuadrado de cada color
_QUICK = 14  # diámetro del círculo de la selección rápida (en la tarjeta, 16)
_ITEM_GAP = 8  # entre los dos botones de la marca
_SWATCH_GAP = 5  # entre dos colores
_GROUP_GAP = 20  # entre grupos (marca · estrellas · colores · selección rápida)
_HIT_PAD = 3  # margen extra alrededor de cada zona para acertar con el clic

# --- Colores propios de la barra (los de las marcas, en 'card_marks') ---
_INACTIVE_CROSS = COLORS.text_disabled  # X de "rechazar" cuando no está activa (tema)
_HOVER_BG = COLORS.bg_hover  # fondo de la zona bajo el ratón (como «Atributos»)
_RING_COLOR = COLORS.text  # anillo del color activo (como «Atributos»)
_DISABLED_OPACITY = 0.35  # sin selección

# Teclas de cada color, para los textos emergentes (la púrpura no tiene)
_COLOR_KEYS = {"red": "6", "yellow": "7", "green": "8", "blue": "9"}


def common_value(values: Iterable[Any]) -> Any:
    """El valor que comparten todos, 'MIXED' si hay varios distintos, o None si no hay ninguno."""
    distinct = set(values)
    if not distinct:
        return None
    return next(iter(distinct)) if len(distinct) == 1 else MIXED


def toggled_value(current: Any, chosen: Any, empty: Any) -> Any:
    """Valor a aplicar al pulsar 'chosen': si TODA la selección ya lo tiene, 'empty'.

    Args:
        current: Valor común de la selección ('common_value'; puede ser 'MIXED').
        chosen: Lo que representa lo pulsado (3 estrellas, 'red', marcada...).
        empty: El valor "sin nada" (0 estrellas, None, sin marca, fuera).
    """
    return empty if current == chosen else chosen


class OrganizeBar(QWidget):
    """Barra de marca, valoración, color y selección rápida (ver el docstring del módulo)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("widget_organize_bar")
        self.setMouseTracking(True)  # para resaltar la zona bajo el ratón
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # los atajos siguen en la cuadrícula
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._star_font = QFont("Arial", 12)

        self._view: QListView | None = None
        self._model: MediaGridModel | None = None
        # Estado de la selección: None = sin selección; si no, el valor común o 'MIXED'
        self._state: dict[str, Any] = {}
        self._hovered: str | None = None
        self._zones = self._build_zones()

        # Los avisos de la selección y del modelo llegan en ráfagas: se juntan en uno
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def attach(self, view: QListView, model: MediaGridModel) -> None:
        """Conecta la barra a la cuadrícula: su selección y su modelo.

        Llamar después de 'view.setModel(model)' (la selección es del modelo de la vista).
        """
        self._view = view
        self._model = model
        view.selectionModel().selectionChanged.connect(self._schedule_refresh)
        model.dataChanged.connect(self._on_data_changed)
        model.modelReset.connect(self._schedule_refresh)
        model.rowsRemoved.connect(self._schedule_refresh)
        self._schedule_refresh()

    def sizeHint(self) -> QSize:  # nombre de Qt
        right = max(rect.right() for rect in self._zones.values())
        return QSize(right + 1 + _HIT_PAD, _HEIGHT)

    def minimumSizeHint(self) -> QSize:  # nombre de Qt
        return self.sizeHint()

    # -------------------------------------------------------------------------
    # Estado de la selección
    # -------------------------------------------------------------------------

    def _selected_rows(self) -> list[int]:
        if self._view is None or self._view.selectionModel() is None:
            return []
        return sorted({index.row() for index in self._view.selectionModel().selectedIndexes()})

    def _schedule_refresh(self, *_args: object) -> None:
        self._refresh_timer.start()

    def _on_data_changed(self, _top_left: object, _bottom_right: object, roles: list[int] = ()) -> None:
        """Solo interesan los cambios de valoración, marca, color o selección rápida.

        (Mientras se cargan las miniaturas llegan muchos avisos de la imagen: se ignoran.)
        """
        if not roles or set(roles) & {ROLE_RATING, ROLE_FLAG, ROLE_COLOR_LABEL, ROLE_QUICK_SELECTION}:
            self._schedule_refresh()

    def _refresh(self) -> None:
        """Recalcula el estado de la selección y repinta."""
        rows = self._selected_rows()
        if self._model is None or not rows:
            self._state = {}
        else:
            self._state = {
                field: common_value(self._model.field_values(field, rows))
                for field in ("rating", "flag", "color_label", QUICK_SELECTION_FIELD)
            }
        self.setEnabled(bool(self._state))
        self.update()

    # -------------------------------------------------------------------------
    # Zonas (dónde se dibuja y se pulsa cada elemento)
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_zones() -> dict[str, QRect]:
        """Rectángulo de cada elemento: 'pick', 'reject', 'star1'..'star5', 'color:red'..., 'quick'."""
        zones: dict[str, QRect] = {}
        x = _HIT_PAD
        middle = _HEIGHT // 2

        zones["pick"] = QRect(x, middle - _FLAG_H // 2, _FLAG_W, _FLAG_H)
        x += _FLAG_W + _ITEM_GAP
        zones["reject"] = QRect(x, middle - _FLAG_H // 2, _FLAG_W, _FLAG_H)
        x += _FLAG_W + _GROUP_GAP

        for number in range(1, 6):
            zones[f"star{number}"] = QRect(x, 0, _STAR_W, _HEIGHT)
            x += _STAR_W
        x += _GROUP_GAP

        for name in COLOR_LABELS:
            zones[f"color:{name}"] = QRect(x, middle - _SWATCH // 2, _SWATCH, _SWATCH)
            x += _SWATCH + _SWATCH_GAP
        x += _GROUP_GAP - _SWATCH_GAP

        zones["quick"] = QRect(x, middle - _QUICK // 2, _QUICK, _QUICK)
        return zones

    def _zone_at(self, pos: QPoint) -> str | None:
        """Zona bajo 'pos' (con un pequeño margen), o None."""
        for name, rect in self._zones.items():
            if rect.adjusted(-_HIT_PAD, -_HIT_PAD, _HIT_PAD, _HIT_PAD).contains(pos):
                return name
        return None

    def _tooltip(self, zone: str) -> str:
        """Texto emergente de cada zona (con su atajo de teclado)."""
        if zone == "pick":
            return "Marcar (P). Si todo ya está marcado, quita la marca."
        if zone == "reject":
            return "Rechazar (X). Si todo ya está rechazado, quita la marca."
        if zone.startswith("star"):
            number = zone[4:]
            stars = "1 estrella" if number == "1" else f"{number} estrellas"
            return f"Valoración: {stars} ({number}). Si ya la tiene, la quita (0)."
        if zone.startswith("color:"):
            name = zone.split(":", 1)[1]
            key = _COLOR_KEYS.get(name)
            shortcut = f" ({key})" if key else ""
            return f"Etiqueta {LABEL_TEXTS[name].lower()}{shortcut}. Si ya la tiene, la quita."
        return "Selección rápida (B). Si todo ya está dentro, lo saca."

    # -------------------------------------------------------------------------
    # Dibujo
    # -------------------------------------------------------------------------

    def paintEvent(self, _event: object) -> None:  # nombre de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(_DISABLED_OPACITY)

        # Fondo suave bajo la zona del ratón (para que se vea qué se va a pulsar)
        if self._hovered is not None and self.isEnabled():
            rect = self._zones[self._hovered].adjusted(-_HIT_PAD, -_HIT_PAD, _HIT_PAD, _HIT_PAD)
            if self._hovered.startswith("star"):
                rect.setTop(2)
                rect.setBottom(_HEIGHT - 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_HOVER_BG))
            painter.drawRoundedRect(QRectF(rect), 3, 3)

        flag = self._state.get("flag")
        # Marcar: recuadro blanco si todo está marcado; si no, su contorno
        card_marks.draw_flag(
            painter, self._zones["pick"],
            card_marks.FLAG_PICKED if flag == card_marks.FLAG_PICKED else card_marks.FLAG_NONE,
            hovered=True,
        )  # fmt: skip
        # Rechazar: la X de la tarjeta si todo está rechazado; si no, una X apagada
        active_reject = flag == card_marks.FLAG_REJECTED
        card_marks.draw_reject_cross(
            painter, self._zones["reject"],
            card_marks.REJECT_COLOR if active_reject else _INACTIVE_CROSS,
        )  # fmt: skip

        # Estrellas: las rellenas si todo tiene la misma valoración; las vacías, siempre
        rating = self._state.get("rating")
        painter.setFont(self._star_font)
        first = self._zones["star1"]
        card_marks.draw_stars(
            painter, QRect(first.left(), 0, _STAR_W * 5, _HEIGHT),
            rating if isinstance(rating, int) else 0, star_width=_STAR_W, show_empty=True,
        )  # fmt: skip

        # Colores: el cuadrado de cada uno; el que tiene toda la selección, con un anillo
        current_label = self._state.get("color_label")
        for name in COLOR_LABELS:
            rect = self._zones[f"color:{name}"]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(label_color(name))
            painter.drawRoundedRect(QRectF(rect), 2, 2)
            if current_label == name:
                painter.setPen(QPen(QColor(_RING_COLOR), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(QRectF(rect).adjusted(-2.5, -2.5, 2.5, 2.5), 3, 3)

        # Selección rápida: blanco si todo está dentro; si no, el círculo gris de la tarjeta
        quick = self._state.get(QUICK_SELECTION_FIELD)
        card_marks.draw_quick_selection(
            painter, QRectF(self._zones["quick"]), quick == 1, hovered=True
        )
        painter.end()

    # -------------------------------------------------------------------------
    # Ratón
    # -------------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # nombre de Qt
        zone = self._zone_at(event.position().toPoint())
        if zone != self._hovered:
            self._hovered = zone
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if zone else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # nombre de Qt
        self._hovered = None
        self.update()
        super().leaveEvent(event)

    def event(self, event: QEvent) -> bool:
        """Textos emergentes según la zona bajo el ratón."""
        if event.type() == QEvent.Type.ToolTip:
            zone = self._zone_at(event.pos())
            if zone and self.isEnabled():
                QToolTip.showText(event.globalPos(), self._tooltip(zone), self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def mousePressEvent(self, event) -> None:  # nombre de Qt
        if event.button() != Qt.MouseButton.LeftButton or not self._state:
            super().mousePressEvent(event)
            return
        zone = self._zone_at(event.position().toPoint())
        if zone is not None:
            self._apply(zone)
        event.accept()

    def _apply(self, zone: str) -> None:
        """Aplica lo pulsado a la selección (como el atajo de teclado equivalente)."""
        rows = self._selected_rows()
        if self._model is None or not rows:
            return
        state = self._state
        if zone == "pick":
            field = "flag"
            value = toggled_value(state.get("flag"), card_marks.FLAG_PICKED, card_marks.FLAG_NONE)
        elif zone == "reject":
            field = "flag"
            value = toggled_value(state.get("flag"), card_marks.FLAG_REJECTED, card_marks.FLAG_NONE)
        elif zone.startswith("star"):
            field = "rating"
            value = toggled_value(state.get("rating"), int(zone[4:]), 0)
        elif zone.startswith("color:"):
            field = "color_label"
            value = toggled_value(state.get("color_label"), zone.split(":", 1)[1], None)
        else:
            field = QUICK_SELECTION_FIELD
            value = toggled_value(state.get(QUICK_SELECTION_FIELD), 1, 0)
        # El modelo actualiza las tarjetas y avisa al controlador para guardarlo; su aviso
        # de cambio ('dataChanged') vuelve aquí y la barra se repinta con el estado nuevo
        self._model.set_field(field, value, rows)


if __name__ == "__main__":
    # Autoprueba de la lógica (sin ventana) y prueba suelta de la barra.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.organize_bar
    import sys

    assert common_value([]) is None and common_value([3, 3]) == 3
    assert common_value([3, 4]) is MIXED and common_value([None, None]) is None
    assert toggled_value(3, 3, 0) == 0 and toggled_value(2, 3, 0) == 3
    assert toggled_value(MIXED, "red", None) == "red" and toggled_value("red", "red", None) is None
    assert toggled_value(1, 1, 0) == 0 and toggled_value(MIXED, 1, 0) == 1
    print("Lógica: correcta")

    from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)
    bar = OrganizeBar()
    bar._state = {"rating": 3, "flag": 1, "color_label": "blue", QUICK_SELECTION_FIELD: 1}
    bar.setEnabled(True)
    bar.setStyleSheet(f"background: {GRID_BG};")  # el fondo de la barra en la ventana
    bar.setWindowTitle("OrganizeBar (prueba: 3 estrellas, marcada, azul, en la selección rápida)")
    bar.show()
    print("Autoprueba finalizada correctamente.")
    app.exec()
