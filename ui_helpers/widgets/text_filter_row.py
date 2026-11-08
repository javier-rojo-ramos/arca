"""Fila de «Texto» de la barra de filtros: dónde buscar, cómo y qué.

    [Todos los campos disponibles ▾] [Contiene ▾] [________________________ ×]

    - Campo:    «Todos los campos disponibles» (nombre de archivo, título, descripción y
                palabras clave) · separador · «Nombre de archivo».
    - Operador: «Contiene» · «No contiene» · separador · «Empieza con» · «Termina con».
    - Caja de texto con el botón «×» para vaciarla.

Solo muestra y avisa: emite 'text_filter_changed(TextFilter)' (de 'core/catalog/
grid_filter.py') y lo que se ve lo pone 'set_filter' (sin emitir). Al escribir, el aviso
espera una pausa ('TYPING_DELAY_MS'): así no se recarga la cuadrícula con cada letra. Los
desplegables avisan en el acto (con lo escrito hasta entonces). Con la caja vacía el
filtro no filtra (lo decide 'TextFilter.rule_set').

Los desplegables no cogen el foco (el teclado sigue donde estaba); la caja sí, para
escribir ('focus_text', que usa Ctrl+F).

Uso (lo crea el controlador principal y se lo pasa al 'FilterController'):
    row = TextFilterRow(parent)
    row.text_filter_changed.connect(...)
    row.set_filter(TextFilter())

1.0.0 Primera versión (paso A.3, subpaso 4).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.text_filter_row
"""

