"""Sección plegable para las barras laterales (como los paneles de Lightroom).

Una cabecera con una flecha y un título que, al pulsarla, muestra u oculta el contenido.
A la derecha de la cabecera se pueden añadir botones (p. ej. el "+" para crear una
colección, en el paso 1d).

Uso:
    section = CollapsibleSection("Carpetas", parent)
    section.set_content(tree_view)
    section.add_header_widget(add_button)   # opcional
    layout.addWidget(section)

El aspecto (fondo de la cabecera, negrita...) se define en la hoja de estilos global
(ui_helpers/helpers/ui_theme.py) con los nombres de objeto:
    - QFrame#frame_section_header     la barra de la cabecera
    - QToolButton#btn_section_header  la flecha + el título

1.4.0 Arrastrar la cabecera (por el título): señales 'header_drag_started',
      'header_drag_moved' y 'header_drag_finished' (lo que se hace con el arrastre lo decide
      quien la usa: 'SectionStack' la cambia de sitio). Un clic sin mover sigue plegando.
1.3.0 Señal 'header_menu_requested': clic derecho en la cabecera (el menú lo pone quien la
      usa: 'SectionStack', con las secciones para mostrar u ocultar). El clic derecho en un
      hueco del contenido no hace nada (no se pasa a la barra).
1.2.0 'set_title': cambiar el título después de crearla (p. ej. «SELECCIÓN (VISTA ACTUAL)»).
1.1.0 Título en mayúsculas. Los botones de la cabecera se alinean a la derecha con los
      contadores de los árboles ('HEADER_RIGHT_MARGIN').
"""

