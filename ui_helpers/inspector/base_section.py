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
    - 'libraries':      de qué bibliotecas es la sección (vacío = de todas, como las
                        palabras clave). Una sección de una biblioteca solo aparece si TODO
                        lo resumido (la selección; sin ella, lo que se ve) es de ella: p. ej.
                        «Metadatos», de Imagen. NO depende del módulo activo: el inspector
                        es el mismo en todos (decidido por el autor el 08/11/2026). Ver 'fits'.
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

Filas "etiqueta | valor | icono": 'InfoGrid' es una rejilla con la etiqueta en gris, el
valor (recortado con '…' si no cabe) y una columna estrecha para un botón o un icono.
Todas las secciones la usan, así que las columnas quedan alineadas de una sección a otra.
Por dentro, las separaciones entre esas columnas son columnas de ancho fijo (no la
separación de Qt): así una caja editable ('add_editor_row') empieza 'EDITOR_TEXT_INSET' px
antes que los valores y su texto queda alineado con el de ellos.

Los iconos de la tercera columna son 'IconCell' (un icono, una inicial o un botón): van
pegados al borde DERECHO, igual que la etiqueta de la extensión de la cabecera, y bajados
'ICON_Y_OFFSET' px para que su centro coincida con el del texto (el centro geométrico
de una línea de texto queda por encima del de las letras, por el hueco de los
descendentes).

1.10.1 Margen derecho de las filas de 8 px, como el izquierdo (antes, 4): el contenido del
       inspector queda a la misma distancia de los dos bordes (pedido por el autor).
1.10.0 Las cajas editables empiezan 'EDITOR_TEXT_INSET' px antes que los valores: su
       texto queda alineado con el de las demás filas (pedido por el autor). Las
       separaciones entre columnas pasan a ser columnas fijas (sin cambio para el resto de
       filas: comprobado midiendo antes y después).
1.9.0 'InfoGrid.add_editor_row': fila con un widget propio como valor (las cajas
      editables de «Metadatos»).
1.8.0 Secciones según la biblioteca de lo resumido ('libraries', 'fits'), no según el
      módulo activo (fuera 'modules', 'hidden_in' y 'shown_in'); paso A.2.
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

__version__ = "1.10.1"
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
# Separación horizontal entre la etiqueta y el valor, y entre el valor y el icono (px)
COLUMN_SPACING = 8
# Distancia del borde izquierdo de una caja editable ('editable_row.py') a su texto (px):
# borde (1) + relleno del QSS (2) + margen propio de la caja (2). Las cajas empiezan esos
# píxeles ANTES que los valores de texto: así su texto queda alineado con el de las demás
# filas y el recuadro asoma por el hueco de la izquierda (pedido por el autor el
# 10/11/2026). La autoprueba de 'editable_row' comprueba que la caja mide eso
EDITOR_TEXT_INSET = 5

