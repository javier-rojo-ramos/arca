"""Un grupo de reglas del editor de colecciones inteligentes, con su propio «todas / alguna de».

    ┃ Coincidir con [alguna de ▾] las reglas siguientes:                    [−]
    ┃ [País ▾]  [es ▾]  [España        ]                                    [−]
    ┃ [País ▾]  [es ▾]  [Francia       ]                                    [−]
    ┃ [+ Añadir regla]

Se lee como un paréntesis: «Valoración ≥ ★★★ y (País es España o País es Francia)». Un
solo nivel: dentro solo hay reglas ('SmartRuleRow'), no otros grupos (lo exige el motor,
'core/catalog/smart_rules.py'). La raya de la izquierda la pone el tema
('QFrame#frame_rule_group' en 'ui_theme.py').

Reglas acordadas con el autor (09/11/2026):
    - un grupo nuevo empieza con «alguna de» y una regla ('DEFAULT_RULE');
    - el [−] de la cabecera pide quitar el grupo entero (lo quita la ventana, sin preguntar);
    - la última regla del grupo no se puede quitar (para eso está el [−] del grupo);
    - la cabecera dice lo mismo que la de la ventana ('MATCH_CHOICES', compartido).

1.0.0 Grupo de reglas (colecciones inteligentes con grupos, subpaso 3).

Uso:
    group = SmartRuleGroup(RuleSet("any", (...)), parent, keyword_names=modelo)
    group.changed.connect(...)          # cualquier cambio (modo, reglas, valores)
    group.remove_requested.connect(...) # pulsó el [−] de la cabecera (recibe el grupo)
    group.row_added.connect(...)        # una regla nueva (recibe la fila; p. ej. para verla)
    group.rule_set()                    # el grupo como 'RuleSet' (ValueError si no vale)

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.smart_rule_group
"""

