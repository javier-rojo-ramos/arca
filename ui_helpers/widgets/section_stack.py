"""Pila de secciones plegables de una barra lateral, colocadas según el modelo.

Es el contenedor común de las tres barras (la del Catálogo, la de Imagen y el inspector):
cada barra crea sus 'CollapsibleSection' como siempre y las da de alta aquí con su 'id' (el
del registro, 'ui_helpers/layout/section_registry.py'). La pila las coloca como diga el
modelo ('SectionLayoutModel') para el modo y la barra a los que está unida:

    - el ORDEN, de arriba abajo;
    - si se VEN (lo que elige el usuario) y, además, si están DISPONIBLES (lo que decide la
      barra: p. ej. el inspector oculta la sección que no se aplica a lo seleccionado). Una
      sección se ve solo si se cumplen las dos cosas;
    - si están DESPLEGADAS. Al plegar o desplegar una con su cabecera, se apunta en el
      modelo (que lo guarda).

Además pone el MENÚ de las secciones (clic derecho en la cabecera de cualquiera y, con
'watch_empty_area', en el hueco vacío de la barra): una casilla por sección para mostrarla
u ocultarla y «Restaurar por defecto» (el orden, las ocultas y las plegadas de ESTA barra
en ESTE modo). El menú solo escribe en el modelo.

Y permite REORDENAR arrastrando las cabeceras (por el título) dentro de la barra: mientras
se arrastra, una raya del color de acento dice dónde quedará la sección; al soltar, se
apunta en el modelo. Soltar con el ratón fuera de la barra, a un lado, lo cancela (la raya
desaparece para avisar). Un clic sin mover sigue plegando o desplegando. Si la barra no cabe
entera, se desplaza al acercar el ratón a su borde de arriba o de abajo.

Y se recoloca sola cuando el modelo avisa de un cambio ('layout_changed'), venga de donde
venga. La pila no guarda nada: la única fuente de verdad es el modelo.

Uso (dentro de una barra):
    stack = SectionStack(content)
    stack.add_section("folders", section_folders)     # en el orden de partida
    content_layout.addWidget(stack)
    content_layout.addStretch(1)
    ...
    stack.bind(model, "image", Sidebar.LEFT)           # cuando se conoce el modelo
    stack.set_mode("catalog")                          # el inspector, al cambiar de módulo
    stack.set_available("metadata", False)             # el inspector, según lo seleccionado
    stack.watch_empty_area(content)                    # el menú, también en el hueco vacío

Sin modelo (antes de 'bind', o en una prueba suelta de una barra) las secciones quedan en
el orden en el que se dieron de alta, todas a la vista. Una sección que el modelo no conoce
para ese modo (falta registrarla) se queda al final, visible: se ve que falta, sin fallar.

1.2.0 Reordenar arrastrando las cabeceras, con una raya que dice dónde caerá (fase 3).
1.1.0 Menú de las secciones: casillas para mostrar u ocultar y «Restaurar por defecto»
      ('build_menu', 'show_menu', 'watch_empty_area'; fase 2).
1.0.0 Primera versión (14/11/2026; fase 1b de las secciones personalizables).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.section_stack
"""

