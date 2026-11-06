"""Ventana "Crear colección inteligente" / "Editar colección inteligente" (como Lightroom).

    Nombre:               [Las mejores de Ordesa          ]
    Dentro del conjunto:  [Ninguno (primer nivel)        ▾]

    Coincidir con [todas ▾] las reglas siguientes:
    ┌─────────────────────────────────────────────────────────────────────┐
    │ [Valoración       ▾] [es mayor o igual que ▾] [★★★        ▾]   [−] │
    │ [Carpeta (ruta)   ▾] [contiene             ▾] [Ordesa       ]   [−] │
    │ [Fecha de captura ▾] [está entre           ▾] [01/06/24] y [30/06/24] [−] │
    └─────────────────────────────────────────────────────────────────────┘
    [+ Añadir regla]                                  Coinciden 128 elementos

                                                      [Crear]  [Cancelar]

Cómo está hecha (para ampliarla sin tocarla):
    - El botón del CAMPO abre un menú con un submenú por grupo (Estándar, Imagen, Tracks
      GPS...) y, dentro, los campos por secciones. Todo sale de 'core/catalog/smart_fields.py':
      un campo nuevo aparece aquí solo.
    - Los OPERADORES de cada campo salen de su tipo ('allowed_operators').
    - El VALOR se edita con un control según el tipo (texto, número con su unidad, fecha
      con calendario, lista, estrellas...). Para un tipo nuevo, añadir su caso en
      '_ValueEditor'.
    - La ventana no toca la base de datos: devuelve un 'SmartCollectionChoice' y quien la
      abre ('controllers/collection_actions.py') crea o guarda la colección. Para mostrar
      cuántos elementos coinciden, recibe una función 'counter' que cuenta en segundo plano.
    - Para el campo «Palabra clave», recibe los nombres de las palabras del catálogo
      ('keyword_names') y los ofrece mientras se escribe (contienen lo escrito, sin
      distinguir mayúsculas).

1.2.0 Autocompletado del nombre en el campo «Palabra clave» ('keyword_names'; paso K4c).

Uso:
    choice = SmartCollectionDialog.ask(parent, sets=[(3, "Álbumes")], counter=contar)
    if choice is not None:
        ...  # choice.name, choice.parent_id, choice.rules
"""

__version__ = "1.2.0"
__all__ = ["SmartCollectionChoice", "SmartCollectionDialog"]

# Librerías estándar
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QDate, QStringListModel, Qt, QTimer, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.smart_fields import (
    FIELDS,
    KIND_DATE,
    KIND_ENUM,
    KIND_KEYWORD,
    KIND_NUMBER,
    KIND_RATING,
    KIND_TEXT,
    OPERATORS,
    SmartField,
    fields_in_group,
    visible_groups,
)
from core.catalog.smart_rules import MATCH_ALL, MATCH_ANY, Rule, RuleSet, validate_rule
from core.catalog.user_collections import MAX_NAME_LENGTH

# Regla con la que empieza una fila nueva
_DEFAULT_RULE = Rule("rating", "gte", 1)
# Espera (ms) tras el último cambio antes de volver a contar los elementos que coinciden
_COUNT_DELAY_MS = 350
# Límites de los números (los campos admiten negativos: p. ej. una altitud bajo el mar)
_NUMBER_LIMIT = 1e12

# Función que cuenta en segundo plano: recibe las reglas y a quién avisar con el número
# (o con None si no se pudo contar)
Counter = Callable[[RuleSet, Callable[[int | None], None]], None]


@dataclass(frozen=True, slots=True)
class SmartCollectionChoice:
    """Lo que ha elegido el usuario.

    Attributes:
        name: Nombre (sin espacios en los extremos).
        parent_id: Conjunto donde guardarla (None = primer nivel).
        rules: Las reglas, ya validadas.
    """

    name: str
    parent_id: int | None
    rules: RuleSet


# -----------------------------------------------------------------------------
# Editor del valor de una regla
# -----------------------------------------------------------------------------