__version__ = "1.0.0"
__all__ = ["MATCH_CHOICES", "SmartRuleGroup"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QStringListModel, Signal
from qtpy.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.smart_rules import MATCH_ALL, MATCH_ANY, Rule, RuleSet
from ui_helpers.widgets.smart_rule_row import DEFAULT_RULE, SmartRuleRow

# Opciones de «Coincidir con [...] las reglas siguientes:» (la ventana usa las mismas)
MATCH_CHOICES = ((MATCH_ALL, "todas"), (MATCH_ANY, "alguna de"))

# Sangría de las reglas del grupo respecto a la raya de la izquierda (px)
_INDENT = 10


class SmartRuleGroup(QFrame):
    """Un grupo: cabecera con su modo y [−], sus reglas y «+ Añadir regla»."""

    changed = Signal()
    remove_requested = Signal(object)  # el propio grupo
    row_added = Signal(object)  # la fila nueva

    def __init__(
        self,
        rule_set: RuleSet | None = None,
        parent: QWidget | None = None,
        keyword_names: QStringListModel | None = None,
    ) -> None:
        """Crea el grupo.

        Args:
            rule_set: Modo y reglas iniciales (None = grupo nuevo: «alguna de» y una regla).
                Solo se usan sus reglas ('Rule'): un grupo dentro no puede llegar, porque
                el motor no lo admite.
            parent: Widget padre.
            keyword_names: Nombres de las palabras clave del catálogo (sugerencias).
        """
        super().__init__(parent)
        self.setObjectName("frame_rule_group")  # la raya de la izquierda, del tema
        self._keyword_names = keyword_names
        self._rows: list[SmartRuleRow] = []
        initial = rule_set if rule_set is not None else RuleSet(MATCH_ANY, (DEFAULT_RULE,))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_INDENT, 2, 0, 2)

        # --- Cabecera: «Coincidir con [alguna de ▾] las reglas siguientes:» y [−] ---
        self.combo_match = QComboBox()
        for match, text in MATCH_CHOICES:
            self.combo_match.addItem(text, match)
        self.combo_match.setCurrentIndex(max(0, self.combo_match.findData(initial.match)))
        self.combo_match.currentIndexChanged.connect(self.changed)
        self.button_remove = QToolButton()
        self.button_remove.setText("−")
        self.button_remove.setToolTip("Quitar este grupo y sus reglas")
        self.button_remove.setAutoRaise(True)
        self.button_remove.clicked.connect(lambda: self.remove_requested.emit(self))
        header = QHBoxLayout()
        header.addWidget(QLabel("Coincidir con"))
        header.addWidget(self.combo_match)
        header.addWidget(QLabel("las reglas siguientes:"))
        header.addStretch(1)
        header.addWidget(self.button_remove)
        layout.addLayout(header)

        # --- Reglas ---
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows_layout)

        # --- «+ Añadir regla» (al grupo) ---
        self.button_add_rule = QPushButton("+ Añadir regla")
        self.button_add_rule.setToolTip("Añadir una regla a este grupo")
        self.button_add_rule.clicked.connect(lambda: self._add_row(DEFAULT_RULE, focus=True))
        footer = QHBoxLayout()
        footer.addWidget(self.button_add_rule)
        footer.addStretch(1)
        layout.addLayout(footer)

        rules = [item for item in initial.rules if isinstance(item, Rule)]
        for rule in rules or [DEFAULT_RULE]:  # nunca vacío: el motor no lo admite
            self._add_row(rule)

    # --- Reglas ------------------------------------------------------------------------------

    def _add_row(self, rule: Rule, *, focus: bool = False) -> None:
        row = SmartRuleRow(rule, self, keyword_names=self._keyword_names)
        row.changed.connect(self.changed)
        row.remove_requested.connect(self._remove_row)
        self._rows_layout.addWidget(row)
        self._rows.append(row)
        self._update_remove_buttons()
        self.changed.emit()
        self.row_added.emit(row)
        if focus:
            row.button_field.setFocus()

    def _remove_row(self, row: SmartRuleRow) -> None:
        if len(self._rows) <= 1:
            return  # la última no se quita: se quita el grupo con su [−]
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()
        self._update_remove_buttons()
        self.changed.emit()

    def _update_remove_buttons(self) -> None:
        """La última regla del grupo no se puede quitar."""
        for row in self._rows:
            row.button_remove.setEnabled(len(self._rows) > 1)

    def rows(self) -> list[SmartRuleRow]:
        """Las filas del grupo, en orden."""
        return list(self._rows)

    def focus_first(self) -> None:
        """Pone el foco en el campo de la primera regla (al crear el grupo)."""
        self._rows[0].button_field.setFocus()

    # --- Resultado ---------------------------------------------------------------------------

    def rule_set(self) -> RuleSet:
        """El grupo como 'RuleSet' (su modo y sus reglas, validadas).

        Raises:
            ValueError: Si alguna regla no vale (mensaje para el usuario).
        """
        return RuleSet(self.combo_match.currentData(), tuple(row.rule() for row in self._rows))


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): grupo nuevo, ida y vuelta, añadir y
    # quitar reglas, señales y errores.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.smart_rule_group
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication, QLineEdit

    app = QApplication([])
    holder = QWidget()  # padre de los grupos (se borran con él)

    # 1. Grupo nuevo: «alguna de» y la regla por defecto, que no se puede quitar
    group = SmartRuleGroup(parent=holder)
    assert group.objectName() == "frame_rule_group"
    assert group.rule_set() == RuleSet(MATCH_ANY, (DEFAULT_RULE,))
    assert group.combo_match.currentText() == "alguna de"
    assert len(group.rows()) == 1 and not group.rows()[0].button_remove.isEnabled()

    # 2. Ida y vuelta: el modo y las reglas salen como entraron
    countries = RuleSet(MATCH_ALL, (Rule("country", "eq", "España"), Rule("rating", "gte", 3)))
    assert SmartRuleGroup(countries, holder).rule_set() == countries
    # Vacío (no debería llegar): una regla por defecto, para que el motor lo acepte
    assert SmartRuleGroup(RuleSet(MATCH_ALL, ()), holder).rule_set() == RuleSet(MATCH_ALL, (DEFAULT_RULE,))

    # 3. Añadir y quitar reglas: avisa de cada cambio y de la fila nueva
    changes: list[int] = []
    added: list[SmartRuleRow] = []
    group.changed.connect(lambda: changes.append(1))
    group.row_added.connect(added.append)
    group.button_add_rule.click()
    assert len(group.rows()) == 2 and added == [group.rows()[1]] and changes
    assert all(row.button_remove.isEnabled() for row in group.rows())
    changes.clear()
    group.rows()[0].button_remove.click()
    assert len(group.rows()) == 1 and changes and not group.rows()[0].button_remove.isEnabled()
    group.rows()[0].button_remove.click()  # la última: no se quita
    assert len(group.rows()) == 1

    # 4. Cambiar el modo también avisa
    changes.clear()
    group.combo_match.setCurrentIndex(group.combo_match.findData(MATCH_ALL))
    assert changes and group.rule_set().match == MATCH_ALL

    # 5. Una regla que no vale: ValueError con el mensaje para el usuario
    group.rows()[0]._on_field_chosen("title")
    try:
        group.rule_set()
    except ValueError as error:
        assert "falta el texto" in str(error), error
    else:
        raise AssertionError("una regla de texto vacía no debía valer")
    group.rows()[0].findChild(QLineEdit).setText("Ordesa")
    assert group.rule_set().rules[0].value == "Ordesa"

    # 6. [−] de la cabecera: pide quitar el grupo (con el propio grupo)
    removed: list[SmartRuleGroup] = []
    group.remove_requested.connect(removed.append)
    group.button_remove.click()
    assert removed == [group]

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