__version__ = "1.4.0"
__all__ = ["HEADER_RIGHT_MARGIN", "CollapsibleSection"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QObject, QPoint, Qt, Signal
from qtpy.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Margen derecho de la cabecera (píxeles lógicos). Pensado para que el "+" quede alineado
# con los contadores de los árboles (que se pintan a unos 6 px del borde, y el SVG tiene
# su propio margen interior). Si en tu pantalla no cuadra, se ajusta aquí.
HEADER_RIGHT_MARGIN = 1


class CollapsibleSection(QWidget):
    """Cabecera con flecha + contenido que se pliega y despliega.

    Signals:
        toggled(bool): la sección se ha desplegado (True) o plegado (False).
        header_menu_requested(QPoint): clic derecho en la cabecera (en cualquier punto,
            también sobre sus botones); lleva la posición en la pantalla.
        header_drag_started(): se empieza a arrastrar la cabecera por el título (el botón
            izquierdo pulsado y el ratón movido más que la distancia de arrastre del sistema).
        header_drag_moved(QPoint): el ratón se mueve durante el arrastre (posición en la
            pantalla).
        header_drag_finished(QPoint): se suelta el botón (posición en la pantalla). La
            sección NO se pliega ni se despliega: no ha sido un clic.
    """

    toggled = Signal(bool)
    header_menu_requested = Signal(QPoint)
    header_drag_started = Signal()
    header_drag_moved = Signal(QPoint)
    header_drag_finished = Signal(QPoint)

    def __init__(
        self, title: str, parent: QWidget | None = None, *, expanded: bool = True
    ) -> None:
        """Crea la sección (todavía sin contenido: ver 'set_content').

        Args:
            title: Texto de la cabecera.
            parent: Widget padre.
            expanded: Si empieza desplegada.
        """
        super().__init__(parent)

        # La sección ocupa el alto de su contenido, ni más ni menos: así varias secciones
        # se apilan una debajo de otra, como en Lightroom
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Cabecera: [▼ Título ............ (botones)] ---
        self._header = QFrame(self)
        self._header.setObjectName("frame_section_header")
        # Clic derecho en la cabecera: se avisa (el botón del título y los de la derecha no
        # tienen menú propio, así que el suyo también llega aquí)
        self._header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._header.customContextMenuRequested.connect(
            lambda position: self.header_menu_requested.emit(self._header.mapToGlobal(position))
        )
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(2, 0, HEADER_RIGHT_MARGIN, 0)
        header_layout.setSpacing(2)

        self._toggle_button = QToolButton(self._header)
        self._toggle_button.setObjectName("btn_section_header")
        # En mayúsculas (como las interfaces actuales); el texto original se guarda
        self._title = title
        self._toggle_button.setText(title.upper())
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(expanded)
        # La flecha la dibuja Qt (no hace falta un icono propio) y el texto va a su lado
        self._toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._toggle_button.setAutoRaise(True)
        # Que ocupe todo el ancho libre: así se puede pulsar en cualquier punto de la cabecera
        self._toggle_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._toggle_button.toggled.connect(self._on_toggled)
        # Arrastrar la cabecera por el título (ver 'eventFilter'): dónde se pulsó el botón
        # izquierdo (None = no está pulsado) y si ya se está arrastrando
        self._press_position: QPoint | None = None
        self._dragging = False
        self._toggle_button.installEventFilter(self)
        header_layout.addWidget(self._toggle_button)
        self._header_layout = header_layout

        layout.addWidget(self._header)

        # --- Contenido ---
        self._body = QWidget(self)
        # El clic derecho en un hueco del contenido se queda aquí: no sube a la barra (que
        # abriría el menú de las secciones, reservado a las cabeceras y al hueco de abajo).
        # Los menús propios del contenido (árboles, cajas de texto) no cambian
        self._body.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 2, 0, 6)  # un poco de aire debajo
        self._body_layout.setSpacing(0)
        layout.addWidget(self._body)

        # Estado inicial (flecha y visibilidad)
        self._apply_state(expanded)

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def set_content(self, widget: QWidget) -> None:
        """Pone el widget que se muestra al desplegar la sección (sustituye al anterior)."""
        while self._body_layout.count():
            old = self._body_layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
        widget.setParent(self._body)
        self._body_layout.addWidget(widget)

    def set_title(self, title: str) -> None:
        """Cambia el texto de la cabecera (se muestra en mayúsculas, como al crearla)."""
        if title != self._title:
            self._title = title
            self._toggle_button.setText(title.upper())

    def add_header_widget(self, widget: QWidget) -> None:
        """Añade un widget (normalmente un botón pequeño) a la derecha de la cabecera."""
        widget.setParent(self._header)
        self._header_layout.addWidget(widget)

    def is_expanded(self) -> bool:
        """True si la sección está desplegada."""
        return self._toggle_button.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        """Despliega o pliega la sección (emite 'toggled' si cambia)."""
        self._toggle_button.setChecked(expanded)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Convierte en un ARRASTRE de la cabecera el pulsar el título y mover el ratón.

        Mientras el botón del título está pulsado, Qt le manda a él todos los movimientos
        del ratón, aunque salga de la cabecera: basta con mirarlos aquí. Un clic sin mover
        (o moviendo menos que la distancia de arrastre del sistema) no se toca: pliega o
        despliega, como siempre.
        """
        if watched is self._toggle_button:
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._press_position = event.globalPosition().toPoint()
                    self._dragging = False
            elif kind == QEvent.Type.MouseMove and self._press_position is not None:
                position = event.globalPosition().toPoint()
                distance = (position - self._press_position).manhattanLength()
                if not self._dragging and distance >= QApplication.startDragDistance():
                    self._dragging = True
                    # Ya no es un clic: el botón deja de estar hundido, así al soltar no
                    # pliega la sección
                    self._toggle_button.setDown(False)
                    self.header_drag_started.emit()
                if self._dragging:
                    self.header_drag_moved.emit(position)
                    return True  # el botón no lo ve (si no, se hundiría otra vez al pasar)
            elif (
                kind == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                was_dragging = self._dragging
                self._press_position = None
                self._dragging = False
                if was_dragging:
                    self._toggle_button.setDown(False)
                    self.header_drag_finished.emit(event.globalPosition().toPoint())
                    # El botón sí ve que se suelta (para quedar en reposo), pero como no
                    # está hundido no hace clic
        return super().eventFilter(watched, event)

    def _on_toggled(self, expanded: bool) -> None:
        self._apply_state(expanded)
        self.toggled.emit(expanded)

    def _apply_state(self, expanded: bool) -> None:
        """Ajusta la flecha (▼ desplegada, ▶ plegada) y muestra u oculta el contenido."""
        arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        self._toggle_button.setArrowType(arrow)
        self._body.setVisible(expanded)
