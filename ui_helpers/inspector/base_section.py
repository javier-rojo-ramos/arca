"""Base de las secciones del inspector (panel derecho).

Cada sección es un widget que sabe mostrar una parte de la información de lo
seleccionado: «Selección» (datos básicos del archivo), y más adelante «Organización»,
«Descripción», «Cámara», «Etiquetas de audio», «Ficha»... El 'InspectorPanel' las coloca
una debajo de otra, cada una dentro de una sección plegable con su título.

Qué define cada sección (sobrescribiendo):
    - 'title':          título de la cabecera (se muestra en mayúsculas).
    - 'title_for(s)':   título para ese resumen, si cambia según lo que se ve (por
                        defecto, 'title'). P. ej. «Selección (vista actual)».
    - 'applies_to(s)':  si tiene algo que mostrar para ese resumen (p. ej. «Cámara» solo
                        con fotos y vídeos). Si no, el panel la oculta entera.
    - 'show_summary(s)': rellena sus filas con el resumen ('SelectionSummary').
    - 'data_request(s, ids)' y 'show_data(r)' (opcional): si la sección necesita datos que
                        no están en el resumen (p. ej. «Metadatos»), dice QUÉ función hay
                        que ejecutar en segundo plano y con qué argumentos; el controlador
                        la lanza ('execute_async') y le entrega el resultado.
    - 'header_widget()' (opcional): un widget para la cabecera, a la derecha del título
                        (p. ej. el desplegable de vistas de «Metadatos»).
    - señal 'refresh_requested': la sección necesita sus datos otra vez (p. ej. al
                        cambiar de vista); el panel la reenvía al controlador.
    - 'modules' / 'hidden_in': en qué módulos aparece (vacío = en todos) y en cuáles no.
                        P. ej. el editor de palabras clave solo en «Imagen», y la lista
                        de solo lectura en todos menos en «Imagen». Ver 'shown_in'.
    - señal 'edit_requested(función, argumentos)': la sección quiere CAMBIAR algo del
                        catálogo (p. ej. asignar una palabra clave). Como con
                        'data_request', la función recibe la conexión y después los
                        argumentos; el controlador la lanza con 'execute_async' y, al
                        terminar, avisa de que hay cambios del usuario y refresca.
    - señal 'navigate_requested(GridSource)': la sección quiere que la cuadrícula muestre
                        otra cosa (p. ej. las fotos de una palabra clave); el módulo activo
                        lo elige en su barra izquierda (que es la que navega).
    - señal 'drop_edit_requested(función, argumentos, MediaDrag)': igual, pero con
                        tarjetas SOLTADAS desde la cuadrícula; el controlador comprueba
                        antes que son del catálogo abierto.

Las secciones NO tocan la base de datos ni hacen nada por su cuenta: piden las acciones con
señales (p. ej. 'reveal_requested', 'edit_requested') y las atiende
'controllers/inspector_controller.py'.

Filas "etiqueta | valor | icono": 'InfoGrid' es una rejilla de tres columnas, con la
etiqueta en gris alineada a la derecha, el valor (recortado con '…' si no cabe) y una
columna estrecha para un botón o un icono. Todas las secciones la usan, así que las
columnas quedan alineadas de una sección a otra.

Los iconos de la tercera columna son 'IconCell' (un icono, una inicial o un botón): van
pegados al borde DERECHO, igual que la etiqueta de la extensión de la cabecera, y bajados
'ICON_Y_OFFSET' px para que su centro coincida con el del texto (el centro geométrico
de una línea de texto queda por encima del de las letras, por el hueco de los
descendentes).

1.7.0 Señal 'navigate_requested' (la flecha «ver sus fotos» del árbol de palabras).
1.6.0 Señal 'drop_edit_requested' (tarjetas soltadas en el inspector).
1.5.0 Secciones según el módulo activo ('modules', 'hidden_in', 'shown_in') y secciones
      que editan el catálogo (señal 'edit_requested'); paso K4b, palabras clave.
1.4.0 Etiquetas alineadas a la IZQUIERDA ('KEY_ALIGNMENT') y columna de etiquetas de
      ancho FIJO: el de la etiqueta más larga de todas las que puede mostrar cada sección
      ('possible_key_labels'), así los valores no se mueven al cambiar de vista.
1.3.0 Secciones con datos propios ('data_request' / 'show_data'), widget en la cabecera
      ('header_widget'), señal 'refresh_requested'; 'InfoGrid.add_separator' y ancho de
      la columna de etiquetas común a todas las secciones ('key_column_width' /
      'set_key_column_width').
1.2.0 'title_for': el título de una sección puede cambiar según el resumen.
1.1.0 Iconos alineados a la derecha ('IconCell', también botón), bajados 'ICON_Y_OFFSET'
      px para centrarlos con el texto; filas sin etiqueta a todo el ancho; separación
      entre filas de 6 px ('ROW_SPACING'), como las filas de la barra izquierda.
"""

