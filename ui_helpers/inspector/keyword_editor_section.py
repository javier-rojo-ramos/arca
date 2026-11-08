"""Sección «Palabras clave»: verlas y escribirlas, con cualquier selección (paso K4b).

    ▼ PALABRAS CLAVE
      ┌──────────────────────────────────────┐
      │ Opel Astra, Playa*, Amigos > Ana     │   <- caja de texto (Ctrl+K)
      └──────────────────────────────────────┘
      ▾ Últimas palabras clave                     <- las 6 últimas usadas (K4c)
        [ Playa ] [ Opel Astra ] [ Ana ]
        [ Nieve ] [ Comidas    ] [ ... ]
      (más adelante: «Conjuntos de palabras clave», personalizables)

El árbol con casillas va en su propia sección, «Lista de palabras clave»
('keyword_list_section.py'), que se pliega por separado.

Como el panel «Palabras clave» de Lightroom, pero en una sola caja:
    - La caja muestra las palabras de lo seleccionado separadas por comas; las que no
      tienen todos llevan un asterisco. Si dos palabras se llaman igual, con su ruta
      («Amigos > Ana»).
    - Se edita como texto y se aplica al pulsar Intro o al salir de la caja (Esc deshace):
        · borrar una palabra la QUITA de todos los seleccionados;
        · quitarle el asterisco la ASIGNA a todos;
        · escribir una nueva la asigna a todos (si no existe, se crea; «Coche > Seat
          Ibiza» la crea dentro de «Coche»).
    - Mientras se escribe, se ofrecen las palabras del árbol que contienen lo escrito. En
      la lista: Intro elige la palabra Y aplica; Tab la elige y se sigue escribiendo; Esc
      cierra la lista.
    - Ctrl+K lleva a la caja, al final, listo para escribir otra palabra.

Bajo la caja, «Últimas palabras clave» ('ui_helpers/widgets/recent_keywords.py'): las
6 últimas palabras asignadas desde la interfaz ('keywords.last_used_at'), en botones del
mismo tamaño; pulsar uno la pone a todos los seleccionados (o la quita, si ya la tenían
todos). Se pliega con su propia cabecera y se recuerda en settings.json
('inspector_sections', clave 'keyword_editor.recent').

Lo que se cambia se guarda AL MOMENTO en el catálogo y queda pendiente de escribir en los
archivos (si está activada la opción «Guardar en los archivos»), como la valoración.

Las teclas se atienden en una subclase de 'QPlainTextEdit' ('KeywordTextEdit'), como en
el ejemplo de autocompletado de Qt, y NO con un filtro de eventos: 'QCompleter' reenvía
las teclas a la caja llamando a su 'event()' directamente, lo que se salta los filtros
(en la 1.0.0, Intro con la lista abierta metía un salto de línea). Y al abrirse la lista
la caja pierde el foco ('PopupFocusReason'): eso no debe aplicar lo escrito a medias (en
la 1.0.0 se creaban palabras como «E» o «Ec»).

La sección no toca la base de datos: lee con 'data_request'
('keywords.fetch_keyword_editor_data') y pide los cambios con 'edit_requested'
('keywords.apply_keyword_changes'), que atiende el controlador del inspector.

Solo aparece en el módulo Imagen ('modules'); en los demás está la de solo lectura
('keywords_section.py').

1.3.0 En todos los módulos, también el Catálogo, y con selecciones de varias bibliotecas
      (paso A.2): las palabras clave son comunes a todos los tipos.
1.2.0 «Últimas palabras clave» bajo la caja (paso K4c); datos con 'KeywordEditorData'.
1.1.0 Arreglos tras verlo el autor: teclas en una subclase (Intro con la lista abierta ya
      no mete un salto de línea ni deja la lista a la vista); al abrirse la lista no se
      aplica lo escrito; la lista se cierra al aplicar. El árbol pasa a su propia sección.

Prueba rápida de la lógica (sin Qt):
    python -m ui_helpers.inspector.keyword_editor_section
"""

__version__ = "1.3.0"
__all__ = ["KeywordEditorSection", "KeywordTextEdit", "completion_names", "current_token_bounds"]

# Librerías estándar
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QStringListModel, Qt, QTimer, Signal
from qtpy.QtGui import QFocusEvent, QKeyEvent, QKeySequence, QShortcut, QTextCursor
from qtpy.QtWidgets import QCompleter, QPlainTextEdit, QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_config import config
from config.app_constants import SETTING_INSPECTOR_SECTIONS
from core.catalog.catalog_schema import fold_text
from core.catalog.keywords import (
    PATH_SEPARATOR,
    TEXT_SEPARATOR,
    KeywordChanges,
    KeywordEditorData,
    KeywordTreeNode,
    SelectionKeywords,
    apply_keyword_changes,
    diff_keyword_text,
    fetch_keyword_editor_data,
    keyword_tokens,
)
from core.catalog.libraries import Library
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.inspector.base_section import InspectorSection
from ui_helpers.widgets.recent_keywords import RecentKeywords

