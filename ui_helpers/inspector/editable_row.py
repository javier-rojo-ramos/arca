"""Valor editable de una fila del inspector: título, pie, creador... (paso C.5).

    Título    Atardecer en León               <- parece texto; recuadro con el ratón
    Pie       Primera línea                      o al entrar en él
              Segunda línea                   <- varias líneas: alto fijo (3), con barra
                                                 si hay más

'EditableValue' es la caja (una línea, 'QLineEdit', o varias, 'QPlainTextEdit') con lo
común a todas:
    - 'set_value(texto, mixed=...)': lo que hay en el catálogo. Con valores distintos en
      la selección ('mixed'), el texto de la caja es «Varios», en gris (como Lightroom): al
      entrar se selecciona entero y lo que se escribe lo sustituye.
    - Intro o salir de la caja: si el texto ha cambiado, señal 'committed(valor)' (None =
      vacío). Un «Varios» sin tocar no cambia nada; borrado, sí (vaciar en todos). Quien
      la usa decide y responde con 'mark_applied()' (se aplica), 'revert()' (no) o
      'reject(aviso)' (no vale: vuelve y muestra el aviso junto a la caja). Con
      Intro, además, la caja suelta el foco y vuelve a verse como texto (si siguiera con
      el borde de acento, parecería que no se ha aplicado; pedido por el autor).
    - Esc: vuelve al valor que se mostró. Tab: a la caja siguiente. En la de varias
      líneas, Mayús+Intro hace un salto de línea.
    - 'is_editing()': el usuario está escribiendo (tiene el foco y ha cambiado algo); quien
      refresca la caja no debe pisarle el texto.

La caja no sabe de qué campo es ni toca la base de datos: lo hace la sección
('metadata_section.py'). Su aspecto, en el QSS de 'ui_theme.py' (objectName
'edit_inspector_value', propiedad 'mixed').

Como en la caja de palabras clave ('keyword_editor_section.py'), las teclas se atienden
en subclases ('keyPressEvent') y salir de la caja para abrir su menú contextual
('PopupFocusReason') no cuenta como salir.

1.3.0 'reject(aviso)': lo escrito no vale (una ubicación imposible): la caja vuelve a su
      valor y muestra el aviso junto a ella, unos segundos (decidido por el autor).
1.2.0 El texto de la caja de varias líneas, a la misma distancia del borde que en la de
      una línea ('base_section.EDITOR_TEXT_INSET'; margen del documento de 2 px): la
      rejilla adelanta las cajas esa distancia y su texto queda alineado con el de las
      demás filas (pedido por el autor). La autoprueba lo mide con el tema.
1.1.0 Tras verlo el autor: con Intro la caja suelta el foco (vuelve a verse como texto);
      sin la ayuda al pasar el ratón (molestaba).
1.0.0 Primera versión: una línea y varias líneas; «Varios» como en Lightroom.

Prueba rápida (sin ventana; necesita PySide6):
    python -m ui_helpers.inspector.editable_row
"""

__version__ = "1.3.0"
__all__ = ["MULTI_LINE_ROWS", "REJECT_NOTICE_MS", "EditableValue"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint, QRect, Qt, QTimer, Signal
from qtpy.QtGui import QFocusEvent, QKeyEvent, QShowEvent
from qtpy.QtWidgets import QLineEdit, QPlainTextEdit, QToolTip, QVBoxLayout, QWidget

# Módulos del proyecto
from ui_helpers.inspector.metadata_fields import MIXED_TEXT

# Líneas a la vista de una caja de varias líneas (decidido por el autor: 3 fijas, así la
# sección no cambia de alto)
MULTI_LINE_ROWS = 3

_ENTER_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)

# Cuánto tiempo se ve el aviso de un valor no válido (milisegundos)
REJECT_NOTICE_MS = 6000


class _LineEditor(QLineEdit):
    """Caja de una línea: Intro aplica, Esc deshace, salir aplica."""

    enter_pressed = Signal()
    commit_requested = Signal()  # al salir de la caja
    revert_requested = Signal()
    focused = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in _ENTER_KEYS:
            event.accept()
            self.enter_pressed.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.revert_requested.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        # Abrir el menú contextual de la caja no es salir de ella
        if event.reason() != Qt.FocusReason.PopupFocusReason:
            self.commit_requested.emit()


