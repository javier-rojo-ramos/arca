"""Fila de «Atributos» de la barra de filtros: marca, valoración, color, selección rápida y tipo.

    [■] [□] [✕]   [≥ ▾] ★★★☆☆   ■ ■ ■ ■ ■ □   ●   (foto) (vídeo) (audio) (track)
     marca         valoración     colores y     sel.  tipos (los del módulo activo)
                                  «sin color»   rápida

Solo iconos (sin etiquetas de grupo), con su nombre en el texto emergente. Se dibujan con
las mismas funciones que la tarjeta y la barra inferior ('card_marks', 'card_glyphs',
'ui_color_labels'), así que se ven igual en los tres sitios.

Cada icono es un interruptor: encendido, a plena intensidad; apagado, atenuado. Dentro de
un grupo se pueden encender varios (marcadas O sin marca; rojo O verde). Las estrellas no
son interruptores: pulsar la tercera es «3 estrellas» (con el operador del desplegable:
≥, ≤ o =) y pulsarla otra vez las apaga, como en la barra inferior. Sin estrellas, solo
«=» filtra (lo que no tiene valoración; lo decide 'AttributeFilter'): lo explica el texto
emergente del desplegable.

Solo muestra y avisa: cada clic emite 'attribute_filter_changed(AttributeFilter)' (de
'core/catalog/grid_filter.py') en el acto, sin pausa; lo que se ve lo pone 'set_filter'
(sin emitir). Los tipos que se ofrecen los pone quien la usa ('set_media_types'), según el
módulo activo. Nada coge el foco: el teclado sigue en la cuadrícula.

Uso (lo crea el controlador principal y se lo pasa al 'FilterController'):
    row = AttributeFilterRow(parent)
    row.set_media_types(("photo", "video"))
    row.attribute_filter_changed.connect(...)

1.0.2 De 34 px de alto (antes, 30), como la fila de las pestañas; los iconos, las
      estrellas y el fondo bajo el ratón, del mismo tamaño que antes y centrados
      ('_STAR_HEIGHT', '_HOVER_HEIGHT'; pedido por el autor el 12/11/2026).
1.0.1 «Sin valoración» = «=» sin estrellas (lo decide el motor); texto emergente del
      desplegable que lo explica.
1.0.0 Primera versión (paso A.3, «Atributos», subpaso 2).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.attribute_filter_row
"""

__version__ = "1.0.2"
__all__ = ["OPERATOR_TEXTS", "OPERATOR_TOOLTIP", "TYPE_TEXTS", "AttributeFilterRow"]

# Librerías estándar
from collections.abc import Callable, Sequence
from dataclasses import replace

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, Signal
from qtpy.QtGui import QColor, QFont, QHelpEvent, QMouseEvent, QPainter, QPen
from qtpy.QtWidgets import QComboBox, QHBoxLayout, QToolTip, QWidget

# Módulos del proyecto
from core.catalog.color_labels import COLOR_LABELS
from core.catalog.grid_filter import COLOR_NONE, RATING_OPERATORS, AttributeFilter
from ui_helpers.helpers import card_marks
from ui_helpers.helpers.card_glyphs import draw_type_glyph
from ui_helpers.helpers.ui_color_labels import LABEL_TEXTS, label_color
from ui_helpers.helpers.ui_theme import COLORS

# Textos de la interfaz
OPERATOR_TEXTS: dict[str, str] = {"gte": "≥", "lte": "≤", "eq": "="}
_FLAG_TEXTS: dict[int, str] = {
    card_marks.FLAG_PICKED: "Marcadas",
    card_marks.FLAG_NONE: "Sin marca",
    card_marks.FLAG_REJECTED: "Rechazadas",
}
_NO_COLOR_TEXT = "Sin color"
_QUICK_TEXT = "En la selección rápida"
OPERATOR_TOOLTIP = "Para filtrar sin valoración: = sin estrellas"
TYPE_TEXTS: dict[str, str] = {
    "photo": "Fotos",
    "video": "Vídeos",
    "audio": "Audio",
    "track": "Tracks GPS",
    "ebook": "Libros electrónicos",
}


def _star_text(stars: int) -> str:
    return "1 estrella" if stars == 1 else f"{stars} estrellas"