__version__ = "1.7.0"
__all__ = [
    "ICON_SIZE",
    "IconCell",
    "InfoGrid",
    "InfoRow",
    "InspectorSection",
    "set_secondary_text",
]

# Librerías estándar
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QSize, Qt, Signal
from qtpy.QtGui import QIcon, QPalette, QPixmap
from qtpy.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

# Módulos del proyecto
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.widgets.elided_label import ElidedLabel

# Lado de los iconos de la tercera columna (px lógicos)
ICON_SIZE = 16
# Cuánto se bajan los iconos respecto al centro de la fila (px lógicos), para que queden
# centrados con las letras. Si en tu pantalla no cuadra, se ajusta aquí
ICON_Y_OFFSET = 2
# Ancho mínimo de la columna de iconos y botones (px lógicos)
ICON_COLUMN_WIDTH = ICON_SIZE
# Separación vertical entre filas (px lógicos): la misma que entre las filas de los
# árboles de la barra izquierda
ROW_SPACING = 6
# Ancho mínimo de la columna de etiquetas: así las de todas las secciones se alinean
# aunque una sección solo tenga etiquetas cortas
KEY_COLUMN_MIN_WIDTH = 64
# Alineación de las etiquetas (decidido por el autor el 02/11/2026: a la izquierda, con la
# columna de ancho fijo). Para alinearlas a la derecha, como Lightroom: Qt.AlignmentFlag.AlignRight
KEY_ALIGNMENT = Qt.AlignmentFlag.AlignLeft


@dataclass(slots=True)
class InfoRow:
    """Una fila de 'InfoGrid': sus tres widgets (para mostrarla u ocultarla entera)."""

    key: QLabel
    value: ElidedLabel
    accessory: QWidget | None = None

    def set_visible(self, visible: bool) -> None:
        """Muestra u oculta la fila completa."""
        self.key.setVisible(visible)
        self.value.setVisible(visible)
        if self.accessory is not None:
            self.accessory.setVisible(visible)


class IconCell(QLabel):
    """Celda de la tercera columna: un icono, una inicial o un botón con icono.

    Mide 'ICON_SIZE' x 'ICON_SIZE' (no cambia el alto de la fila) y dibuja su contenido
    'ICON_Y_OFFSET' px más abajo. Si es "pulsable" ('clickable=True'), se comporta como un
    botón sin marco: mano al pasar el ratón, icono con el color de pasar el ratón (el modo
    Active del QIcon, ver 'tinted_icon(hover_color=...)') y señal 'clicked'.

    Signals:
        clicked(): se ha pulsado (solo si es pulsable y está activado).
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, clickable: bool = False) -> None:
        super().__init__(parent)
        self._icon: QIcon | None = None
        self._hovered = False
        self._clickable = clickable
        self.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # El contenido se centra en el rectángulo interior: un margen superior del doble
        # baja el centro exactamente 'ICON_Y_OFFSET' px
        self.setContentsMargins(0, 2 * ICON_Y_OFFSET, 0, 0)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon(self, icon: QIcon | None) -> None:
        """Pone un icono (None = vacía la celda)."""
        self._icon = icon
        self.setText("")
        self._update_pixmap()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Pone una imagen ya dibujada (p. ej. el círculo de estado)."""
        self._icon = None
        self.setText("")
        self.setPixmap(pixmap)

    def set_letter(self, letter: str) -> None:
        """Pone una letra (la inicial de un módulo sin icono)."""
        self._icon = None
        self.clear()
        self.setText(letter)

    # --- Qt ---

    def changeEvent(self, event) -> None:  # noqa: N802 - nombre de Qt
        super().changeEvent(event)
        self._update_pixmap()  # activado / desactivado

    def enterEvent(self, event) -> None:  # noqa: N802 - nombre de Qt
        super().enterEvent(event)
        self._hovered = True
        self._update_pixmap()

    def leaveEvent(self, event) -> None:  # noqa: N802 - nombre de Qt
        super().leaveEvent(event)
        self._hovered = False
        self._update_pixmap()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - nombre de Qt
        super().mouseReleaseEvent(event)
        inside = self.rect().contains(event.position().toPoint())
        if self._clickable and self.isEnabled() and inside:
            self.clicked.emit()

    def _update_pixmap(self) -> None:
        """Dibuja el icono en el estado que toque (normal, ratón encima o desactivado)."""
        if self._icon is None:
            return
        if not self.isEnabled():
            mode = QIcon.Mode.Disabled
        elif self._clickable and self._hovered:
            mode = QIcon.Mode.Active
        else:
            mode = QIcon.Mode.Normal
        self.setPixmap(self._icon.pixmap(QSize(ICON_SIZE, ICON_SIZE), mode))


