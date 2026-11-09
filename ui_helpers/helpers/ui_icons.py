"""Iconos SVG monocromos que se tiñen en el momento de dibujarse.

Idea: los SVG del .qrc se guardan en un único color (el que sea) y este módulo
los "pinta" con el color que toque, en lugar de tener un archivo por color
(check_circle__green.svg, error__red.svg...).

Por defecto el color sale de la paleta de Qt (QPalette), así que los iconos se
adaptan solos a un tema claro u oscuro:

    - Estado normal      -> color del texto de los botones (ButtonText)
    - Botón desactivado  -> color de ButtonText en grupo Disabled
    - Botón marcado (On) -> color de acento del sistema (Highlight)
    - Ratón encima       -> color propio ('hover_color'), si se indica

También se puede forzar un color fijo para iconos concretos (errores, avisos...).

Uso:
    from ui_helpers.helpers.ui_icons import tinted_icon

    boton.setIcon(tinted_icon(AppIcons.SETTINGS))             # sigue la paleta
    boton.setIcon(tinted_icon(AppIcons.ERROR, COLORS.error))   # color fijo (del tema)
    boton.setIcon(tinted_icon(AppIcons.SETTINGS, hover_color=COLORS.accent))  # acento con el ratón

Para un QLabel (que muestra un QPixmap, no un QIcon) está 'tinted_pixmap': tiñe el SVG
directamente al tamaño en píxeles físicos de la pantalla, sin pasar por QIcon.

    ratio = label.devicePixelRatioF()
    label.setPixmap(tinted_pixmap(AppIcons.WARNING, COLORS.warning, 16, ratio))

En una opción de MENÚ, el icono va con 'menu_icon': Qt pide el icono de la opción
resaltada en modo 'Active' (el mismo que el del ratón encima de un botón), y ahí tiene que
tomar el color del texto sobre el acento, como el texto de la opción.

    action = menu.addAction(menu_icon(AppIcons.COLLECTION_SMART), "Editar...")

Nota: los iconos a todo color (logo, etc.) NO deben pasar por aquí; para ellos
se sigue usando QIcon(ruta) normal, porque el teñido borraría sus colores.

1.3.0 'menu_icon': en la opción resaltada de un menú, el icono toma el color del texto
      sobre el acento (antes se quedaba claro sobre el ámbar).
1.2.1 Los ejemplos de esta cabecera usan colores del tema, no «#rrggbb» sueltos.
1.2.0 Un icono en una fila SELECCIONADA (modo 'Selected') toma 'HighlightedText', el texto
      sobre el acento, aunque tenga color fijo: con el acento ámbar, los iconos claros de la
      barra lateral no se veían sobre la fila elegida, y la carpeta abierta (en el acento),
      nada.
1.1.0 'tinted_pixmap' para los QLabel (el icono de la barra de estado).
"""

__version__ = "1.3.0"
__all__ = ["menu_icon", "tinted_icon", "tinted_pixmap"]

# Librerías estándar
from functools import lru_cache

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint, QRect, QRectF, QSize, Qt
from qtpy.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QIconEngine,
    QImage,
    QPainter,
    QPalette,
    QPixmap,
)
from qtpy.QtSvg import QSvgRenderer


@lru_cache(maxsize=256)
def _render_tinted(path: str, width: int, height: int, rgba: int) -> QPixmap:
    """Renderiza un SVG a 'width x height' píxeles y lo tiñe con el color 'rgba'.

    Está cacheada: Qt pide el pixmap cada vez que repinta el botón, y así solo se
    renderiza el SVG una vez por (archivo, tamaño, color). Si cambia la paleta,
    el color cambia y por tanto se genera una entrada nueva automáticamente.
    Los argumentos son tipos simples (hashables) para poder usar lru_cache.
    """
    if width <= 0 or height <= 0:
        return QPixmap()

    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        logger.warning(f"No se pudo cargar el icono SVG: {path}")
        return QPixmap()
    renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)

    # 1) Se dibuja el SVG sobre una imagen transparente...
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, width, height))

    # 2) ...y se rellena con el color deseado SOLO donde el SVG tiene tinta
    # (SourceIn conserva el canal alfa del SVG y sustituye el color)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), QColor.fromRgba(rgba))
    painter.end()

    return QPixmap.fromImage(image)