class _ValueEditor(QWidget):
    """Control para el valor de una regla, según el tipo del campo y el operador.

    Muestra: nada (operadores sin valor), un control, o dos con "y" en medio ("entre").
    Los números se muestran en la unidad del usuario (km, MB...) y se devuelven en la
    de la base de datos (ver 'SmartField.scale').
    """

    changed = Signal()

    def __init__(
        self,
        spec: SmartField,
        operator: str,
        parent: QWidget | None = None,
        keyword_names: QStringListModel | None = None,
    ) -> None:
        super().__init__(parent)
        self._spec = spec
        self._operator = operator
        self._keyword_names = keyword_names  # sugerencias del campo «Palabra clave»
        self._editors: list[QWidget] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        arity = OPERATORS[operator].arity
        for position in range(arity):
            if position == 1:
                layout.addWidget(QLabel("y"))
            editor = self._make_editor()
            self._editors.append(editor)
            layout.addWidget(editor, 1)
        if arity == 0:
            layout.addStretch(1)

    def _make_editor(self) -> QWidget:
        """Crea UN control para el tipo del campo (y lo conecta a 'changed')."""
        spec = self._spec
        if spec.kind == KIND_DATE and self._operator == "in_last":
            editor = QSpinBox()
            editor.setRange(1, 36500)
            editor.setValue(30)
            editor.setSuffix(" días")
            editor.valueChanged.connect(self.changed)
            return editor
        if spec.kind in (KIND_TEXT, KIND_KEYWORD):
            editor = QLineEdit()
            editor.setMaxLength(500)
            # Palabra clave: el nombre de UNA palabra («Coche»), sin la ruta
            editor.setPlaceholderText("palabra clave" if spec.kind == KIND_KEYWORD else "texto")
            if spec.kind == KIND_KEYWORD and self._keyword_names is not None:
                # Las palabras del catálogo que contienen lo escrito (la regla compara
                # nombres, así que se ofrecen nombres, no rutas)
                completer = QCompleter(self._keyword_names, editor)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                editor.setCompleter(completer)
            editor.textChanged.connect(self.changed)
            return editor
        if spec.kind == KIND_NUMBER:
            editor = QDoubleSpinBox()
            editor.setDecimals(spec.decimals)
            editor.setRange(-_NUMBER_LIMIT, _NUMBER_LIMIT)
            editor.setGroupSeparatorShown(True)
            if spec.unit:
                editor.setSuffix(f" {spec.unit}")
            editor.valueChanged.connect(self.changed)
            return editor
        if spec.kind == KIND_DATE:
            editor = QDateEdit()
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy")
            editor.setDate(QDate.currentDate())
            editor.dateChanged.connect(self.changed)
            return editor
        if spec.kind == KIND_RATING:
            editor = QComboBox()
            editor.addItem("sin estrellas", 0)
            for stars in range(1, 6):
                editor.addItem("★" * stars, stars)
            editor.currentIndexChanged.connect(self.changed)
            return editor
        if spec.kind == KIND_ENUM:
            editor = QComboBox()
            for value, text in spec.choices:
                editor.addItem(text, value)
            editor.currentIndexChanged.connect(self.changed)
            return editor
        # Tipo sin control propio (no debería pasar: se ve en la autoprueba de smart_fields)
        return QLabel(f"(tipo {spec.kind!r} sin editor)")

    # --- Leer y escribir el valor -------------------------------------------------------

    def value(self) -> Any:
        """Valor de la regla: None, un valor o una tupla de dos ("entre")."""
        values = [self._read(editor) for editor in self._editors]
        if not values:
            return None
        return tuple(values) if len(values) == 2 else values[0]

    def set_value(self, value: Any) -> None:
        """Pone un valor (el de una regla guardada). Lo que no encaja se ignora."""
        if not self._editors:
            return
        values = value if isinstance(value, (tuple, list)) else (value,)
        for editor, item in zip(self._editors, values, strict=False):
            self._write(editor, item)

    def _read(self, editor: QWidget) -> Any:
        spec = self._spec
        if isinstance(editor, QSpinBox):
            return editor.value()
        if isinstance(editor, QLineEdit):
            return editor.text()
        if isinstance(editor, QDoubleSpinBox):
            stored = editor.value() * spec.scale
            # Sin decimales ni escala (ISO, píxeles...): entero
            if spec.decimals == 0 and spec.scale == 1:
                return int(round(stored))
            return round(stored, 6)
        if isinstance(editor, QDateEdit):
            return editor.date().toString("yyyy-MM-dd")
        if isinstance(editor, QComboBox):
            return editor.currentData()
        return None

    def _write(self, editor: QWidget, value: Any) -> None:
        try:
            if isinstance(editor, QSpinBox) and isinstance(value, int):
                editor.setValue(value)
            elif isinstance(editor, QLineEdit) and isinstance(value, str):
                editor.setText(value)
            elif isinstance(editor, QDoubleSpinBox) and isinstance(value, (int, float)):
                editor.setValue(value / self._spec.scale)
            elif isinstance(editor, QDateEdit) and isinstance(value, str):
                day = date.fromisoformat(value)
                editor.setDate(QDate(day.year, day.month, day.day))
            elif isinstance(editor, QComboBox):
                position = editor.findData(value)
                if position >= 0:
                    editor.setCurrentIndex(position)
        except (ValueError, TypeError):
            pass  # un valor que no encaja (p. ej. de otra versión): se deja el de por defecto

    def focus_first(self) -> None:
        """Pone el cursor en el primer control (p. ej. para escribir el texto)."""
        if self._editors:
            self._editors[0].setFocus()


