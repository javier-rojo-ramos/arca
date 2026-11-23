"""Caja de búsqueda del mapa: escribir un lugar o una dirección y pulsar Intro (GEN 8.4).

    [🔍 Buscar un lugar o una dirección     × ▾]
                                           ├ Torla
                                           ├ Museo del Prado
                                           ├ ───────────────
                                           └ Borrar las búsquedas recientes

Va en la barra de filtros, a la derecha ('FilterBar.add_right_widget'), y solo se ve con el
mapa (lo decide 'controllers/map_search_controller.py'). Solo muestra y avisa:
    - Intro o la lupa: 'search_requested(texto)'. Nunca mientras se escribe: las
      condiciones de Nominatim prohíben autocompletar con su servicio.
    - Elegir una búsqueda reciente en la lista: también 'search_requested', con su texto
      (el controlador ya tiene su lugar: no se vuelve a pedir).
    - «Borrar las búsquedas recientes»: 'clear_history_requested()' (lo escrito se queda).
    - Esc con la lista cerrada: 'escape_pressed()' (el controlador devuelve el teclado al
      mapa).
    - La caja se queda vacía (con la «×» o borrando lo escrito): 'text_cleared()' (el
      controlador quita la chincheta del lugar encontrado).
Las búsquedas recientes las pone el controlador ('set_history'), cada una con el nombre
completo de su lugar en el texto emergente.

Es un QComboBox editable, con tres cosas cambiadas:
    - Lo escrito no se añade a la lista al pulsar Intro: lo añade el controlador, y solo si
      se encuentra.
    - No completa con la lista mientras se escribe: escribir «Madrid» y pulsar Intro tiene
      que buscar «Madrid», no «Madrid Río» porque esté en la lista.
    - Las flechas y la rueda no van pasando por la lista (dejarían en la caja «Borrar las
      búsquedas recientes»): las flechas abren la lista; la rueda no hace nada.

Teclado: coge el foco solo al hacer clic, no con Tab. Los atajos de las fotos («3», «P»,
«G»...) no le llegan: están en la cuadrícula, la vista individual y el mapa. El teclado lo
tiene el propio QComboBox, no su caja: Intro, Esc y las flechas se atienden en su
'keyPressEvent' (ver allí; docs/TRAMPAS.md).

1.1.0 'text_cleared': la caja se ha quedado vacía (para quitar la chincheta, GEN 8.4c).
1.0.1 Intro, Esc y las flechas, en 'keyPressEvent' del QComboBox: con un filtro de eventos
      en la caja no llegaban (Intro no buscaba, Esc no devolvía el teclado al mapa y las
      flechas iban eligiendo búsquedas recientes, hasta «Borrar...»). Lo vio el autor.
1.0.0 Primera versión (GEN 8.4b).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.widgets.map_search_box
"""

__version__ = "1.1.0"
__all__ = ["CLEAR_HISTORY_TEXT", "PLACEHOLDER_TEXT", "TOOLTIP_TEXT", "MapSearchBox"]

# Librerías estándar
from collections.abc import Sequence

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile, QSize, Qt, Signal
from qtpy.QtGui import QKeyEvent, QWheelEvent
from qtpy.QtWidgets import QComboBox, QLineEdit, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.maps.geocoding import MAX_QUERY_LENGTH
from ui_helpers.helpers.ui_icons import tinted_icon

# Textos de la interfaz (los acordados con el autor el 23/11/2026; el texto emergente cita
# a OpenStreetMap, como piden sus condiciones)
PLACEHOLDER_TEXT = "Buscar un lugar o una dirección"
TOOLTIP_TEXT = (
    "Escribe un lugar o una dirección y pulsa Intro.\n"
    "Búsqueda: © colaboradores de OpenStreetMap (Nominatim)"
)
CLEAR_HISTORY_TEXT = "Borrar las búsquedas recientes"

# Ancho: el que pide (cabe entero el texto de ayuda) y, si la barra no tiene sitio, lo
# menos a lo que se encoge (unas 12 letras) antes de apartar las pestañas del centro
PREFERRED_WIDTH = 250
MIN_CHARACTERS = 12
# Nombre de objeto (por si el QSS lo necesita)
OBJECT_NAME = "combo_map_search"

