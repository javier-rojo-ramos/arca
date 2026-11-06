"""Estilo propio sobre Fusion: dibuja los botones de opción y las casillas del tema.

Con la paleta oscura, Fusion pinta el borde de estos indicadores con el color de la
ventana oscurecido ('window.darker(140)'): casi negro sobre un fondo casi negro, así que
apenas se ven. Este 'QProxyStyle' deja a Fusion todo lo demás y solo cambia tres piezas:

    PE_IndicatorRadioButton         círculo de QRadioButton
    PE_IndicatorCheckBox            casilla de QCheckBox
    PE_IndicatorItemViewItemCheck   casilla dentro de listas y árboles (p. ej. el árbol
                                    de palabras clave con casillas del inspector)

Aspecto (colores con nombre de 'theme_colors.py'):
    - Sin marcar: borde 'text_dim' sobre el fondo de los campos ('bg_input').
    - Ratón encima o pulsado: borde del acento (en listas y árboles no: allí el «ratón
      encima» es de la fila entera y la casilla cambiaría al pasar por cualquier sitio).
    - Marcado: relleno del acento con un punto (círculo) o una marca (casilla) blancos.
    - Parcial (casilla de tres estados): relleno del acento con una raya.
    - Desactivado: borde 'line'; si está marcado, relleno 'line' y marca 'text_disabled'.

Además, el círculo y la casilla de QRadioButton y QCheckBox se dibujan
'INDICATOR_OFFSET_Y' píxeles más abajo: Qt los centra en la altura del control
redondeando hacia arriba, y el centro visual del texto queda algo más abajo, así que se
veían un poco altos. Se mueve el DIBUJO, no el rectángulo: Fusion calcula ese rectángulo
por dentro sin pasar por este estilo, así que cambiarlo en 'subElementRect' no tenía
efecto (versión 1.1.0). Las casillas de listas y árboles no se mueven.

Se hace con un estilo y no con QSS porque el QSS de la casilla necesita imágenes para la
marca y la raya, y no llega a las casillas que dibujan las vistas (el árbol). Lo instala
'ui_theme.apply_theme()'; la hoja de estilos de la aplicación no tiene reglas
'::indicator', así que Qt le pasa estos dibujos a este estilo.

1.2.0 El desplazamiento se aplica al dibujar (el de 1.1.0, en 'subElementRect', no se
      veía); solo en QRadioButton y QCheckBox.
1.1.0 El círculo y la casilla bajan 'INDICATOR_OFFSET_Y' px para alinearse con el texto.

Prueba visual (abre una ventana con todos los estados):
    python -m ui_helpers.helpers.theme_style
"""