class _TextEditor(QPlainTextEdit):
    """Caja de varias líneas: Intro aplica, Mayús+Intro salto de línea, Esc deshace, salir
    aplica."""

    enter_pressed = Signal()
    commit_requested = Signal()  # al salir de la caja
    revert_requested = Signal()
    focused = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in _ENTER_KEYS:
            event.accept()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Un párrafo nuevo (no el separador de línea que pondría Qt): en el texto
                # sale como '\n'
                self.textCursor().insertText("\n")
            else:
                self.enter_pressed.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.revert_requested.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        if event.reason() != Qt.FocusReason.PopupFocusReason:
            self.commit_requested.emit()


class EditableValue(QWidget):
    """Caja editable de una fila del inspector (ver el docstring del módulo).

    Signals:
        committed(object): el usuario ha aplicado un texto distinto del mostrado (str, o
            None si lo ha dejado vacío). Quien escucha responde con 'mark_applied()' o
            'revert()'.
    """

    committed = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, multiline: bool = False) -> None:
        super().__init__(parent)
        self._multiline = multiline
        self._shown = ""  # texto puesto por el programa (el del catálogo o «Varios»)
        self._mixed = False  # se mostró «Varios» (valores distintos en la selección)
        self._updating = False  # el texto lo está poniendo el programa
        self._busy = False  # avisando de un cambio (p. ej. con un aviso abierto)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._editor: _LineEditor | _TextEditor
        if multiline:
            editor = _TextEditor(self)
            editor.setTabChangesFocus(True)
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            # Con 2 px, su texto empieza a la misma distancia del borde que en la caja de una
            # línea ('base_section.EDITOR_TEXT_INSET'; lo comprueba la autoprueba)
            editor.document().setDocumentMargin(2)
            self._editor = editor
        else:
            self._editor = _LineEditor(self)
        self._editor.setObjectName("edit_inspector_value")
        self._editor.enter_pressed.connect(self._on_enter_pressed)
        self._editor.commit_requested.connect(self._on_commit_requested)
        self._editor.revert_requested.connect(self.revert)
        self._editor.focused.connect(self._on_focused)
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor)
        self._set_mixed_style(False)

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------

    @property
    def mixed(self) -> bool:
        """True si se está mostrando «Varios» (valores distintos en la selección)."""
        return self._mixed

    def text(self) -> str:
        """El texto de la caja, tal como está."""
        if isinstance(self._editor, QPlainTextEdit):
            return self._editor.toPlainText()
        return self._editor.text()

    def set_value(self, text: str | None, *, mixed: bool = False) -> None:
        """Muestra el valor del catálogo (o «Varios», en gris, si 'mixed')."""
        self._mixed = mixed
        self._shown = MIXED_TEXT if mixed else (text or "")
        self._set_text(self._shown)

    def is_editing(self) -> bool:
        """True si el usuario está escribiendo: tiene el foco y ha cambiado el texto."""
        return self._editor.hasFocus() and self.text() != self._shown

    def mark_applied(self) -> None:
        """Lo escrito se ha aplicado: pasa a ser el valor mostrado (hasta el refresco)."""
        self._mixed = False
        self._shown = self.text()
        self._set_mixed_style(False)

    def revert(self) -> None:
        """Vuelve al valor que se mostró (Esc, o un cambio que no se aplica)."""
        self._set_text(self._shown)

    def reject(self, notice: str) -> None:
        """Lo escrito no vale: vuelve al valor mostrado y avisa junto a la caja.

        El aviso es un texto emergente justo debajo de la caja, unos segundos
        ('REJECT_NOTICE_MS'); no es la ayuda al pasar el ratón (las cajas no la tienen).
        """
        self.revert()
        below = self._editor.mapToGlobal(QPoint(0, self._editor.height()))
        QToolTip.showText(below, notice, self._editor, QRect(), REJECT_NOTICE_MS)

    def editor(self) -> QWidget:
        """La caja de texto (para el orden del tabulador y las pruebas)."""
        return self._editor

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _set_text(self, text: str) -> None:
        """Pone el texto sin que cuente como escrito por el usuario."""
        self._updating = True
        try:
            if isinstance(self._editor, QPlainTextEdit):
                self._editor.setPlainText(text)
            else:
                self._editor.setText(text)
                self._editor.setCursorPosition(0)  # un texto largo se ve desde el principio
        finally:
            self._updating = False
        self._set_mixed_style(self._mixed and text == MIXED_TEXT)

    def _on_text_changed(self, *_args: object) -> None:
        """Al escribir sobre «Varios», el texto deja de ir en gris."""
        if not self._updating:
            self._set_mixed_style(self._mixed and self.text() == self._shown)

    def _on_focused(self) -> None:
        """Al entrar en «Varios», se selecciona entero (lo que se escriba lo sustituye).

        Después de que el clic coloque el cursor (si no, lo deseleccionaría).
        """
        if self._mixed and self.text() == self._shown:
            QTimer.singleShot(0, self._editor.selectAll)

    def _on_enter_pressed(self) -> None:
        """Intro: aplica y suelta el foco, para que la caja vuelva a verse como texto.

        Soltar el foco no vuelve a aplicar (aunque quien escucha no haya respondido).
        """
        self._on_commit_requested()
        self._busy = True
        try:
            self._editor.clearFocus()
        finally:
            self._busy = False

    def _on_commit_requested(self) -> None:
        """Intro o salir de la caja: avisa si el texto ha cambiado."""
        if self._busy:
            return  # p. ej. el foco se va al aviso que abre quien escucha
        text = self.text()
        if text == self._shown:
            return
        self._busy = True
        try:
            self.committed.emit(text if text.strip() else None)
        finally:
            self._busy = False

    def _set_mixed_style(self, mixed: bool) -> None:
        """«Varios» en gris (propiedad 'mixed' del QSS; hay que volver a aplicar el estilo)."""
        if self._editor.property("mixed") == mixed:
            return
        self._editor.setProperty("mixed", mixed)
        style = self._editor.style()
        style.unpolish(self._editor)
        style.polish(self._editor)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        """Alto fijo de la caja de varias líneas: 'MULTI_LINE_ROWS' líneas de texto."""
        if not isinstance(self._editor, QPlainTextEdit):
            return
        self._editor.ensurePolished()
        metrics = self._editor.fontMetrics()
        margins = self._editor.contentsMargins()
        document = int(2 * self._editor.document().documentMargin())
        frame = 2 * self._editor.frameWidth()
        self._editor.setFixedHeight(
            MULTI_LINE_ROWS * metrics.lineSpacing() + document + frame
            + margins.top() + margins.bottom()
        )


