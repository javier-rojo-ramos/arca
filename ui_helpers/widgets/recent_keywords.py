"""«Últimas palabras clave»: botones para asignar con un clic las 6 últimas usadas (K4c).

    ▾ Últimas palabras clave
      [ Playa      ] [ Opel Astra ] [ Ana        ]
      [ Nieve      ] [ Comidas    ] [ Eclipse    ]

Va dentro de la sección «Palabras clave» del inspector (módulo Imagen), justo bajo la caja
de texto, y se pliega con su propia cabecera (se recuerda en settings.json). Más adelante,
al lado, «Conjuntos de palabras clave» (personalizables, como Lightroom).

Los botones miden SIEMPRE lo mismo (dos filas de tres columnas iguales, decidido por el
autor el 04/11/2026): el nombre largo se recorta con «…» y el completo, con su ruta, sale
en el texto emergente. Un hueco sin palabra no se ve pero conserva su sitio, así los
demás botones no cambian de tamaño.

Cada botón dice si la tienen los seleccionados (como las casillas del árbol):
    marcado (borde y texto en el color de acento)  -> la tienen todos: pulsar la QUITA;
    con «*»                                        -> la tienen algunos: pulsar la pone a todos;
    normal                                         -> ninguno: pulsar la pone a todos.

El widget no toca la base de datos: emite 'keyword_clicked(id, asignar)'.

El aspecto se define en ui_theme.py con 'btn_recent_keyword' y 'btn_recent_keywords_toggle'.

Prueba rápida de la lógica (sin Qt):
    python -m ui_helpers.widgets.recent_keywords
"""

__version__ = "1.0.0"
__all__ = ["RecentKeywords", "recent_button_states"]

# Librerías estándar
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.catalog.keywords import PARTIAL_MARK, PATH_SEPARATOR, RECENT_LIMIT, SelectionKeywords

# Columnas de botones (con RECENT_LIMIT = 6, dos filas)
COLUMNS = 3
# Título de la cabecera plegable
TITLE = "Últimas palabras clave"
# Margen horizontal del texto dentro del botón (px lógicos), para recortarlo con «…»
_TEXT_PADDING = 14

# Estados de un botón
NONE, SOME, ALL = 0, 1, 2


@dataclass(frozen=True, slots=True)
class RecentButtonState:
    """Lo que muestra un botón: palabra, texto, texto emergente y si la tienen."""

    keyword_id: int
    text: str
    tooltip: str
    state: int  # NONE, SOME o ALL


def recent_button_states(
    recent: Sequence[tuple[int, tuple[str, ...]]], selection: SelectionKeywords
) -> list[RecentButtonState]:
    """Estado de cada botón: nombre (o «Padre > Nombre» si dos de las recientes se llaman
    igual), con «*» si solo la tienen algunos, y la ruta completa en el emergente."""
    counts = dict(zip(selection.keyword_ids, (count for _path, count in selection.items), strict=False))
    leaves = Counter(fold_text(path[-1]) for _id, path in recent if path)
    result = []
    for keyword_id, path in recent:
        if not path:
            continue
        full = f" {PATH_SEPARATOR} ".join(path)
        name = full if leaves[fold_text(path[-1])] > 1 else path[-1]
        count = counts.get(keyword_id, 0)
        total = selection.total
        if total and count >= total:
            state, tip = ALL, f"{full}\nLa tienen todos los seleccionados: pulsar la quita."
        elif count:
            state, tip = SOME, f"{full}\nLa tienen {count} de {total}: pulsar la pone a todos."
            name += PARTIAL_MARK
        else:
            state, tip = NONE, f"{full}\nPulsar la pone a los seleccionados."
        result.append(RecentButtonState(keyword_id, name, tip, state))
    return result