__version__ = "1.2.0"
__all__ = ["INDICATOR_OFFSET_Y", "ThemeStyle"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QPointF, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPainterPath, QPen
from qtpy.QtWidgets import (
    QCheckBox,
    QProxyStyle,
    QRadioButton,
    QStyle,
    QStyleOption,
    QWidget,
)

# Módulos del proyecto
from ui_helpers.helpers.theme_colors import ThemeColors

# Grosor del borde de los indicadores (px lógicos): 1,5 se ve nítido en pantallas al 100 %
# y no engorda en las de alta densidad
_BORDER_WIDTH = 1.5
# Radio de las esquinas de la casilla (px lógicos)
_CHECKBOX_RADIUS = 2.0
# Diámetro del punto del botón de opción marcado, en proporción al círculo
_RADIO_DOT_RATIO = 0.4
# Grosor de la marca y de la raya de la casilla, en proporción a la casilla
_MARK_WIDTH_RATIO = 0.14

# Cuánto bajan el círculo de QRadioButton y la casilla de QCheckBox (px lógicos; en una
# pantalla al 125 % o 150 %, 1 px lógico son 1,25 o 1,5 píxeles reales). Si cambia la
# fuente de la aplicación, puede hacer falta ajustarlo
INDICATOR_OFFSET_Y = 1

_PE = QStyle.PrimitiveElement
_STATE = QStyle.StateFlag


class ThemeStyle(QProxyStyle):
    """Fusion con los botones de opción y las casillas dibujados con los colores del tema."""

    def __init__(self, colors: ThemeColors, base_style: str = "Fusion") -> None:
        """Crea el estilo.

        Args:
            colors: Colores del tema (los de 'theme_colors.py').
            base_style: Estilo al que se pasa todo lo demás.
        """
        super().__init__(base_style)
        self._colors = colors

    # ------------------------------------------------------------------
    # Punto de entrada de Qt
    # ------------------------------------------------------------------

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Dibuja los indicadores del tema; el resto, como Fusion."""
        # Solo los controles sueltos bajan un poco (ver la cabecera); los menús y otros
        # usos de estos mismos dibujos se quedan donde los pone Qt
        offset = INDICATOR_OFFSET_Y if isinstance(widget, (QRadioButton, QCheckBox)) else 0
        if element == _PE.PE_IndicatorRadioButton:
            self._draw_radio(option, painter, offset)
        elif element == _PE.PE_IndicatorCheckBox:
            self._draw_checkbox(option, painter, allow_hover=True, offset=offset)
        elif element == _PE.PE_IndicatorItemViewItemCheck:
            self._draw_checkbox(option, painter, allow_hover=False)
        else:
            super().drawPrimitive(element, option, painter, widget)

    # ------------------------------------------------------------------
    # Dibujo
    # ------------------------------------------------------------------

    def _colors_for(
        self, option: QStyleOption, *, checked: bool, allow_hover: bool
    ) -> tuple[QColor, QColor | None, QColor]:
        """Colores (borde, relleno o None, marca) de un indicador según su estado."""
        c = self._colors
        state = option.state
        enabled = bool(state & _STATE.State_Enabled)
        if not enabled:
            if checked:
                return QColor(c.line), QColor(c.line), QColor(c.text_disabled)
            return QColor(c.line), None, QColor(c.text_disabled)
        if checked:
            return QColor(c.accent), QColor(c.accent), QColor(c.text_on_accent)
        active = allow_hover and bool(state & (_STATE.State_MouseOver | _STATE.State_Sunken))
        border = c.accent if active else c.text_dim
        return QColor(border), QColor(c.bg_input), QColor(c.text_on_accent)

    @staticmethod
    def _indicator_rect(option: QStyleOption, offset: float = 0) -> QRectF:
        """Cuadrado centrado en el rectángulo del indicador, encogido medio borde.

        Así el trazo cae entero dentro del rectángulo que reserva Fusion (no se corta) y
        el indicador queda cuadrado aunque Qt le dé un rectángulo algo apaisado.

        Args:
            option: Opciones del dibujo (su 'rect' es el del indicador).
            offset: Píxeles que baja el indicador (ver 'INDICATOR_OFFSET_Y').
        """
        rect = QRectF(option.rect)
        side = min(rect.width(), rect.height()) - 1.0
        square = QRectF(0.0, 0.0, side, side)
        square.moveCenter(rect.center() + QPointF(0.0, offset))
        half = _BORDER_WIDTH / 2
        return square.adjusted(half, half, -half, -half)

    @staticmethod
    def _prepare(painter: QPainter, border: QColor, fill: QColor | None) -> None:
        """Pincel y relleno del contorno, con antialiasing."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(border, _BORDER_WIDTH))
        if fill is None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setBrush(fill)

    def _draw_radio(self, option: QStyleOption, painter: QPainter, offset: float = 0) -> None:
        """Círculo del botón de opción (con punto si está marcado)."""
        checked = bool(option.state & _STATE.State_On)
        border, fill, mark = self._colors_for(option, checked=checked, allow_hover=True)
        rect = self._indicator_rect(option, offset)

        painter.save()
        self._prepare(painter, border, fill)
        painter.drawEllipse(rect)
        if checked:
            radius = rect.width() * _RADIO_DOT_RATIO / 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(mark)
            painter.drawEllipse(rect.center(), radius, radius)
        painter.restore()

    def _draw_checkbox(
        self, option: QStyleOption, painter: QPainter, *, allow_hover: bool, offset: float = 0
    ) -> None:
        """Casilla: vacía, con marca (marcada) o con raya (parcial, tres estados)."""
        state = option.state
        partial = bool(state & _STATE.State_NoChange)
        checked = bool(state & _STATE.State_On) or partial
        border, fill, mark = self._colors_for(option, checked=checked, allow_hover=allow_hover)
        rect = self._indicator_rect(option, offset)

        painter.save()
        self._prepare(painter, border, fill)
        painter.drawRoundedRect(rect, _CHECKBOX_RADIUS, _CHECKBOX_RADIUS)
        if checked:
            pen = QPen(mark, max(1.2, rect.width() * _MARK_WIDTH_RATIO))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            if partial:
                # Raya horizontal centrada
                painter.drawLine(QPointF(x + w * 0.28, y + h / 2), QPointF(x + w * 0.72, y + h / 2))
            else:
                # Marca: dos tramos, el corto hacia abajo y el largo hacia arriba
                path = QPainterPath(QPointF(x + w * 0.24, y + h * 0.52))
                path.lineTo(QPointF(x + w * 0.43, y + h * 0.70))
                path.lineTo(QPointF(x + w * 0.77, y + h * 0.31))
                painter.drawPath(path)
        painter.restore()


if __name__ == "__main__":
    # Prueba visual: una ventana con todos los estados (pasa el ratón por encima de cada
    # control) y una comprobación automática de los colores del centro de cada indicador.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.helpers.theme_style
    import sys

    from qtpy.QtGui import QImage, QStandardItem, QStandardItemModel
    from qtpy.QtWidgets import (
        QApplication,
        QCheckBox,
        QGridLayout,
        QRadioButton,
        QStyleOptionButton,
        QTreeView,
    )

    from ui_helpers.helpers.ui_theme import COLORS, apply_theme

    app = QApplication(sys.argv)
    apply_theme()
    style = app.style()

    # 1. Comprobación automática: se dibuja cada indicador en una imagen y se mira el
    #    color del centro (relleno) y el del borde. Pasa por el estilo de la aplicación,
    #    como en la interfaz real (hoja de estilos incluida)
    def center_and_edge(
        element: QStyle.PrimitiveElement, state: QStyle.StateFlag
    ) -> tuple[str, str]:
        """Colores (#rrggbb) del centro y del borde izquierdo de un indicador dibujado."""
        image = QImage(20, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor(COLORS.bg_panel))
        option = QStyleOptionButton()
        option.rect = image.rect()
        option.state = state
        painter = QPainter(image)
        style.drawPrimitive(element, option, painter, None)
        painter.end()
        edge_x = next(  # primer píxel distinto del fondo por la izquierda, a media altura
            (x for x in range(20) if image.pixelColor(x, 10) != QColor(COLORS.bg_panel)), 0
        )
        return image.pixelColor(10, 10).name(), image.pixelColor(edge_x + 1, 10).name()

    enabled = _STATE.State_Enabled
    center, _edge = center_and_edge(_PE.PE_IndicatorCheckBox, enabled | _STATE.State_Off)
    assert center == QColor(COLORS.bg_input).name(), center  # vacía: fondo de los campos
    center, _edge = center_and_edge(_PE.PE_IndicatorRadioButton, enabled | _STATE.State_On)
    assert center == QColor(COLORS.text_on_accent).name(), center  # punto blanco
    _center, edge = center_and_edge(_PE.PE_IndicatorRadioButton, enabled | _STATE.State_On)
    assert QColor(edge).blue() > QColor(edge).red(), edge  # borde azul del acento
    partial = enabled | _STATE.State_NoChange
    center, _edge = center_and_edge(_PE.PE_IndicatorItemViewItemCheck, partial)
    assert center == QColor(COLORS.text_on_accent).name(), center  # raya blanca del parcial
    print("Colores de los indicadores: correctos")

    # 2. Ventana para verlos de verdad
    window = QWidget()
    window.setWindowTitle("Botones de opción y casillas del tema")
    grid = QGridLayout(window)
    radio_off, radio_on = QRadioButton("Sin marcar"), QRadioButton("Marcado")
    radio_on.setChecked(True)
    radio_disabled = QRadioButton("Desactivado (marcado)")
    radio_disabled.setChecked(True)
    radio_disabled.setEnabled(False)
    check_off, check_on = QCheckBox("Casilla"), QCheckBox("Marcada")
    check_on.setChecked(True)
    check_partial = QCheckBox("Parcial")
    check_partial.setTristate(True)
    check_partial.setCheckState(Qt.CheckState.PartiallyChecked)
    check_disabled = QCheckBox("Desactivada")
    check_disabled.setEnabled(False)
    for row, (left, right) in enumerate(
        ((radio_off, check_off), (radio_on, check_on), (radio_disabled, check_partial),
         (None, check_disabled))
    ):  # fmt: skip
        if left is not None:
            grid.addWidget(left, row, 0)
        grid.addWidget(right, row, 1)

    # Árbol con casillas de tres estados (como el de palabras clave del inspector)
    model = QStandardItemModel(window)
    parent_item = QStandardItem("Coche")
    parent_item.setCheckable(True)
    parent_item.setCheckState(Qt.CheckState.PartiallyChecked)
    for name, state in (("Toyota Corolla", Qt.CheckState.Checked),
                        ("Seat Ibiza", Qt.CheckState.Unchecked)):  # fmt: skip
        child = QStandardItem(name)
        child.setCheckable(True)
        child.setCheckState(state)
        parent_item.appendRow(child)
    model.appendRow(parent_item)
    tree = QTreeView(window)
    tree.setHeaderHidden(True)
    tree.setModel(model)
    tree.expandAll()
    grid.addWidget(tree, 4, 0, 1, 2)

    window.resize(380, 300)
    window.show()
    print("Autoprueba finalizada correctamente.")
    sys.exit(app.exec())