class _TintedSvgEngine(QIconEngine):
    """Motor de icono de Qt que dibuja un SVG teñido según el estado del botón."""

    def __init__(
        self,
        path: str,
        color: QColor | None = None,
        hover_color: QColor | None = None,
        *,
        in_menu: bool = False,
    ) -> None:
        super().__init__()
        self._path = path
        self._color = color  # None -> se usa la paleta de la aplicación
        self._hover_color = hover_color  # None -> el hover no cambia el color
        # En un menú, 'Active' es la opción resaltada (sobre el acento), no el ratón encima
        self._in_menu = in_menu

    def clone(self) -> QIconEngine:
        """Qt copia los iconos internamente; cada copia necesita su propio motor."""
        return _TintedSvgEngine(self._path, self._color, self._hover_color, in_menu=self._in_menu)

    def _resolve_color(self, mode: QIcon.Mode, state: QIcon.State) -> QColor:
        """Elige el color según el modo (activo/desactivado) y estado (marcado)."""
        palette = QGuiApplication.palette()

        # Opción resaltada de un menú (modo 'Active'): el color de su texto, el del texto
        # sobre el acento (si no, un icono claro se pierde sobre el ámbar)
        if mode == QIcon.Mode.Active and self._in_menu:
            return palette.color(QPalette.ColorRole.HighlightedText)

        # Ratón encima: Qt pide el icono en modo 'Active' (los QToolButton con
        # autoRaise=True lo hacen). Si se definió un color de hover, se usa ese.
        if mode == QIcon.Mode.Active and self._hover_color is not None:
            return QColor(self._hover_color)

        # Fila seleccionada de una lista o árbol: el color del texto sobre el acento, también
        # con color fijo (si no, un icono en el acento desaparecería sobre la fila)
        if mode == QIcon.Mode.Selected:
            return palette.color(QPalette.ColorRole.HighlightedText)

        if self._color is not None:
            # Color fijo: si el botón está desactivado se atenúa con transparencia
            color = QColor(self._color)
            if mode == QIcon.Mode.Disabled:
                color.setAlphaF(color.alphaF() * 0.4)
            return color

        if mode == QIcon.Mode.Disabled:
            return palette.color(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText
            )
        if state == QIcon.State.On:
            # Botón marcado (checkable): color de acento
            return palette.color(QPalette.ColorRole.Highlight)
        return palette.color(QPalette.ColorRole.ButtonText)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        """Camino principal: Qt pide aquí el icono al tamaño en píxeles físicos.

        Al renderizar el SVG directamente a ese tamaño, el icono sale nítido
        también en pantallas HiDPI (no se escala un bitmap pequeño).
        """
        rgba = self._resolve_color(mode, state).rgba()
        return _render_tinted(self._path, size.width(), size.height(), rgba)

    def paint(
        self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State
    ) -> None:
        """Dibujo directo (QIcon.paint): reutiliza pixmap() para tener un único camino."""
        dpr = painter.device().devicePixelRatio()
        size = QSize(round(rect.width() * dpr), round(rect.height() * dpr))
        pixmap = self.pixmap(size, mode, state)
        pixmap.setDevicePixelRatio(dpr)
        painter.drawPixmap(QPoint(rect.x(), rect.y()), pixmap)


def tinted_icon(
    path: str,
    color: QColor | str | None = None,
    *,
    hover_color: QColor | str | None = None,
) -> QIcon:
    """Crea un QIcon a partir de un SVG monocromo.

    Args:
        path: ruta del SVG (normalmente una constante de AppIcons, ":/img/xxx.svg").
        color: color fijo (QColor o texto "#rrggbb"; del tema, p. ej. 'COLORS.error'). Si
            es None, el icono sigue la paleta de la aplicación (claro/oscuro/acento).
        hover_color: color que toma el icono mientras el ratón está encima.
            Solo se nota en botones con autoRaise=True (como los de la toolbar).
            Si es None, el icono no cambia al pasar el ratón.
    """
    fixed = QColor(color) if color is not None else None
    hover = QColor(hover_color) if hover_color is not None else None
    return QIcon(_TintedSvgEngine(path, fixed, hover))


def menu_icon(path: str, color: QColor | str | None = None) -> QIcon:
    """Icono para una opción de menú: como 'tinted_icon', pero en la opción resaltada toma
    el color del texto sobre el acento ('HighlightedText'), como el texto de la opción.

    Args:
        path: ruta del SVG (normalmente una constante de AppIcons, ":/img/xxx.svg").
        color: color fijo en reposo (QColor o "#rrggbb" del tema); None = el de la paleta.
    """
    fixed = QColor(color) if color is not None else None
    return QIcon(_TintedSvgEngine(path, fixed, None, in_menu=True))


def tinted_pixmap(
    path: str, color: QColor | str, size: int, device_pixel_ratio: float = 1.0
) -> QPixmap:
    """Pixmap de un SVG monocromo teñido de un color, para mostrarlo en un QLabel.

    Se dibuja a 'size' píxeles LÓGICOS: el SVG se renderiza a los píxeles físicos de la
    pantalla ('device_pixel_ratio', p. ej. 1,25 o 1,5) y el pixmap lo sabe, así que se ve
    nítido y del tamaño correcto también con la pantalla escalada.

    Args:
        path: ruta del SVG (normalmente una constante de AppIcons, ":/img/xxx.svg").
        color: color del icono (QColor o texto "#rrggbb"; del tema, p. ej. 'COLORS.success').
        size: lado del icono en píxeles lógicos.
        device_pixel_ratio: el de la pantalla del widget ('widget.devicePixelRatioF()').
    """
    physical = max(1, round(size * device_pixel_ratio))
    pixmap = QPixmap(_render_tinted(path, physical, physical, QColor(color).rgba()))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    return pixmap