# --- Medidas (px lógicos; las de las marcas, como en la barra inferior) ---
ROW_HEIGHT = 34  # la misma que la fila de las pestañas (lo de dentro va centrado)
_STAR_HEIGHT = 22  # zona de cada estrella
_HOVER_HEIGHT = 24  # fondo bajo el ratón (no crece con la fila: va centrado)
_FLAG_W, _FLAG_H = 10, 14
_STAR_W = 16
_SWATCH = 12
_QUICK = 14
_GLYPH = 16  # dibujo de cada tipo
_ITEM_GAP = 8  # entre dos iconos del mismo grupo (las estrellas y colores, más juntos)
_SWATCH_GAP = 5
_GROUP_GAP = 20  # entre grupos
_HIT_PAD = 3  # margen extra alrededor de cada icono para acertar con el clic

# --- Aspecto ---
_OFF_OPACITY = 0.35  # interruptor apagado
_HOVER_BG = COLORS.bg_hover  # fondo bajo el ratón
_RING_COLOR = COLORS.text  # anillo del color encendido

# Una zona de la tira: (clave, ancho, alto, texto emergente); clave None = hueco
_Zone = tuple[str | None, int, int, str]


class _ZoneStrip(QWidget):
    """Tira de iconos dibujados con QPainter: sabe dónde está cada uno, cuál tiene el ratón
    encima y cuál se pulsa; el dibujo lo hace la fila ('paint')."""

    zone_clicked = Signal(str)

    def __init__(
        self, paint: Callable[[QPainter, dict[str, QRect], str | None], None], parent: QWidget
    ) -> None:
        super().__init__(parent)
        self._paint = paint
        self._zones: dict[str, QRect] = {}
        self._tooltips: dict[str, str] = {}
        self._hovered: str | None = None
        self._width = 0
        self.setMouseTracking(True)
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_zones(self, zones: Sequence[_Zone]) -> None:
        """Coloca las zonas de izquierda a derecha, centradas en vertical."""
        self._zones.clear()
        self._tooltips.clear()
        x = _HIT_PAD
        for key, width, height, tooltip in zones:
            if key is not None:
                self._zones[key] = QRect(x, (ROW_HEIGHT - height) // 2, width, height)
                self._tooltips[key] = tooltip
            x += width
        self._width = x + _HIT_PAD
        self.setFixedWidth(self._width)
        self._hovered = None
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._width, ROW_HEIGHT)

    def _zone_at(self, point: QPoint) -> str | None:
        for key, rect in self._zones.items():
            hit = rect.adjusted(-_HIT_PAD, 0, _HIT_PAD, 0)
            hit.setTop(0)
            hit.setBottom(ROW_HEIGHT)
            if hit.contains(point):
                return key
        return None

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hovered is not None and self.isEnabled():
            rect = self._zones[self._hovered].adjusted(-_HIT_PAD, 0, _HIT_PAD, 0)
            rect.setTop((ROW_HEIGHT - _HOVER_HEIGHT) // 2)
            rect.setHeight(_HOVER_HEIGHT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_HOVER_BG))
            painter.drawRoundedRect(QRectF(rect), 3, 3)
        self._paint(painter, self._zones, self._hovered)
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hovered = self._zone_at(event.position().toPoint())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()

    def leaveEvent(self, _event: object) -> None:
        self._hovered = None
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            key = self._zone_at(event.position().toPoint())
            if key is not None:
                self.zone_clicked.emit(key)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            key = self._zone_at(event.pos())
            if key is not None:
                QToolTip.showText(event.globalPos(), self._tooltips[key], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class AttributeFilterRow(QWidget):
    """Fila de «Atributos» de la barra de filtros (ver el docstring del archivo).

    Signals:
        attribute_filter_changed(object): el usuario ha cambiado algo (lleva el
            'AttributeFilter' nuevo).
    """

    attribute_filter_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(ROW_HEIGHT)
        self._filter = AttributeFilter()
        self._media_types: tuple[str, ...] = ()
        self._star_font = QFont("Arial", 12)  # la de la barra inferior

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Marca | desplegable del operador | estrellas, colores, selección rápida y tipos
        self._flags = _ZoneStrip(self._paint_flags, self)
        self._flags.set_zones(self._flag_zones())
        self._operator = QComboBox(self)
        self._operator.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._operator.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._operator.setToolTip(OPERATOR_TOOLTIP)
        for key in RATING_OPERATORS:
            self._operator.addItem(OPERATOR_TEXTS[key], key)
        self._rest = _ZoneStrip(self._paint_rest, self)

        layout.addStretch(1)
        layout.addWidget(self._flags)
        layout.addSpacing(_GROUP_GAP - _HIT_PAD)
        layout.addWidget(self._operator)
        layout.addSpacing(_ITEM_GAP - _HIT_PAD)
        layout.addWidget(self._rest)
        layout.addStretch(1)

        self._flags.zone_clicked.connect(self._on_zone_clicked)
        self._rest.zone_clicked.connect(self._on_zone_clicked)
        self._operator.activated.connect(self._on_operator)
        self.set_media_types(())
        self.set_filter(AttributeFilter())

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def current(self) -> AttributeFilter:
        """Lo que se ve ahora."""
        return self._filter

    def set_filter(self, attributes: AttributeFilter) -> None:
        """Muestra unos atributos (no emite nada)."""
        self._filter = attributes
        index = self._operator.findData(attributes.rating_operator)
        self._operator.setCurrentIndex(max(index, 0))
        self._flags.update()
        self._rest.update()

    def set_media_types(self, media_types: Sequence[str]) -> None:
        """Tipos que se ofrecen (los del módulo activo), en su orden. Un tipo elegido que no
        se ofrece no se ve, pero sigue en el filtro (es de otro momento del módulo)."""
        self._media_types = tuple(t for t in media_types if t in TYPE_TEXTS)
        self._rest.set_zones(self._rest_zones())

    # -------------------------------------------------------------------------
    # Zonas
    # -------------------------------------------------------------------------

    @staticmethod
    def _flag_zones() -> list[_Zone]:
        zones: list[_Zone] = []
        for i, flag in enumerate(_FLAG_TEXTS):
            if i:
                zones.append((None, _ITEM_GAP, 0, ""))
            zones.append((f"flag:{flag}", _FLAG_W, _FLAG_H, _FLAG_TEXTS[flag]))
        return zones

    def _rest_zones(self) -> list[_Zone]:
        zones: list[_Zone] = []
        for stars in range(1, 6):
            zones.append((f"star:{stars}", _STAR_W, _STAR_HEIGHT, _star_text(stars)))
        zones.append((None, _GROUP_GAP, 0, ""))
        for i, name in enumerate((*COLOR_LABELS, COLOR_NONE)):
            if i:
                zones.append((None, _SWATCH_GAP, 0, ""))
            tooltip = _NO_COLOR_TEXT if name == COLOR_NONE else LABEL_TEXTS.get(name, name)
            zones.append((f"color:{name}", _SWATCH, _SWATCH, tooltip))
        zones.append((None, _GROUP_GAP, 0, ""))
        zones.append(("quick", _QUICK, _QUICK, _QUICK_TEXT))
        if self._media_types:
            zones.append((None, _GROUP_GAP, 0, ""))
            for i, media_type in enumerate(self._media_types):
                if i:
                    zones.append((None, _ITEM_GAP, 0, ""))
                zones.append((f"type:{media_type}", _GLYPH, _GLYPH, TYPE_TEXTS[media_type]))
        return zones

    # -------------------------------------------------------------------------
    # Dibujo
    # -------------------------------------------------------------------------

    def _paint_flags(self, painter: QPainter, zones: dict[str, QRect], _hovered: str | None) -> None:
        for flag in _FLAG_TEXTS:
            rect = zones[f"flag:{flag}"]
            painter.setOpacity(1.0 if flag in self._filter.flags else _OFF_OPACITY)
            # «Sin marca» es el contorno (en la tarjeta, el que sale con el ratón encima)
            card_marks.draw_flag(painter, rect, flag, hovered=True)
        painter.setOpacity(1.0)

    def _paint_rest(self, painter: QPainter, zones: dict[str, QRect], _hovered: str | None) -> None:
        attributes = self._filter
        # Estrellas: rellenas hasta la valoración elegida; las demás, vacías
        painter.setFont(self._star_font)
        first = zones["star:1"]
        card_marks.draw_stars(
            painter, QRect(first.left(), first.top(), _STAR_W * 5, first.height()),
            attributes.rating, star_width=_STAR_W, show_empty=True,
        )  # fmt: skip

        # Colores: el cuadrado de cada uno; «sin color», solo el contorno
        for name in (*COLOR_LABELS, COLOR_NONE):
            rect = QRectF(zones[f"color:{name}"])
            on = name in attributes.colors
            painter.setOpacity(1.0 if on else _OFF_OPACITY)
            if name == COLOR_NONE:
                painter.setPen(QPen(QColor(card_marks.FLAG_OUTLINE_COLOR), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2, 2)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(label_color(name))
                painter.drawRoundedRect(rect, 2, 2)
            if on:
                painter.setPen(QPen(QColor(_RING_COLOR), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-2.5, -2.5, 2.5, 2.5), 3, 3)
        painter.setOpacity(1.0)

        # Selección rápida: blanco encendido; el círculo gris de la tarjeta, apagado
        card_marks.draw_quick_selection(painter, QRectF(zones["quick"]), attributes.quick, hovered=True)

        # Tipos: el dibujo del marcador de la tarjeta, en el color del texto
        for media_type in self._media_types:
            on = media_type in attributes.media_types
            painter.setOpacity(1.0 if on else _OFF_OPACITY)
            draw_type_glyph(painter, QRectF(zones[f"type:{media_type}"]), media_type, COLORS.text)
        painter.setOpacity(1.0)

    # -------------------------------------------------------------------------
    # Clics
    # -------------------------------------------------------------------------

    def _on_zone_clicked(self, key: str) -> None:
        """Cambia lo pulsado y avisa en el acto."""
        attributes = self._filter
        kind, _, value = key.partition(":")
        if kind == "flag":
            attributes = replace(attributes, flags=attributes.flags ^ {int(value)})
        elif kind == "star":
            stars = int(value)
            attributes = replace(attributes, rating=0 if attributes.rating == stars else stars)
        elif kind == "color":
            attributes = replace(attributes, colors=attributes.colors ^ {value})
        elif kind == "quick":
            attributes = replace(attributes, quick=not attributes.quick)
        elif kind == "type":
            attributes = replace(attributes, media_types=attributes.media_types ^ {value})
        self._change(attributes)

    def _on_operator(self, _index: int) -> None:
        operator = self._operator.currentData() or RATING_OPERATORS[0]
        self._change(replace(self._filter, rating_operator=operator))

    def _change(self, attributes: AttributeFilter) -> None:
        if attributes == self._filter:
            return
        self.set_filter(attributes)
        self.attribute_filter_changed.emit(attributes)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica y el dibujo.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.attribute_filter_row
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtTest import QTest
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    holder = QWidget()  # padre que nunca se muestra: no se crea ninguna ventana
    row = AttributeFilterRow(holder)
    seen: list[AttributeFilter] = []
    row.attribute_filter_changed.connect(seen.append)

    def click(strip: _ZoneStrip, key: str) -> None:
        QTest.mouseClick(strip, Qt.MouseButton.LeftButton, pos=strip._zones[key].center())

    # Sin tipos: no hay zonas de tipo; con los de Imagen, dos
    assert not any(k.startswith("type:") for k in row._rest._zones)
    row.set_media_types(("photo", "video", "otro"))
    assert [k for k in row._rest._zones if k.startswith("type:")] == ["type:photo", "type:video"]
    assert [row._operator.itemText(i) for i in range(row._operator.count())] == ["≥", "≤", "="]
    assert row._operator.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert row._operator.toolTip() == "Para filtrar sin valoración: = sin estrellas"

    # Marca: interruptores que se combinan
    click(row._flags, "flag:1")
    click(row._flags, "flag:-1")
    assert seen[-1].flags == {1, -1}
    click(row._flags, "flag:1")
    assert seen[-1].flags == {-1}

    # Estrellas: la tercera = 3; otra vez la tercera = sin valoración; el operador
    click(row._rest, "star:3")
    assert seen[-1].rating == 3
    row._operator.setCurrentIndex(row._operator.findData("eq"))
    row._operator.activated.emit(row._operator.currentIndex())
    assert seen[-1].rating_operator == "eq" and seen[-1].rating == 3
    click(row._rest, "star:3")
    assert seen[-1].rating == 0

    # Colores (con «sin color»), selección rápida y tipos
    click(row._rest, "color:red")
    click(row._rest, f"color:{COLOR_NONE}")
    click(row._rest, "quick")
    click(row._rest, "type:video")
    last = seen[-1]
    assert last.colors == {"red", COLOR_NONE} and last.quick and last.media_types == {"video"}
    count = len(seen)

    # 'set_filter' no avisa; el desplegable sigue al filtro
    row.set_filter(AttributeFilter(rating_operator="lte"))
    assert len(seen) == count and row._operator.currentData() == "lte"
    assert row.current() == AttributeFilter(rating_operator="lte")

    # Textos emergentes y dibujo (sin errores; algún píxel de estrella y de color)
    assert row._rest._tooltips["star:1"] == "1 estrella" and row._rest._tooltips["quick"] == _QUICK_TEXT
    row.set_filter(AttributeFilter(rating=2, colors=frozenset({"green"})))
    row.resize(row.sizeHint())
    image = row._rest.grab().toImage()
    colors = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
    assert QColor(card_marks.STAR_COLOR).name() in colors or len(colors) > 3
    assert label_color("green").name() in colors

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