__version__ = "1.0.0"
__all__ = ["FIELD_TEXTS", "OPERATOR_TEXTS", "TYPING_DELAY_MS", "TextFilterRow"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget

# Módulos del proyecto
from core.catalog.grid_filter import (
    MAX_TEXT_LENGTH,
    TEXT_ALL_FIELDS,
    TEXT_FILE_NAME,
    TEXT_OPERATORS,
    TextFilter,
)

# Textos de la interfaz, en el orden de los desplegables (None = separador)
FIELD_TEXTS: tuple[tuple[str, str] | None, ...] = (
    (TEXT_ALL_FIELDS, "Todos los campos disponibles"),
    None,
    (TEXT_FILE_NAME, "Nombre de archivo"),
)
OPERATOR_TEXTS: tuple[tuple[str, str] | None, ...] = (
    ("contains", "Contiene"),
    ("not_contains", "No contiene"),
    None,
    ("starts_with", "Empieza con"),
    ("ends_with", "Termina con"),
)

# Pausa al escribir antes de filtrar (ms)
TYPING_DELAY_MS = 300

# Medidas (px lógicos)
ROW_HEIGHT = 30  # la misma que la fila de las pestañas
TEXT_WIDTH = 320  # caja de texto
_SPACING = 6

# Nombre de objeto (por si el QSS lo necesita)
OBJECT_NAME = "widget_text_filter_row"


class TextFilterRow(QWidget):
    """Fila de «Texto» de la barra de filtros (ver el docstring del archivo).

    Signals:
        text_filter_changed(object): el usuario ha cambiado el campo, el operador o el
            texto (lleva el 'TextFilter' nuevo).
    """

    text_filter_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(OBJECT_NAME)
        self.setFixedHeight(ROW_HEIGHT)
        self._shown = TextFilter()  # lo último puesto o avisado

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_SPACING)

        self._field = self._make_combo(FIELD_TEXTS)
        self._operator = self._make_combo(OPERATOR_TEXTS)
        self._text = QLineEdit(self)
        self._text.setClearButtonEnabled(True)
        self._text.setMaxLength(MAX_TEXT_LENGTH)
        self._text.setFixedWidth(TEXT_WIDTH)

        # Centrada, como las pestañas de encima
        layout.addStretch(1)
        layout.addWidget(self._field)
        layout.addWidget(self._operator)
        layout.addWidget(self._text)
        layout.addStretch(1)

        # El texto avisa tras una pausa; los desplegables, en el acto
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TYPING_DELAY_MS)
        self._timer.timeout.connect(self._emit)
        self._text.textEdited.connect(lambda _text: self._timer.start())
        # La «×» vacía la caja sin pasar por 'textEdited': se avisa igual (tras la pausa)
        self._text.textChanged.connect(self._on_text_changed)
        self._field.activated.connect(lambda _index: self._emit())
        self._operator.activated.connect(lambda _index: self._emit())

        self.set_filter(TextFilter())

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def current(self) -> TextFilter:
        """Lo que se ve ahora (campo, operador y texto)."""
        return TextFilter(
            self._field.currentData() or TEXT_ALL_FIELDS,
            self._operator.currentData() or TEXT_OPERATORS[0],
            self._text.text(),
        )

    def set_filter(self, text_filter: TextFilter) -> None:
        """Muestra un filtro de texto (no emite nada). Si ya es lo que se ve, no toca nada
        (así no se mueve el cursor mientras se escribe)."""
        if text_filter == self.current():
            self._shown = text_filter
            return
        self._timer.stop()  # lo pendiente de avisar ya no vale
        self._select(self._field, text_filter.field)
        self._select(self._operator, text_filter.operator)
        if self._text.text() != text_filter.text:
            self._text.blockSignals(True)
            self._text.setText(text_filter.text)
            self._text.blockSignals(False)
        self._shown = text_filter

    def focus_text(self) -> None:
        """Pone el cursor en la caja con todo lo escrito seleccionado (Ctrl+F)."""
        self._text.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._text.selectAll()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _make_combo(self, items: tuple[tuple[str, str] | None, ...]) -> QComboBox:
        """Desplegable con sus opciones (clave en los datos) y sus separadores."""
        combo = QComboBox(self)
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for item in items:
            if item is None:
                combo.insertSeparator(combo.count())
            else:
                key, text = item
                combo.addItem(text, key)
        return combo

    @staticmethod
    def _select(combo: QComboBox, key: str) -> None:
        """Elige la opción con esa clave (si no existe, la primera)."""
        index = combo.findData(key)
        combo.setCurrentIndex(max(index, 0))

    def _on_text_changed(self, text: str) -> None:
        """Al vaciar la caja con la «×» (o con lo que sea), se avisa tras la pausa."""
        if not text and self._shown.text:
            self._timer.start()

    def _emit(self) -> None:
        """Avisa con lo que se ve, si ha cambiado desde lo último puesto o avisado."""
        self._timer.stop()
        current = self.current()
        if current == self._shown:
            return
        self._shown = current
        self.text_filter_changed.emit(current)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): comprueba la lógica de la fila.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.text_filter_row
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtTest import QTest
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    holder = QWidget()  # padre que nunca se muestra: no se crea ninguna ventana
    row = TextFilterRow(holder)
    seen: list[TextFilter] = []
    row.text_filter_changed.connect(seen.append)

    # Opciones y separadores, en el orden acordado
    texts = [row._field.itemText(i) for i in range(row._field.count())]
    assert texts == ["Todos los campos disponibles", "", "Nombre de archivo"], texts
    ops = [row._operator.itemText(i) for i in range(row._operator.count())]
    assert ops == ["Contiene", "No contiene", "", "Empieza con", "Termina con"], ops
    assert row.current() == TextFilter() and row._field.focusPolicy() == Qt.FocusPolicy.NoFocus

    # Escribir: un solo aviso, tras la pausa
    row._text.setText("bo")
    row._text.textEdited.emit("bo")
    row._text.setText("boda")
    row._text.textEdited.emit("boda")
    assert seen == []
    QTest.qWait(TYPING_DELAY_MS + 150)
    assert seen == [TextFilter(text="boda")], seen

    # Un desplegable: aviso en el acto
    row._operator.setCurrentIndex(row._operator.findData("ends_with"))
    row._operator.activated.emit(row._operator.currentIndex())
    assert seen[-1] == TextFilter(TEXT_ALL_FIELDS, "ends_with", "boda")

    # Vaciar con la «×» (textChanged sin textEdited): aviso tras la pausa
    row._text.clear()
    QTest.qWait(TYPING_DELAY_MS + 150)
    assert seen[-1].text == "" and len(seen) == 3

    # 'set_filter' no avisa, y anula lo pendiente
    row._text.setText("x")
    row._text.textEdited.emit("x")
    row.set_filter(TextFilter(TEXT_FILE_NAME, "starts_with", "IMG"))
    QTest.qWait(TYPING_DELAY_MS + 150)
    assert len(seen) == 3 and row.current() == TextFilter(TEXT_FILE_NAME, "starts_with", "IMG")
    # Una clave desconocida: la primera opción
    row.set_filter(TextFilter("otra", "eq", ""))
    assert row.current() == TextFilter()
    assert row._text.maxLength() == MAX_TEXT_LENGTH

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
