"""Una regla del editor de colecciones inteligentes: [campo ▾] [operador ▾] [valor] [−].

    [Valoración       ▾] [es mayor o igual que ▾] [★★★        ▾]   [−]
    [Fecha de captura ▾] [está entre           ▾] [01/06/24] y [30/06/24] [−]

Cómo está hecha (para ampliarla sin tocarla):
    - El botón del CAMPO abre un menú con un submenú por grupo (Estándar, Imagen, Tracks
      GPS...) y, dentro, los campos por secciones. Todo sale de 'core/catalog/smart_fields.py':
      un campo nuevo aparece aquí solo.
    - Los OPERADORES de cada campo salen de su tipo ('allowed_operators').
    - El VALOR se edita con un control según el tipo (texto, número con su unidad, fecha
      con calendario, lista, estrellas...). Para un tipo nuevo, añadir su caso en
      '_ValueEditor'.
    - Para el campo «Palabra clave», recibe los nombres de las palabras del catálogo
      ('keyword_names') y los ofrece mientras se escribe (contienen lo escrito, sin
      distinguir mayúsculas).

La usa 'ui_helpers/dialogs/smart_collection_dialog.py' (una fila por regla).

1.0.0 Separada del diálogo de colecciones inteligentes, sin cambios de comportamiento
      ('_RuleRow' pasa a ser 'SmartRuleRow'; antes de los grupos de reglas).

Uso:
    row = SmartRuleRow(Rule("rating", "gte", 3), parent, keyword_names=modelo)
    row.changed.connect(...)            # cualquier cambio de campo, operador o valor
    row.remove_requested.connect(...)   # pulsó [−] (recibe la propia fila)
    row.rule()                          # la regla, validada (ValueError si no vale)

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.smart_rule_row
"""

__version__ = "1.0.0"
__all__ = ["DEFAULT_RULE", "SmartRuleRow"]

# Librerías estándar
from datetime import date
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QDate, QStringListModel, Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QSpinBox,
    QToolButton,
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
from core.catalog.smart_rules import Rule, validate_rule

# Regla con la que empieza una fila nueva
DEFAULT_RULE = Rule("rating", "gte", 1)
# Límites de los números (los campos admiten negativos: p. ej. una altitud bajo el mar)
_NUMBER_LIMIT = 1e12


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


class SmartRuleRow(QWidget):
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

        self._set_field(rule.field if rule.field in FIELDS else DEFAULT_RULE.field, rule.operator)
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


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): cada tipo de valor de ida y vuelta,
    # cambios de campo y de operador, sugerencias de palabras clave y la señal de quitar.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.smart_rule_row
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    holder = QWidget()  # padre de todas las filas (se borran con él)

    # 1. Cada tipo de valor: la regla sale igual que entró
    for original in (
        Rule("rating", "gte", 3),
        Rule("title", "contains", "Ordesa"),
        Rule("keyword", "kw_is", "Coche"),
        Rule("file_size", "gt", 4 * 1024 * 1024),  # se ve en MB, se guarda en bytes
        Rule("track_distance", "between", (12_500.0, 20_000.0)),  # se ve en km
        Rule("iso", "eq", 800),
        Rule("captured_at", "between", ("2024-06-01", "2024-06-30")),
        Rule("added_at", "in_last", 7),
        Rule("color_label", "eq", "red"),
        Rule("has_gps", "is_true"),
        Rule("title", "is_not_set"),
    ):
        row = SmartRuleRow(original, holder)
        assert row.rule() == original, (row.rule(), original)
    assert row.button_field.text() == FIELDS["title"].label

    # 2. Un campo que ya no existe: la fila usa el de la regla por defecto
    assert SmartRuleRow(Rule("zzz", "eq", 1), holder).rule() == Rule(DEFAULT_RULE.field, "eq", 1)

    # 3. Cambiar de campo: el operador se conserva si el campo nuevo lo admite; sin texto,
    # la regla no vale (con un mensaje para el usuario)
    changes: list[int] = []
    row = SmartRuleRow(Rule("iso", "gte", 100), holder)
    row.changed.connect(lambda: changes.append(1))
    row._on_field_chosen("track_distance")
    assert row.rule().operator == "gte" and changes
    row._on_field_chosen("title")
    assert row.combo_operator.currentData() == FIELDS["title"].allowed_operators[0]
    try:
        row.rule()
    except ValueError as error:
        assert "falta el texto" in str(error), error
    else:
        raise AssertionError("una regla de texto vacía no debía valer")

    # 4. Cambiar de operador: el valor se conserva si tiene sentido («entre» lo repite)
    row = SmartRuleRow(Rule("iso", "gte", 400), holder)
    for operator, expected in (
        ("between", Rule("iso", "between", (400, 400))),
        ("lt", Rule("iso", "lt", 400)),
        ("is_set", Rule("iso", "is_set")),
    ):
        row.combo_operator.setCurrentIndex(row.combo_operator.findData(operator))
        assert row.rule() == expected, (row.rule(), expected)

    # 5. «Palabra clave»: ofrece los nombres del catálogo; otros campos de texto, no
    names = QStringListModel(["Coche", "Toyota Corolla"], holder)
    row = SmartRuleRow(Rule("keyword", "contains", "co"), holder, keyword_names=names)
    completer = row.findChild(QLineEdit).completer()
    assert completer is not None and completer.model().rowCount() == 2
    title_row = SmartRuleRow(Rule("title", "contains", "co"), holder, keyword_names=names)
    assert title_row.findChild(QLineEdit).completer() is None

    # 6. [−]: avisa con la propia fila
    removed: list[QWidget] = []
    row.remove_requested.connect(removed.append)
    row.button_remove.click()
    assert removed == [row]

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