__version__ = "1.2.0"
__all__ = ["RESTORE_TEXT", "SECTION_SPACING", "SectionStack"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint, Qt, Signal
from qtpy.QtWidgets import (
    QApplication,
    QFrame,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from ui_helpers.layout.section_layout import SectionEntry
from ui_helpers.layout.section_layout_model import SectionLayoutModel
from ui_helpers.layout.section_registry import Sidebar
from ui_helpers.widgets.collapsible_section import CollapsibleSection

# Separación vertical entre secciones (px lógicos): la que tenían las barras
SECTION_SPACING = 2
# Grosor de la raya que dice dónde caerá la sección arrastrada (px lógicos): el del hueco
# entre secciones, que es donde se pinta. Su color, en 'ui_theme.py'
# ('#frame_section_drop_indicator')
DROP_INDICATOR_HEIGHT = SECTION_SPACING
# Al arrastrar una cabecera cerca del borde de arriba o de abajo de la barra, esta se
# desplaza para que el ratón quede al menos a esta distancia del borde (px lógicos)
DRAG_SCROLL_MARGIN = 32
# Texto de la opción del menú que devuelve la barra a su colocación de partida
RESTORE_TEXT = "Restaurar por defecto"


class SectionStack(QWidget):
    """Las secciones de una barra, colocadas según el modelo (ver el docstring del archivo).

    Signals:
        shown_sections_changed(): ha cambiado QUÉ secciones tiene el usuario a la vista (al
            ocultar o mostrar una, o al cambiar de modo). No se emite al reordenar ni al
            plegar. Para la barra que tenga que rellenar una sección que vuelve a verse.
    """

    shown_sections_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Del alto de sus secciones, ni más ni menos: el hueco que sobre en la barra queda
        # debajo (lo pone la barra con 'addStretch')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(SECTION_SPACING)

        # Las secciones por su 'id', en el orden en el que se dieron de alta
        self._sections: dict[str, CollapsibleSection] = {}
        # Los 'id' en el orden en el que están ahora en pantalla
        self._order: list[str] = []
        # Lo que la barra ha dicho que no está disponible (las que no constan, sí)
        self._available: dict[str, bool] = {}
        # Los 'id' que el usuario tiene a la vista (None hasta la primera colocación)
        self._shown: frozenset[str] | None = None

        self._model: SectionLayoutModel | None = None
        self._mode = ""
        self._sidebar: Sidebar | None = None

        # Arrastre de una cabecera: el 'id' de la sección que se arrastra (None = ninguna)
        self._drag_id: str | None = None
        # La raya que dice dónde caerá: fuera del layout (se coloca a mano sobre el hueco)
        self._drop_indicator = QFrame(self)
        self._drop_indicator.setObjectName("frame_section_drop_indicator")
        self._drop_indicator.setFixedHeight(DROP_INDICATOR_HEIGHT)
        # Que no se lleve los clics ni los movimientos del ratón
        self._drop_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drop_indicator.hide()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def add_section(self, section_id: str, section: CollapsibleSection) -> None:
        """Da de alta una sección con su 'id' del registro (queda la última hasta que el
        modelo diga otra cosa).

        Raises:
            ValueError: Si el 'id' está vacío o repetido.
        """
        if not section_id or section_id in self._sections:
            raise ValueError(f"Id de sección vacío o repetido: {section_id!r}")
        self._sections[section_id] = section
        self._order.append(section_id)
        self._layout.addWidget(section)  # el layout la hace hija de la pila
        # Clic derecho en su cabecera: el menú de las secciones
        section.header_menu_requested.connect(self.show_menu)
        # Arrastrar su cabecera: cambiarla de sitio
        section.header_drag_started.connect(lambda sid=section_id: self._on_drag_started(sid))
        section.header_drag_moved.connect(self._on_drag_moved)
        section.header_drag_finished.connect(self._on_drag_finished)
        # Plegar o desplegar con la cabecera se apunta en el modelo
        section.toggled.connect(
            lambda expanded, sid=section_id: self._on_section_toggled(sid, expanded)
        )
        if self._model is not None:
            self._apply()

    def section(self, section_id: str) -> CollapsibleSection | None:
        """La sección con ese 'id' (None si no está en la pila)."""
        return self._sections.get(section_id)

    def section_ids(self) -> tuple[str, ...]:
        """Los 'id' de las secciones, en el orden en el que están en pantalla."""
        return tuple(self._order)

    def bind(self, model: SectionLayoutModel, mode: str, sidebar: Sidebar) -> None:
        """Une la pila a un modo y una barra del modelo, y coloca las secciones."""
        if self._model is not None:
            self._model.layout_changed.disconnect(self._on_layout_changed)
        self._model = model
        self._mode = mode
        self._sidebar = sidebar
        model.layout_changed.connect(self._on_layout_changed)
        self._apply()

    def mode(self) -> str:
        """El modo al que está unida ("" si a ninguno)."""
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Cambia de modo (para una barra compartida por varios, como el inspector)."""
        if mode != self._mode:
            self._mode = mode
            self._apply()

    def set_available(self, section_id: str, available: bool) -> None:
        """La barra dice si una sección tiene ahora algo que mostrar. Sin ello no se ve,
        aunque el usuario la tenga a la vista."""
        self._available[section_id] = available
        section = self._sections.get(section_id)
        if section is not None:
            section.setVisible(self._is_wanted(section_id))

    def is_user_visible(self, section_id: str) -> bool:
        """True si el usuario tiene esa sección a la vista en el modo actual (también las
        que el modelo no conoce)."""
        entry = self._entry(section_id)
        return entry.visible if entry is not None else True

    # -------------------------------------------------------------------------
    # Menú de las secciones
    # -------------------------------------------------------------------------

    def build_menu(self) -> QMenu | None:
        """El menú de las secciones de esta barra en el modo actual: una casilla por
        sección (marcada = a la vista), en su orden, y «Restaurar por defecto».

        Están todas las del modo, también las que ahora no tienen nada que mostrar (p. ej.
        «Metadatos» sin una foto seleccionada): la casilla dice si el usuario la quiere ver.

        Returns:
            El menú (hijo de la pila; quien lo pide lo muestra y lo descarta), o None si no
            hay modelo o ninguna sección que ofrecer.
        """
        model, mode, sidebar = self._model, self._mode, self._sidebar
        if model is None or sidebar is None:
            return None
        entries = [entry for entry in model.entries(mode, sidebar) if entry.id in self._sections]
        if not entries:
            return None
        menu = QMenu(self)
        for entry in entries:
            action = menu.addAction(model.title(mode, entry.id))
            action.setCheckable(True)
            action.setChecked(entry.visible)
            action.toggled.connect(
                lambda checked, sid=entry.id: model.set_visible(mode, sid, checked)
            )
        menu.addSeparator()
        restore = menu.addAction(RESTORE_TEXT)
        # Sin nada cambiado no hay nada que restaurar
        restore.setEnabled(not model.is_default(mode, sidebar))
        restore.triggered.connect(lambda: model.reset(mode, sidebar))
        return menu

    def show_menu(self, global_position: QPoint) -> None:
        """Abre el menú de las secciones en ese punto de la pantalla (si hay qué ofrecer)."""
        menu = self.build_menu()
        if menu is None:
            return
        menu.exec(global_position)
        menu.deleteLater()

    def watch_empty_area(self, widget: QWidget) -> None:
        """El clic derecho en 'widget' (el fondo de la barra, donde está la pila) abre también
        el menú: así se llega a él aunque estén todas las secciones ocultas."""
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda position: self.show_menu(widget.mapToGlobal(position))
        )

    # -------------------------------------------------------------------------
    # Reordenar arrastrando las cabeceras
    # -------------------------------------------------------------------------

    def _drop_candidates(self) -> list[str]:
        """Las secciones entre las que se puede soltar: las del modelo que están a la
        vista, en su orden en pantalla (también la que se arrastra)."""
        if self._model is None or self._sidebar is None:
            return []
        known = {entry.id for entry in self._model.entries(self._mode, self._sidebar)}
        return [
            sid for sid in self._order if sid in known and not self._sections[sid].isHidden()
        ]

    def drop_target(self, position: QPoint) -> tuple[bool, str | None]:
        """Dónde caería la sección arrastrada si se soltara en ese punto de la pila.

        Se suelta ANTES de la primera sección cuya mitad queda por debajo del ratón (así,
        con secciones altas, basta con pasar de su mitad); por debajo de todas, al final.

        Returns:
            (vale, antes_de): 'vale' es False si soltar ahí cancela (el ratón, a un lado
            de la barra); 'antes_de' es el 'id' de la sección delante de la cual quedaría,
            o None = la última.
        """
        if not 0 <= position.x() <= self.width():
            return False, None
        for section_id in self._drop_candidates():
            geometry = self._sections[section_id].geometry()
            if position.y() < geometry.center().y():
                return True, section_id
        return True, None

    def drop_index(self, before: str | None) -> int | None:
        """Posición del modelo ('SectionLayoutModel.move') en la que queda la sección
        arrastrada al soltarla delante de 'before' (None = la última de las que se ven).
        None = se queda donde está (nada que mover)."""
        if self._model is None or self._sidebar is None or self._drag_id is None:
            return None
        if before == self._drag_id:
            return None  # delante de sí misma
        # La lista del modelo sin la arrastrada: la posición que se pide es en esa lista.
        # Tiene también las ocultas: se cuenta por 'id', no por lo que se ve
        rest = [
            entry.id
            for entry in self._model.entries(self._mode, self._sidebar)
            if entry.id != self._drag_id
        ]
        if before is not None:
            return rest.index(before) if before in rest else None
        others = [sid for sid in self._drop_candidates() if sid != self._drag_id]
        if not others:
            return None  # es la única a la vista
        return rest.index(others[-1]) + 1  # detrás de la última que se ve

    def _on_drag_started(self, section_id: str) -> None:
        """Se empieza a arrastrar una cabecera (solo las secciones que el modelo conoce)."""
        if section_id not in self._drop_candidates():
            return
        self._drag_id = section_id
        QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)

    def _on_drag_moved(self, global_position: QPoint) -> None:
        """El ratón se mueve con una cabecera cogida: la raya, donde caería."""
        if self._drag_id is None:
            return
        self._scroll_towards(global_position)
        valid, before = self.drop_target(self.mapFromGlobal(global_position))
        if not valid:
            self._drop_indicator.hide()  # soltar aquí cancela
            return
        self._place_indicator(before)

    def _scroll_towards(self, global_position: QPoint) -> None:
        """Si la barra tiene desplazamiento y el ratón se acerca a su borde de arriba o de
        abajo, la desplaza hacia allí: así se llega a una sección que no cabe a la vista."""
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parentWidget()
        if parent is None or parent.widget() is None:
            return
        point = parent.widget().mapFromGlobal(global_position)
        # Solo en vertical (las barras no se desplazan a lo ancho)
        parent.ensureVisible(0, point.y(), 0, DRAG_SCROLL_MARGIN)

    def _on_drag_finished(self, global_position: QPoint) -> None:
        """Se suelta la cabecera: la sección, a su sitio nuevo (lo apunta el modelo, que
        avisa y la pila se recoloca)."""
        if self._drag_id is None:
            return
        QApplication.restoreOverrideCursor()
        self._drop_indicator.hide()
        valid, before = self.drop_target(self.mapFromGlobal(global_position))
        index = self.drop_index(before) if valid else None
        section_id, self._drag_id = self._drag_id, None
        if index is not None and self._model is not None:
            self._model.move(self._mode, section_id, index)

    def _place_indicator(self, before: str | None) -> None:
        """Pone la raya en el hueco de encima de 'before' (None = debajo de la última)."""
        candidates = self._drop_candidates()
        if before is not None:
            # El hueco entre secciones mide lo que la raya: lo llena
            y = self._sections[before].y() - SECTION_SPACING
        elif candidates:
            y = self._sections[candidates[-1]].geometry().bottom() + 1
        else:
            y = 0
        # Dentro de la pila (encima de la primera y debajo de la última no hay hueco)
        y = max(0, min(y, self.height() - DROP_INDICATOR_HEIGHT))
        self._drop_indicator.setGeometry(0, y, self.width(), DROP_INDICATOR_HEIGHT)
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _entry(self, section_id: str) -> SectionEntry | None:
        """La sección en el modelo, para el modo actual (None sin modelo o si no está)."""
        if self._model is None or self._sidebar is None:
            return None
        for entry in self._model.entries(self._mode, self._sidebar):
            if entry.id == section_id:
                return entry
        return None

    def _is_wanted(self, section_id: str) -> bool:
        """Visible para el usuario Y disponible según la barra."""
        return self.is_user_visible(section_id) and self._available.get(section_id, True)

    def _on_layout_changed(self, mode: str, sidebar: str) -> None:
        """El modelo ha cambiado: si es lo de esta pila, se recoloca."""
        if mode == self._mode and sidebar == self._sidebar:
            self._apply()

    def _on_section_toggled(self, section_id: str, expanded: bool) -> None:
        """Una sección se ha plegado o desplegado: se apunta en el modelo. (Si el cambio
        viene del propio modelo, ya tiene ese valor y no pasa nada.)"""
        if self._model is not None:
            self._model.set_expanded(self._mode, section_id, expanded)

    def _apply(self) -> None:
        """Coloca las secciones como dice el modelo: orden, visibles y desplegadas."""
        entries = (
            self._model.entries(self._mode, self._sidebar)
            if self._model is not None and self._sidebar is not None
            else ()
        )
        known = {entry.id: entry for entry in entries if entry.id in self._sections}
        # Primero las del modelo, en su orden; detrás, las que no conoce, como se dieron de alta
        order = list(known) + [sid for sid in self._sections if sid not in known]

        # Sin repintar a medias (se quitan y se vuelven a poner)
        self.setUpdatesEnabled(False)
        try:
            if order != self._order:
                for section in self._sections.values():
                    self._layout.removeWidget(section)
                for section_id in order:
                    self._layout.addWidget(self._sections[section_id])
                self._order = order
            for section_id in order:
                section = self._sections[section_id]
                entry = known.get(section_id)
                if entry is not None:
                    section.set_expanded(entry.expanded)
                section.setVisible(self._is_wanted(section_id))
        finally:
            self.setUpdatesEnabled(True)

        shown = frozenset(sid for sid in order if sid not in known or known[sid].visible)
        previous, self._shown = self._shown, shown
        if previous is not None and previous != shown:
            self.shown_sections_changed.emit()


if __name__ == "__main__":
    # Autoprueba SIN ventana (nada se muestra: se comprueba el orden en el layout y lo que
    # cada sección tiene oculto). Desde la raíz del proyecto:
    #     python -m ui_helpers.widgets.section_stack
    import copy
    import os
    from typing import Any

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qtpy.QtWidgets import QApplication, QLabel

    from ui_helpers.layout.section_registry import LEFT, RIGHT, SectionRegistry, SectionSpec

    app = QApplication.instance() or QApplication([])

    class _FakeConfig:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

        def get(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self.data[key] = copy.deepcopy(value)

    registry = SectionRegistry()
    registry.register_mode("a", "A")
    registry.register_mode("b", "B")
    for number, name in enumerate(("one", "two", "three"), start=1):
        registry.register(SectionSpec(name, name.title(), LEFT, number * 100))
    registry.register(SectionSpec("info", "Info", RIGHT, 100))
    model = SectionLayoutModel(registry, _FakeConfig())

    def _build(*ids: str) -> SectionStack:
        new_stack = SectionStack()
        for sid in ids:
            section = CollapsibleSection(sid.title(), new_stack)
            section.set_content(QLabel(sid))
            new_stack.add_section(sid, section)
        return new_stack

    def _on_screen(a_stack: SectionStack) -> list[str]:
        """Los 'id' en el orden real del layout (no el que la pila cree tener)."""
        by_widget = {a_stack.section(sid): sid for sid in a_stack.section_ids()}
        layout = a_stack.layout()
        return [by_widget[layout.itemAt(i).widget()] for i in range(layout.count())]

    def _hidden(a_stack: SectionStack) -> set[str]:
        return {sid for sid in a_stack.section_ids() if a_stack.section(sid).isHidden()}

    # --- Sin modelo: en el orden de alta, todas a la vista. 'extra' no está en el registro
    stack = _build("two", "extra", "one", "three")
    assert _on_screen(stack) == ["two", "extra", "one", "three"] and not _hidden(stack)
    try:
        stack.add_section("one", CollapsibleSection("Repetida"))
        raise AssertionError("debía rechazar un id repetido")
    except ValueError:
        pass

    # --- Con modelo: el orden del modelo; la que no conoce, al final y visible
    changes: list[int] = []
    stack.shown_sections_changed.connect(lambda: changes.append(1))
    stack.bind(model, "a", Sidebar.LEFT)
    assert _on_screen(stack) == ["one", "two", "three", "extra"] and not changes

    # --- El modelo cambia (desde cualquier sitio) y la pila se recoloca
    model.move("a", "three", 0)
    assert _on_screen(stack) == ["three", "one", "two", "extra"] and not changes
    model.set_visible("a", "one", False)
    assert _hidden(stack) == {"one"} and len(changes) == 1
    assert stack.is_user_visible("one") is False and stack.is_user_visible("extra") is True
    model.set_expanded("a", "two", False)
    assert stack.section("two").is_expanded() is False and len(changes) == 1
    # Los cambios de otro modo o de la otra barra no la tocan
    model.move("b", "three", 0)
    model.set_visible("a", "info", False)
    assert _on_screen(stack) == ["three", "one", "two", "extra"] and len(changes) == 1

    # --- Plegar con la cabecera se apunta en el modelo (solo en ese modo)
    stack.section("three").set_expanded(False)
    assert model.entry("a", "three").expanded is False and model.entry("b", "three").expanded is True
    stack.section("three").set_expanded(True)
    assert model.entry("a", "three").expanded is True

    # --- Disponible (lo decide la barra) y visible (el usuario): hacen falta las dos
    stack.set_available("two", False)
    assert _hidden(stack) == {"one", "two"}
    model.set_visible("a", "one", True)
    assert _hidden(stack) == {"two"} and len(changes) == 2
    model.set_visible("a", "two", False)
    stack.set_available("two", True)
    assert _hidden(stack) == {"two"}  # disponible, pero el usuario la tiene oculta
    model.set_visible("a", "two", True)
    assert not _hidden(stack)

    # --- Cambiar de modo: la colocación del otro (lo no disponible sigue sin verse)
    changes.clear()
    stack.set_available("one", False)
    stack.set_mode("b")
    assert stack.mode() == "b" and _on_screen(stack) == ["three", "one", "two", "extra"]
    assert stack.section("two").is_expanded() is True and _hidden(stack) == {"one"}
    assert not changes  # en los dos modos el usuario ve las mismas
    assert model.entry("a", "two").expanded is False  # cambiar de modo no escribe en el otro
    model.set_visible("b", "three", False)
    stack.set_mode("a")
    assert _hidden(stack) == {"one"} and len(changes) == 2  # al ocultarla y al volver
    assert stack.section("two").is_expanded() is False

    # --- Restaurar: todo como al principio
    stack.set_available("one", True)
    model.reset()
    assert _on_screen(stack) == ["one", "two", "three", "extra"] and not _hidden(stack)
    assert stack.section("two").is_expanded() is True

    # --- Menú: una casilla por sección del modelo, en su orden, y «Restaurar por defecto»
    def _menu_items(a_menu) -> list[tuple[str, bool]]:
        return [(a.text(), a.isChecked()) for a in a_menu.actions() if a.isCheckable()]

    assert _build("one").build_menu() is None  # sin modelo no hay menú
    menu = stack.build_menu()
    # 'extra' no está en el registro: no se ofrece
    assert _menu_items(menu) == [("One", True), ("Two", True), ("Three", True)]
    restore = menu.actions()[-1]
    assert restore.text() == RESTORE_TEXT and not restore.isEnabled()  # nada que restaurar
    assert menu.actions()[-2].isSeparator()
    menu.actions()[1].trigger()  # desmarcar «Two»: se oculta, en el modelo y en pantalla
    assert model.entry("a", "two").visible is False and _hidden(stack) == {"two"}
    menu.deleteLater()
    model.move("a", "three", 0)
    menu = stack.build_menu()
    assert _menu_items(menu) == [("Three", True), ("One", True), ("Two", False)]
    assert menu.actions()[-1].isEnabled()
    menu.actions()[2].trigger()  # marcar «Two»: vuelve
    assert model.entry("a", "two").visible is True and not _hidden(stack)
    model.set_expanded("a", "info", False)  # la otra barra, cambiada
    menu.actions()[-1].trigger()  # «Restaurar por defecto»: solo esta barra de este modo
    assert _on_screen(stack) == ["one", "two", "three", "extra"]
    assert model.is_default("a", Sidebar.LEFT) and model.entry("a", "info").expanded is False
    menu.deleteLater()
    model.reset()
    # Con todas ocultas, el menú sigue ofreciéndolas
    for sid in ("one", "two", "three"):
        model.set_visible("a", sid, False)
    menu = stack.build_menu()
    assert _menu_items(menu) == [("One", False), ("Two", False), ("Three", False)]
    menu.deleteLater()
    model.reset()

    # --- Clic derecho en la cabecera (también sobre el botón del título): avisa con el
    # punto de la pantalla; en el contenido, no. (Con una sección suelta: en la pila
    # abriría el menú de verdad y se quedaría esperando.)
    from qtpy.QtCore import QPoint
    from qtpy.QtGui import QContextMenuEvent

    loose = CollapsibleSection("Suelta")
    loose_label = QLabel("contenido")
    loose.set_content(loose_label)
    loose.resize(200, 80)
    asked: list[QPoint] = []
    loose.header_menu_requested.connect(asked.append)
    reached: list[int] = []  # lo que llega al padre de la sección (la barra)
    holder = QWidget()
    holder.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    holder.customContextMenuRequested.connect(lambda _position: reached.append(1))
    loose.setParent(holder)

    def _right_click(widget: QWidget) -> None:
        point = QPoint(3, 3)
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, widget.mapToGlobal(point))
        QApplication.sendEvent(widget, event)

    _right_click(loose._toggle_button)
    assert len(asked) == 1 and not reached
    _right_click(loose._header)
    assert len(asked) == 2 and not reached
    _right_click(loose_label)  # en el contenido: ni avisa ni sube a la barra
    assert len(asked) == 2 and not reached
    _right_click(holder)  # el fondo de la barra sí tiene su menú
    assert len(reached) == 1

    # --- Arrastrar las cabeceras: con el ratón de verdad (eventos), sin ventana
    from qtpy.QtCore import QEvent, QPointF
    from qtpy.QtGui import QMouseEvent

    left, no_button = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    def _mouse(widget: QWidget, kind: QEvent.Type, point: QPoint, pressed: bool) -> None:
        """Manda al widget un evento de ratón en ese punto de la pantalla."""
        button = no_button if kind == QEvent.Type.MouseMove else left
        event = QMouseEvent(
            kind, QPointF(widget.mapFromGlobal(point)), QPointF(point), button,
            left if pressed else no_button, Qt.KeyboardModifier.NoModifier,
        )  # fmt: skip
        QApplication.sendEvent(widget, event)

    def _point(sid: str, where: float, x: int = 20) -> QPoint:
        """Un punto de la pantalla sobre la sección 'sid', a esa fracción de su alto."""
        section = stack.section(sid)
        return section.mapToGlobal(QPoint(x, int(section.height() * where)))

    def _drag(sid: str, target: QPoint, *, check=None) -> None:
        """Coge la cabecera de 'sid' por el título, la lleva a 'target' y la suelta."""
        title = stack.section(sid)._toggle_button
        start = title.mapToGlobal(QPoint(10, 5))
        _mouse(title, QEvent.Type.MouseButtonPress, start, True)
        _mouse(title, QEvent.Type.MouseMove, target, True)
        if check is not None:
            check()
        _mouse(title, QEvent.Type.MouseButtonRelease, target, False)

    # Del alto justo de sus secciones, como en una barra (con más alto, el layout las separaría)
    stack.resize(200, stack.sizeHint().height())
    stack.show()
    app.processEvents()
    assert _on_screen(stack) == ["one", "two", "three", "extra"] and model.is_default("a", Sidebar.LEFT)
    indicator = stack._drop_indicator
    assert indicator.isHidden()

    # Dónde caería: delante de la primera cuya mitad queda por debajo; abajo del todo, la última
    def _target(sid: str, where: float, x: int = 20) -> tuple[bool, str | None]:
        return stack.drop_target(stack.mapFromGlobal(_point(sid, where, x)))

    assert _target("one", 0.2) == (True, "one") and _target("one", 0.8) == (True, "two")
    assert _target("three", 0.8) == (True, None)  # 'extra' no es del modelo: no cuenta
    assert _target("two", 0.2, x=-30) == (False, None) and _target("two", 0.2, x=260) == (False, None)

    # Un clic sin mover (o moviendo muy poco) sigue plegando
    title_two = stack.section("two")._toggle_button
    start_two = title_two.mapToGlobal(QPoint(10, 5))
    _mouse(title_two, QEvent.Type.MouseButtonPress, start_two, True)
    _mouse(title_two, QEvent.Type.MouseMove, start_two + QPoint(1, 1), True)
    _mouse(title_two, QEvent.Type.MouseButtonRelease, start_two + QPoint(1, 1), False)
    assert model.entry("a", "two").expanded is False and _on_screen(stack)[:3] == ["one", "two", "three"]
    model.set_expanded("a", "two", True)
    app.processEvents()

    # Arrastrar «three» encima de «one»: pasa a ser la primera; no se pliega; la raya, solo
    # mientras se arrastra, en el hueco de encima de donde caerá
    def _while_dragging() -> None:
        assert not indicator.isHidden() and indicator.y() == 0 and indicator.width() == stack.width()
        assert QApplication.overrideCursor() is not None

    _drag("three", _point("one", 0.2), check=_while_dragging)
    assert _on_screen(stack) == ["three", "one", "two", "extra"]
    assert [e.id for e in model.entries("a", Sidebar.LEFT)] == ["three", "one", "two"]
    assert model.entry("a", "three").expanded is True and stack.section("three").is_expanded()
    assert indicator.isHidden() and QApplication.overrideCursor() is None
    app.processEvents()

    # Hacia abajo: «three» pasada la mitad de «one» queda entre «one» y «two» (la raya, en
    # el hueco de encima de «two»)
    def _between() -> None:
        assert indicator.y() == stack.section("two").y() - SECTION_SPACING

    _drag("three", _point("one", 0.8), check=_between)
    assert _on_screen(stack) == ["one", "three", "two", "extra"]
    app.processEvents()
    # Al final (por debajo de todas): la última de las del modelo
    _drag("one", _point("extra", 0.9))
    assert _on_screen(stack) == ["three", "two", "one", "extra"]
    app.processEvents()
    # Soltarla donde está (encima de sí misma o de la siguiente): nada cambia
    _drag("two", _point("two", 0.2))
    _drag("two", _point("one", 0.2))
    assert _on_screen(stack) == ["three", "two", "one", "extra"]
    # Soltar a un lado de la barra cancela (la raya desaparece para avisar)
    _drag("one", _point("three", 0.2, x=300), check=lambda: indicator.isHidden() or 1 / 0)
    assert _on_screen(stack) == ["three", "two", "one", "extra"]
    assert QApplication.overrideCursor() is None
    # Una sección que el modelo no conoce no se arrastra
    _drag("extra", _point("three", 0.2), check=lambda: indicator.isHidden() or 1 / 0)
    assert _on_screen(stack) == ["three", "two", "one", "extra"]
    assert QApplication.overrideCursor() is None

    # Con una oculta en medio se cuenta por 'id': «one» delante de «three» salta también
    # a la oculta, y la oculta conserva su sitio respecto a las demás
    model.set_visible("a", "two", False)
    app.processEvents()
    _drag("one", _point("three", 0.2))
    assert [e.id for e in model.entries("a", Sidebar.LEFT)] == ["one", "three", "two"]
    # La única a la vista no tiene adónde ir
    model.set_visible("a", "three", False)
    app.processEvents()
    _drag("one", _point("extra", 0.9))
    assert [e.id for e in model.entries("a", Sidebar.LEFT)] == ["one", "three", "two"]
    model.reset()
    stack.hide()

    # --- Dar de alta una sección con la pila ya unida: va a su sitio
    late = _build("three")
    late.bind(model, "a", Sidebar.LEFT)
    late.add_section("one", CollapsibleSection("One", late))
    assert _on_screen(late) == ["one", "three"]

    # --- Volver a unir a otro modelo deja de escuchar al anterior
    other = SectionLayoutModel(registry, _FakeConfig())
    late.bind(other, "a", Sidebar.LEFT)
    model.move("a", "three", 0)
    assert _on_screen(late) == ["one", "three"]
    other.move("a", "three", 0)
    assert _on_screen(late) == ["three", "one"]

    print("Autoprueba finalizada correctamente.")