# Columnas de la rejilla. Sin separación propia ('setHorizontalSpacing(0)'): los huecos son
# columnas de ancho fijo, para que una caja editable pueda empezar en la del margen
_KEY_COLUMN, _GAP_COLUMN, _INSET_COLUMN, _VALUE_COLUMN, _ICON_GAP_COLUMN, _ICON_COLUMN = range(6)
_COLUMN_COUNT = 6


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

    def changeEvent(self, event) -> None:  # nombre de Qt
        super().changeEvent(event)
        self._update_pixmap()  # activado / desactivado

    def enterEvent(self, event) -> None:  # nombre de Qt
        super().enterEvent(event)
        self._hovered = True
        self._update_pixmap()

    def leaveEvent(self, event) -> None:  # nombre de Qt
        super().leaveEvent(event)
        self._hovered = False
        self._update_pixmap()

    def mouseReleaseEvent(self, event) -> None:  # nombre de Qt
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
        # 8 px a cada lado, simétrico (pedido por el autor el 11/11/2026; antes, 4 a la
        # derecha). Las secciones que no usan la rejilla repiten estos márgenes
        self._layout.setContentsMargins(8, 2, 8, 2)
        # Columnas: etiqueta | hueco | margen de las cajas | valor | hueco | icono. Los
        # huecos son columnas fijas (ver '_KEY_COLUMN'...): hueco + margen = COLUMN_SPACING
        self._layout.setHorizontalSpacing(0)
        self._layout.setVerticalSpacing(ROW_SPACING)
        self._layout.setColumnMinimumWidth(_KEY_COLUMN, KEY_COLUMN_MIN_WIDTH)
        self._layout.setColumnMinimumWidth(_GAP_COLUMN, COLUMN_SPACING - EDITOR_TEXT_INSET)
        self._layout.setColumnMinimumWidth(_INSET_COLUMN, EDITOR_TEXT_INSET)
        self._layout.setColumnStretch(_VALUE_COLUMN, 1)  # el valor se queda con el ancho libre
        # El hueco antes de los iconos, siempre (como cuando era la separación de Qt: las
        # rejillas del inspector siempre tienen filas a todo el ancho o iconos)
        self._layout.setColumnMinimumWidth(_ICON_GAP_COLUMN, COLUMN_SPACING)
        self._layout.setColumnMinimumWidth(_ICON_COLUMN, ICON_COLUMN_WIDTH)
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
        self._layout.setColumnMinimumWidth(_KEY_COLUMN, max(KEY_COLUMN_MIN_WIDTH, width))

    def add_separator(self) -> None:
        """Línea fina de separación entre grupos de filas, a todo el ancho."""
        line = QFrame(self)
        line.setObjectName("line_inspector_separator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(1)
        self.add_widget_row(line)

    def add_widget_row(self, widget: QWidget) -> None:
        """Fila sin etiqueta: el widget ocupa todo el ancho (todas las columnas).

        Así lo que lleve a su derecha (p. ej. la extensión de la cabecera) queda alineado
        con los iconos de las filas.
        """
        row = self._layout.rowCount()
        self._layout.addWidget(widget, row, 0, 1, _COLUMN_COUNT)

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
        self._layout.addWidget(key_label, row, _KEY_COLUMN)
        self._layout.addWidget(value_label, row, _VALUE_COLUMN)
        if accessory is not None:
            accessory.setParent(self)
            self._layout.addWidget(
                accessory, row, _ICON_COLUMN,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )  # fmt: skip
        return InfoRow(key_label, value_label, accessory)

    def add_editor_row(self, key: str, editor: QWidget, *, align_top: bool = False) -> QLabel:
        """Añade una fila cuyo valor es un widget propio (p. ej. una caja editable).

        El widget empieza 'EDITOR_TEXT_INSET' px antes que los valores de texto (su texto
        queda alineado con el de ellos) y llega hasta el borde derecho (no lleva icono).

        Args:
            key: Texto de la etiqueta.
            editor: El widget del valor (pasa a ser hijo de la rejilla).
            align_top: True si el widget ocupa varias líneas (la etiqueta va arriba, a la
                altura de la primera).

        Returns:
            La etiqueta (para su texto emergente).
        """
        row = self._layout.rowCount()
        key_label = QLabel(key, self)
        vertical = Qt.AlignmentFlag.AlignTop if align_top else Qt.AlignmentFlag.AlignVCenter
        key_label.setAlignment(KEY_ALIGNMENT | vertical)
        set_secondary_text(key_label)
        self._key_labels.append(key_label)
        editor.setParent(self)
        self._layout.addWidget(key_label, row, _KEY_COLUMN, vertical)
        self._layout.addWidget(editor, row, _INSET_COLUMN, 1, _COLUMN_COUNT - _INSET_COLUMN)
        return key_label


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
    # Bibliotecas de las que es la sección ('image', 'audio'...); vacío = de todas
    libraries: tuple[str, ...] = ()

    @classmethod
    def fits(cls, summary: SelectionSummary) -> bool:
        """True si la sección es de la biblioteca de lo resumido (o de todas). Lo comprueba
        el panel antes de 'applies_to'."""
        return not cls.libraries or summary.single_library in cls.libraries

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