if __name__ == "__main__":
    # Autoprueba sin ventana: la lógica de las dos cajas. Se usa la plataforma 'offscreen'
    # de Qt (las cajas se «muestran» para tener foco, pero no aparece nada en pantalla).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.inspector.editable_row
    import os
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qtpy.QtTest import QTest
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    received: list[object] = []

    # 1. Una línea: solo avisa si cambia; tras aplicar, no vuelve a avisar
    line = EditableValue()
    line.committed.connect(received.append)
    line.set_value("Atardecer")
    line.editor().commit_requested.emit()  # sin cambios: nada
    assert received == []
    line.editor().setText("  Nuevo título ")
    QTest.keyClick(line.editor(), Qt.Key.Key_Return)
    assert received == ["  Nuevo título "], received  # el núcleo lo limpia ('normalize_value')
    line.mark_applied()
    line.editor().commit_requested.emit()
    assert received == ["  Nuevo título "]
    # Esc vuelve a lo mostrado; vaciar avisa con None
    line.editor().setText("otro")
    QTest.keyClick(line.editor(), Qt.Key.Key_Escape)
    assert line.text() == "  Nuevo título "
    line.editor().setText("   ")
    line.editor().commit_requested.emit()
    assert received[-1] is None
    print("1. Una línea: Intro aplica, Esc deshace, vaciar = None")

    # 2. «Varios»: en gris; sin tocar, nada; escribir lo sustituye; borrarlo vacía en todos
    received.clear()
    line.set_value("", mixed=True)
    assert line.text() == MIXED_TEXT and line.mixed and line.editor().property("mixed")
    line.editor().commit_requested.emit()
    assert received == []
    line.editor().setText("León")
    assert not line.editor().property("mixed")  # lo escrito, en el color normal
    line.editor().commit_requested.emit()
    assert received == ["León"]
    line.revert()  # p. ej. «Cancelar» en el aviso: vuelve «Varios», en gris
    assert line.text() == MIXED_TEXT and line.editor().property("mixed") and line.mixed
    line.editor().setText("")
    line.editor().commit_requested.emit()
    assert received == ["León", None]
    print("2. «Varios»: como en Lightroom")

    # 3. Varias líneas: Mayús+Intro, salto de línea; Intro, aplica
    received.clear()
    text = EditableValue(multiline=True)
    text.committed.connect(received.append)
    text.set_value("Primera")
    editor = text.editor()
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    QTest.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClicks(editor, "Segunda")
    assert text.text() == "Primera\nSegunda" and received == []
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert received == ["Primera\nSegunda"], received
    print("3. Varias líneas: Mayús+Intro, nueva línea; Intro, aplica")

    # 4. Un aviso que se lleva el foco no vuelve a avisar (sin bucles)
    received.clear()
    nested = EditableValue()
    nested.set_value("a")

    def reenter(value: object) -> None:
        received.append(value)
        nested.editor().commit_requested.emit()  # como si saliera de la caja al abrir el aviso

    nested.committed.connect(reenter)
    nested.editor().setText("b")
    nested.editor().commit_requested.emit()
    assert received == ["b"], received
    print("4. Sin avisos repetidos mientras se decide")

    # 5. Con Intro la caja suelta el foco (vuelve a verse como texto) sin avisar dos veces;
    #    con Esc se queda en ella
    received.clear()
    focused = EditableValue()
    focused.committed.connect(received.append)
    focused.set_value("a")
    focused.show()
    focused.activateWindow()
    focused.editor().setFocus()
    app.processEvents()
    if focused.editor().hasFocus():
        QTest.keyClick(focused.editor(), Qt.Key.Key_End)  # el cursor empieza al principio
        QTest.keyClicks(focused.editor(), "bc")
        QTest.keyClick(focused.editor(), Qt.Key.Key_Escape)
        assert focused.editor().hasFocus() and focused.text() == "a" and received == []
        QTest.keyClick(focused.editor(), Qt.Key.Key_End)  # Esc también lo deja al principio
        QTest.keyClicks(focused.editor(), "b")
        assert focused.is_editing()
        QTest.keyClick(focused.editor(), Qt.Key.Key_Return)
        app.processEvents()
        assert received == ["ab"], received  # una sola vez, aunque al soltar el foco se pida otra
        assert not focused.editor().hasFocus()
        print("5. Intro suelta el foco; Esc no")
    else:
        print("5. (sin foco en esta plataforma: no se comprueba)")
    focused.hide()

    # 6. Con el tema, el texto de las dos cajas empieza 'EDITOR_TEXT_INSET' px después que
    #    el de una etiqueta (lo que la rejilla adelanta las cajas): alineados en el inspector
    from qtpy.QtCore import QPoint
    from qtpy.QtGui import QColor, QImage, QPainter
    from qtpy.QtWidgets import QLabel

    import resources.recursos_rc  # noqa: F401 - recursos del tema
    from ui_helpers.helpers.ui_theme import apply_theme
    from ui_helpers.inspector.base_section import EDITOR_TEXT_INSET

    apply_theme()

    def ink_start(widget: QWidget) -> int:
        """Primera columna con texto (claro sobre el fondo oscuro) del widget dibujado."""
        widget.resize(200, max(widget.sizeHint().height(), 20))
        widget.show()
        app.processEvents()
        image = QImage(widget.size(), QImage.Format.Format_ARGB32)
        image.fill(QColor("#000000"))
        painter = QPainter(image)
        widget.render(painter, QPoint(0, 0))
        painter.end()
        widget.hide()
        for x in range(image.width()):
            if any(image.pixelColor(x, y).red() > 100 for y in range(image.height())):
                return x
        raise AssertionError("no se ve el texto")

    label = QLabel("Varios")
    reference = ink_start(label)
    for multiline in (False, True):
        box = EditableValue(multiline=multiline)
        box.editor().setFocusPolicy(Qt.FocusPolicy.NoFocus)  # sin el borde del foco
        box.set_value("Varios")
        inset = ink_start(box) - reference
        assert inset == EDITOR_TEXT_INSET, (multiline, inset)
        box.deleteLater()
    label.deleteLater()
    print(f"6. Con el tema, el texto de las cajas empieza a {EDITOR_TEXT_INSET} px del borde")

    # 7. Un valor que no vale: vuelve al mostrado (y avisa junto a la caja)
    line.set_value("42°40'55\" N 0°4'12\" E")
    line.editor().setText("abc")
    line.reject("No es una ubicación válida.")
    assert line.text() == "42°40'55\" N 0°4'12\" E" and not line.is_editing()
    print("7. Valor no válido: vuelve al de antes")

    for widget in (line, text, nested, focused):
        widget.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