class InfoGrid(QWidget):
    """Rejilla "etiqueta | valor | icono" (ver el docstring del módulo)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        # Márgenes como los de las filas de la barra izquierda
        self._layout.setContentsMargins(8, 2, 4, 2)
        self._layout.setHorizontalSpacing(8)
        self._layout.setVerticalSpacing(ROW_SPACING)
        self._layout.setColumnMinimumWidth(0, KEY_COLUMN_MIN_WIDTH)
        self._layout.setColumnStretch(1, 1)  # el valor se queda con el ancho libre
        self._layout.setColumnMinimumWidth(2, ICON_COLUMN_WIDTH)
        self._key_labels: list[QLabel] = []  # para igualar el ancho entre secciones

    def key_labels(self) -> list[QLabel]:
        """Etiquetas de sus filas."""
        return list(self._key_labels)

    def key_column_width(self) -> int:
        """Ancho que necesitan sus etiquetas (la más larga)."""
        widths = [label.sizeHint().width() for label in self._key_labels]
        return max([KEY_COLUMN_MIN_WIDTH, *widths])

    def set_key_column_width(self, width: int) -> None:
        """Fija el ancho de la columna de etiquetas (el panel pone el mismo en todas)."""
        self._layout.setColumnMinimumWidth(0, max(KEY_COLUMN_MIN_WIDTH, width))

    def add_separator(self) -> None:
        """Línea fina de separación entre grupos de filas, a todo el ancho."""
        line = QFrame(self)
        line.setObjectName("line_inspector_separator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(1)
        self.add_widget_row(line)

    def add_widget_row(self, widget: QWidget) -> None:
        """Fila sin etiqueta: el widget ocupa todo el ancho (las tres columnas).

        Así lo que lleve a su derecha (p. ej. la extensión de la cabecera) queda alineado
        con los iconos de las filas.
        """
        row = self._layout.rowCount()
        self._layout.addWidget(widget, row, 0, 1, 3)

    def add_row(
        self,
        key: str,
        *,
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
        accessory: QWidget | None = None,
    ) -> InfoRow:
        """Añade una fila y devuelve sus widgets (el valor se rellena después).

        Args:
            key: Texto de la etiqueta («Carpeta», «Tamaño»...).
            mode: Por dónde se recorta el valor si no cabe (las rutas, por la izquierda).
            accessory: Icono o botón de la tercera columna (opcional; normalmente un
                'IconCell'). Se pega al borde derecho.
        """
        row = self._layout.rowCount()
        key_label = QLabel(key, self)
        key_label.setAlignment(KEY_ALIGNMENT | Qt.AlignmentFlag.AlignVCenter)
        set_secondary_text(key_label)
        self._key_labels.append(key_label)
        value_label = ElidedLabel(self, mode=mode)
        self._layout.addWidget(key_label, row, 0)
        self._layout.addWidget(value_label, row, 1)
        if accessory is not None:
            accessory.setParent(self)
            self._layout.addWidget(
                accessory, row, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        return InfoRow(key_label, value_label, accessory)


def set_secondary_text(label: QWidget, secondary: bool = True) -> None:
    """Pone el texto de un widget en gris (el de las etiquetas) o lo devuelve al normal.

    Se usa el color de los textos de ayuda de la paleta ('PlaceholderText'), así que sigue
    al tema (claro u oscuro) sin colores fijos.
    """
    # Se parte de la paleta del padre (la heredada): la propia puede tener ya el gris
    parent = label.parentWidget()
    palette = parent.palette() if parent is not None else label.palette()
    role = QPalette.ColorRole.PlaceholderText if secondary else QPalette.ColorRole.WindowText
    color = palette.color(role)
    own = label.palette()
    own.setColor(QPalette.ColorRole.WindowText, color)
    label.setPalette(own)


class InspectorSection(QWidget):
    """Una sección del inspector (ver el docstring del módulo).

    Signals:
        reveal_requested(object): mostrar una ruta ('Path') en el explorador de archivos.
    """

    reveal_requested = Signal(object)
    # La sección necesita sus datos otra vez (p. ej. ha cambiado de vista)
    refresh_requested = Signal()
    # La sección quiere cambiar el catálogo: (función, tupla de argumentos). Ver el módulo
    edit_requested = Signal(object, object)
    # Como 'edit_requested', con tarjetas soltadas: (función, argumentos, MediaDrag)
    drop_edit_requested = Signal(object, object, object)
    # Que la cuadrícula muestre otro origen ('GridSource'); lo elige la barra del módulo
    navigate_requested = Signal(object)

    # Título de la cabecera de la sección (el panel lo pasa a mayúsculas)
    title: str = ""
    # Clave estable (para recordar si está plegada): 'selection', 'organization'...
    key: str = ""
    # Módulos en los que aparece ('catalog', 'image'...); vacío = en todos
    modules: tuple[str, ...] = ()
    # Módulos en los que NO aparece (p. ej. donde otra sección la sustituye)
    hidden_in: tuple[str, ...] = ()

    @classmethod
    def shown_in(cls, module: str | None) -> bool:
        """True si la sección aparece en el módulo 'module' (None = aún sin módulo: en
        ese caso solo las que valen para todos)."""
        if module is None:
            return not cls.modules
        if module in cls.hidden_in:
            return False
        return not cls.modules or module in cls.modules

    def title_for(self, summary: SelectionSummary) -> str:
        """Título de la cabecera para este resumen (por defecto, el fijo: 'title')."""
        return self.title

    def applies_to(self, summary: SelectionSummary) -> bool:
        """True si la sección tiene algo que mostrar para este resumen."""
        return True

    def show_summary(self, summary: SelectionSummary) -> None:
        """Rellena la sección con el resumen de lo seleccionado (o de lo que se ve)."""
        raise NotImplementedError

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Datos propios que necesita, además del resumen (por defecto, ninguno).

        Returns:
            (función, argumentos): la función recibe la conexión como primer parámetro y
            después esos argumentos (se ejecuta con 'execute_async'); su resultado llega a
            'show_data'. None = no necesita nada.
        """
        return None

    def show_data(self, result: Any) -> None:
        """Recibe el resultado de 'data_request' (en el hilo principal)."""

    def header_widget(self) -> QWidget | None:
        """Widget para la cabecera, a la derecha del título (por defecto, ninguno)."""
        return None

    def possible_key_labels(self) -> list[str]:
        """TODAS las etiquetas que puede llegar a mostrar (no solo las de ahora).

        El panel fija el ancho de la columna de etiquetas con la más larga de todas las
        secciones: así los valores empiezan siempre en el mismo sitio, aunque la sección
        cambie de vista. Por defecto, las que tiene ahora; una sección con vistas
        («Metadatos») devuelve las de todos sus campos.
        """
        return [label.text() for grid in self.info_grids() for label in grid.key_labels()]

    def info_grids(self) -> list["InfoGrid"]:
        """Sus rejillas de filas (para igualar el ancho de las etiquetas entre secciones)."""
        return self.findChildren(InfoGrid)