# -----------------------------------------------------------------------------
# Una fila: campo, operador, valor y quitar
# -----------------------------------------------------------------------------


class _RuleRow(QWidget):
    """Una regla: [campo ▾] [operador ▾] [valor] [−]."""

    changed = Signal()
    remove_requested = Signal(object)  # la propia fila

    def __init__(
        self,
        rule: Rule,
        parent: QWidget | None = None,
        keyword_names: QStringListModel | None = None,
    ) -> None:
        super().__init__(parent)
        self._keyword_names = keyword_names
        self._field_key = ""
        self._value_editor: _ValueEditor | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Campo: botón con un menú por grupos y secciones (ver '_build_field_menu')
        self.button_field = QToolButton()
        self.button_field.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button_field.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.button_field.setMinimumWidth(190)
        self.button_field.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.button_field.setMenu(self._build_field_menu())

        self.combo_operator = QComboBox()
        self.combo_operator.setMinimumWidth(170)
        self.combo_operator.currentIndexChanged.connect(self._on_operator_changed)

        self._value_holder = QHBoxLayout()
        self._value_holder.setContentsMargins(0, 0, 0, 0)

        self.button_remove = QToolButton()
        self.button_remove.setText("−")
        self.button_remove.setToolTip("Quitar esta regla")
        self.button_remove.setAutoRaise(True)
        self.button_remove.clicked.connect(lambda: self.remove_requested.emit(self))

        layout.addWidget(self.button_field)
        layout.addWidget(self.combo_operator)
        layout.addLayout(self._value_holder, 1)
        layout.addWidget(self.button_remove)

        self._set_field(rule.field if rule.field in FIELDS else _DEFAULT_RULE.field, rule.operator)
        if self._value_editor is not None:
            self._value_editor.set_value(rule.value)

    # --- Menú de campos -----------------------------------------------------------------

    def _build_field_menu(self) -> QMenu:
        """Menú con un submenú por grupo y, dentro, los campos separados por secciones."""
        menu = QMenu(self)
        for group in visible_groups():
            submenu = menu.addMenu(group.label)
            section = None
            for spec in fields_in_group(group.key):
                if spec.section != section:
                    # Título de la sección (en negrita y sin poder pulsarse)
                    if section is not None:
                        submenu.addSeparator()
                    header = submenu.addAction(spec.section)
                    header.setEnabled(False)
                    font = QFont(header.font())
                    font.setBold(True)
                    header.setFont(font)
                    section = spec.section
                action = submenu.addAction(f"    {spec.label}")
                action.triggered.connect(lambda _checked=False, key=spec.key: self._on_field_chosen(key))
        return menu

    def _on_field_chosen(self, key: str) -> None:
        if key != self._field_key:
            self._set_field(key, self.combo_operator.currentData())
            self.changed.emit()
            if self._value_editor is not None:
                self._value_editor.focus_first()

    # --- Cambios de campo y operador ------------------------------------------------------

    def _set_field(self, key: str, operator: str | None) -> None:
        """Cambia el campo: rellena sus operadores (mantiene el actual si lo admite)."""
        spec = FIELDS[key]
        self._field_key = key
        group = next(g.label for g in visible_groups() if g.key == spec.group)
        self.button_field.setText(spec.label)
        self.button_field.setToolTip(f"{group} › {spec.section} › {spec.label}")

        self.combo_operator.blockSignals(True)
        self.combo_operator.clear()
        for op in spec.allowed_operators:
            self.combo_operator.addItem(OPERATORS[op].label, op)
        position = self.combo_operator.findData(operator) if operator else -1
        self.combo_operator.setCurrentIndex(max(0, position))
        self.combo_operator.blockSignals(False)
        self._rebuild_value_editor()

    def _on_operator_changed(self, _index: int) -> None:
        old = self._value_editor.value() if self._value_editor is not None else None
        old_arity = len(old) if isinstance(old, tuple) else (0 if old is None else 1)
        self._rebuild_value_editor()
        # Si el valor sigue teniendo sentido (misma cantidad), se conserva
        if self._value_editor is not None and old is not None:
            new_arity = OPERATORS[self.combo_operator.currentData()].arity
            if new_arity == old_arity:
                self._value_editor.set_value(old)
            elif new_arity == 2 and old_arity == 1:
                self._value_editor.set_value((old, old))
            elif new_arity == 1 and old_arity == 2:
                self._value_editor.set_value(old[0])
        self.changed.emit()

    def _rebuild_value_editor(self) -> None:
        """Cambia el control del valor por el que corresponde al campo y al operador."""
        if self._value_editor is not None:
            self._value_holder.removeWidget(self._value_editor)
            self._value_editor.deleteLater()
        self._value_editor = _ValueEditor(
            FIELDS[self._field_key],
            self.combo_operator.currentData(),
            keyword_names=self._keyword_names,
        )
        self._value_editor.changed.connect(self.changed)
        self._value_holder.addWidget(self._value_editor)

    # --- Resultado ------------------------------------------------------------------------

    def rule(self) -> Rule:
        """La regla de esta fila, validada.

        Raises:
            ValueError: Si falta el valor o no es válido (mensaje para el usuario).
        """
        value = self._value_editor.value() if self._value_editor is not None else None
        return validate_rule(Rule(self._field_key, self.combo_operator.currentData(), value))