# Marca de la opción «Borrar las búsquedas recientes» en la lista (sus datos)
_CLEAR_KEY = "__clear_history__"


class MapSearchBox(QComboBox):
    """La caja de búsqueda del mapa (ver el docstring del archivo).

    Signals:
        search_requested(str): Intro, la lupa o una búsqueda reciente elegida (el texto).
        clear_history_requested(): se ha elegido «Borrar las búsquedas recientes».
        escape_pressed(): Esc en la caja, con la lista cerrada.
        text_cleared(): la caja se ha quedado vacía (no al rehacer la lista: 'set_history').
    """

    search_requested = Signal(str)
    clear_history_requested = Signal()
    escape_pressed = Signal()
    text_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(OBJECT_NAME)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setCompleter(None)  # sin completar con la lista (ver el docstring del archivo)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(MIN_CHARACTERS)  # lo menos; lo que pide, 'sizeHint'
        self.setToolTip(TOOLTIP_TEXT)
        # Lo escrito al abrir la lista: vuelve a la caja si se elige «Borrar...»
        self._text_before_popup = ""
        # True mientras 'set_history' rehace la lista (vacía la caja y la repone: no avisa)
        self._updating = False

        edit = self.lineEdit()
        edit.setPlaceholderText(PLACEHOLDER_TEXT)
        edit.setMaxLength(MAX_QUERY_LENGTH)
        edit.setClearButtonEnabled(True)
        if QFile.exists(AppIcons.SEARCH):
            # La lupa, a la izquierda: pulsarla es como pulsar Intro. Sin color fijo: sigue
            # la paleta, como el candado de la barra
            search = edit.addAction(tinted_icon(AppIcons.SEARCH),
                                    QLineEdit.ActionPosition.LeadingPosition)
            search.setToolTip(TOOLTIP_TEXT)
            search.triggered.connect(self._request_search)
        # Intro, Esc y las flechas, en 'keyPressEvent' (ver allí por qué no con
        # 'returnPressed' ni con un filtro de eventos en la caja)
        self.activated.connect(self._on_activated)
        edit.textChanged.connect(self._on_text_changed)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def text(self) -> str:
        """Lo escrito en la caja."""
        return self.lineEdit().text()

    def set_history(self, entries: Sequence[tuple[str, str]]) -> None:
        """Pone las búsquedas recientes en la lista, en su orden (la primera, la más
        reciente), y detrás, si hay alguna, «Borrar las búsquedas recientes». No emite
        nada y lo escrito en la caja se queda como estaba.

        Args:
            entries: (lo que se escribió, el nombre completo de su lugar) de cada una.
        """
        text = self.text()
        self.blockSignals(True)
        self._updating = True  # la caja se vacía un momento: no es el usuario
        try:
            self.clear()
            for query, label in entries:
                self.addItem(query)
                self.setItemData(self.count() - 1, label, Qt.ItemDataRole.ToolTipRole)
            if entries:
                self.insertSeparator(self.count())
                self.addItem(CLEAR_HISTORY_TEXT, _CLEAR_KEY)
            # Sin ninguna elegida: si no, la caja mostraría la primera
            self.setCurrentIndex(-1)
            self.setEditText(text)
        finally:
            self._updating = False
            self.blockSignals(False)

    def history(self) -> list[str]:
        """Las búsquedas recientes que hay en la lista (sin «Borrar...»)."""
        return [
            self.itemText(row) for row in range(self.count())
            if self.itemText(row) and self.itemData(row) != _CLEAR_KEY
        ]

    def showPopup(self) -> None:  # nombre de Qt
        self._remember_text()
        super().showPopup()

    def sizeHint(self) -> QSize:  # nombre de Qt
        """Pide 'PREFERRED_WIDTH'; si no hay sitio, la barra la encoge hasta su mínimo."""
        hint = super().sizeHint()
        return QSize(max(hint.width(), PREFERRED_WIDTH), hint.height())

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _remember_text(self) -> None:
        self._text_before_popup = self.text()

    def _request_search(self) -> None:
        self.search_requested.emit(self.text())

    def _on_text_changed(self, text: str) -> None:
        if not text and not self._updating:
            self.text_cleared.emit()

    def _on_activated(self, row: int) -> None:
        """Una opción de la lista: una búsqueda reciente o «Borrar...»."""
        if self.itemData(row) == _CLEAR_KEY:
            # Al elegirla, Qt ha puesto su texto en la caja: vuelve lo que había
            self.setCurrentIndex(-1)
            self.setEditText(self._text_before_popup)
            self.clear_history_requested.emit()
            return
        self.search_requested.emit(self.itemText(row))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # nombre de Qt
        """Intro busca; Esc avisa; las flechas (y Re Pág / Av Pág) abren la lista. Lo demás,
        como siempre (a la caja, para escribir).

        Va aquí y no en la caja porque el teclado lo tiene el QComboBox (es el 'focusProxy'
        de su caja), que le pasa las teclas llamando a su 'event()': un filtro de eventos en
        la caja no las ve (así se rompió Intro el 23/11/2026). Sin esto, las flechas irían
        eligiendo opciones de la lista, y cada una emite 'activated': buscaría cada búsqueda
        reciente y, al llegar a «Borrar...», las borraría todas. Si una tecla llega a la caja
        por otro camino (p. ej. una prueba que se la manda a ella), la caja no la usa y sube
        hasta aquí: también una sola vez.
        """
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._request_search()
        elif key == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            if self.count():
                self.showPopup()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:  # nombre de Qt
        """La rueda no cambia lo escrito (pasaría por las búsquedas y por «Borrar...»)."""
        event.ignore()


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'): la lógica de la caja.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.widgets.map_search_box
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtTest import QTest
    from qtpy.QtWidgets import QApplication

    try:
        import resources.recursos_rc  # noqa: F401  (los iconos del .qrc, como en main.py)
    except ImportError:
        pass

    app = QApplication([])
    holder = QWidget()  # padre que nunca se muestra: no se crea ninguna ventana
    box = MapSearchBox(holder)
    searches: list[str] = []
    clears: list[bool] = []
    escapes: list[bool] = []
    popups: list[bool] = []
    box.search_requested.connect(searches.append)
    box.clear_history_requested.connect(lambda: clears.append(True))
    box.escape_pressed.connect(lambda: escapes.append(True))
    # La lista de verdad abriría una ventana emergente: se apunta sin abrirla
    def fake_popup() -> None:
        box._remember_text()
        popups.append(True)

    box.showPopup = fake_popup  # type: ignore[method-assign]
    edit = box.lineEdit()

    # 1. Cómo está hecha: editable, sin añadir ni completar, textos, sin Tab
    assert box.isEditable() and box.insertPolicy() == QComboBox.InsertPolicy.NoInsert
    assert box.completer() is None and box.count() == 0
    assert edit.placeholderText() == PLACEHOLDER_TEXT and box.toolTip() == TOOLTIP_TEXT
    assert edit.isClearButtonEnabled() and edit.maxLength() == MAX_QUERY_LENGTH
    assert box.focusPolicy() == Qt.FocusPolicy.ClickFocus
    # Pide su ancho, pero se puede encoger
    assert box.sizeHint().width() >= PREFERRED_WIDTH > box.minimumSizeHint().width()

    # Las teclas, al QComboBox, como en la aplicación: es el 'focusProxy' de su caja (una
    # prueba que se las manda a la caja no recorre el mismo camino: ver 'keyPressEvent')
    assert edit.focusProxy() is box

    # 2. Intro busca lo escrito UNA vez, y no lo añade a la lista; Intro del teclado
    # numérico, igual; mandado a la caja (por otro camino), también una sola vez
    QTest.keyClicks(box, "Torla")
    assert box.text() == "Torla"
    QTest.keyClick(box, Qt.Key.Key_Return)
    assert searches == ["Torla"] and box.count() == 0, searches
    QTest.keyClick(box, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
    assert searches == ["Torla", "Torla"], searches
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert searches == ["Torla"] * 3, searches
    searches.clear()
    searches.append("Torla")

    # 3. Las búsquedas recientes, con su nombre completo en el texto emergente; lo escrito
    # se queda; detrás, el separador y «Borrar...»
    box.set_history([("Torla", "Torla-Ordesa, Sobrarbe, Huesca, Aragón, España"),
                     ("Museo del Prado", "Museo del Prado, Paseo del Prado, Madrid")])
    assert box.history() == ["Torla", "Museo del Prado"]
    assert box.count() == 4 and box.itemText(3) == CLEAR_HISTORY_TEXT
    assert box.itemData(0, Qt.ItemDataRole.ToolTipRole).startswith("Torla-Ordesa")
    assert box.currentIndex() == -1 and box.text() == "Torla"
    # Sin ninguna, ni separador ni «Borrar...»; lo escrito, igual
    box.set_history([])
    assert box.count() == 0 and box.text() == "Torla"
    box.set_history([("Torla", "Torla-Ordesa"), ("Museo del Prado", "Museo del Prado")])

    # 4. Elegir una reciente: busca con su texto
    box.showPopup()
    box.setCurrentIndex(1)  # como hace Qt al elegirla: su texto, en la caja
    box.activated.emit(1)
    assert searches[-1] == "Museo del Prado" and box.text() == "Museo del Prado"

    # 5. «Borrar...»: avisa y deja en la caja lo que había (no su propio texto); no busca
    edit.setText("Rascafría")
    box.showPopup()
    box.setCurrentIndex(3)
    assert box.text() == CLEAR_HISTORY_TEXT  # lo que hace Qt al elegirla
    box.activated.emit(3)
    assert clears == [True] and box.text() == "Rascafría" and box.currentIndex() == -1
    assert searches[-1] == "Museo del Prado"

    # 6. Esc avisa (también mandado a la caja); las flechas abren la lista sin elegir nada:
    # ni buscan ni, al pasar por «Borrar...», borran
    QTest.keyClick(box, Qt.Key.Key_Escape)
    QTest.keyClick(edit, Qt.Key.Key_Escape)
    assert escapes == [True, True]
    popups.clear()
    searches_before = list(searches)
    for key in (Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Down,
                Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
        QTest.keyClick(box, key)
    QTest.keyClick(edit, Qt.Key.Key_Down)
    assert len(popups) == 8 and box.text() == "Rascafría" and box.currentIndex() == -1
    assert searches == searches_before and clears == [True]
    # Sin búsquedas recientes, las flechas no hacen nada
    box.set_history([])
    popups.clear()
    QTest.keyClick(box, Qt.Key.Key_Down)
    assert popups == [] and box.text() == "Rascafría"
    # Las demás teclas siguen escribiendo y moviendo el cursor en la caja
    QTest.keyClick(box, Qt.Key.Key_End)
    QTest.keyClick(box, Qt.Key.Key_Backspace)
    QTest.keyClicks(box, "a")
    assert box.text() == "Rascafría"

    # 7. La caja vacía avisa: con la «×» o borrando; rehacer la lista (que la vacía un
    # momento) no avisa, ni escribir
    cleared: list[bool] = []
    box.text_cleared.connect(lambda: cleared.append(True))
    box.set_history([("Torla", "Torla-Ordesa")])
    box.set_history([])
    assert cleared == [] and box.text() == "Rascafría"
    edit.clear()  # lo que hace la «×»
    assert cleared == [True]
    QTest.keyClicks(box, "Ab")
    assert cleared == [True]
    QTest.keyClick(box, Qt.Key.Key_Backspace)
    QTest.keyClick(box, Qt.Key.Key_Backspace)
    assert cleared == [True, True] and box.text() == ""
    edit.setText("Rascafría")

    # 8. La lupa, a la izquierda de la caja, busca como Intro (si el icono está en el .qrc)
    actions = edit.actions()
    if QFile.exists(AppIcons.SEARCH):
        lupa = [a for a in actions if a.toolTip() == TOOLTIP_TEXT]
        assert len(lupa) == 1
        lupa[0].trigger()
        assert searches[-1] == "Rascafría"
    else:
        print("Aviso: falta el icono de la lupa en el .qrc (scripts/build_ui.py)")

    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