class _ElidedButton(QPushButton):
    """Botón que recorta su texto con «…» al ancho que tenga (no crece con el texto)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        # Ancho decidido por la rejilla (columnas iguales), no por el texto
        policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        policy.setRetainSizeWhenHidden(True)  # un hueco vacío conserva su sitio
        self.setSizePolicy(policy)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self._update_text()

    def resizeEvent(self, event) -> None:  # nombre de Qt
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self) -> None:
        width = max(0, self.width() - _TEXT_PADDING)
        self.setText(self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width))


class RecentKeywords(QWidget):
    """Cabecera plegable + rejilla de botones (ver el docstring del módulo).

    Signals:
        keyword_clicked(int, bool): se ha pulsado una palabra; True = ponerla a todos,
            False = quitarla de todos.
        expanded_changed(bool): se ha plegado o desplegado (para recordarlo).
    """

    keyword_clicked = Signal(int, bool)
    expanded_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None, *, expanded: bool = True) -> None:
        super().__init__(parent)
        self._states: list[RecentButtonState] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Cabecera: flecha + título (pulsar pliega o despliega)
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("btn_recent_keywords_toggle")
        self._toggle.setText(TITLE)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setAutoRaise(True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle)

        # Rejilla de botones, columnas del mismo ancho
        self._body = QWidget(self)
        grid = QGridLayout(self._body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self._buttons: list[_ElidedButton] = []
        for position in range(RECENT_LIMIT):
            button = _ElidedButton(self._body)
            button.setObjectName("btn_recent_keyword")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # el foco se queda en la caja
            button.clicked.connect(lambda _checked=False, p=position: self._on_clicked(p))
            button.setVisible(False)
            grid.addWidget(button, position // COLUMNS, position % COLUMNS)
            self._buttons.append(button)
        for column in range(COLUMNS):
            grid.setColumnStretch(column, 1)
        layout.addWidget(self._body)

        # Aviso cuando aún no hay recientes (en gris: desactivado)
        self._hint = QLabel("Aquí aparecerán las últimas palabras que asignes.", self)
        self._hint.setObjectName("lbl_recent_keywords_hint")
        self._hint.setWordWrap(True)
        self._hint.setEnabled(False)
        layout.addWidget(self._hint)

        self._on_toggled(expanded, notify=False)

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def set_data(
        self, recent: Sequence[tuple[int, tuple[str, ...]]], selection: SelectionKeywords
    ) -> None:
        """Pone las últimas palabras y su estado para la selección."""
        self._states = recent_button_states(recent, selection)
        for position, button in enumerate(self._buttons):
            if position < len(self._states):
                state = self._states[position]
                button.set_full_text(state.text)
                button.setToolTip(state.tooltip)
                button.setChecked(state.state == ALL)
                button.setProperty("partial", state.state == SOME)
                button.style().unpolish(button)  # aplica el estilo de 'partial'
                button.style().polish(button)
                button.setVisible(True)
            else:
                button.setVisible(False)
        self._update_visibility()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_toggled(self, expanded: bool, notify: bool = True) -> None:
        """Pliega o despliega los botones (flecha hacia abajo = desplegado)."""
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._update_visibility()
        if notify:
            self.expanded_changed.emit(expanded)

    def _update_visibility(self) -> None:
        expanded = self._toggle.isChecked()
        self._body.setVisible(expanded and bool(self._states))
        self._hint.setVisible(expanded and not self._states)

    def _on_clicked(self, position: int) -> None:
        """Pulsado: quitar si la tenían todos; si no, ponerla a todos."""
        if position >= len(self._states):
            return
        state = self._states[position]
        # Qt ya ha cambiado el estado del botón; se deja como estaba hasta que lleguen los
        # datos nuevos (si falla el guardado, no queda marcado sin estarlo)
        self._buttons[position].setChecked(state.state == ALL)
        self.keyword_clicked.emit(state.keyword_id, state.state != ALL)


if __name__ == "__main__":
    # Autoprueba de la lógica (no necesita Qt real). Desde la raíz del proyecto:
    #     python -m ui_helpers.widgets.recent_keywords
    recent = ((5, ("Playa",)), (2, ("Amigos", "Ana")), (6, ("Familia", "Ana")), (9, ("Nieve",)))
    sel = SelectionKeywords(total=3, items=((("Amigos", "Ana"), 1), (("Playa",), 3)), keyword_ids=(2, 5))
    states = recent_button_states(recent, sel)
    assert [s.text for s in states] == ["Playa", "Amigos > Ana*", "Familia > Ana", "Nieve"], states
    assert [s.state for s in states] == [ALL, SOME, NONE, NONE]
    assert states[0].tooltip.endswith("pulsar la quita.") and "1 de 3" in states[1].tooltip
    # Sin selección (total 0): nada marcado
    assert all(s.state == NONE for s in recent_button_states(recent, SelectionKeywords()))
    print("Autoprueba finalizada correctamente.")
