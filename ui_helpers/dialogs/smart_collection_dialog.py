"""Ventana "Crear colección inteligente" / "Editar colección inteligente" (como Lightroom).

    Nombre:               [Las mejores de Ordesa          ]
    Dentro del conjunto:  [Ninguno (primer nivel)        ▾]

    Coincidir con [todas ▾] las reglas siguientes:
    ┌─────────────────────────────────────────────────────────────────────┐
    │ [Valoración       ▾] [es mayor o igual que ▾] [★★★        ▾]   [−] │
    │ [Fecha de captura ▾] [está entre           ▾] [01/06/24] y [30/06/24] [−] │
    │ ┃ Coincidir con [alguna de ▾] las reglas siguientes:            [−] │
    │ ┃ [País ▾]  [es ▾]  [España        ]                            [−] │
    │ ┃ [País ▾]  [es ▾]  [Francia       ]                            [−] │
    │ ┃ [+ Añadir regla]                                                  │
    └─────────────────────────────────────────────────────────────────────┘
    [+ Añadir regla]  [+ Añadir grupo]                Coinciden 128 elementos

                                                      [Crear]  [Cancelar]

Cómo está hecha (para ampliarla sin tocarla):
    - Cada regla es una fila 'SmartRuleRow' ('ui_helpers/widgets/smart_rule_row.py'): el
      menú de campos, los operadores y el control del valor según el tipo están allí.
    - Cada GRUPO (un paréntesis con su propio «todas / alguna de») es un 'SmartRuleGroup'
      ('ui_helpers/widgets/smart_rule_group.py'), con sus reglas dentro. Un solo nivel,
      como el motor. La lista principal guarda al menos una regla o un grupo.
    - La ventana no toca la base de datos: devuelve un 'SmartCollectionChoice' y quien la
      abre ('controllers/collection_actions.py') crea o guarda la colección. Para mostrar
      cuántos elementos coinciden, recibe una función 'counter' que cuenta en segundo plano.
    - Para el campo «Palabra clave», recibe los nombres de las palabras del catálogo
      ('keyword_names') y se los pasa a las filas, que los ofrecen mientras se escribe.
    - Los colores salen del tema ('ui_theme.py'): el aviso de arriba es '#lbl_dialog_warning'
      y el texto del recuento, '#lbl_dialog_status' (en rojo con la propiedad 'error').

1.4.0 Grupos de reglas: «+ Añadir grupo» y los grupos guardados ('SmartRuleGroup'); la
      lista se desplaza hasta la regla o el grupo que se añade.
1.3.0 Las filas de las reglas pasan a 'ui_helpers/widgets/smart_rule_row.py' (sin cambios
      de comportamiento); colores del tema en lugar de colores sueltos; autoprueba sin
      ventana (la ventana, con '--ventana').
1.2.0 Autocompletado del nombre en el campo «Palabra clave» ('keyword_names'; paso K4c).

Uso:
    choice = SmartCollectionDialog.ask(parent, sets=[(3, "Álbumes")], counter=contar)
    if choice is not None:
        ...  # choice.name, choice.parent_id, choice.rules

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.dialogs.smart_collection_dialog
Para verla (abre la ventana y espera a que se cierre):
    python -m ui_helpers.dialogs.smart_collection_dialog --ventana
"""

__version__ = "1.4.0"
__all__ = ["SmartCollectionChoice", "SmartCollectionDialog"]

# Librerías estándar
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QStringListModel, Qt, QTimer
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from core.catalog.smart_rules import MATCH_ALL, MATCH_ANY, Rule, RuleSet
from core.catalog.user_collections import MAX_NAME_LENGTH
from ui_helpers.widgets.smart_rule_group import MATCH_CHOICES, SmartRuleGroup
from ui_helpers.widgets.smart_rule_row import DEFAULT_RULE, SmartRuleRow

# Lo que hay en la lista principal: reglas y grupos
_Item = SmartRuleRow | SmartRuleGroup