# Atajo para ir a la caja de texto (el de Lightroom para «Añadir palabras clave»)
FOCUS_SHORTCUT = "Ctrl+K"
# Biblioteca de los recuentos del árbol (la del módulo Imagen)
LIBRARY = Library.IMAGE.value
# Líneas de alto de la caja (crece hasta 'MAX_LINES' si hay muchas palabras)
MIN_LINES = 2
MAX_LINES = 6
# Caracteres escritos a partir de los que se ofrecen palabras
COMPLETION_MIN_CHARS = 1
# Clave en 'inspector_sections' (settings.json) de lo plegado de «Últimas palabras clave»
RECENT_STATE_KEY = "keyword_editor.recent"
# Teclas que son de la lista de sugerencias mientras está abierta
_POPUP_KEYS = (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab)


def completion_names(nodes: Iterable[KeywordTreeNode]) -> list[str]:
    """Textos que se ofrecen al escribir: el nombre de cada palabra, o su ruta
    («Familia > Ana») si hay varias con ese nombre. Por orden alfabético."""
    paths: list[tuple[str, ...]] = []

    def visit(node: KeywordTreeNode, parents: tuple[str, ...]) -> None:
        path = (*parents, node.name)
        paths.append(path)
        for child in node.children:
            visit(child, path)

    for node in nodes:
        visit(node, ())
    repeated = Counter(fold_text(path[-1]) for path in paths)
    names = {
        f" {PATH_SEPARATOR} ".join(path) if repeated[fold_text(path[-1])] > 1 else path[-1]
        for path in paths
    }
    return sorted(names, key=lambda name: fold_text(name) or "")


def current_token_bounds(text: str, position: int) -> tuple[int, int]:
    """Inicio y fin (sin espacios) de la palabra en la que está el cursor.

    El inicio es justo después de la coma anterior (y de los espacios que la siguen); el
    fin, la posición del cursor. Lo usa el autocompletado para sustituir lo escrito.
    """
    start = text.rfind(TEXT_SEPARATOR, 0, position) + 1
    while start < position and text[start] in " \n":
        start += 1
    return start, position


class KeywordTextEdit(QPlainTextEdit):
    """Caja de las palabras: Intro aplica, Esc deshace, salir de la caja aplica.

    No admite saltos de línea (las palabras van con comas). Con la lista de sugerencias
    abierta, Intro, Tab y Esc son para ella (se ignoran aquí y 'QCompleter' los atiende);
    Intro, además, aplica en cuanto se ha insertado la palabra elegida.

    Signals:
        commit_requested(): aplicar lo escrito.
        revert_requested(): volver a lo que había (Esc).
    """

    commit_requested = Signal()
    revert_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._completer: QCompleter | None = None

    def set_completer(self, completer: QCompleter) -> None:
        """La lista de sugerencias de la caja (para saber si está abierta)."""
        self._completer = completer
        completer.setWidget(self)

    def popup_visible(self) -> bool:
        """True si la lista de sugerencias está a la vista."""
        popup = self._completer.popup() if self._completer is not None else None
        return popup is not None and popup.isVisible()

    def hide_popup(self) -> None:
        """Cierra la lista de sugerencias (p. ej. al aplicar)."""
        if self.popup_visible():
            self._completer.popup().hide()

    # --- Qt ---

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - nombre de Qt
        key = event.key()
        if self.popup_visible() and key in _POPUP_KEYS:
            # 'QCompleter' reenvía la tecla aquí ANTES de atenderla: se ignora para que
            # inserte la palabra elegida (o cierre la lista, con Esc)
            event.ignore()
            if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                # Se aplica después de que la lista inserte su palabra
                QTimer.singleShot(0, self.commit_requested.emit)
            return
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            event.accept()  # sin salto de línea, ni con Mayús
            self.commit_requested.emit()
            return
        if key == Qt.Key.Key_Escape:
            event.accept()
            self.revert_requested.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802 - nombre de Qt
        super().focusOutEvent(event)
        # Al abrirse la lista de sugerencias la caja pierde el foco: eso no es salir
        if event.reason() == Qt.FocusReason.PopupFocusReason or self.popup_visible():
            return
        self.commit_requested.emit()


