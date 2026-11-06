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

1.2.0 'set_title': cambiar el título después de crearla (p. ej. «SELECCIÓN (VISTA ACTUAL)»).
1.1.0 Título en mayúsculas. Los botones de la cabecera se alinean a la derecha con los
      contadores de los árboles ('HEADER_RIGHT_MARGIN').
"""

__version__ = "1.2.0"
__all__ = ["HEADER_RIGHT_MARGIN", "CollapsibleSection"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
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
    """

    toggled = Signal(bool)

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
        header_layout.addWidget(self._toggle_button)
        self._header_layout = header_layout

        layout.addWidget(self._header)

        # --- Contenido ---
        self._body = QWidget(self)
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

    def _on_toggled(self, expanded: bool) -> None:
        self._apply_state(expanded)
        self.toggled.emit(expanded)

    def _apply_state(self, expanded: bool) -> None:
        """Ajusta la flecha (▼ desplegada, ▶ plegada) y muestra u oculta el contenido."""
        arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        self._toggle_button.setArrowType(arrow)
        self._body.setVisible(expanded)