# -----------------------------------------------------------------------------
# La ventana
# -----------------------------------------------------------------------------


class SmartCollectionDialog(QDialog):
    """Ventana para crear o editar una colección inteligente."""

    def __init__(
        self,
        *,
        sets: list[tuple[int, str]],
        parent_id: int | None = None,
        name: str = "",
        rules: RuleSet | None = None,
        editing: bool = False,
        counter: Counter | None = None,
        note: str = "",
        keyword_names: Sequence[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        """Crea la ventana.

        Args:
            sets: Conjuntos donde se puede guardar: (id, nombre con sus conjuntos delante).
            parent_id: Conjunto elegido al abrir.
            name: Nombre inicial (al editar).
            rules: Reglas iniciales (al editar). None = una regla de ejemplo.
            editing: True para "Editar" (botón "Guardar") en lugar de "Crear".
            counter: Función que cuenta en segundo plano los elementos que coinciden
                (None = no se muestra el número).
            note: Aviso que se muestra arriba (p. ej. "las reglas guardadas no se podían leer").
            keyword_names: Nombres de las palabras clave del catálogo, para sugerirlos en
                las reglas «Palabra clave».
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle("Editar colección inteligente" if editing else "Crear colección inteligente")
        self.setModal(True)
        self.setMinimumWidth(720)
        self._counter = counter
        # Nombres de las palabras clave del catálogo (autocompletado de esas reglas)
        self._keyword_names = QStringListModel(list(keyword_names), self)
        self._rows: list[_RuleRow] = []
        # Para descartar recuentos que llegan tarde (ventana cerrada o reglas ya cambiadas)
        self._count_generation = 0
        self._alive = True

        # --- Nombre y conjunto ---
        self.edit_name = QLineEdit(name)
        self.edit_name.setMaxLength(MAX_NAME_LENGTH)
        self.edit_name.setPlaceholderText("Nombre de la colección inteligente")
        self.combo_parent = QComboBox()
        self.combo_parent.addItem("Ninguno (primer nivel)", None)
        for set_id, set_name in sets:
            self.combo_parent.addItem(set_name, set_id)
        position = self.combo_parent.findData(parent_id) if parent_id is not None else 0
        self.combo_parent.setCurrentIndex(max(0, position))
        form = QFormLayout()
        form.addRow("Nombre:", self.edit_name)
        form.addRow("Dentro del conjunto:", self.combo_parent)

        # --- Coincidir con todas / alguna ---
        self.combo_match = QComboBox()
        self.combo_match.addItem("todas", MATCH_ALL)
        self.combo_match.addItem("alguna de", MATCH_ANY)
        initial = rules or RuleSet(rules=(_DEFAULT_RULE,))
        self.combo_match.setCurrentIndex(max(0, self.combo_match.findData(initial.match)))
        self.combo_match.currentIndexChanged.connect(self._schedule_count)
        match_row = QHBoxLayout()
        match_row.addWidget(QLabel("Coincidir con"))
        match_row.addWidget(self.combo_match)
        match_row.addWidget(QLabel("las reglas siguientes:"))
        match_row.addStretch(1)

        # --- Reglas (con desplazamiento si son muchas) ---
        self._rules_widget = QWidget()
        self._rules_layout = QVBoxLayout(self._rules_widget)
        self._rules_layout.setContentsMargins(6, 6, 6, 6)
        self._rules_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        scroll.setWidget(self._rules_widget)
        scroll.setMinimumHeight(170)

        self.button_add_rule = QPushButton("+ Añadir regla")
        self.button_add_rule.clicked.connect(lambda: self._add_row(_DEFAULT_RULE, focus=True))
        self.label_status = QLabel()
        self.label_status.setWordWrap(True)
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.button_add_rule)
        bottom_row.addWidget(self.label_status, 1)

        # --- Botones ---
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.button_ok.setText("Guardar" if editing else "Crear")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self.edit_name.textChanged.connect(self._update_ok)

        layout = QVBoxLayout(self)
        if note:
            label_note = QLabel(note)
            label_note.setWordWrap(True)
            label_note.setStyleSheet("color: #e0a030;")
            layout.addWidget(label_note)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addLayout(match_row)
        layout.addWidget(scroll, 1)
        layout.addLayout(bottom_row)
        layout.addWidget(self.buttons)

        # Recuento con retardo: no se cuenta con cada tecla, sino al dejar de escribir
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(_COUNT_DELAY_MS)
        self._count_timer.timeout.connect(self._count_now)

        for rule in initial.rules:
            self._add_row(rule)
        self._update_ok()
        self._schedule_count()

    # --- Filas ------------------------------------------------------------------------------

    def _add_row(self, rule: Rule, *, focus: bool = False) -> None:
        row = _RuleRow(rule, self._rules_widget, keyword_names=self._keyword_names)
        row.changed.connect(self._schedule_count)
        row.remove_requested.connect(self._remove_row)
        # Antes del 'stretch' final (así las filas se apilan arriba)
        self._rules_layout.insertWidget(self._rules_layout.count() - 1, row)
        self._rows.append(row)
        self._update_remove_buttons()
        self._schedule_count()
        if focus:
            row.button_field.setFocus()

    def _remove_row(self, row: _RuleRow) -> None:
        if len(self._rows) <= 1:
            return  # siempre queda al menos una regla
        self._rows.remove(row)
        self._rules_layout.removeWidget(row)
        row.deleteLater()
        self._update_remove_buttons()
        self._schedule_count()

    def _update_remove_buttons(self) -> None:
        """La última regla que queda no se puede quitar."""
        for row in self._rows:
            row.button_remove.setEnabled(len(self._rows) > 1)

    # --- Reglas y recuento ------------------------------------------------------------------

    def _rule_set(self) -> RuleSet:
        """Las reglas de todas las filas. ValueError si alguna no es válida."""
        return RuleSet(self.combo_match.currentData(), tuple(row.rule() for row in self._rows))

    def _schedule_count(self, *_args: object) -> None:
        self._update_ok()
        if self._counter is not None:
            self._count_timer.start()

    def _count_now(self) -> None:
        """Pide (en segundo plano) cuántos elementos cumplen las reglas."""
        try:
            rule_set = self._rule_set()
        except ValueError as error:
            self._show_status(str(error), error=True)
            return
        self._count_generation += 1
        generation = self._count_generation
        self._show_status("Contando…")
        self._counter(rule_set, lambda count: self._on_count(generation, count))

    def _on_count(self, generation: int, count: int | None) -> None:
        """Llega el recuento. Se ignora si la ventana ya se cerró o las reglas cambiaron."""
        if not self._alive or generation != self._count_generation:
            return
        try:
            if count is None:
                self._show_status("No se pudo contar.", error=True)
            elif count == 1:
                self._show_status("Coincide 1 elemento")
            else:
                self._show_status(f"Coinciden {count:,} elementos".replace(",", "."))
        except RuntimeError:
            pass  # la ventana ya no existe (se cerró mientras se contaba)

    def _show_status(self, text: str, *, error: bool = False) -> None:
        self.label_status.setText(text)
        self.label_status.setStyleSheet("color: #e05050;" if error else "")

    def _update_ok(self, *_args: object) -> None:
        self.button_ok.setEnabled(bool(self.edit_name.text().strip()) and bool(self._rows))

    def _on_accept(self) -> None:
        """Comprueba las reglas antes de cerrar: si alguna no vale, se dice y no se cierra."""
        try:
            self._rule_set()
        except ValueError as error:
            self._show_status(str(error), error=True)
            return
        self.accept()

    def done(self, result: int) -> None:  # noqa: D401 - nombre de Qt
        """Al cerrar, los recuentos que lleguen después se ignoran."""
        self._alive = False
        self._count_timer.stop()
        super().done(result)

    def choice(self) -> SmartCollectionChoice:
        """Lo elegido (llamar tras 'exec()' con resultado aceptado)."""
        return SmartCollectionChoice(
            name=" ".join(self.edit_name.text().split()),
            parent_id=self.combo_parent.currentData(),
            rules=self._rule_set(),
        )

    @classmethod
    def ask(
        cls,
        parent: QWidget | None,
        *,
        sets: list[tuple[int, str]],
        parent_id: int | None = None,
        name: str = "",
        rules: RuleSet | None = None,
        editing: bool = False,
        counter: Counter | None = None,
        note: str = "",
        keyword_names: Sequence[str] = (),
    ) -> SmartCollectionChoice | None:
        """Abre la ventana y devuelve lo elegido, o None si se canceló."""
        dialog = cls(
            sets=sets,
            parent_id=parent_id,
            name=name,
            rules=rules,
            editing=editing,
            counter=counter,
            note=note,
            keyword_names=keyword_names,
            parent=parent,
        )
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return dialog.choice()
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    # Prueba manual: abre la ventana sola, con un contador simulado.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.smart_collection_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    def fake_counter(rule_set: RuleSet, callback: Callable[[int | None], None]) -> None:
        # Simula un recuento en segundo plano (llega un poco después)
        QTimer.singleShot(200, lambda: callback(len(rule_set.rules) * 42))

    result = SmartCollectionDialog.ask(None, sets=[(1, "Álbumes"), (2, "Álbumes › Viajes")], counter=fake_counter)
    print(result)