class KeywordEditorSection(InspectorSection):
    """Caja de las palabras clave de lo seleccionado (ver el docstring del módulo)."""

    title = "Palabras clave"
    key = "keyword_editor"
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ids: tuple[int, ...] = ()           # a quién se aplican los cambios
        self._pending_ids: tuple[int, ...] = ()   # los de la última petición de datos
        self._selection = SelectionKeywords()      # lo que muestra la caja
        self._shown_text = ""                      # el texto tal como se puso
        self._updating = False                     # el texto lo está poniendo el programa

        layout = QVBoxLayout(self)
        # Mismos márgenes que las filas de las demás secciones ('InfoGrid')
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(6)

        # Caja de texto: las palabras separadas por comas (con saltos de línea automáticos,
        # como en Lightroom; no admite saltos de línea propios)
        self._text = KeywordTextEdit(self)
        self._text.setObjectName("edit_keywords")
        self._text.setPlaceholderText(f"Escribe palabras clave separadas por comas ({FOCUS_SHORTCUT})")
        self._text.setTabChangesFocus(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._text.textChanged.connect(self._on_text_changed)
        self._text.commit_requested.connect(self.commit_text)
        self._text.revert_requested.connect(self.revert_text)
        layout.addWidget(self._text)

        # Sugerencias: las palabras del árbol que contienen lo escrito
        self._completion_model = QStringListModel(self)
        self.completer = QCompleter(self._completion_model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.activated.connect(self._insert_completion)
        self._text.set_completer(self.completer)
        self._fit_text_height()

        # «Últimas palabras clave»: botones para asignar con un clic
        self._recent = RecentKeywords(self, expanded=self._recent_expanded())
        self._recent.keyword_clicked.connect(self._on_recent_clicked)
        self._recent.expanded_changed.connect(self._save_recent_expanded)
        layout.addWidget(self._recent)

        # Ctrl+K: a la caja (solo funciona mientras la sección se ve)
        self._shortcut = QShortcut(QKeySequence(FOCUS_SHORTCUT), self)
        self._shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcut.activated.connect(self.focus_text)

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Con algo seleccionado (de cualquier biblioteca: las palabras son comunes)."""
        return summary.scope == "selection" and not summary.is_empty

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: los datos llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Palabras de los seleccionados y el árbol (para las sugerencias)."""
        if not ids:
            return None
        self._pending_ids = tuple(ids)
        return fetch_keyword_editor_data, (list(ids), LIBRARY)

    def show_data(self, result: Any) -> None:
        """Pone el texto. Si el usuario está escribiendo para ESTOS mismos seleccionados,
        su texto no se pisa (p. ej. un refresco por otra causa)."""
        data = result if isinstance(result, KeywordEditorData) else KeywordEditorData()
        selection, tree = data.selection, data.tree
        ids = self._pending_ids
        typing = self._text.hasFocus() and self._text.toPlainText() != self._shown_text
        same = ids == self._ids
        self._ids = ids
        self._selection = selection
        text = ", ".join(keyword_tokens(selection))
        if typing and same:
            self._shown_text = text
        else:
            self._set_text(text)
        self._completion_model.setStringList(completion_names(tree))
        self._recent.set_data(data.recent, selection)

    # -------------------------------------------------------------------------
    # Acciones
    # -------------------------------------------------------------------------

    def commit_text(self) -> None:
        """Aplica lo escrito (si ha cambiado algo) a todos los seleccionados."""
        self._text.hide_popup()
        text = self._text.toPlainText()
        if text == self._shown_text or not self._ids:
            return
        changes = diff_keyword_text(text, self._selection)
        if changes.is_empty:
            # Solo cambió la forma (espacios, mayúsculas...): se vuelve a mostrar bien
            self._set_text(self._shown_text)
            return
        self.edit_requested.emit(apply_keyword_changes, (list(self._ids), changes))
        # Hasta que llegue la respuesta, se queda lo escrito; al refrescar se pone limpio
        self._shown_text = text

    def revert_text(self) -> None:
        """Esc: deshace lo escrito desde la última vez que se aplicó."""
        self._set_text(", ".join(keyword_tokens(self._selection)))

    def focus_text(self) -> None:
        """Ctrl+K: cursor al final de la caja, tras una coma, para escribir otra palabra."""
        if not self.isVisible():
            return
        text = self._text.toPlainText().rstrip()
        if text and not text.endswith(TEXT_SEPARATOR):
            self._updating = True
            try:
                self._text.setPlainText(f"{text}{TEXT_SEPARATOR} ")
            finally:
                self._updating = False
        self._text.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._text.moveCursor(QTextCursor.MoveOperation.End)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_recent_clicked(self, keyword_id: int, assign: bool) -> None:
        """Botón de «Últimas palabras clave»: ponerla a todos o quitarla de todos."""
        if not self._ids:
            return
        changes = KeywordChanges(add_ids=(keyword_id,)) if assign else KeywordChanges(remove_ids=(keyword_id,))
        self.edit_requested.emit(apply_keyword_changes, (list(self._ids), changes))

    @staticmethod
    def _recent_expanded() -> bool:
        """Si «Últimas palabras clave» estaba desplegada (True si no consta)."""
        states = config.get(SETTING_INSPECTOR_SECTIONS)
        value = states.get(RECENT_STATE_KEY) if isinstance(states, dict) else None
        return value if isinstance(value, bool) else True

    @staticmethod
    def _save_recent_expanded(expanded: bool) -> None:
        """Guarda al momento si «Últimas palabras clave» se ha plegado o desplegado."""
        states = config.get(SETTING_INSPECTOR_SECTIONS)
        states = dict(states) if isinstance(states, dict) else {}
        states[RECENT_STATE_KEY] = expanded
        config.set(SETTING_INSPECTOR_SECTIONS, states)

    def _set_text(self, text: str) -> None:
        """Pone el texto de la caja sin que cuente como escrito por el usuario."""
        self._text.hide_popup()
        self._updating = True
        try:
            self._text.setPlainText(text)
        finally:
            self._updating = False
        self._shown_text = text
        self._fit_text_height()

    def _fit_text_height(self) -> None:
        """Alto de la caja según sus líneas (entre 'MIN_LINES' y 'MAX_LINES').

        En un 'QPlainTextEdit', el alto del documento se mide en LÍNEAS (con las de los
        saltos automáticos), no en píxeles.
        """
        document = self._text.document()
        lines = max(MIN_LINES, min(MAX_LINES, int(document.size().height()) or MIN_LINES))
        metrics = self._text.fontMetrics()
        margins = self._text.contentsMargins()
        frame = 2 * self._text.frameWidth() + int(2 * document.documentMargin())
        self._text.setFixedHeight(
            lines * metrics.lineSpacing() + frame + margins.top() + margins.bottom()
        )

    def _on_text_changed(self) -> None:
        """Mientras el usuario escribe: ajustar el alto y ofrecer palabras."""
        self._fit_text_height()
        if self._updating or not self._text.hasFocus():
            return
        text = self._text.toPlainText()
        cursor = self._text.textCursor()
        start, end = current_token_bounds(text, cursor.position())
        prefix = text[start:end].strip()
        popup = self.completer.popup()
        if len(prefix) < COMPLETION_MIN_CHARS:
            popup.hide()
            return
        if prefix != self.completer.completionPrefix():
            self.completer.setCompletionPrefix(prefix)
            popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        if self.completer.completionCount() == 0:
            popup.hide()
            return
        rect = self._text.cursorRect()
        rect.setWidth(max(200, popup.sizeHintForColumn(0) + 24))
        self.completer.complete(rect)

    def _insert_completion(self, completion: str) -> None:
        """Sustituye la palabra que se está escribiendo por la elegida, y añade «, »."""
        text = self._text.toPlainText()
        cursor = self._text.textCursor()
        start, end = current_token_bounds(text, cursor.position())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._updating = True  # no se vuelve a abrir la lista por este cambio
        try:
            cursor.insertText(f"{completion}{TEXT_SEPARATOR} ")
        finally:
            self._updating = False
        self._text.setTextCursor(cursor)


if __name__ == "__main__":
    # Autoprueba de la lógica (no necesita Qt real). Desde la raíz del proyecto:
    #     python -m ui_helpers.inspector.keyword_editor_section
    tree = (
        KeywordTreeNode(1, "Amigos", 0, 0, False, (KeywordTreeNode(2, "Ana", 0, 0, False, ()),)),
        KeywordTreeNode(3, "Coche", 0, 0, False, (KeywordTreeNode(4, "Opel Astra", 0, 0, False, ()),)),
        KeywordTreeNode(5, "Familia", 0, 0, False, (KeywordTreeNode(6, "Ana", 0, 0, False, ()),)),
    )
    assert completion_names(tree) == [
        "Amigos", "Amigos > Ana", "Coche", "Familia", "Familia > Ana", "Opel Astra"
    ], completion_names(tree)
    assert current_token_bounds("Playa, Opel", 11) == (7, 11)
    assert current_token_bounds("Opel", 4) == (0, 4)
    assert current_token_bounds("Playa,", 6) == (6, 6)
    print("Autoprueba finalizada correctamente.")