# Espera (ms) tras el último cambio antes de volver a contar los elementos que coinciden
_COUNT_DELAY_MS = 350

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
        self._items: list[_Item] = []  # reglas y grupos de la lista principal, en orden
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
        for match, text in MATCH_CHOICES:  # las mismas que en la cabecera de un grupo
            self.combo_match.addItem(text, match)
        initial = rules or RuleSet(rules=(DEFAULT_RULE,))
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
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.StyledPanel)
        self._scroll.setWidget(self._rules_widget)
        self._scroll.setMinimumHeight(170)

        self.button_add_rule = QPushButton("+ Añadir regla")
        self.button_add_rule.clicked.connect(lambda: self._add_row(DEFAULT_RULE, focus=True))
        self.button_add_group = QPushButton("+ Añadir grupo")
        self.button_add_group.setToolTip(
            "Añadir un grupo de reglas con su propio «todas» o «alguna de» (como un paréntesis)"
        )
        self.button_add_group.clicked.connect(lambda: self._add_group(None, focus=True))
        self.label_status = QLabel()
        # El rojo de los errores lo pone el tema con la propiedad 'error' ('_show_status')
        self.label_status.setObjectName("lbl_dialog_status")
        self.label_status.setWordWrap(True)
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.button_add_rule)
        bottom_row.addWidget(self.button_add_group)
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
            label_note.setObjectName("lbl_dialog_warning")  # color de aviso, del tema
            label_note.setWordWrap(True)
            layout.addWidget(label_note)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addLayout(match_row)
        layout.addWidget(self._scroll, 1)
        layout.addLayout(bottom_row)
        layout.addWidget(self.buttons)

        # Recuento con retardo: no se cuenta con cada tecla, sino al dejar de escribir
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(_COUNT_DELAY_MS)
        self._count_timer.timeout.connect(self._count_now)

        for item in initial.rules:
            if isinstance(item, RuleSet):
                self._add_group(item)
            else:
                self._add_row(item)
        self._update_ok()
        self._schedule_count()

    # --- Reglas y grupos de la lista principal -------------------------------------------------

    def _add_row(self, rule: Rule, *, focus: bool = False) -> None:
        row = SmartRuleRow(rule, self._rules_widget, keyword_names=self._keyword_names)
        row.changed.connect(self._schedule_count)
        row.remove_requested.connect(self._remove_item)
        self._insert_item(row, scroll=focus)
        if focus:
            row.button_field.setFocus()

    def _add_group(self, rule_set: RuleSet | None, *, focus: bool = False) -> None:
        """Añade un grupo: el guardado o, con None, uno nuevo («alguna de» y una regla)."""
        group = SmartRuleGroup(rule_set, self._rules_widget, keyword_names=self._keyword_names)
        group.changed.connect(self._schedule_count)
        group.remove_requested.connect(self._remove_item)
        group.row_added.connect(self._scroll_to)  # una regla nueva en el grupo, a la vista
        self._insert_item(group, scroll=focus)
        if focus:
            group.focus_first()

    def _insert_item(self, item: _Item, *, scroll: bool) -> None:
        """Pone una regla o un grupo al final de la lista (antes del 'stretch', para que se
        apilen arriba). 'scroll': desplazarse hasta él (al añadirlo el usuario; al abrir la
        ventana, no, para que la lista empiece por arriba)."""
        self._rules_layout.insertWidget(self._rules_layout.count() - 1, item)
        self._items.append(item)
        self._update_remove_buttons()
        self._schedule_count()
        if scroll:
            self._scroll_to(item)

    def _remove_item(self, item: _Item) -> None:
        """Quita una regla o un grupo entero, con sus reglas (sin preguntar, como siempre)."""
        if len(self._items) <= 1:
            return  # siempre queda al menos una regla o un grupo
        self._items.remove(item)
        self._rules_layout.removeWidget(item)
        item.deleteLater()
        self._update_remove_buttons()
        self._schedule_count()

    def _update_remove_buttons(self) -> None:
        """Lo último que queda en la lista principal (regla o grupo) no se puede quitar."""
        for item in self._items:
            item.button_remove.setEnabled(len(self._items) > 1)

    def _scroll_to(self, widget: QWidget) -> None:
        """Desplaza la lista hasta 'widget' (una regla o un grupo recién añadidos).

        Qt coloca lo nuevo con retraso (con eventos pendientes, en varias vueltas): ni
        siquiera en la siguiente vuelta del bucle tiene aún su sitio ni la barra su nuevo
        recorrido. Por eso, en la siguiente vuelta, se fuerza la colocación (el layout de la
        lista y el recorrido de la barra) antes de desplazarse.
        """

        def scroll() -> None:
            try:
                self._rules_layout.activate()  # coloca reglas y grupos (y lo de dentro)
                # El área recalcula el tamaño de la lista y el recorrido de la barra
                QApplication.sendEvent(self._scroll, QEvent(QEvent.Type.LayoutRequest))
                self._scroll.ensureWidgetVisible(widget)
            except RuntimeError:
                pass  # ya no existe (se quitó o se cerró la ventana)

        QTimer.singleShot(0, scroll)

    # --- Reglas y recuento ------------------------------------------------------------------

    def _rule_set(self) -> RuleSet:
        """Las reglas y los grupos de la lista. ValueError si alguna regla no es válida."""
        return RuleSet(
            self.combo_match.currentData(),
            tuple(
                item.rule_set() if isinstance(item, SmartRuleGroup) else item.rule()
                for item in self._items
            ),
        )

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
        if self.label_status.property("error") != error:
            # El tema pinta en rojo 'QLabel#lbl_dialog_status[error="true"]'; al cambiar la
            # propiedad hay que volver a aplicar el estilo
            self.label_status.setProperty("error", error)
            self.label_status.style().unpolish(self.label_status)
            self.label_status.style().polish(self.label_status)

    def _update_ok(self, *_args: object) -> None:
        self.button_ok.setEnabled(bool(self.edit_name.text().strip()) and bool(self._items))

    def _on_accept(self) -> None:
        """Comprueba las reglas antes de cerrar: si alguna no vale, se dice y no se cierra."""
        try:
            self._rule_set()
        except ValueError as error:
            self._show_status(str(error), error=True)
            return
        self.accept()

    def done(self, result: int) -> None:  # nombre de Qt
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
    # Autoprueba SIN ventana (plataforma 'offscreen'): filas, recuento, errores y lo elegido.
    # Con '--ventana', la abre de verdad con un contador simulado (y espera a que se cierre).
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.smart_collection_dialog
    import os
    import sys

    show_window = "--ventana" in sys.argv
    if not show_window:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # (antes de crear la aplicación: Qt lee la plataforma al crearla)

    from core.catalog.smart_fields import FIELDS

    app = QApplication([])
    sets = [(1, "Álbumes"), (2, "Álbumes › Viajes")]

    if show_window:
        from ui_helpers.helpers.ui_theme import apply_theme

        apply_theme()

        def fake_counter(rule_set: RuleSet, callback: Callable[[int | None], None]) -> None:
            # Simula un recuento en segundo plano (llega un poco después)
            QTimer.singleShot(200, lambda: callback(len(rule_set.rules) * 42))

        note = "Aviso de ejemplo, con el color de aviso del tema."
        print(SmartCollectionDialog.ask(None, sets=sets, counter=fake_counter, note=note))
        sys.exit(0)

    # 1. Crear: una regla de ejemplo con «todas»; sin nombre no se puede crear
    counts: list[tuple[RuleSet, Callable[[int | None], None]]] = []
    dialog = SmartCollectionDialog(sets=sets, counter=lambda rules, done: counts.append((rules, done)))
    assert dialog.windowTitle() == "Crear colección inteligente" and dialog.button_ok.text() == "Crear"
    assert dialog._rule_set() == RuleSet(MATCH_ALL, (DEFAULT_RULE,))
    assert not dialog.button_ok.isEnabled()
    assert not dialog._items[0].button_remove.isEnabled()  # la única regla no se quita
    assert dialog.findChild(QLabel, "lbl_dialog_warning") is None  # sin aviso
    dialog.edit_name.setText("  Las   mejores ")
    assert dialog.button_ok.isEnabled()

    # 2. Añadir y quitar reglas
    dialog.button_add_rule.click()
    assert len(dialog._items) == 2 and all(row.button_remove.isEnabled() for row in dialog._items)
    dialog._items[1].button_remove.click()
    assert len(dialog._items) == 1 and not dialog._items[0].button_remove.isEnabled()

    # 2b. Grupos: «+ Añadir grupo» añade al final uno nuevo («alguna de» y una regla)
    dialog.button_add_group.click()
    group = dialog._items[1]
    assert isinstance(group, SmartRuleGroup) and len(dialog._items) == 2
    assert dialog._rule_set() == RuleSet(MATCH_ALL, (DEFAULT_RULE, RuleSet(MATCH_ANY, (DEFAULT_RULE,))))
    assert group.button_remove.isEnabled() and dialog._items[0].button_remove.isEnabled()
    assert not group.rows()[0].button_remove.isEnabled()  # la última regla del grupo
    # Un cambio dentro del grupo vuelve a contar
    dialog._count_timer.stop()
    group.button_add_rule.click()
    assert dialog._count_timer.isActive() and len(group.rows()) == 2
    # Si solo queda el grupo, tampoco se puede quitar
    dialog._items[0].button_remove.click()
    assert dialog._items == [group] and not group.button_remove.isEnabled()
    assert dialog._rule_set() == RuleSet(MATCH_ALL, (RuleSet(MATCH_ANY, (DEFAULT_RULE,) * 2),))
    # Con otra regla, el [−] del grupo lo quita entero, con sus reglas
    dialog.button_add_rule.click()
    group.button_remove.click()
    assert len(dialog._items) == 1 and isinstance(dialog._items[0], SmartRuleRow)
    assert not dialog._items[0].button_remove.isEnabled()
    assert dialog._rule_set() == RuleSet(MATCH_ALL, (DEFAULT_RULE,))

    # 3. Recuento: «Contando…» y el número; uno que llega tarde (reglas ya cambiadas), no
    dialog._count_now()
    assert dialog.label_status.text() == "Contando…" and counts[-1][0] == dialog._rule_set()
    late = counts[-1][1]
    dialog._count_now()
    late(5)
    assert dialog.label_status.text() == "Contando…"
    counts[-1][1](1)
    assert dialog.label_status.text() == "Coincide 1 elemento"
    counts[-1][1](1234)
    assert dialog.label_status.text() == "Coinciden 1.234 elementos"
    assert dialog.label_status.property("error") is False
    counts[-1][1](None)
    assert dialog.label_status.text() == "No se pudo contar."
    assert dialog.label_status.property("error") is True  # el tema lo pinta en rojo

    # 4. Una regla que no vale: el error (en rojo) y la ventana no se cierra
    dialog._items[0]._on_field_chosen("title")  # texto vacío
    dialog._count_now()
    assert "falta el texto" in dialog.label_status.text()
    assert dialog.label_status.property("error") is True
    dialog._on_accept()
    assert dialog.result() == 0  # sin aceptar
    dialog._items[0].findChild(QLineEdit).setText("Ordesa")
    dialog._count_now()
    assert dialog.label_status.property("error") is False

    # 5. Lo elegido: nombre sin espacios de más, conjunto, modo y reglas
    dialog.combo_parent.setCurrentIndex(dialog.combo_parent.findData(2))
    dialog.combo_match.setCurrentIndex(dialog.combo_match.findData(MATCH_ANY))
    title_rule = Rule("title", FIELDS["title"].allowed_operators[0], "Ordesa")
    expected = SmartCollectionChoice("Las mejores", 2, RuleSet(MATCH_ANY, (title_rule,)))
    assert dialog.choice() == expected, dialog.choice()
    dialog._on_accept()
    assert dialog.result() == 1  # aceptada
    counts[-1][1](7)  # un recuento que llega con la ventana ya cerrada: se ignora
    assert dialog.label_status.text() == "Contando…"

    # 6. Editar: las reglas y los grupos guardados, «Guardar» y el aviso de arriba
    countries = RuleSet(MATCH_ANY, (Rule("country", "eq", "España"), Rule("country", "eq", "Francia")))
    saved = RuleSet(MATCH_ALL, (
        Rule("rating", "gte", 3),
        countries,
        Rule("captured_at", "between", ("2024-06-01", "2024-06-30")),
        Rule("color_label", "eq", "red"),
    ))  # fmt: skip
    edit = SmartCollectionDialog(
        sets=sets, parent_id=2, name="Ordesa", rules=saved, editing=True, note="Aviso"
    )
    assert edit.windowTitle() == "Editar colección inteligente" and edit.button_ok.text() == "Guardar"
    assert edit._rule_set() == saved and edit.combo_parent.currentData() == 2
    assert [type(item) for item in edit._items] == [SmartRuleRow, SmartRuleGroup, SmartRuleRow, SmartRuleRow]
    assert edit.button_ok.isEnabled() and len(edit._items[1].rows()) == 2
    assert edit.findChild(QLabel, "lbl_dialog_warning").text() == "Aviso"
    # Sin contador: no se cuenta ni se muestra nada
    edit._schedule_count()
    assert edit.label_status.text() == ""

    dialog.deleteLater()
    edit.deleteLater()
    print("Autoprueba finalizada correctamente.")
